#!/usr/bin/env bash
# install.sh GAMEDIR — put BepInEx into the game if missing, then copy the plugin.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RE_HOME="${RE_HOME:-$HOME/re}"
[[ $# -eq 1 && -d "$1" ]] || { echo "usage: install.sh <game directory>" >&2; exit 2; }
game="$1"
dll="$here/bin/Release/netstandard2.0/ExamplePlugin.dll"
[[ -f "$dll" ]] || { echo "build first: dotnet build -c Release -p:GameDir=\"$game\"" >&2; exit 1; }

if [[ ! -d "$game/BepInEx" ]]; then
    bepinex="$RE_HOME/tools/bepinex"
    [[ -f "$bepinex/winhttp.dll" ]] || { echo "$bepinex is missing. Run './setup.sh user' first." >&2; exit 1; }
    cp -r "$bepinex/." "$game/"
    echo "installed BepInEx into $game"
fi
mkdir -p "$game/BepInEx/plugins"
cp "$dll" "$game/BepInEx/plugins/"
echo "installed: $game/BepInEx/plugins/ExamplePlugin.dll"
echo 'Steam launch options: WINEDLLOVERRIDES="winhttp=n,b" %command%'
