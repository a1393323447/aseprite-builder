#!/usr/bin/env bash
# Run from aseprite/build/bin after cleanup and before packaging/upload.
set -euo pipefail

[[ -x ./aseprite ]] || { echo 'Missing Linux executable' >&2; exit 1; }
smoke_dir=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/aseprite-smoke.XXXXXX")
trap 'rm -rf "$smoke_dir"' EXIT
mkdir -p "$smoke_dir/home" "$smoke_dir/config" "$smoke_dir/user"

# --version initializes configuration and resources before printing the version.
# ASEPRITE_USER_FOLDER alone does not stop migration of $HOME/.asepriterc or
# resource lookups under $XDG_CONFIG_HOME (falling back to $HOME/.config).
# A missing dynamic dependency or other startup failure must stop the workflow.
version=$(HOME="$smoke_dir/home" \
  XDG_CONFIG_HOME="$smoke_dir/config" \
  ASEPRITE_USER_FOLDER="$smoke_dir/user" ./aseprite --version)
[[ "$version" == Aseprite\ [0-9]* ]] || {
  echo "Unexpected Aseprite version output: $version" >&2
  exit 1
}
printf '%s\n' "$version"
