from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NormalizedImage:
    original_path: Path
    normalized_path: Path
    original_sha256: str
    normalized_sha256: str
    input_format: str
    capsule_header_size: int | None = None


@dataclass(frozen=True)
class Efivar:
    name: str
    guid: str
    attributes: int
    data: bytes
    path: Path


@dataclass(frozen=True)
class ToolPaths:
    uefiextract: Path
    ifrextract: Path
