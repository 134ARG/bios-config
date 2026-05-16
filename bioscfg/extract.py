from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

from .model import NormalizedImage, ToolPaths
from .util import sha256_file


EFI_CAPSULE_HEADER_LEN = 28
HII_PACKAGE_TYPE_FORM = 0x02
HII_PACKAGE_TYPE_STRINGS = 0x04
CACHE_VERSION = "canonical-json-v2"


class ToolError(RuntimeError):
    pass


def normalize_bios_input(input_path: Path, cache_root: Path) -> NormalizedImage:
    input_path = input_path.resolve()
    cache_root = cache_root.resolve()
    original_sha = sha256_file(input_path)
    image_cache = cache_root / "images" / original_sha
    image_cache.mkdir(parents=True, exist_ok=True)

    header_size = detect_capsule_header_size(input_path)
    if header_size is None:
        normalized_path = image_cache / input_path.name
        input_format = "raw"
        capsule_header_size = None
        if not normalized_path.exists():
            shutil.copy2(input_path, normalized_path)
    else:
        stem = input_path.stem
        normalized_path = image_cache / f"{stem}.bin"
        input_format = "uefi-capsule"
        capsule_header_size = header_size
        if not normalized_path.exists():
            with input_path.open("rb") as src, normalized_path.open("wb") as dst:
                src.seek(header_size)
                shutil.copyfileobj(src, dst)

    normalized_sha = sha256_file(normalized_path)
    meta = NormalizedImage(
        original_path=input_path,
        normalized_path=normalized_path,
        original_sha256=original_sha,
        normalized_sha256=normalized_sha,
        input_format=input_format,
        capsule_header_size=capsule_header_size,
    )
    (image_cache / "image.json").write_text(json.dumps(_image_meta(meta), indent=2) + "\n")
    return meta


def detect_capsule_header_size(path: Path) -> int | None:
    size = path.stat().st_size
    if size < EFI_CAPSULE_HEADER_LEN:
        return None

    with path.open("rb") as f:
        header = f.read(EFI_CAPSULE_HEADER_LEN)

    header_size = int.from_bytes(header[16:20], "little")
    capsule_size = int.from_bytes(header[24:28], "little")

    if capsule_size != size:
        return None
    if header_size < EFI_CAPSULE_HEADER_LEN or header_size >= size:
        return None
    if header_size % 8 != 0:
        return None

    return header_size


def find_tools() -> ToolPaths:
    uefiextract = _find_tool("UEFIEXTRACT", "uefiextract", [
        Path("build/UEFIExtract/uefiextract"),
        Path("build/UEFITool/UEFIExtract/uefiextract"),
        Path("third-party/UEFITool/UEFIExtract/uefiextract"),
    ])
    ifrextract = _find_tool("IFREXTRACT", "ifrextractor", [
        Path("third-party/IFRExtractor-RS/target/release/ifrextractor"),
        Path("third-party/IFRExtractor-RS/target/debug/ifrextractor"),
    ])
    return ToolPaths(uefiextract=uefiextract, ifrextract=ifrextract)


def extract_ifr_all(
    input_path: Path,
    cache_root: Path,
    tools: ToolPaths | None = None,
    force: bool = False,
) -> dict:
    cache_root = cache_root.resolve()
    normalized = normalize_bios_input(input_path, cache_root)
    tools = tools or find_tools()

    run_root = cache_root / normalized.normalized_sha256
    dump_dir = run_root / "dump-leaf-json"
    ifr_dir = run_root / "ifr"
    logs_dir = run_root / "logs"
    work_dir = run_root / "work"
    manifest_path = run_root / "manifest.json"

    if manifest_path.exists() and not force:
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("cache_version") == CACHE_VERSION:
            return manifest
        force = True

    if force:
        manifest_path.unlink(missing_ok=True)
        for path in (ifr_dir, logs_dir):
            if path.exists():
                shutil.rmtree(path)
    for path in (ifr_dir, logs_dir, work_dir):
        path.mkdir(parents=True, exist_ok=True)

    work_image = work_dir / "input.bin"
    if force and work_image.exists():
        work_image.unlink()
    if not work_image.exists():
        shutil.copy2(normalized.normalized_path, work_image)

    generated_dump = work_dir / "input.bin.dump"
    if not dump_dir.exists():
        if generated_dump.exists():
            shutil.rmtree(generated_dump)
        _run(
            [str(tools.uefiextract), str(work_image), "dump"],
            cwd=work_dir,
            log_path=logs_dir / "uefiextract.log",
        )
        if not generated_dump.exists():
            raise ToolError(f"UEFIExtract did not create expected dump: {generated_dump}")
        generated_dump.rename(dump_dir)

    candidates = [p for p in sorted(dump_dir.rglob("*")) if p.is_file() and p.stat().st_size > 0]
    kept = []
    kept_hashes: set[str] = set()
    candidate_hashes: set[str] = set()
    skipped_duplicate_candidates = 0
    skipped_non_hii_candidates = 0

    for idx, candidate in enumerate(candidates):
        if force:
            for stale in candidate.parent.glob(f"{candidate.name}.*.ifr.json"):
                stale.unlink(missing_ok=True)

        if not _has_hii_form_and_strings(candidate):
            skipped_non_hii_candidates += 1
            continue

        candidate_hash = sha256_file(candidate)
        if candidate_hash in candidate_hashes:
            skipped_duplicate_candidates += 1
            continue
        candidate_hashes.add(candidate_hash)

        before = set(candidate.parent.glob(f"{candidate.name}.*.ifr.json"))
        log_path = logs_dir / f"ifrextractor-{idx:06d}.log"
        proc = subprocess.run(
            [str(tools.ifrextract), candidate.name, "json"],
            cwd=candidate.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
        log_path.write_text(proc.stdout)
        after = set(candidate.parent.glob(f"{candidate.name}.*.ifr.json"))
        generated = sorted(after - before)
        if proc.returncode != 0:
            if generated or proc.returncode not in (2, 3):
                for ifr_file in generated:
                    ifr_file.unlink(missing_ok=True)
                raise ToolError(f"IFRExtractor failed ({proc.returncode}): {candidate}; see {log_path}")
            continue

        for ifr_file in generated:
            content_hash = sha256_file(ifr_file)
            if content_hash in kept_hashes:
                ifr_file.unlink(missing_ok=True)
                continue
            kept_hashes.add(content_hash)
            dest = ifr_dir / f"{idx:06d}-{ifr_file.name}"
            if dest.exists():
                dest.unlink()
            shutil.move(str(ifr_file), dest)
            kept.append({
                "ifr_file": str(dest),
                "source_file": str(candidate),
                "source_rel": str(candidate.relative_to(dump_dir)),
                "size": candidate.stat().st_size,
                "source_sha256": candidate_hash,
                "sha256": content_hash,
            })

    manifest = {
        "cache_version": CACHE_VERSION,
        "image": _image_meta(normalized),
        "tools": {
            "uefiextract": str(tools.uefiextract),
            "ifrextract": str(tools.ifrextract),
        },
        "dump_dir": str(dump_dir),
        "ifr_dir": str(ifr_dir),
        "candidate_count": len(candidates),
        "candidate_unique_count": len(candidate_hashes),
        "candidate_duplicate_count": skipped_duplicate_candidates,
        "candidate_non_hii_count": skipped_non_hii_candidates,
        "ifr_count": len(kept),
        "ifr": kept,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def _image_meta(image: NormalizedImage) -> dict:
    out = asdict(image)
    out["original_path"] = str(image.original_path)
    out["normalized_path"] = str(image.normalized_path)
    return out


def _has_hii_form_and_strings(path: Path) -> bool:
    data = path.read_bytes()
    return (
        _contains_hii_package(data, HII_PACKAGE_TYPE_FORM)
        and _contains_hii_package(data, HII_PACKAGE_TYPE_STRINGS)
    )


def _contains_hii_package(data: bytes, package_type: int) -> bool:
    size = len(data)
    for offset in range(0, max(0, size - 3)):
        length_raw = int.from_bytes(data[offset:offset + 4], "little")
        length = length_raw & 0x00FFFFFF
        current_type = (length_raw >> 24) & 0xFF
        if current_type != package_type or length <= 4 or offset + length > size:
            continue
        if package_type == HII_PACKAGE_TYPE_FORM:
            if length > 7 and data[offset + 4] == 0x0E and data[offset + length - 2:offset + length] == b"\x29\x02":
                return True
        elif package_type == HII_PACKAGE_TYPE_STRINGS:
            if length > 0x38 and data[offset + 4:offset + 8] == b"\x34\x00\x00\x00" and data[offset + length - 2:offset + length] == b"\x00\x00":
                return True
    return False


def _find_tool(env_name: str, executable: str, local_candidates: list[Path]) -> Path:
    env_value = os.environ.get(env_name)
    if env_value:
        path = Path(env_value).expanduser()
        if path.exists():
            return path.resolve()
        raise ToolError(f"{env_name} points to missing executable: {path}")

    for candidate in local_candidates:
        if candidate.exists():
            return candidate.resolve()

    found = shutil.which(executable)
    if found:
        return Path(found).resolve()

    raise ToolError(
        f"Missing {executable}. Build third-party tools with scripts/build-third-party.sh "
        f"or set {env_name}."
    )


def _run(cmd: list[str], cwd: Path, log_path: Path) -> None:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    log_path.write_text(proc.stdout)
    if proc.returncode != 0:
        raise ToolError(f"Command failed ({proc.returncode}): {' '.join(cmd)}; see {log_path}")
