#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  source .venv/bin/activate
fi

if [[ ! -f ".env" ]]; then
  echo "Missing .env file in $ROOT_DIR" >&2
  exit 1
fi

set -a
source .env
set +a

PYTHONPATH=src python3 -m discourse_monitor collect "$@"
