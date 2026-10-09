# re-env

A reverse engineering and modding setup for Windows games running under Proton
on Linux, with Claude Code driving Ghidra and local models for the bulk work.

One script installs Ghidra, rizin and Cutter, x64dbg (inside the game's Proton
prefix), scanmem, Frida, ImHex, the .NET tools for Unity games, Ollama with
three coding models, and the mingw, Rust and .NET toolchains for building mods.
Claude Code gets a Ghidra MCP server and a switch to run offline against the
local models. Four templates cover proxy DLLs in C and Rust, BepInEx plugins,
and reading game memory from Linux.

Built for a CachyOS box with an RTX 4080. Any Arch based system with an NVIDIA
card and 16 GB of VRAM should work the same way.

## Requirements

- Arch Linux or a derivative with the `extra` repo, sudo
- NVIDIA GPU with 16 GB VRAM (one 14B model plus 32K context fits)
- Steam with Proton, `protontricks`
- flatpak (for ImHex)

## Install

```
git clone https://github.com/Miriweth/re-env ~/Projects/re-env
cd ~/Projects/re-env
./setup.sh pacman
./setup.sh system
./setup.sh user
re-check
```

`pacman` and `system` ask for sudo; `user` runs without root and pulls about
23 GB of models at the end. Everything is idempotent. Afterwards start Ghidra
once and enable the Ghydra extension under File > Configure > Developer.

## What you get

Commands, linked into `~/.local/bin`:

- `re-new <game> [template [name]]` creates `~/re/targets/<game>/` and copies a mod template into it.
- `re-check [--full]` checks the whole chain and names the setup step for anything that fails.
- `re-dash [--port N]` serves a read-only dashboard on `127.0.0.1:8780` with notes, log tails, mods, `ollama ps`, VRAM and the last `re-check`.
- `claude-local [model]` runs Claude Code against Ollama instead of the Anthropic API.
- `ask-local [model] "prompt" < file` sends text to a local model, for bulk work.
- `llm-off` unloads all models from VRAM, for before you start a game.
- `game-pid Game.exe` prints the PID of the running Wine process.
- `x64dbg-in <appid>` starts x64dbg inside the game's Proton prefix.
- `il2cppdumper ...` runs Il2CppDumper on the installed .NET.

Templates in `templates/`: `dll-proxy-c` (version.dll, MinHook),
`dll-proxy-rust` (dinput8.dll), `bepinex-plugin` (Unity Mono), `memreader-py`
(procfs memory reader for overlays and feeds).

Models (uncensored): `qwen` (`qwen2.5-coder-abliterate:14b`) is the default, `llama`
(`llama3.1-8b-abliterated`) for quick jobs, `qwen3` (`qwen3-abliterated:14b`) is
ask-local only (no agent use). Old tags go with
`ollama rm qwen2.5-coder:14b deepseek-coder-v2:16b llama3.1:8b`.

## Docs

- [docs/using.md](docs/using.md): what to ask Claude Code for and what happens then
- [docs/workflow.md](docs/workflow.md): first start, taking a game apart, dynamic analysis, Unity, mods, local models, maintenance
- [docs/anti-cheat.md](docs/anti-cheat.md): which games to leave alone and how to tell
- [docs/ue4ss.md](docs/ue4ss.md): Unreal games
- [docs/design.md](docs/design.md): why things are the way they are

## Tests

```
python3 -m unittest discover -s tests -v
```

The suite runs the scripts against fake binaries and builds each template
with its real toolchain when that toolchain is installed.
