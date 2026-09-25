# Anti-cheat

Only games you own, only single player or offline modes. A debugger, an
injected DLL or a memory reader in a game that runs anti-cheat can get the
account banned, offline mode included. Anti-cheat reports what it sees, and a
ban hits the whole account. Claude Code checks the game folder first and, if it
finds anti-cheat, asks you once, yes or no. The call is yours; this page is
what it is based on.

## How to tell

Look in the game folder before doing anything else:

- `EasyAntiCheat/` folder, `EasyAntiCheat_EOS_Setup.exe`, `start_protected_game.exe`
- `BattlEye/` folder, `BEService.exe`, `BEClient_x64.dll`
- `vgc.exe`, `vgk.sys` (Riot Vanguard; does not run under Proton anyway)
- `nProtect`, `GameGuard`, `XIGNCODE`, `PunkBuster` in file or folder names

Steam shows it too. The store page lists "Uses third-party anti-cheat" or
"third-party DRM" in the box on the right, and areweanticheatyet.com tracks
which ones run under Proton.

Denuvo is DRM, not anti-cheat, but games with it are a poor target as well:
the code is obfuscated and repeated launches while you patch things can trip
its activation limit.

## What is fine

Offline single player games without any of the above. Mods for them through a
proxy DLL or BepInEx, memory reading for an overlay, taking the binary apart in
Ghidra. If a game has both a multiplayer mode with anti-cheat and a single
player mode, treat it as an anti-cheat game.
