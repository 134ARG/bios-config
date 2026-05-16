from __future__ import annotations

from pathlib import Path

from .model import Efivar


def load_efivarfs(root: Path) -> dict[tuple[str, str], Efivar]:
    root = root.resolve()
    out: dict[tuple[str, str], Efivar] = {}
    if not root.exists():
        return out

    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        parsed = split_efivar_name(path.name)
        if parsed is None:
            continue
        name, guid = parsed
        try:
            raw = path.read_bytes()
        except (OSError, PermissionError):
            continue
        if len(raw) < 4:
            continue
        attrs = int.from_bytes(raw[:4], "little")
        out[(name, guid)] = Efivar(
            name=name,
            guid=guid,
            attributes=attrs,
            data=raw[4:],
            path=path,
        )
    return out


def split_efivar_name(filename: str) -> tuple[str, str] | None:
    if len(filename) < 38:
        return None
    if filename[-37] != "-":
        return None
    name = filename[:-37]
    guid = filename[-36:].lower()
    if not name or not _looks_like_guid(guid):
        return None
    return name, guid


def _looks_like_guid(value: str) -> bool:
    if len(value) != 36:
        return False
    for idx, ch in enumerate(value):
        if idx in (8, 13, 18, 23):
            if ch != "-":
                return False
        elif ch not in "0123456789abcdef":
            return False
    return True
