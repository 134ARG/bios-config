from __future__ import annotations

from typing import Any

from .model import Efivar


def decode_settings(schema: dict[str, Any], efivars: dict[tuple[str, str], Efivar] | None) -> dict[str, Any]:
    efivars = efivars or {}
    decoded_settings = []
    for setting in schema.get("settings", []):
        item = dict(setting)
        current = decode_setting(setting, efivars)
        item["current"] = current
        decoded_settings.append(item)

    out = dict(schema)
    out["settings"] = decoded_settings
    out["summary"] = summarize(decoded_settings)
    return out


def decode_setting(setting: dict[str, Any], efivars: dict[tuple[str, str], Efivar]) -> dict[str, Any]:
    varstore = setting.get("varstore")
    if not varstore:
        return {"status": "missing_varstore", "available": False}

    name = varstore.get("name")
    guid = (varstore.get("guid") or "").lower()
    if not name or not guid:
        return {"status": "missing_varstore_identity", "available": False}

    ev = efivars.get((name, guid))
    if ev is None:
        return {"status": "missing_efivar", "available": False}

    offset = setting.get("offset")
    if offset is None:
        return {"status": "missing_offset", "available": False}

    if setting.get("type") == "string":
        return _decode_string_setting(setting, ev, offset)

    size_bits = setting.get("size_bits") or 8
    size_bytes = max(1, (size_bits + 7) // 8)
    if offset + size_bytes > len(ev.data):
        return {
            "status": "offset_out_of_range",
            "available": False,
            "efivar_size": len(ev.data),
            "offset": offset,
            "size_bytes": size_bytes,
        }

    raw = ev.data[offset:offset + size_bytes]
    value = int.from_bytes(raw, "little")
    decoded = _decode_value(setting, value)
    return {
        "status": "ok" if decoded is not None or setting.get("type") != "oneof" else "decoded_unknown_option",
        "available": True,
        "value": value,
        "raw_hex": "0x" + raw.hex(),
        "decoded": decoded,
        "efivar": str(ev.path),
        "attributes": f"0x{ev.attributes:08x}",
        "efivar_data_size": len(ev.data),
    }


def _decode_string_setting(setting: dict[str, Any], ev: Efivar, offset: int) -> dict[str, Any]:
    max_size = setting.get("max_size") or setting.get("size_bytes") or 1
    size_bytes = max(1, int(max_size) * 2)
    if offset >= len(ev.data):
        return {
            "status": "offset_out_of_range",
            "available": False,
            "efivar_size": len(ev.data),
            "offset": offset,
            "size_bytes": size_bytes,
        }

    raw = ev.data[offset:min(offset + size_bytes, len(ev.data))]
    decoded = _decode_string_bytes(raw)
    return {
        "status": "ok",
        "available": True,
        "value": decoded,
        "raw_hex": "0x" + raw.hex(),
        "decoded": decoded,
        "efivar": str(ev.path),
        "attributes": f"0x{ev.attributes:08x}",
        "efivar_data_size": len(ev.data),
    }


def summarize(settings: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {"total": len(settings)}
    for setting in settings:
        status = setting.get("current", {}).get("status", "unknown")
        summary[status] = summary.get(status, 0) + 1
    return summary


def _decode_value(setting: dict[str, Any], value: int) -> str | None:
    if setting.get("type") == "oneof":
        for option in setting.get("options", []):
            if option.get("value") == value:
                return option.get("label")
        return None
    if setting.get("type") == "checkbox":
        return "Enabled" if value else "Disabled"
    if setting.get("type") == "numeric":
        return str(value)
    return None


def _decode_string_bytes(raw: bytes) -> str:
    if len(raw) >= 2:
        end = len(raw)
        for idx in range(0, len(raw) - 1, 2):
            if raw[idx:idx + 2] == b"\x00\x00":
                end = idx
                break
        try:
            return raw[:end].decode("utf-16le", errors="replace").rstrip("\x00")
        except UnicodeDecodeError:
            pass
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
