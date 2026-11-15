#!/usr/bin/env bash
# Run from aseprite/build/bin after cleanup and before packaging/upload.
set -euo pipefail

[[ -x ./aseprite ]] || { echo 'Missing Linux executable' >&2; exit 1; }
user_dir=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/aseprite-smoke.XXXXXX")
trap 'rm -rf "$user_dir"' EXIT

# Do not use or write the runner user's existing Aseprite configuration.
# A missing dynamic dependency or other startup failure must stop the workflow.
version=$(ASEPRITE_USER_FOLDER="$user_dir" ./aseprite --version)
[[ "$version" == Aseprite\ [0-9]* ]] || {
  echo "Unexpected Aseprite version output: $version" >&2
  exit 1
}
printf '%s\n' "$version"
