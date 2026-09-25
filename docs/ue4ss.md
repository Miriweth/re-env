# Unreal games and UE4SS

UE4SS injects a Lua and C++ scripting layer into Unreal Engine 4 and 5 games.
It is not installed by the setup; here is how to add it to a game.

Download `UE4SS_v3.0.1.zip` from the releases of `UE4SS-RE/RE-UE4SS` on GitHub
and unpack it next to the game's shipping exe, usually
`<Game>/Binaries/Win64/`. UE4SS loads as a `dwmapi.dll` proxy, so the Steam
launch option is:

```
WINEDLLOVERRIDES="dwmapi=n,b" %command%
```

Lua mods live in `Mods/<name>/Scripts/main.lua` and are switched on in
`Mods/mods.txt` (`<name> : 1`). `UE4SS-settings.ini` next to the DLL controls
the console, the GUI and the object dumper. The dumper writes every UObject
with its offsets to a text file, which is the fastest way to map an Unreal
game before opening it in Ghidra.

Same rule as everywhere else in this repo: not on games with anti-cheat.
