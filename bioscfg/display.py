from __future__ import annotations

from typing import Any


def display_current(setting: dict[str, Any]) -> str:
    current = setting.get("current") or {}
    if not current.get("available"):
        return ""
    decoded = current.get("decoded")
    if decoded:
        return str(decoded)
    if "value" in current:
        value = str(current["value"])
        raw = current.get("raw_hex")
        return f"{value} ({raw})".strip() if raw else value
    return str(current.get("raw_hex") or "")


def display_default(setting: dict[str, Any]) -> str:
    for option in setting.get("options", []):
        if option.get("default"):
            return option.get("label") or str(option.get("value"))
    default = setting.get("default")
    if default:
        return str(default)
    defaults = setting.get("defaults") or []
    if defaults and defaults[0].get("value") is not None:
        return str(defaults[0]["value"])
    return ""


def setting_location(setting: dict[str, Any]) -> str:
    varstore = setting.get("varstore") or {}
    if not varstore.get("name") or setting.get("offset") is None:
        return ""
    return f"{varstore['name']}[0x{setting['offset']:X}]"


def clip(value: str, width: int) -> str:
    value = str(value)
    if width <= 0:
        return ""
    if len(value) <= width:
        return value.ljust(width)
    if width <= 3:
        return value[:width]
    return value[: width - 3] + "..."
