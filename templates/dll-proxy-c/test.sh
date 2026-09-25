#!/usr/bin/env bash
# Build the proxy DLL in a temp dir and check its exports and static linking.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT

cmake -S "$here" -B "$build" -G Ninja --toolchain "$here/toolchain-mingw.cmake" >/dev/null 2>&1
cmake --build "$build" >/dev/null
dll="$build/version.dll"
[[ -f "$dll" ]] || { echo "version.dll was not built" >&2; exit 1; }

dump="$(x86_64-w64-mingw32-objdump -p "$dll")"
for sym in GetFileVersionInfoA GetFileVersionInfoW GetFileVersionInfoExA GetFileVersionInfoExW \
           GetFileVersionInfoSizeA GetFileVersionInfoSizeW GetFileVersionInfoSizeExA GetFileVersionInfoSizeExW \
           VerFindFileA VerFindFileW VerInstallFileA VerInstallFileW VerLanguageNameA VerLanguageNameW \
           VerQueryValueA VerQueryValueW; do
    grep -qE "^\s*\[\s*[0-9]+\].*\s$sym\$" <<<"$dump" || { echo "missing export: $sym" >&2; exit 1; }
done
text="$(x86_64-w64-mingw32-objdump -d -j .text "$dll")"
for sym in GetFileVersionInfoA VerQueryValueW VerLanguageNameA; do
    grep -q "<$sym>:" <<<"$text" || { echo "export $sym is not in .text (the jmp stub landed in .bss, the DLL would crash)" >&2; exit 1; }
done
if grep -qiE 'DLL Name: (libgcc|libwinpthread|libstdc\+\+)' <<<"$dump"; then
    echo "DLL is not statically linked" >&2; exit 1
fi
echo "ok: version.dll with 16 exports, statically linked"
