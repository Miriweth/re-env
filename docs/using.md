# Using it

You do not run most of this by hand. You start Claude Code in the workspace and
say what you want:

```
cd ~/re
claude
```

Things you can ask for, in your own words:

- "Make a sidehud feed for Stardew Valley: player position on the map, money and energy in the panel."
- "Find out where Hollow Knight keeps the player's health and geo."
- "Reverse the inventory structure of <game> and write it up in the modlog."
- "Build a version.dll mod for <game> that hooks the function that applies fall damage."
- "Decompile Assembly-CSharp of <game> and find the save routine."

Claude then does the rounds on its own: finds the game and its app id, creates
`~/re/targets/<game>/`,
works out the engine, opens the binary in Ghidra over MCP or the assemblies with
ILSpy, digs for the values, builds from a template, tests what it built, and
writes the recon result into `MODDING_PLAN.md`, the facts and a one-line journal into `MODLOG.md` and open problems into `issues.md`, all in `targets/<game>/`. Bulk work goes to the
local models, so the API is not burned on two hundred functions.

Two things it cannot do without you:

1. Start the game. It will tell you when (in the station, as lines starting with `FRAGE:`).
2. Act in the game when it is narrowing down an address: stand still, move,
   take damage, read a number off the HUD. `find_offset.py` in the feed folder
   does the scanning and only asks you to press Enter at the right moments; you
   can run it yourself without Claude.

And once, after install: start Ghidra, File > Configure > Developer, tick
Ghydra. Without that Claude cannot see into Ghidra.

## What you get back

A folder per game in `~/re/targets/<game>/` with `MODDING_PLAN.md`, `MODLOG.md`,
`issues.md`, the Ghidra project and the mods. A sidehud feed is a small Python program; you run it while the game
runs and the map tile shows up on the phone:

```
cd ~/re/targets/<game>/mods/feed
uv run feed.py
```

Games without any mod support get their minimap the same way: the feed reads
the player position straight out of the game's memory, no mod involved.
`uv run find_offset.py position` finds it with you at the controller (stand
still, move, stand still), `uv run find_offset.py value 45` finds a stat you can
read on the HUD, and the map image is calibrated from two spots you stand on. A screenshot of the in-game map is enough to start with;
without an image the phone draws a grid.

Panels for the phone (the game's own numbers next to the map) live in the
sidehud repo under `sidehud/static/games/`; Claude can write one there too, it
knows that repo's rules. A finished feed can move over as well, into
`games/<game>/` next to the Stardew integration; sidehud's spec allows senders
that read game memory.

## The command station

`re-dash` prints `re-dash on http://127.0.0.1:8780/#<token>`; open exactly that
URL, the token is in the fragment. Pick a game, type a request, choose a backend
(`auto` lets Claude route, or `claude`, `claude-local:qwen|llama`,
`ask-local:qwen|qwen3|llama`) and press Send. Recon, Mod and Field note fill
canned prompts. The settings panel sets `bulk_model`, `offline` and
`default_backend`, stored in `~/re/station.json`. Runs are
`claude -p --permission-mode bypassPermissions` in `~/re` with
`ECC_GATEGUARD=off`; one run per game, Cancel and New conversation are buttons.
When Claude needs you it ends with `FRAGE:` lines and waits.

## Offline, or when a step does not go through

`claude-local` instead of `claude` runs the same session against the local
models. Slower and less sharp, fine for a Sunday without internet, and the way
to finish a step that did not go through the API, whether that was quota,
network, or Claude Code declining it. `ask-local` takes single pieces: one
function to explain, one struct to name, one crash log to read. Hand the local
models small, self-contained jobs; they do badly with a whole binary and well
with one function.

## When something is off

`re-check` tells you which part of the setup is unhappy and which command fixes
it. `docs/workflow.md` has the long version of everything above.
