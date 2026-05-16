from __future__ import annotations

import json
from pathlib import Path
from typing import Any


QUESTION_OPCODES = {"OneOf", "CheckBox", "Numeric", "String", "OrderedList", "Date", "Time"}
CONDITION_OPCODES = {"SuppressIf", "GrayOutIf", "DisableIf", "NoSubmitIf", "InconsistentIf", "WarningIf"}


def parse_ifr_dir(ifr_dir: Path) -> dict[str, Any]:
    settings = []
    seen_settings: set[tuple[Any, ...]] = set()

    for path in sorted(ifr_dir.rglob("*.ifr.json")):
        try:
            module = parse_ifr_file(path)
        except json.JSONDecodeError:
            continue
        if not module["settings"]:
            continue

        unique_settings = []
        for setting in module["settings"]:
            key = _setting_dedupe_key(setting)
            if key in seen_settings:
                continue
            seen_settings.add(key)
            unique_settings.append(setting)

        settings.extend(unique_settings)

    return {
        "setting_count": len(settings),
        "settings": settings,
    }


def parse_ifr_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(errors="replace"))
    varstores: dict[int, dict[str, Any]] = {}
    settings: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []

    for op in data.get("operations") or []:
        opcode = op.get("opcode")
        depth = int(op.get("depth") or 0)

        while stack and stack[-1]["depth"] >= depth:
            stack.pop()

        if opcode == "End":
            continue

        fields = op.get("fields") or {}
        if opcode == "FormSet":
            entry = {"depth": depth, "opcode": opcode, "formset": _formset(fields)}
            if op.get("scope_start"):
                stack.append(entry)
            continue

        if opcode == "Form":
            entry = {"depth": depth, "opcode": opcode, "form": _form(fields)}
            if op.get("scope_start"):
                stack.append(entry)
            continue

        if opcode in ("VarStore", "VarStoreEfi", "VarStoreNameValue"):
            varstore = _varstore(fields)
            if varstore.get("id") is not None:
                varstores[varstore["id"]] = varstore
            continue

        if opcode in CONDITION_OPCODES:
            if op.get("scope_start"):
                stack.append({
                    "depth": depth,
                    "opcode": opcode,
                    "condition": {"opcode": opcode, "fields": fields},
                })
            continue

        if opcode in QUESTION_OPCODES:
            formset, form = _context(stack)
            setting = _question(opcode, fields)
            setting["source"] = {"ifr_file": str(path), "offset": op.get("offset")}
            setting["formset"] = formset
            setting["form"] = form
            setting["path"] = _setting_path(formset, form)
            setting["visibility"] = _visibility(stack)
            setting["options"] = []
            setting["defaults"] = []
            settings.append(setting)
            if op.get("scope_start"):
                stack.append({"depth": depth, "opcode": opcode, "setting": setting})
            continue

        if opcode == "OneOfOption":
            setting = _nearest_setting(stack)
            if setting is not None:
                setting["options"].append(_oneof_option(fields))
            continue

        if opcode == "Default":
            setting = _nearest_setting(stack)
            if setting is not None:
                setting["defaults"].append(_default(fields))
            continue

    for setting in settings:
        setting["varstore"] = varstores.get(setting.get("varstore_id"))

    return {
        "ifr_file": str(path),
        "formset": _first_formset(settings),
        "varstores": varstores,
        "settings": settings,
    }


def _setting_dedupe_key(setting: dict[str, Any]) -> tuple[Any, ...]:
    varstore = setting.get("varstore") or {}
    options = tuple((opt.get("value"), opt.get("label")) for opt in setting.get("options", []))
    return (
        tuple(setting.get("path") or []),
        setting.get("prompt"),
        setting.get("type"),
        varstore.get("name"),
        varstore.get("guid"),
        setting.get("offset"),
        setting.get("size_bits"),
        options,
    )


def _formset(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "guid": _lower(fields.get("guid")),
        "title": _text(fields.get("title")),
        "help": _text(fields.get("help")),
        "flags": fields.get("flags"),
        "class_guids": [_lower(g) for g in fields.get("class_guids") or []],
    }


def _form(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": fields.get("form_id"),
        "title": _text(fields.get("title")),
    }


def _varstore(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": fields.get("kind"),
        "guid": _lower(fields.get("guid")),
        "id": fields.get("varstore_id"),
        "size": fields.get("size"),
        "name": fields.get("name"),
        "attributes": fields.get("attributes"),
    }


def _question(opcode: str, fields: dict[str, Any]) -> dict[str, Any]:
    minmax = fields.get("min_max_step") or {}
    out = {
        "type": fields.get("kind") or _question_type(opcode),
        "prompt": _text(fields.get("prompt")),
        "help": _text(fields.get("help")),
        "question_id": fields.get("question_id"),
        "question_flags": fields.get("question_flags"),
        "varstore_id": fields.get("varstore_id"),
        "offset": fields.get("var_offset"),
        "size_bits": minmax.get("size_bits"),
        "min": minmax.get("min"),
        "max": minmax.get("max"),
        "step": minmax.get("step"),
        "flags": fields.get("flags"),
    }
    if opcode == "String":
        out["min_size"] = fields.get("min_size")
        out["max_size"] = fields.get("max_size")
    if opcode == "OrderedList":
        out["max_containers"] = fields.get("max_containers")
    if opcode == "CheckBox":
        out["default"] = fields.get("default")
        out["mfg_default"] = fields.get("mfg_default")
        out["size_bits"] = out["size_bits"] or 8
    return out


def _oneof_option(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": _text(fields.get("option")),
        "value": _typed_value(fields.get("value")),
        "default": bool(fields.get("default")),
        "mfg_default": bool(fields.get("mfg_default")),
        "flags": fields.get("flags"),
    }


def _default(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "default_id": fields.get("default_id"),
        "value": _typed_value(fields.get("value")),
    }


def _typed_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        raw = value["value"]
        if isinstance(raw, bool):
            return int(raw)
        return raw
    return None


def _nearest_setting(stack: list[dict[str, Any]]) -> dict[str, Any] | None:
    for entry in reversed(stack):
        setting = entry.get("setting")
        if setting is not None:
            return setting
    return None


def _context(stack: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    formset = None
    form = None
    for entry in stack:
        if entry.get("formset"):
            formset = entry["formset"]
        if entry.get("form"):
            form = entry["form"]
    return formset, form


def _first_formset(settings: list[dict[str, Any]]) -> dict[str, Any] | None:
    for setting in settings:
        if setting.get("formset"):
            return setting["formset"]
    return None


def _visibility(stack: list[dict[str, Any]]) -> dict[str, Any]:
    conditions = [entry["condition"] for entry in stack if entry.get("condition")]
    opcodes = [condition["opcode"] for condition in conditions]
    return {
        "has_suppress_if": "SuppressIf" in opcodes,
        "has_gray_out_if": "GrayOutIf" in opcodes,
        "evaluated": False,
        "raw_conditions": [json.dumps(condition, sort_keys=True) for condition in conditions],
    }


def _setting_path(formset: dict[str, Any] | None, form: dict[str, Any] | None) -> list[str]:
    out = []
    if formset and formset.get("title"):
        out.append(formset["title"])
    if form and form.get("title") and form.get("title") not in out:
        out.append(form["title"])
    return out


def _question_type(opcode: str) -> str:
    return {
        "OneOf": "oneof",
        "CheckBox": "checkbox",
        "Numeric": "numeric",
        "String": "string",
        "OrderedList": "ordered_list",
        "Date": "date",
        "Time": "time",
    }.get(opcode, opcode.lower())


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or "")
    if value is None:
        return ""
    return str(value)


def _lower(value: Any) -> str:
    return str(value or "").lower()
