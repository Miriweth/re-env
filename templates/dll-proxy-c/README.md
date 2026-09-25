# dll-proxy-c

A proxy `version.dll` in C. The game loads it instead of Wine's own, it forwards
all 16 exports to the real `System32\version.dll`, and next to that it starts a
thread with your hooks (MinHook 1.3.4, pulled in by CMake FetchContent).

## Build

```
cmake -S . -B build -G Ninja --toolchain toolchain-mingw.cmake
cmake --build build
```

The result is `build/version.dll`, statically linked, no libgcc or winpthread
next to it. `./test.sh` builds into a temp dir and checks exports and linking.

## Install

```
./install.sh "/path/to/the/game"
```

Steam launch options for the game: `WINEDLLOVERRIDES="version=n,b" %command%`
(`n,b`: native DLL from the game folder first, Wine builtin second). After the
game starts, `mod.log` appears in its working directory.

## Your own hooks

`src/dllmain.c` hooks `kernel32!Sleep` as a demo. For a game function:

1. Find the function in Ghidra. RVA = address minus image base.
2. At runtime the target is `(char *)GetModuleHandleA(NULL) + RVA`. If the game
   updates often, copy a byte pattern from Ghidra and search the module instead.
3. Call `MH_CreateHook(target, hook_fn, (LPVOID *)&real_fn)` instead of
   `MH_CreateHookApi`. Take the calling convention from Ghidra; on x64 that is
   the Microsoft ABI, `WINAPI` in mingw.
4. `MH_EnableHook(MH_ALL_HOOKS)`.

Proxying `version.dll` covers almost every game because nearly every exe loads
it through the CRT. Do not use this on games with anti-cheat; see
`docs/anti-cheat.md` in the re-env repo.
