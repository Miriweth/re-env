"""Read the player position and a few stats from a running game and feed them to sidehud.

    uv run feed.py                 # the game named in CONFIG must be running
    uv run feed.py --fake          # no game: one marker moving in a circle
    uv run feed.py --seconds 5     # stop after 5 seconds

Fill in CONFIG. Every chain is a list of offsets: all but the last are read as
u64 pointers, the last is added. `module` is a file name from /proc/<pid>/maps
(the exe or a DLL); None means the chain starts at address 0, i.e. it is absolute.
"""
from __future__ import annotations

import argparse
import math
import sys
import time

from memreader import Process, Sender, build_packet, find_pid

CONFIG = {
    "exe": "Game.exe",              # argv[0] basename of the game process
    "game": None,                   # panel id (sidehud/static/games/<id>.js) or None
    "map": None,                    # None = grid, or {"id":..,"name":..,"image":..,"origin_px":[..],"px_per_unit":[..]}
    "player": {
        "module": "Game.exe",
        "x": [0x0, 0x0],            # replace: chain to the player's x
        "y": [0x0, 0x4],
        "heading": None,            # chain to a heading in degrees, or None
        "type": "f32",              # f64 for Unreal Engine 5 (positions are doubles)
        "label": "me",
    },
    "stats": {                      # name -> {"module":..,"chain":[..],"type":..}
        # "hp": {"module": "Game.exe", "chain": [0x0, 0x10], "type": "u32"},
    },
    "rate": 10,                     # packets per second
}

READERS = {"f32": "read_f32", "f64": "read_f64", "u32": "read_u32", "u64": "read_u64"}


def read_value(proc: Process, base: int, chain: list[int], type: str = "f32"):
    if type not in READERS:
        raise ValueError(f"unknown type {type!r}, use one of {', '.join(READERS)}")
    return getattr(proc, READERS[type])(proc.follow(base, chain))


def _base(proc: Process, module: str | None) -> int:
    return proc.base(module) if module else 0


def read_state(proc: Process, config: dict) -> tuple[list[dict], dict]:
    pl = config["player"]
    base = _base(proc, pl.get("module"))
    t = pl.get("type", "f32")
    player = {"id": "player", "kind": "player",
              "x": read_value(proc, base, pl["x"], t), "y": read_value(proc, base, pl["y"], t)}
    if pl.get("heading"):
        player["heading"] = read_value(proc, base, pl["heading"], t)
    if pl.get("label"):
        player["label"] = pl["label"]
    stats = {}
    for name, spec in (config.get("stats") or {}).items():
        stats[name] = read_value(proc, _base(proc, spec.get("module")), spec["chain"], spec.get("type", "f32"))
    return [player], stats


def fake_state(t: float) -> tuple[list[dict], dict]:
    return ([{"id": "player", "kind": "player", "x": 100 * math.cos(t / 5), "y": 100 * math.sin(t / 5),
              "heading": (t * 36) % 360, "label": "fake"}],
            {"hp": round(50 + 50 * math.sin(t / 3)), "t": round(t, 1)})


def run(sender: Sender, state, config: dict, source: str, seconds: float | None = None) -> int:
    interval = 1 / config.get("rate", 10)
    t0 = time.monotonic()
    sent = 0
    while seconds is None or time.monotonic() - t0 < seconds:
        entities, stats = state(time.monotonic() - t0)
        sender.send(build_packet(game=config.get("game"), source=source, map=config.get("map"),
                                 entities=entities, stats=stats))
        sent += 1
        time.sleep(interval)
    return sent


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fake", action="store_true", help="send a moving marker instead of reading a game")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--seconds", type=float, default=None, help="stop after this many seconds")
    args = ap.parse_args(argv[1:])

    with Sender(args.host, args.port) as sender:
        if args.fake:
            run(sender, fake_state, CONFIG, "memreader-fake", args.seconds)
            return 0
        try:
            pid = find_pid(CONFIG["exe"])
        except LookupError as e:
            print(f"error: {e}. Start the game first, or use --fake.", file=sys.stderr)
            return 1
        with Process(pid) as proc:
            print(f"feeding {CONFIG['exe']} (pid {pid}) to {args.host}:{args.port}, ctrl-c to stop")
            try:
                run(sender, lambda t: read_state(proc, CONFIG), CONFIG, "memreader", args.seconds)
            except OSError as e:
                print(f"error: lost the process: {e}", file=sys.stderr)
                return 1
            except KeyboardInterrupt:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
