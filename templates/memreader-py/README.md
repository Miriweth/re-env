# memreader-py

Reads the memory of a Proton game from the Linux side through `/proc/<pid>/mem`
and can feed what it reads to sidehud. No Windows code and no injection; the
Wine process is an ordinary Linux process.

## Requirement

`kernel.yama.ptrace_scope` must be `0`, otherwise a process may not read other
processes of the same user. `re-env` sets it in `setup.sh system`
(`/etc/sysctl.d/10-ptrace.conf`). Check with `sysctl kernel.yama.ptrace_scope`.

## Use

```
uv run main.py Game.exe Game.exe 0x1A2B3C0 0x10 0x48
```

Arguments: the game's exe name (basename of argv[0], case does not matter), a
module name, then a pointer chain. Every offset except the last is read as a
u64 pointer; the last one is added. The output is the final address and the
u32, u64 and f32 stored there.

As a library:

```python
from memreader import Process, find_pid

with Process(find_pid("Game.exe")) as p:
    base = p.base("UnityPlayer.dll")            # module base from /proc/<pid>/maps
    hits = p.scan("48 8B ?? 05 ?? ?? ?? ??", module="Game.exe")
    hp = p.read_f32(p.follow(base, [0x1A2B3C0, 0x10, 0x48]))
```

## sidehud feed

`feed.py` reads the player position and a few stats ten times a second and
sends them to sidehud's map port as described in sidehud's `docs/plugin-spec.md`.
Fill in `CONFIG` at the top: the exe name, the module, the pointer chains for
x, y and heading, the stats you want, and a map definition or `None` for a grid.

```
uv run feed.py --fake      # a marker circles on the phone, no game needed
uv run feed.py             # the real thing, game must be running
```

If sidehud shows the map tile with the fake marker, the pipeline works and only
the offsets are left. `memreader/sidehud.py` has `build_packet` and `Sender`
for your own scripts.

## Notes

The module name is the file name as it appears in `/proc/<pid>/maps`
(`Game.exe`, `UnityPlayer.dll`, `GameAssembly.dll`). Wine maps PE files
directly, so they show up there with their path.

`find_pid` only compares argv[0]. `pgrep -f Game.exe` would also match
steam.sh, reaper and proton, which carry the path as an argument.

Offsets come from Ghidra (RVA = address minus image base) or from a pattern
scan. Addresses change with every game update, patterns less often.

Tests: `uv run pytest -q`.
