#!/usr/bin/env bash
# install.sh GAMEDIR — copy the built proxy DLL next to the game's exe.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ $# -eq 1 && -d "$1" ]] || { echo "usage: install.sh <game directory>" >&2; exit 2; }
dll="$here/target/x86_64-pc-windows-gnu/release/dinput8.dll"
[[ -f "$dll" ]] || { echo "build first: cargo build --release" >&2; exit 1; }
cp "$dll" "$1/dinput8.dll"
echo "installed: $1/dinput8.dll"
echo 'Steam launch options: WINEDLLOVERRIDES="dinput8=n,b" %command%'
