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
folder for anti-cheat and stops if there is any, creates `~/re/targets/<game>/`,
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

Panels for the phone (the game's own numbers next to the map) live in the
sidehud repo under `sidehud/static/games/`; Claude can write one there too, it
knows that repo's rules. The feeds themselves stay here in re-env: sidehud only
takes integrations that use a game's own modding API, not memory readers.

## Offline

`claude-local` instead of `claude` runs the same thing against the local models.
Slower and less sharp, fine for a Sunday without internet.

## When something is off

`re-check` tells you which part of the setup is unhappy and which command fixes
it. `docs/workflow.md` has the long version of everything above.
