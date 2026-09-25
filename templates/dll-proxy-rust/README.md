# dll-proxy-rust

A proxy `dinput8.dll` in Rust. Most DirectX games load dinput8, and it has a
single export, `DirectInput8Create`, so the proxy needs no assembler stubs:
one function that loads the real DLL from System32 and passes the call on.
`mod_main` runs on its own thread once the DLL is in the process.

## Build

```
cargo build --release
```

`.cargo/config.toml` sets the target to `x86_64-pc-windows-gnu`, the mingw
linker, and a static CRT. The result is
`target/x86_64-pc-windows-gnu/release/dinput8.dll`. `./test.sh` builds into a
temp dir and checks the exports.

## Install

```
./install.sh "/path/to/the/game"
```

Steam launch options: `WINEDLLOVERRIDES="dinput8=n,b" %command%`. `mod.log`
shows up in the game's working directory after launch.

## Your own hooks

`src/lib.rs` only writes a log line. For hooking, add a crate like `retour` or
`minhook-sys` and call it from `mod_main`. Addresses come from Ghidra as RVA
(address minus image base); at runtime add them to
`GetModuleHandleW(null)`. If the game does not load dinput8 at all, use the
`dll-proxy-c` template, which proxies `version.dll`.

Not for games with anti-cheat; see `docs/anti-cheat.md` in the re-env repo.
