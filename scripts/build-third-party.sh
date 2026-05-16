#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cargo build --release --manifest-path "$ROOT/third-party/IFRExtractor-RS/Cargo.toml"

cmake -S "$ROOT/third-party/UEFITool/UEFIExtract" -B "$ROOT/build/UEFIExtract"
cmake --build "$ROOT/build/UEFIExtract"
