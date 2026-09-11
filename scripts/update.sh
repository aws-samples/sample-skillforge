#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(dirname -- "$script_dir")

git -C "$repo_root" pull --ff-only
cd "$repo_root"

if command -v python3 >/dev/null 2>&1; then
  exec python3 -m skillforge update --root "$repo_root" "$@"
fi

exec python -m skillforge update --root "$repo_root" "$@"
