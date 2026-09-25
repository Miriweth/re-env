# Working with re-env

How the pieces fit, from a fresh install to a working mod. Commands assume the
repo is in `~/Projects/re-env` and the workspace in `~/re`.

## First start

Run the three setup phases once:

```
cd ~/Projects/re-env
./setup.sh pacman     # packages, asks for sudo
./setup.sh system     # ollama drop-in, ptrace sysctl, ollama service, asks for sudo
./setup.sh user       # downloads, tools, ~/re, models (about 23 GB)
```

Every step is safe to repeat. `./setup.sh user:downloads` or `user:models` reruns
a single step.

One thing the script cannot do for you: start Ghidra once, open any CodeBrowser,
go to File > Configure > Developer and tick Ghydra. The console (the monitor
icon bottom right) should then say that GhydraMCP is listening on port 8192.

Then run `re-check`. Every line should be PASS. `mcp` says WARN while Ghidra is
not running, that is fine. A FAIL line names the setup step that fixes it.

## New game

Find the game and its app id:

```
protontricks -l
```

The game folder is `steamapps/common/<Game>` in whichever Steam library holds
it; `~/.steam/steam/steamapps/libraryfolders.vdf` lists the libraries (a second
SSD is common). The Proton prefix sits next to it in
`steamapps/compatdata/<appid>/pfx`. Games with anti-cheat are your call;
`anti-cheat.md` says what to look for, nothing checks it for you.

Create the target:

```
re-new <game>
```

This makes `~/re/targets/<game>/` with `notes.md`, `ghidra/`, `dumps/` and
`mods/`. Write into `notes.md` from the first minute: which exe, which engine,
which version. Everything you find later goes there too. Findings that only
exist in a chat window are gone by tomorrow.

## Static analysis

Start Ghidra, create a project in `~/re/targets/<game>/ghidra/`, import the
exe (and the DLLs you care about, `UnityPlayer.dll`, `GameAssembly.dll`) and
let the auto analysis run. For a big game that takes a while.

Then, in a second terminal:

```
cd ~/re
claude
```

Claude Code picks up `.mcp.json` from `~/re` and talks to Ghidra through the
Ghydra bridge. It can list functions, strings and imports, decompile, rename,
add comments and follow cross references. The first time it asks whether to
trust the project's MCP server.

A way through an unknown binary that has worked for me:

1. Strings first. Error messages, file names, format strings and debug output
   tell you what a function does before you read a single instruction. Ask for
   the strings, pick the interesting ones, follow their references.
2. Imports next. `CreateFileW`, `ReadFile`, `socket`, `D3D11CreateDevice`:
   the imports show which parts of the program do I/O, rendering, networking.
3. Find the loop. Games have a main loop; everything you care about hangs off
   it. Start from the entry point or from a render or input import and walk up.
4. Name as you go. Every function you understand gets a name in Ghidra, every
   struct you recognize gets a type. Ghidra is the source of truth; `notes.md`
   holds the address, the RVA (address minus image base) and how you know.
5. Let the local model do the boring part. Decompiler output of two hundred
   functions is a job for `ask-local`, not for you and not for the Claude API:

   ```
   ask-local qwen "Summarize what each function does in one line" < dump.txt
   ```

   Check the result before you trust it.

RVAs survive a restart, absolute addresses do not (ASLR). Write down RVAs.

## Dynamic analysis

Run `llm-off` first. A loaded 14B model holds 12 GB of the 16 GB VRAM and the
game will not appreciate that.

Start the game from Steam, then:

```
game-pid Game.exe          # the PID of the Wine process
scanmem <pid>              # search for values by hand, narrow down, find the address
x64dbg-in <appid>          # x64dbg inside the game's prefix; File > Attach
```

The feed template automates the scanmem part. From `targets/<game>/mods/<feed>/`:

```
uv run find_offset.py position          # player position: stand still, move, stand still
uv run find_offset.py value 45          # a stat you can read on the HUD
```

It talks to scanmem through libscanmem, asks you to press Enter at the right
moments, and prints the surviving addresses with their neighbours and a CONFIG
snippet for `feed.py`. Heap addresses change per game start; rescan or turn
them into a pointer chain.

x64dbg runs in the same Proton prefix as the game, which is why it can see it.
Attaching works for most games, not all; when it does not, `winedbg` inside
the prefix is the fallback.

Cheat Engine is not installed by the setup because its installer bundles
offers. If you want it, get the installer from cheatengine.org, decline the
extras, and run it in the game's prefix:

```
protontricks-launch --appid <appid> ~/re/tools/CheatEngine.exe
```

Frida attaches to the Wine process as a Linux process. `Memory.scan` and
`Interceptor.attach` on an address work, `Process.enumerateModules` only shows
the Linux side. Use it for tracing once you already know the addresses.

When a game refuses to start with a mod or an override, add
`PROTON_LOG=1 %command%` to the launch options. The log lands in
`~/steam-<appid>.log`.

## Unity games

Look into `<Game>_Data/`. A `Managed/` folder with `Assembly-CSharp.dll` means
Mono: the game logic is C# bytecode and decompiles to readable source.

```
ilspycmd -p -o ~/re/targets/<game>/dumps/src "<Game>_Data/Managed/Assembly-CSharp.dll"
```

No `Managed/`, but a `GameAssembly.dll` next to the exe, means IL2CPP: the C#
was compiled to native code. The names survive in the metadata:

```
il2cppdumper GameAssembly.dll "<Game>_Data/il2cpp_data/Metadata/global-metadata.dat" ~/re/targets/<game>/dumps/il2cpp
```

The output has `dump.cs` (every class and method with its RVA), `script.json`
and `il2cpp.h`. The release also ships Ghidra scripts that import those names
and types into a `GameAssembly.dll` project, which turns a wall of `FUN_1800`
into method names.

## Mods

Three ways in, one template each:

- `dll-proxy-c`: a `version.dll` proxy with MinHook. Works for almost any
  native game. Launch option `WINEDLLOVERRIDES="version=n,b" %command%`.
- `dll-proxy-rust`: a `dinput8.dll` proxy in Rust. One export, no assembler.
  Launch option `WINEDLLOVERRIDES="dinput8=n,b" %command%`.
- `bepinex-plugin`: a BepInEx 5 plugin for Mono Unity games, patching with
  Harmony. Launch option `WINEDLLOVERRIDES="winhttp=n,b" %command%`.

And one for reading instead of injecting: `memreader-py` reads the game's
memory from Linux through procfs and its `feed.py` sends positions and stats to
sidehud ten times a second. `uv run feed.py --fake` puts a moving marker on the
phone without a game, which proves the pipeline before you hunt for offsets.

The loop is the same for all of them:

```
re-new <game> dll-proxy-c hud     # copies the template to targets/<game>/mods/hud
cd ~/re/targets/<game>/mods/hud
# build, see the template's README
./install.sh "<library>/steamapps/common/<Game>"
```

`install.sh` prints the launch option. Set it in Steam under Properties, start
the game, read `mod.log` (or `BepInEx/LogOutput.log`) in the game folder.

## Local models

Three models are installed. `qwen2.5-coder:14b` is the default for anything
with code. `llama3.1:8b` is faster and fine for summaries. `deepseek-coder-v2:16b`
is quick for bulk work but cannot do tool calls, so only `ask-local` accepts it.

```
claude-local                 # Claude Code against qwen, offline
claude-local llama -p "..."  # one-shot with llama
ask-local deepseek "Comment this" < func.c
```

`claude-local` sets the Anthropic environment variables to point at Ollama and
starts `claude`. Ollama's Anthropic compatible endpoint has no `tool_choice`,
no prompt caching and no token counting, and the context is 32K. Use it
offline and for bulk work; the API stays the main path.

`llm-off` unloads whatever is in VRAM. Ollama also drops models after ten
minutes idle (`OLLAMA_KEEP_ALIVE=10m`).

## Maintenance

pacman updates Ghidra without asking about your extensions. After that,
`re-check` says WARN on `ghidra` with the two versions. Pick the Ghydra zip
that matches the new Ghidra from the GhydraMCP releases, put its URL and sha256
into `versions.env`, then run `./setup.sh user:downloads`. Ghidra keeps a
settings folder per version, so the old extension does not get in the way.

`./setup.sh system` set `kernel.yama.ptrace_scope` to 0. That means every
process of your user may read the memory of every other process of your user.
scanmem, frida and memreader need it; on a single-user machine used for this
it is an acceptable trade. To undo it, remove `/etc/sysctl.d/10-ptrace.conf`
and run `sysctl --system`.

Models update with `ollama pull <tag>`. Everything else updates with pacman,
`uv tool upgrade`, `dotnet tool update -g` and `rustup update`, and
`./setup.sh user` can be rerun at any time.
