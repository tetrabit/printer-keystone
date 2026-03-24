#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
uv run printer-keystone verify --paper letter "$@"
