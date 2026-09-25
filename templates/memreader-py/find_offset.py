"""Find the memory address of a value while you play, then print it as a CONFIG chain.

    uv run find_offset.py position              # unknown float64 (Unreal 5) that changes when you move
    uv run find_offset.py position --type float32
    uv run find_offset.py value 45              # a float32 you can read on the HUD, e.g. oxygen
    uv run find_offset.py value 45 --type int32

Both modes talk to scanmem through libscanmem and only ask you to act in the
game and press Enter. Addresses on the heap change with every game start; put
them into CONFIG as absolute chains ("module": None) and rescan per session,
or use them as the starting point for a stable pointer chain.
"""
from __future__ import annotations

import argparse
import struct
import sys

from memreader import Process, find_pid
from memreader.scanner import Scanner
from feed import CONFIG

SIZE = {"float64": 8, "float32": 4, "int64": 8, "int32": 4, "int16": 2, "int8": 1}
FMT = {"float64": "<d", "float32": "<f", "int64": "<q", "int32": "<i", "int16": "<h", "int8": "<b"}
FEED_TYPE = {"float64": "f64", "float32": "f32", "int32": "u32", "int64": "u64"}


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip().lower()
    except EOFError:
        return "q"


def show(sc: Scanner, proc: Process, scan_type: str) -> None:
    size, fmt = SIZE[scan_type], FMT[scan_type]
    maps = proc.maps()
    print(f"\n{sc.matches} match(es):")
    for m in sc.list()[:20]:
        neigh = []
        for k in (-1, 0, 1, 2):
            try:
                neigh.append(f"{struct.unpack(fmt, proc.read(m.addr + k * size, size))[0]:g}")
            except OSError:
                neigh.append("?")
        where = ""
        for r in maps:
            if r.start <= m.addr < r.end and r.path and not r.path.startswith("["):
                where = f"  {r.path.rsplit('/', 1)[-1]}+0x{m.addr - proc.base(r.path.rsplit('/', 1)[-1]):x}"
                break
        print(f"  0x{m.addr:x}  {m.region:6s}  value {m.value:>12s}   around: {' '.join(neigh)}{where}")
    if sc.matches:
        first = sc.list()[0].addr
        t = FEED_TYPE.get(scan_type, "f32")
        print("\nCONFIG snippet (absolute, valid until the game restarts):")
        print(f'  "x": [0x{first:x}], "y": [0x{first + size:x}], "type": "{t}", "module": None')


def position(sc: Scanner, proc: Process, scan_type: str) -> None:
    sc.set_type(scan_type)
    ask("Stand still in the game, then press Enter to take the snapshot... ")
    sc.snapshot()
    print(f"{sc.matches} candidates. Keep standing still.")
    ask("Still standing? Enter... ")
    sc.narrow("=")
    while True:
        print(f"{sc.matches} candidates left.")
        if sc.matches <= 20:
            break
        a = ask("Move a bit in one direction, then Enter (or l = list, q = quit)... ")
        if a == "q":
            return
        if a == "l":
            show(sc, proc, scan_type); continue
        sc.narrow("!=")
        print(f"{sc.matches} candidates left.")
        a = ask("Stop, stand still, then Enter... ")
        if a == "q":
            return
        sc.narrow("=")
    show(sc, proc, scan_type)


def value(sc: Scanner, proc: Process, scan_type: str, first: str) -> None:
    sc.set_type(scan_type)
    sc.narrow(first)
    while True:
        print(f"{sc.matches} candidates left.")
        if sc.matches <= 20:
            break
        a = ask("Let the value change in the game, then type what the HUD shows now (Enter = just 'changed', q = quit): ")
        if a == "q":
            return
        sc.narrow(a if a else "!=")
    show(sc, proc, scan_type)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["position", "value"])
    ap.add_argument("first", nargs="?", help="value mode: the value shown in the game right now")
    ap.add_argument("--exe", default=CONFIG["exe"], help="game process name (argv[0] basename)")
    ap.add_argument("--type", default=None, help="scanmem type: float64 (default for position), float32 (default for value), int32 ...")
    args = ap.parse_args(argv[1:])
    scan_type = args.type or ("float64" if args.mode == "position" else "float32")
    if scan_type not in SIZE:
        ap.error(f"unknown type {scan_type}, use one of {', '.join(SIZE)}")
    if args.mode == "value" and args.first is None:
        ap.error("value mode needs the current value, e.g. `value 45`")
    try:
        pid = find_pid(args.exe)
    except LookupError as e:
        print(f"error: {e}. Start the game first.", file=sys.stderr)
        return 1
    print(f"scanning {args.exe} (pid {pid}) as {scan_type}")
    with Process(pid) as proc, Scanner(pid) as sc:
        if args.mode == "position":
            position(sc, proc, scan_type)
        else:
            value(sc, proc, scan_type, args.first)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
