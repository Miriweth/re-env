# ~/re

Workspace for taking apart Windows games that run under Proton, and for the
tools and mods that come out of it. Claude Code is the main agent, Ghidra is
reachable over MCP, and local Ollama models take the bulk work. Scripts and
templates live in `~/Projects/re-env`.

## Purpose

Static and dynamic analysis of game binaries, then mods (proxy DLLs, BepInEx
plugins) and Linux side tools that read game memory. Nothing else.

## Layout

`targets/<game>/` holds one game, created with `re-new <game>`:

- `notes.md` collects everything learned: offsets, structs, function names, open questions.
- `ghidra/` is the Ghidra project, `dumps/` holds metadata and memory dumps, `mods/` the mods.

`tools/` has x64dbg, Il2CppDumper, BepInEx and the GhydraMCP bridge.

Start Claude Code from `~/re`. `.mcp.json` lives there; from a subfolder the
Ghidra connection is missing.

## Ghidra via MCP

Ghidra has to be running with the Ghydra plugin enabled; the first CodeBrowser
listens on port 8192.

On a fresh binary, look at strings and imports first, find the entry points,
then name functions and set types. Wide before deep.

Write every finding into `targets/<game>/notes.md` right away, with address,
RVA, name and how you know. Nothing stays only in the chat. Renames in Ghidra
are the source of truth; `notes.md` points at them.

## Local models

`ask-local [qwen|deepseek|llama] "prompt" < file` sends text to Ollama. Use it
for bulk work: first-pass comments on 200 functions, decompiler output into
pseudocode, sorting strings. Check the results, these models guess.

`deepseek` has no tool calling. It works with `ask-local` only, never as the
agent. `claude-local [qwen|llama]` runs Claude Code offline against Ollama.

Run `llm-off` before starting a game. The game and the model share the VRAM.

## Mod loop

1. `re-new <game> <template> [name]` copies a template to `targets/<game>/mods/<name>`.
   Templates: `dll-proxy-c`, `dll-proxy-rust`, `bepinex-plugin`, `memreader-py`.
2. Build as described in the template's README.
3. `./install.sh <game directory>` copies the mod into the game and prints the
   Steam launch option.
4. Set the launch option in Steam and start the game. If it fails, add
   `PROTON_LOG=1 %command%` and read `~/steam-<appid>.log`.
5. For reading memory from Linux, `memreader-py` reads the Proton process through
   procfs. Get the PID with `game-pid <Game.exe>`.

## Rules

Only games you own, only single player or offline. No debugger, injection or
memory access on games with anti-cheat (EasyAntiCheat, BattlEye, Vanguard,
Ricochet); that gets accounts banned. How to spot them:
`~/Projects/re-env/docs/anti-cheat.md`. No network protocol work for online
advantages.
