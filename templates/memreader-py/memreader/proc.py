"""procfs access to another process: maps, module bases, reads, pointer chains, scans."""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass

from .scan import find_all, parse_pattern

PTRACE_HINT = (
    "cannot open /proc/{pid}/mem: Permission denied. Reading another process needs "
    "kernel.yama.ptrace_scope = 0 (sysctl -w kernel.yama.ptrace_scope=0, "
    "or /etc/sysctl.d/10-ptrace.conf via re-env setup.sh system)."
)


@dataclass(frozen=True)
class Region:
    start: int
    end: int
    perms: str
    path: str


def parse_maps(text: str) -> list[Region]:
    regions = []
    for line in text.splitlines():
        parts = line.split(maxsplit=5)
        if len(parts) < 5:
            continue
        lo, hi = parts[0].split("-")
        regions.append(Region(int(lo, 16), int(hi, 16), parts[1], parts[5] if len(parts) > 5 else ""))
    return regions


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def module_base(regions: list[Region], module: str) -> int:
    starts = [r.start for r in regions if _basename(r.path).lower() == module.lower()]
    if not starts:
        raise LookupError(f"module not mapped: {module}")
    return min(starts)


def find_pid(exe_name: str) -> int:
    """PID of the process whose argv[0] basename is exe_name (case-insensitive).

    argv[0] only: for a Proton game, steam.sh, reaper and proton all carry the
    exe path in their arguments but are not the game.
    """
    want = exe_name.lower()
    me = os.getpid()
    hits = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) == me:
            continue
        try:
            argv0 = open(f"/proc/{entry}/cmdline", "rb").read().split(b"\0", 1)[0]
        except OSError:
            continue
        if _basename(argv0.decode(errors="replace").strip('"')).lower() == want:
            hits.append(int(entry))
    if not hits:
        raise LookupError(f"no process for {exe_name}")
    if len(hits) > 1:
        raise RuntimeError(f"several processes for {exe_name}: {' '.join(map(str, hits))}")
    return hits[0]


class Process:
    def __init__(self, pid: int):
        self.pid = pid
        try:
            self._mem = open(f"/proc/{pid}/mem", "rb", buffering=0)
        except PermissionError as e:
            raise PermissionError(PTRACE_HINT.format(pid=pid)) from e

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self._mem.close()

    def maps(self) -> list[Region]:
        with open(f"/proc/{self.pid}/maps") as f:
            return parse_maps(f.read())

    def base(self, module: str) -> int:
        return module_base(self.maps(), module)

    def read(self, addr: int, size: int) -> bytes:
        return os.pread(self._mem.fileno(), size, addr)

    def read_u32(self, addr: int) -> int:
        return struct.unpack("<I", self.read(addr, 4))[0]

    def read_u64(self, addr: int) -> int:
        return struct.unpack("<Q", self.read(addr, 8))[0]

    def read_f32(self, addr: int) -> float:
        return struct.unpack("<f", self.read(addr, 4))[0]

    def follow(self, base: int, offsets: list[int]) -> int:
        addr = base
        for off in offsets[:-1]:
            addr = self.read_u64(addr + off)
        return addr + offsets[-1]

    def scan(self, pattern: str, module: str | None = None) -> list[int]:
        pat = parse_pattern(pattern)
        regions = self.maps()
        if module is not None:
            regions = [r for r in regions if _basename(r.path).lower() == module.lower()]
        hits = []
        for r in regions:
            if "r" not in r.perms or r.path in ("[vvar]", "[vsyscall]"):
                continue
            try:
                data = self.read(r.start, r.end - r.start)
            except OSError:
                continue
            hits.extend(r.start + i for i in find_all(data, pat))
        return hits
