# ~/re

Workspace for taking apart Windows games that run under Proton, and for the
tools and mods that come out of it. Claude Code is the main agent, Ghidra is
reachable over MCP, and local Ollama models take the bulk work. Scripts and
templates live in `~/Projects/re-env`.

If `HANDOVER.md` exists in this folder, read it first; it carries the state of
the last session.

## Purpose

Static and dynamic analysis of game binaries, then mods (proxy DLLs, BepInEx
plugins) and Linux side tools that read game memory. Nothing else.

## Layout

`targets/<game>/` holds one game, created with `re-new <game>`:

- `notes.md` collects everything learned: offsets, structs, function names, open questions.
- `log.md` gets one line per step: `- YYYY-MM-DD HH:MM what — why — model` (model = who did it: Claude, qwen, qwen3, llama).
- `ghidra/` is the Ghidra project, `dumps/` holds metadata and memory dumps, `mods/` the mods.

`tools/` has x64dbg, Il2CppDumper, BepInEx and the GhydraMCP bridge.

`re-dash` serves a read-only view at 127.0.0.1:8780: notes, log tails, mods,
`ollama ps`, VRAM and the last `re-check`.

Start Claude Code from `~/re`. `.mcp.json` lives there; from a subfolder the
Ghidra connection is missing.

## Requests

The user asks in plain words: "make a sidehud feed for X", "find where X keeps
the player's health", "a mod for X that hooks Y". Do the whole job; ask only for
the two things below. Order of work:

1. Find the game: `protontricks -l` for the app id; the install folder is
   `steamapps/common/<Game>` inside one of the Steam library folders listed in
   `~/.steam/steam/steamapps/libraryfolders.vdf` (on this machine that includes
   `/mnt/SSD1/Steam`), the Proton prefix is
   `<library>/steamapps/compatdata/<appid>/pfx`. Then the exe. There is no
   anti-cheat check; folder markers are unreliable and the user decides.
2. `re-new <game>`, then engine: `*_Data/Managed/Assembly-CSharp.dll` is Unity
   Mono (ILSpy, BepInEx), `GameAssembly.dll` is IL2CPP (`il2cppdumper`, then
   Ghidra), `Binaries/Win64/*-Shipping.exe` is Unreal (UE4SS, see
   `docs/ue4ss.md`), anything else is native (Ghidra).
3. Public sources before reversing from scratch. Someone has usually done the
   first pass: the game's thread on unknowncheats.me (and its Unreal Engine
   section for GWorld, GNames and GObjects patterns per engine version), SDK
   dumps on GitHub, Cheat Engine tables on fearlessrevolution.com. Offsets are
   tied to a game version; take them as a starting point, verify with
   `find_offset.py`, and write the source and version into `notes.md`. Claude
   Code cannot open unknowncheats.me itself; ask the user to look and paste.
   For Unreal games the reliable route is an SDK dump: Dumper-7 is a DLL that
   writes the whole SDK with offsets when loaded into the game; the
   `dll-proxy-c` template can load it from `mod_main` with `LoadLibraryA`.
4. Static next. Ghidra over MCP, strings and imports, name what you understand.
   For a value like health or position, look for the code that reads it (damage,
   HUD drawing, movement) and follow the pointer chain back to a static base
   in the module. Ask `ask-local` to pre-sort large batches.
5. Dynamic when static does not settle it. Ask the user to start the game, run
   `llm-off` before that. Then, from the game's `mods/<feed>/` folder,
   `uv run find_offset.py position` for the player position or
   `uv run find_offset.py value <hud value>` for a stat; it drives scanmem and
   only asks the user to stand still, move, or read the HUD. It prints a
   CONFIG snippet at the end. Convert every found address into module + RVA or a pointer
   chain from the module base; absolute addresses die with the next launch.
6. Build from a template with `re-new <game> <template> <name>`. For a sidehud
   feed that is `memreader-py`: fill `CONFIG` in `feed.py` (exe, module, chains,
   type, map, stats), run `uv run feed.py --fake` first to prove the pipeline,
   then `uv run feed.py` with the game, and check `curl -s localhost:8765/api/map`
   shows the packet. For a mod, build, `./install.sh <game dir>`, tell the user
   the launch option, read `mod.log` or `BepInEx/LogOutput.log` after a start.

   A minimap for a game without any mod support is the memory reader's main
   job. The recipe:
   - Position: `uv run find_offset.py position` (float64 for Unreal 5,
     `--type float32` for most other engines) narrows the address down while
     the user alternates standing still and moving; the neighbouring values it
     prints are the other axes. Heading is often a float in radians or degrees
     next to them, or a direction vector. Or find the movement code in Ghidra
     and take the chain from there.
   - Chain: turn the address into module + RVA (static) or a pointer chain from
     a static base (`scanmem`'s pointer scan, or Ghidra: who writes this
     address, where does that pointer come from). Prove it survives a restart.
   - Map image: a screenshot of the in-game map, or an extracted map asset,
     saved to `~/.config/sidehud/maps/<game>.png`. Calibrate with two
     positions the user stands on: solve `origin_px + pos * px_per_unit` for
     scale and origin (y is usually flipped). Write `<game>.toml` next to the
     image with `name`, `image`, `origin_px`, `px_per_unit` and use its id in
     `CONFIG["map"]`. Without an image `map = None` draws a grid, which is
     enough to check the axes.
   - Other markers (enemies, NPCs) are entity arrays: find one, then the
     stride and count, and emit them as `kind: other` with a stable `id`.
7. A sidehud panel goes into `~/Projects/sidehud/sidehud/static/games/<game>.js`,
   following that repo's `AGENTS.md` and `docs/plugin-spec.md`. The spec allows
   senders that read game memory, so a finished feed can move to
   `~/Projects/sidehud/games/<game>/` with its own README, like `games/stardew/`.
8. Append a line to `log.md` after every step. Write `notes.md` as you go, not at the end: what, where (module + RVA or
   chain), how you know. Finish with what works, what is still guessed, and the
   exact commands to run it.

Ask the user only to start the game and to change values on cue. Everything
else, decide and do.

## Ghidra via MCP

Ghidra has to be running with the Ghydra plugin enabled; the first CodeBrowser
listens on port 8192.

On a fresh binary, look at strings and imports first, find the entry points,
then name functions and set types. Wide before deep.

Write every finding into `targets/<game>/notes.md` right away, with address,
RVA, name and how you know. Nothing stays only in the chat. Renames in Ghidra
are the source of truth; `notes.md` points at them.

## Local models

Routing is by task type, and you say which model did what. Bulk work, summaries,
first-pass comments, sorting strings and anything offline go to the local
models through `ask-local`. Planning, reversing with Ghidra, writing code and
anything that needs the whole picture stays with Claude.

`ask-local [qwen|qwen3|llama] "prompt" < file` sends text to Ollama. Use it
for bulk work: first-pass comments on 200 functions, decompiler output into
pseudocode, sorting strings. Check the results, these models guess.

`qwen3` is for `ask-local` only, never as the agent. `claude-local [qwen|llama]` runs Claude Code offline against Ollama.

When a step cannot go through the API (offline, out of quota, or Claude Code
declines it), the user runs that step with `claude-local`, or hands the piece to
`ask-local`. Keep such pieces small and self-contained: one function, one struct,
one crash log. The 14B models are good at that and poor at reasoning about a
whole binary.

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

Only games you own, only single player or offline. Games with anti-cheat can
ban the account for a debugger, an injected DLL or a memory reader; what that
looks like is in `~/Projects/re-env/docs/anti-cheat.md`, the decision is the
user's and nothing checks it automatically. No network protocol work for online
advantages.
