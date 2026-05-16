from __future__ import annotations

from typing import Any

from .display import clip, display_current, display_default, setting_location


def filter_settings(settings: list[dict[str, Any]], grep: str | None = None, varstore: str | None = None) -> list[dict[str, Any]]:
    out = settings
    if grep:
        needle = grep.lower()
        out = [s for s in out if needle in _search_blob(s)]
    if varstore:
        target = varstore.lower()
        out = [s for s in out if ((s.get("varstore") or {}).get("name") or "").lower() == target]
    return out


def render_table(settings: list[dict[str, Any]], limit: int | None = None) -> str:
    rows = []
    for setting in settings[:limit]:
        path = " > ".join(setting.get("path") or [])
        prompt = setting.get("prompt") or ""
        current = display_current(setting)
        default = display_default(setting)
        location = setting_location(setting)
        status = setting.get("current", {}).get("status", "")
        rows.append([path, prompt, current, default, location, status])

    headers = ["Path", "Setting", "Current", "Default", "Location", "Status"]
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = min(max(widths[idx], len(value)), 48 if idx < 2 else 24)

    def fmt(row: list[str]) -> str:
        cells = []
        for idx, value in enumerate(row):
            cells.append(clip(value, widths[idx]))
        return "  ".join(cells)

    lines = [fmt(headers), fmt(["-" * w for w in widths])]
    lines.extend(fmt(row) for row in rows)
    return "\n".join(lines)

def _search_blob(setting: dict[str, Any]) -> str:
    varstore = setting.get("varstore") or {}
    parts = [
        " > ".join(setting.get("path") or []),
        setting.get("prompt") or "",
        setting.get("help") or "",
        varstore.get("name") or "",
        varstore.get("guid") or "",
        setting.get("current", {}).get("decoded") or "",
    ]
    return "\n".join(parts).lower()
