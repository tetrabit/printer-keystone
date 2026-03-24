#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
uv run printer-keystone analyze \
  --front front.png \
  --back back.png \
  --paper letter \
  --debug-dir debug \
  "$@"
