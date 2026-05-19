#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for pid_file in "${ROOT_DIR}"/.run/*.pid; do
  [[ -e "$pid_file" ]] || exit 0
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid"
  fi
  rm -f "$pid_file"
done
