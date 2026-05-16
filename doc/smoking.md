# Smoking Notes

## ASUS ROG STRIX B650E-I BIOS 3854

Fixture:

```text
tests/smoking/ROG-STRIX-B650E-I-GAMING-WIFI-ASUS-3854.CAP
```

The `.CAP` file is a UEFI capsule. `bioscfg-view` detects the capsule header and caches the 32 MiB raw payload automatically. ASUS BIOS zips may also include `.CFG` metadata files, but they are not needed for parsing and are not kept as smoke fixtures.

Build vendored tools:

```bash
scripts/build-third-party.sh
```

Run extraction and decode against live efivarfs:

```bash
python3 -m bioscfg.cli \
  tests/smoking/ROG-STRIX-B650E-I-GAMING-WIFI-ASUS-3854.CAP \
  --json .bioscfg-cache/b650ei-settings.json \
  --schema-json .bioscfg-cache/b650ei-schema.json \
  --table \
  --grep "Curve Optimizer" \
  --limit 30
```

Open the TUI:

```bash
python3 -m bioscfg.cli \
  tests/smoking/ROG-STRIX-B650E-I-GAMING-WIFI-ASUS-3854.CAP \
  --tui \
  --grep "Curve Optimizer"
```

Current smoke result on this machine:

```text
Settings: 5644
ok: 4642
missing_efivar: 994
decoded_unknown_option: 5
missing_varstore: 3
```

Useful checks:

```bash
python3 -m bioscfg.cli tests/smoking/ROG-STRIX-B650E-I-GAMING-WIFI-ASUS-3854.CAP \
  --table --grep "Precision Boost Overdrive" --limit 40

python3 -m bioscfg.cli tests/smoking/ROG-STRIX-B650E-I-GAMING-WIFI-ASUS-3854.CAP \
  --table --grep "Core 0 Curve" --limit 10
```

Example decoded live entries:

```text
Setup > Curve Optimizer  Core 0 Curve Optimizer Sign       Negative  ...  ok
Setup > Curve Optimizer  Core 0 Curve Optimizer Magnitude  15        ...  ok
```
