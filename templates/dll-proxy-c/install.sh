#!/usr/bin/env bash
# install.sh GAMEDIR — copy the built proxy DLL next to the game's exe.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ $# -eq 1 && -d "$1" ]] || { echo "usage: install.sh <game directory>" >&2; exit 2; }
dll="$here/build/version.dll"
[[ -f "$dll" ]] || { echo "build first: cmake -S . -B build -G Ninja --toolchain toolchain-mingw.cmake && cmake --build build" >&2; exit 1; }
cp "$dll" "$1/version.dll"
echo "installed: $1/version.dll"
echo 'Steam launch options: WINEDLLOVERRIDES="version=n,b" %command%'
