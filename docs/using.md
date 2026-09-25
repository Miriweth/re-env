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
- "Reverse the inventory structure of <game> and write it up in notes."
- "Build a version.dll mod for <game> that hooks the function that applies fall damage."
- "Decompile Assembly-CSharp of <game> and find the save routine."

Claude then does the rounds on its own: finds the game and its app id, checks the
folder for anti-cheat and asks you yes or no before going on if it finds some,
creates `~/re/targets/<game>/`,
works out the engine, opens the binary in Ghidra over MCP or the assemblies with
ILSpy, digs for the values, builds from a template, tests what it built, and
writes everything it learned into `targets/<game>/notes.md`. Bulk work goes to the
local models, so the API is not burned on two hundred functions.

Two things it cannot do without you:

1. Start the game. It will tell you when.
2. Change a value in the game when it is narrowing down an address. "Take some
   damage now", "pick up a coin", "walk east". It watches memory while you play.

And once, after install: start Ghidra, File > Configure > Developer, tick
Ghydra. Without that Claude cannot see into Ghidra.

## What you get back

A folder per game in `~/re/targets/<game>/` with the notes, the Ghidra project
and the mods. A sidehud feed is a small Python program; you run it while the game
runs and the map tile shows up on the phone:

```
cd ~/re/targets/<game>/mods/feed
uv run feed.py
```

Games without any mod support get their minimap the same way: the feed reads
the player position straight out of the game's memory, no mod involved. Claude
finds the position with you at the controller ("walk east", "walk west"), turns
it into an address that survives a restart, and calibrates a map image from two
spots you stand on. A screenshot of the in-game map is enough to start with;
without an image the phone draws a grid.

Panels for the phone (the game's own numbers next to the map) live in the
sidehud repo under `sidehud/static/games/`; Claude can write one there too, it
knows that repo's rules. The feeds themselves stay here in re-env: sidehud only
takes integrations that use a game's own modding API, not memory readers.

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
