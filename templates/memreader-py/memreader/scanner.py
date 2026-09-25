"""Drive scanmem through libscanmem, so a script can narrow down addresses
while the user acts in the game. Same commands as interactive scanmem:
snapshot, then =, !=, <, > (or a value) to keep only matching addresses.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import re
import tempfile
from dataclasses import dataclass

LIST_LINE = re.compile(r"^\[\s*\d+\]\s+([0-9a-fA-F]+),\s*\d+\s*\+\s*[0-9a-fA-F]+,\s*(\w+),\s*([^,]+),")


@dataclass(frozen=True)
class Match:
    addr: int
    region: str
    value: str


def parse_list(text: str) -> list[Match]:
    out = []
    for line in text.splitlines():
        m = LIST_LINE.match(line)
        if m:
            out.append(Match(int(m.group(1), 16), m.group(2), m.group(3).strip()))
    return out


class ScanError(RuntimeError):
    pass


class Scanner:
    def __init__(self, pid: int):
        name = ctypes.util.find_library("scanmem") or "libscanmem.so"
        self._lib = ctypes.CDLL(name)
        self._libc = ctypes.CDLL(None)
        self._lib.sm_init.restype = ctypes.c_bool
        self._lib.sm_get_num_matches.restype = ctypes.c_ulong
        self._lib.sm_backend_exec_cmd.argtypes = [ctypes.c_char_p]
        if not self._lib.sm_init():
            raise ScanError("sm_init failed")
        self._lib.sm_set_backend()
        self.pid = pid
        self.exec(f"pid {pid}")
        self.exec("option region_scan_level 2")   # every readable+writable region, Wine heaps included

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self._lib.sm_cleanup()

    def _capture(self, fd: int, cmd: str) -> str:
        """Run cmd with C-level fd redirected into a temp file, return what was written."""
        with tempfile.TemporaryFile("w+b") as tmp:
            saved = os.dup(fd)
            try:
                self._libc.fflush(None)
                os.dup2(tmp.fileno(), fd)
                self._lib.sm_backend_exec_cmd(cmd.encode())
                self._libc.fflush(None)
            finally:
                os.dup2(saved, fd)
                os.close(saved)
            tmp.seek(0)
            return tmp.read().decode(errors="replace")

    def exec(self, cmd: str) -> None:
        msgs = self._capture(2, cmd)
        for line in msgs.splitlines():
            if line.startswith("error:"):
                raise ScanError(line)

    def set_type(self, scan_type: str) -> None:
        """float64, float32, int32, int64, ... (scanmem's scan_data_type names)."""
        self.exec(f"option scan_data_type {scan_type}")

    def snapshot(self) -> None:
        self.exec("snapshot")

    def narrow(self, op: str) -> None:
        """'=' unchanged, '!=' changed, '>' increased, '<' decreased, or a number."""
        self.exec(op)

    def reset(self) -> None:
        self.exec("reset")

    @property
    def matches(self) -> int:
        return int(self._lib.sm_get_num_matches())

    def list(self) -> list[Match]:
        return parse_list(self._capture(1, "list"))
