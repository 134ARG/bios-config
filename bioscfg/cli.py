from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .decode import decode_settings
from .efivarfs import load_efivarfs
from .extract import ToolError, extract_ifr_all, normalize_bios_input
from .ifr_json import parse_ifr_dir
from .table import filter_settings, render_table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bioscfg-view")
    parser.add_argument("bios", type=Path, help="BIOS image, raw .bin or vendor .CAP")
    parser.add_argument("--cache", type=Path, default=Path(".bioscfg-cache"))
    parser.add_argument("--json", type=Path, help="Write decoded settings JSON")
    parser.add_argument("--schema-json", type=Path, help="Write schema-only JSON before efivar decode")
    parser.add_argument("--table", action="store_true", help="Print table output")
    parser.add_argument("--tui", action="store_true", help="Open curses TUI")
    parser.add_argument("--grep", help="Case-insensitive setting search")
    parser.add_argument("--varstore", help="Filter by VarStore name")
    parser.add_argument("--efivars", default="/sys/firmware/efi/efivars", help="efivarfs directory, or 'none'")
    parser.add_argument("--normalize-only", action="store_true", help="Only normalize input image and print result")
    parser.add_argument("--force", action="store_true", help="Re-run extraction even if cache exists")
    parser.add_argument("--limit", type=int, help="Limit printed table rows")
    args = parser.parse_args(argv)

    try:
        if args.normalize_only:
            image = normalize_bios_input(args.bios, args.cache)
            print(json.dumps({
                "original_path": str(image.original_path),
                "normalized_path": str(image.normalized_path),
                "input_format": image.input_format,
                "capsule_header_size": image.capsule_header_size,
                "original_sha256": image.original_sha256,
                "normalized_sha256": image.normalized_sha256,
            }, indent=2))
            return 0

        manifest = extract_ifr_all(args.bios, args.cache, force=args.force)
        schema = parse_ifr_dir(Path(manifest["ifr_dir"]))
        schema["bios"] = manifest["image"]

        if args.schema_json:
            args.schema_json.parent.mkdir(parents=True, exist_ok=True)
            args.schema_json.write_text(json.dumps(schema, indent=2) + "\n")

        efivars = {}
        if args.efivars != "none":
            efivars = load_efivarfs(Path(args.efivars))
        decoded = decode_settings(schema, efivars)

        settings = filter_settings(decoded["settings"], grep=args.grep, varstore=args.varstore)
        decoded["filtered_setting_count"] = len(settings)

        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(decoded, indent=2) + "\n")

        if args.table or (not args.json and not args.tui):
            print(f"Settings: {decoded['summary'].get('total', 0)}  Filtered: {len(settings)}  Summary: {decoded['summary']}")
            print(render_table(settings, limit=args.limit))

        if args.tui:
            from .tui import run_tui
            run_tui(settings, decoded["summary"], initial_search=args.grep)

        return 0
    except ToolError as exc:
        print(f"bioscfg-view: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
