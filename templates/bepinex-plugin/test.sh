#!/usr/bin/env bash
# test.sh [GAMEDIR] — restore and build the plugin; with GAMEDIR against that game's assemblies.
# Builds into a temp dir so the template itself stays clean.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
art="$(mktemp -d)"
trap 'rm -rf "$art"' EXIT
cd "$here"
dotnet restore --nologo -v quiet --artifacts-path "$art" >/dev/null
if [[ $# -ge 1 ]]; then
    dotnet build -c Release --no-restore --nologo -v quiet --artifacts-path "$art" -p:GameDir="$1" >/dev/null
    what="build against $1"
else
    dotnet build -c Release --no-restore --nologo -v quiet --artifacts-path "$art" >/dev/null
    what="build without a game (demo patch only needs UnityEngine)"
fi
[[ -n "$(find "$art" -name ExamplePlugin.dll -print -quit)" ]] || { echo "ExamplePlugin.dll was not built" >&2; exit 1; }
echo "ok: $what"
