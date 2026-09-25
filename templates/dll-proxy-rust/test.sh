#!/usr/bin/env bash
# Build the dinput8 proxy in a temp target dir and check its exports.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CARGO_TARGET_DIR="$(mktemp -d)"
trap 'rm -rf "$CARGO_TARGET_DIR"' EXIT

(cd "$here" && cargo build --release --target x86_64-pc-windows-gnu --quiet)
dll="$CARGO_TARGET_DIR/x86_64-pc-windows-gnu/release/dinput8.dll"
[[ -f "$dll" ]] || { echo "dinput8.dll was not built" >&2; exit 1; }

dump="$(x86_64-w64-mingw32-objdump -p "$dll")"
for sym in DirectInput8Create DllMain; do
    grep -qE "^\s*\[\s*[0-9]+\].*\s$sym\$" <<<"$dump" || { echo "missing export: $sym" >&2; exit 1; }
done
if grep -qiE 'DLL Name: (libgcc|libwinpthread|libstdc\+\+)' <<<"$dump"; then
    echo "DLL is not statically linked" >&2; exit 1
fi
echo "ok: dinput8.dll exports DirectInput8Create and DllMain, statically linked"
