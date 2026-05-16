# BIOS Config Viewer Implementation Plan

## Goal

Build a read-only Linux tool that takes:

- an exact BIOS image, such as `bios.bin`
- live or saved UEFI variables, normally `/sys/firmware/efi/efivars`

and produces:

- a normalized JSON model of discoverable BIOS setup settings
- a terminal UI for browsing current values, defaults, options, offsets, and source metadata

The honest scope is:

> Every IFR-described BIOS setup setting whose backing UEFI variable is present and readable.

This is intentionally not write support, not firmware patching, and not a guarantee that all firmware policy state is represented. Some settings can be hardcoded, generated dynamically, stored outside efivarfs, or hidden in vendor-specific storage.

## Product Shape

Primary command:

```bash
bioscfg-view bios.bin --tui
```

Useful non-interactive commands:

```bash
bioscfg-view bios.bin --json out/settings.json
bioscfg-view bios.bin --table
bioscfg-view bios.bin --grep "Core Performance Boost"
bioscfg-view bios.bin --varstore AmdSetup
bioscfg-view bios.bin --efivars /sys/firmware/efi/efivars
bioscfg-view bios.bin --efivars-snapshot ./efivars-snapshot
```

MVP defaults:

- read live efivarfs from `/sys/firmware/efi/efivars`
- extract IFR automatically into a cache directory
- write JSON unless disabled
- open the TUI when `--tui` is passed
- never write to efivarfs

## Existing Repo Inputs

Use the current repo assets like this:

- `third-party/UEFITool`: build/use `UEFIExtract` for recursive BIOS image extraction.
- `third-party/IFRExtractor-RS`: build/use `ifrextractor` for IFR text extraction.
- `doc/chat.md`: design source notes and known examples.
- `doc/fancontrol-tui`: curses-style TUI reference: blue background, centered dialog, selectable table, modal popup pattern.
- `set-r1606g-boost.sh`: historical proof of the efivar offset model only. Do not reuse write behavior.

## Architecture

Proposed Python package layout:

```text
bioscfg/
  __init__.py
  cli.py
  extract.py
  model.py
  ifr_json.py
  efivarfs.py
  decode.py
  display.py
  table.py
  tui.py
  util.py
scripts/
  build-third-party.sh
tests/
  fixtures/
  test_ifr_json.py
  test_efivarfs.py
  test_decode.py
```

Keep runtime dependencies minimal for v0:

- Python standard library for CLI, JSON, efivarfs reading, and curses TUI.
- External build/runtime tools: `UEFIExtract` and `ifrextractor`.
- Optional later: `rich` for prettier non-TUI tables, `python-uefivars` for snapshot import/export, CHIPSEC for SPI/NVRAM advanced workflows.

## Pipeline

### Stage 0: Normalize BIOS Input

Accept both raw firmware images and vendor capsule files.

For the ASUS B650E-I smoking fixture:

```text
tests/smoking/ROG-STRIX-B650E-I-GAMING-WIFI-ASUS-3854.CAP
tests/smoking/ROG-STRIX-B650E-I-GAMING-WIFI-ASUS-3854.CFG
```

The `.CFG` file is BIOSRenamer metadata from the ASUS zip. It points to the `.CAP` and can be ignored for read-only extraction.

The `.CAP` file is a UEFI capsule-wrapped image. Its capsule header has:

```text
header size: 0x1000
capsule size: 0x2001000
payload size: 0x2000000
```

So the raw image is the `.CAP` payload after the first `0x1000` bytes. Manual extraction:

```bash
dd if=tests/smoking/ROG-STRIX-B650E-I-GAMING-WIFI-ASUS-3854.CAP \
  of=tests/smoking/ROG-STRIX-B650E-I-GAMING-WIFI-ASUS-3854.bin \
  bs=4096 skip=1 status=progress
```

The tool should do this automatically:

1. Read the first 28 bytes as an EFI capsule header candidate.
2. Validate that `HeaderSize` is sane and `CapsuleImageSize` equals the file size.
3. If valid, cache `input[HeaderSize:]` as the normalized BIOS image.
4. If not valid, treat the input as an already-raw image.

Do not commit generated `.bin` files unless they are intentionally part of test fixtures; prefer cache/runtime generation for large vendor images.

### Stage 1: Build/Locate Tools

Implement `extract.py` tool discovery:

1. Use `UEFIEXTRACT` env var if set.
2. Use `IFREXTRACT` env var if set.
3. Search common local build outputs under `third-party/`.
4. Search `PATH`.
5. If missing, print exact build instructions.

Add `scripts/build-third-party.sh`:

```bash
cargo build --release --manifest-path third-party/IFRExtractor-RS/Cargo.toml
cmake -S third-party/UEFITool/UEFIExtract -B build/UEFIExtract
cmake --build build/UEFIExtract
```

The exact UEFIExtract CMake invocation may need adjustment after a local build test because the vendored UEFITool tree also has root-level build files.

### Stage 2: Extract BIOS Tree

Input:

```text
bios.bin
```

Process:

```text
UEFIExtract bios.bin all
```

Output cache:

```text
.bioscfg-cache/<bios-sha256>/
  bios.sha256
  uefiextract.log
  dump/
  ifr/
  manifest.json
```

Implementation notes:

- Hash the BIOS image and cache by SHA256.
- Copy or symlink the BIOS into a temp work directory before running `UEFIExtract`, because UEFIExtract writes `<input>.dump`.
- Preserve a manifest mapping extracted file path to generated IFR output.
- Keep logs for debugging bad vendor images.

### Stage 3: Run IFRExtractor-RS on Candidates

MVP strategy: brute force every non-empty extracted file.

For each file:

```text
ifrextractor extracted-file
```

Patched `IFRExtractor-RS` JSON mode writes one canonical output per form package, using names like:

```text
<input>.<package-list-index>.<form-index>.uefi.ifr.json
```

JSON mode prefers real UEFI HII package lists. If UEFIExtract handed us a leaf with loose form/string packages and no package-list header, it may pair only within that same candidate file. It never pairs forms and strings across different extracted files. The wrapper snapshots the directory before/after execution, then collects generated `*.ifr.json` files into the cache and dedups by SHA.

This avoids hardcoding module names like `Setup`, `CbsSetupDxe`, `AodSetup`, or `CpuSetup`.

Later optimization:

- Use file size/type filters.
- Use UEFI report metadata to prioritize PE32/DXE/HII modules.
- Add a cache so unchanged extracted files are not reprocessed.

### Stage 4: Parse IFR JSON into Schema

Parse patched IFRExtractor-RS JSON output directly.

Important IFR JSON opcodes:

```text
FormSet
Form
VarStore / VarStoreEfi / VarStoreNameValue
OneOf / Numeric / CheckBox / String / OrderedList
OneOfOption
Default
SuppressIf / GrayOutIf / DisableIf / NoSubmitIf / InconsistentIf
```

Parser approach:

- Walk JSON operations and use opcode depth/scope to maintain a scope stack.
- Track current `FormSet` and `Form`.
- Track active condition scopes: `SuppressIf`, `GrayOutIf`, `DisableIf`, `NoSubmitIf`, `InconsistentIf`.
- Attach child `OneOfOption` and `Default` records to the parent question.
- Resolve `VarStoreId` to VarStore metadata.

Do not fully evaluate conditions in v0. Instead, mark settings:

```json
"visibility": {
  "has_suppress_if": true,
  "has_gray_out_if": false,
  "evaluated": false,
  "raw_conditions": ["SuppressIf", "EqIdVal ..."]
}
```

### Stage 5: Normalize Schema JSON

Use a stable internal JSON model:

```json
{
  "bios": {
    "path": "bios.bin",
    "sha256": "...",
    "cache_key": "..."
  },
  "setting_count": 1,
  "settings": [
    {
      "path": ["AMD CBS", "Zen Common Options"],
      "prompt": "Core Performance Boost",
      "help": "Disable CPB",
      "type": "oneof",
      "question_id": 4660,
      "varstore": {
        "id": 20480,
        "name": "AmdSetup",
        "guid": "3a997502-647a-4c82-998e-52ef9486a247",
        "size": 1343,
        "kind": "buffer"
      },
      "offset": 36,
      "size_bits": 8,
      "options": [
        {"value": 0, "label": "Disabled", "default": true},
        {"value": 1, "label": "Auto", "default": false}
      ],
      "defaults": [],
      "visibility": {
        "has_suppress_if": false,
        "has_gray_out_if": false,
        "evaluated": false
      },
      "source": {
        "ifr_file": "...",
        "line": 123
      }
    }
  ]
}
```

Keep numeric values as integers in JSON. Add display formatting only in the table/TUI layers.

### Stage 6: Read Efivarfs

Primary backend: direct Python stdlib reader.

Linux efivarfs file layout:

```text
/sys/firmware/efi/efivars/<Name>-<guid>
bytes 0..3: UEFI variable attributes, little-endian
bytes 4.. : variable data
```

Decoder rule:

```text
live byte offset = IFR VarOffset inside data bytes
raw file offset = IFR VarOffset + 4
```

Backend model:

```json
{
  "name": "AmdSetup",
  "guid": "3a997502-647a-4c82-998e-52ef9486a247",
  "attributes": "0x00000007",
  "data_size": 1343,
  "data_hex": "...",
  "source": "efivarfs",
  "path": "/sys/firmware/efi/efivars/AmdSetup-..."
}
```

Implementation details:

- Split filenames using the last 37 characters: `-` plus 36-character GUID.
- Normalize GUIDs to lowercase for matching.
- Read permission failures become per-variable diagnostics, not fatal errors.
- For live mode, read all variables once before decoding.
- For snapshot mode, accept a directory with efivarfs-style files.
- Later, add tar snapshot support with Python `tarfile`.

### Stage 7: Decode Current Values

Join key:

```text
(varstore.name, varstore.guid)
```

Decode by question type:

- `oneof`: read integer, match `options[].value`, display label or raw unknown.
- `checkbox`: read one byte/bit as disabled/enabled; use IFR defaults where available.
- `numeric`: read little-endian integer by `size_bits`; display decimal and hex; show min/max/step.
- `string`: v0 mark unsupported or decode simple UTF-16/ASCII only when size is clear.
- `ordered_list`, `date`, `time`: mark unsupported in v0, keep schema metadata.

Statuses:

```text
ok
decoded_unknown_option
missing_varstore
missing_efivar
offset_out_of_range
unsupported_type
permission_denied
duplicate_alias
```

Duplicate handling:

- Same `(name, guid, offset, size_bits)` means same underlying setting.
- Keep all UI paths, but group aliases in detail view.
- For PBO/CO, this matters because vendor pages and AMD Overclocking pages may mirror or wrap the same setting.

### Stage 8: Non-TUI Output

Implement plain table output before curses:

```text
Path                                      Setting                   Current   Default   VarStore[Offset]
AMD CBS > Zen Common Options             Core Performance Boost    Auto      Disabled  AmdSetup[0x24]
AMD CBS > Zen Common Options             Global C-state Control    Auto      Auto      AmdSetup[0x25]
```

Filtering:

- `--grep`: case-insensitive match against prompt, path, help, varstore, GUID.
- `--varstore`: exact or case-insensitive varstore name.
- `--status`: show only missing/unsupported/ok/etc.
- `--hidden`: include or exclude condition-marked entries.

### Stage 9: TUI

Use Python `curses` for v0 to match `doc/fancontrol-tui` and avoid adding runtime dependencies.

Reference details to reuse:

- `ESCDELAY=25`
- `curses.wrapper`
- blue background
- centered dialog or full-screen table panel
- color-pair highlight for selected row
- modal popup pattern for filters/search
- no write-mode footer or mutation controls

Recommended TUI layout:

```text
+ bioscfg-view --------------------------------------------------------------+
| BIOS: <sha>   Efivars: live   Settings: 1842   Decoded: 1331   Missing: 94 |
| Search: <text>   Filter: all   Sort: path                                  |
|----------------------------------------------------------------------------|
| Path / Setting                         Current       Default   Location    |
| AMD CBS > Zen Common Options           Auto          Disabled  AmdSetup:24 |
| Global C-state Control                 Auto          Auto      AmdSetup:25 |
| ...                                                                        |
|----------------------------------------------------------------------------|
| Help: Disable Core Performance Boost                                       |
| Raw: 0x01   Options: 0 Disabled, 1 Auto   Source: CbsSetupDxe...ifr.txt    |
+----------------------------------------------------------------------------+
```

Keys:

```text
q / Esc       quit
Up/Down       move row
PgUp/PgDn     page
Home/End      jump
/             search
f             filter popup
v             varstore popup
h             toggle condition-marked/hidden entries
d             toggle duplicate alias grouping
j             write current filtered view to JSON
Enter         details popup
```

TUI must remain read-only:

- no value editing
- no efivar writes
- no root-only write controls
- if run as root, show `READ ONLY` anyway

### Stage 10: Test Plan

Unit fixtures:

- Small synthetic IFR text with `FormSet`, `VarStore`, `OneOf`, `OneOfOption`, `CheckBox`, `Numeric`, `SuppressIf`, and `End`.
- Synthetic efivarfs directory:
  - `AmdSetup-3a997502-647a-4c82-998e-52ef9486a247`
  - first four bytes attributes
  - known bytes at offsets for CPB-like settings

Tests:

- IFR parser resolves varstores and child options.
- Scope parser attaches form paths and condition markers.
- Efivarfs reader strips attributes and normalizes GUIDs.
- Decoder uses `offset`, not `offset + 4`, after efivarfs data normalization.
- OneOf values decode to labels.
- Numeric values decode little-endian.
- Missing variables and out-of-range offsets return statuses, not crashes.

Integration tests:

- If a real BIOS image fixture is available, run extraction and assert at least one module/settings count.
- If live efivarfs is available, run read-only smoke test and assert no writes.

Manual validation targets:

- GHF51: `Core Performance Boost`, expected `AmdSetup[0x24]`.
- ASUS B650E-I: PBO, PPT/TDC/EDC, Curve Optimizer, Curve Shaper if present in that BIOS/AGESA.

### Stage 11: Milestones

#### v0.1: JSON pipeline

- Build/locate `UEFIExtract` and `ifrextractor`.
- Extract all candidate modules.
- Parse IFR text into schema JSON.
- Read direct efivarfs.
- Decode `OneOf`, `CheckBox`, `Numeric`.
- Emit `settings.json`.
- Support `--grep` and `--varstore`.

#### v0.2: TUI MVP

- Curses table browser.
- Search/filter popups.
- Detail pane.
- Status counts.
- Duplicate alias grouping.
- Export filtered view.

#### v0.3: Better schema fidelity

- More robust condition scope capture.
- `DefaultStore` support.
- Better path reconstruction through `Ref` forms.
- Support `VarStoreEfi` records separately from buffer-style `VarStore`.
- Tar snapshot support.

#### v0.4: Structured IFR backend

- Patch IFRExtractor-RS with canonical package-list JSON.
- Keep Python parser small: parse generated JSON files directly.
- Do not keep a text-parser compatibility fallback.

#### v1.0: Hardened read-only viewer

- Reliable CLI docs.
- Known-board validation notes.
- Better handling for duplicate vendor/AMD pages.
- Optional `python-uefivars` snapshot import/export.
- Optional CHIPSEC backend for SPI/NVRAM workflows.

## Key Design Choices

1. Use direct efivarfs for v0.

   It is simple, read-only, and exactly matches the needed data model. Libraries can be optional backends later.

2. Parse IFRExtractor text first.

   It is the lowest-code route from the current vendored dependency. Structured IFR JSON is a good v0.4 improvement, not a blocker.

3. Treat "hidden" as metadata first.

   Full IFR expression evaluation is useful, but not needed to show current values. Capture the condition context now, evaluate later.

4. Keep JSON as the core product.

   The TUI is a presentation layer over normalized JSON. This makes testing and offline analysis much easier.

5. Preserve raw provenance.

   Every setting should retain source IFR file, line, VarStore, GUID, offset, size, raw value, and status. Firmware data gets weird; provenance is what keeps the tool debuggable.

## First Implementation Pass

Implement in this order:

1. `bioscfg/efivarfs.py` plus tests using synthetic efivar files.
2. `bioscfg/ifr_json.py` plus tests using hand-written IFR JSON snippets.
3. `bioscfg/decode.py` to join schema and efivar data.
4. `bioscfg/extract.py` wrapper around third-party tools.
5. `bioscfg/cli.py` with `--json`, `--table`, `--grep`, `--varstore`.
6. `bioscfg/tui.py` once JSON/table output is trustworthy.

This order gives fast feedback without needing a real BIOS image for every test run.
