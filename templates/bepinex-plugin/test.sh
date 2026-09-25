#!/usr/bin/env bash
# test.sh [GAMEDIR] — restore and build the plugin; with GAMEDIR against that game's assemblies.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"
dotnet restore --nologo -v quiet >/dev/null
if [[ $# -ge 1 ]]; then
    dotnet build -c Release --no-restore --nologo -v quiet -p:GameDir="$1" >/dev/null
    what="build against $1"
else
    dotnet build -c Release --no-restore --nologo -v quiet >/dev/null
    what="build without a game (demo patch only needs UnityEngine)"
fi
[[ -f bin/Release/netstandard2.0/ExamplePlugin.dll ]] || { echo "ExamplePlugin.dll was not built" >&2; exit 1; }
echo "ok: $what"
