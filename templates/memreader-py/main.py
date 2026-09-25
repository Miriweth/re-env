"""Usage: uv run main.py EXE MODULE OFFSET [OFFSET...]

Finds the process by exe name, takes MODULE's base and follows the pointer
chain OFFSET... (all but the last are dereferenced as u64), then prints what
is at the final address.
"""
import sys

from memreader import Process, find_pid


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    exe, module, *offs = argv[1:]
    offsets = [int(o, 0) for o in offs]
    with Process(find_pid(exe)) as p:
        addr = p.follow(p.base(module), offsets)
        print(f"addr=0x{addr:x}")
        print(f"u32={p.read_u32(addr)}")
        print(f"u64={p.read_u64(addr)}")
        print(f"f32={p.read_f32(addr)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
