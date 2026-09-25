import ctypes.util
import os
import subprocess
import sys
import time

import pytest

from memreader.scanner import Match, Scanner, parse_list

CHILD = r"""
import ctypes, sys, struct
buf = ctypes.create_string_buffer(struct.pack("<d", 1000.0), 8)
sys.stdout.write("%d\n" % ctypes.addressof(buf)); sys.stdout.flush()
for line in sys.stdin:
    v = struct.unpack("<d", buf.raw)[0]
    cmd = line.strip()
    if cmd == "inc": v += 7.5
    elif cmd == "dec": v -= 2.25
    elif cmd == "quit": break
    ctypes.memmove(buf, struct.pack("<d", v), 8)
    sys.stdout.write("ok\n"); sys.stdout.flush()
"""

needs_scanner = pytest.mark.skipif(
    not ctypes.util.find_library("scanmem") or open("/proc/sys/kernel/yama/ptrace_scope").read().strip() != "0",
    reason="libscanmem or ptrace_scope 0 missing")


def test_parse_list():
    text = ("[ 0] 7ffd12345678,  3 +      2f8, stack, 1000.0, [F64 F32 I64 I32 I16 I8 ]\n"
            "[ 1]     55aa0000, 12 +       10, heap, 1007.5, [F64 ]\n"
            "info: something else\n")
    assert parse_list(text) == [Match(0x7FFD12345678, "stack", "1000.0"), Match(0x55AA0000, "heap", "1007.5")]


@needs_scanner
def test_scanner_narrows_a_changing_double_to_its_address():
    child = subprocess.Popen([sys.executable, "-c", CHILD], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        addr = int(child.stdout.readline())

        def tell(cmd):
            child.stdin.write(cmd + "\n"); child.stdin.flush(); child.stdout.readline()

        with Scanner(child.pid) as sc:
            sc.set_type("float64")
            sc.snapshot()
            first = sc.matches
            assert first > 1000
            sc.narrow("=")                 # standing still: unchanged
            tell("inc"); sc.narrow("!=")   # moved: changed
            tell("same"); sc.narrow("=")
            tell("dec"); sc.narrow("!=")
            tell("inc"); sc.narrow(">")    # went up
            assert 1 <= sc.matches < first
            found = sc.list()
        assert addr in [m.addr for m in found]
        hit = [m for m in found if m.addr == addr][0]
        assert abs(float(hit.value) - (1000.0 + 7.5 - 2.25 + 7.5)) < 1e-6
    finally:
        child.stdin.write("quit\n"); child.stdin.flush(); child.wait(timeout=5)
