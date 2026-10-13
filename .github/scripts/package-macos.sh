#!/usr/bin/env bash
# Run from aseprite/build/bin after resource cleanup and translation validation.
set -euo pipefail

fail() {
  echo "macOS packaging failed: $*" >&2
  exit 1
}

[[ "$(uname -s)" == Darwin ]] || fail "this script requires macOS"
[[ $# == 1 && "$1" == *.zip && "$1" != */* ]] || fail "expected a ZIP filename"
[[ -x Aseprite.app/Contents/MacOS/aseprite ]] || fail "missing app executable"
[[ -f aseprite.ini && ! -L aseprite.ini ]] || fail "missing portable configuration"

archive_path="$PWD/$1"
work_dir=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/aseprite-package.XXXXXX")
trap 'rm -rf "$work_dir"' EXIT
work_dir=$(cd "$work_dir" && pwd -P)
package_dir="$work_dir/package"
app="$package_dir/Aseprite.app"
mkdir -p "$package_dir"

# Do not copy upstream's absolute bin/aseprite and bin/data build-tree links.
ditto Aseprite.app "$app"
cp aseprite.ini "$package_dir/aseprite.ini"
cat > "$package_dir/aseprite" <<'LAUNCHER'
#!/bin/sh
set -eu
app_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec "$app_dir/Aseprite.app/Contents/MacOS/aseprite" "$@"
LAUNCHER
chmod 755 "$package_dir/aseprite"
cat > "$package_dir/README-macOS.txt" <<'NOTICE'
This build is ad-hoc signed and is not notarized.
The packaging checks verify bundle integrity and --version after extraction.
They do not establish Gatekeeper trust or test Finder/GUI launch.
Only run software from sources you trust.
NOTICE

check_links() {
  local root="$1" link target resolved
  while IFS= read -r -d '' link; do
    target=$(readlink "$link")
    [[ "$target" != /* && -e "$link" ]] || fail "absolute or broken link: $link"
    resolved=$(realpath "$link")
    [[ "$resolved" == "$root/"* ]] || fail "link escapes the package: $link"
  done < <(find "$root" -type l -print0)
}
check_links "$package_dir"

# Do not let a runner-installed library hide a missing runtime dependency.
# Supporting a future non-system dependency requires bundling/signing it first.
otool -L "$app/Contents/MacOS/aseprite" > "$work_dir/dependencies.txt"
while read -r dependency rest; do
  case "$dependency" in
    /System/Library/*|/usr/lib/*) ;;
    *) fail "unbundled runtime dependency: $dependency" ;;
  esac
done < <(tail -n +2 "$work_dir/dependencies.txt")

# Current Aseprite bundles contain one executable and statically linked vendor
# libraries. Seal the complete staged app after the final resource changes.
# This ad-hoc signature validates integrity, not Developer ID/Gatekeeper trust.
codesign --force --sign - --timestamp=none "$app"
codesign --verify --deep --strict --verbose=2 "$app"

archive="$work_dir/verified.zip"
ditto -c -k --sequesterRsrc "$package_dir" "$archive"
extracted="$work_dir/relocated archive"
ditto -x -k "$archive" "$extracted"
check_links "$extracted"

extracted_app="$extracted/Aseprite.app"
[[ -f "$extracted/aseprite" && ! -L "$extracted/aseprite" && -x "$extracted/aseprite" ]] ||
  fail "extracted launcher must be a regular executable file"
[[ -x "$extracted_app/Contents/MacOS/aseprite" ]] || fail "extracted app is not executable"
codesign --verify --deep --strict --verbose=2 "$extracted_app"

# Use a different working directory and fresh user folders so the smoke tests
# cannot depend on the archive location or change resources in the signed app.
mkdir -p "$work_dir/direct config" "$work_dir/launcher config"
cd "$work_dir"
direct_version=$(ASEPRITE_USER_FOLDER="$work_dir/direct config" "$extracted_app/Contents/MacOS/aseprite" --version)
launcher_version=$(ASEPRITE_USER_FOLDER="$work_dir/launcher config" "$extracted/aseprite" --version)
[[ "$direct_version" == Aseprite* && "$launcher_version" == "$direct_version" ]] ||
  fail "extracted --version smoke tests did not match"
printf '%s\n' "$direct_version"
codesign --verify --deep --strict --verbose=2 "$extracted_app"

# Only make the archive available to artifact/release upload after every check.
mv "$archive" "$archive_path"
echo "Verified macOS archive: $archive_path (ad-hoc signed, not notarized)"
