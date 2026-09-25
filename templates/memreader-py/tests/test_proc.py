import builtins
import ctypes
import os
import struct
import subprocess
from pathlib import Path

import pytest

from memreader.proc import Process, Region, find_pid, module_base, parse_maps

MAPS = (
    "7ff000000000-7ff000001000 r--p 00000000 08:01 1 /home/u/.steam/steamapps/common/G/Game.exe\n"
    "7ff000001000-7ff000005000 r-xp 00001000 08:01 1 /home/u/.steam/steamapps/common/G/Game.exe\n"
    "7ff100000000-7ff100002000 r--p 00000000 08:01 2 /home/u/.steam/steamapps/common/G/UnityPlayer.dll\n"
    "7ff200000000-7ff200001000 rw-p 00000000 00:00 0 \n"
)


def test_parse_maps():
    regions = parse_maps(MAPS)
    assert len(regions) == 4
    assert regions[1] == Region(0x7FF000001000, 0x7FF000005000, "r-xp",
                                "/home/u/.steam/steamapps/common/G/Game.exe")
    assert regions[2].path.endswith("UnityPlayer.dll")
    assert regions[3].path == ""


def test_module_base_case_insensitive():
    assert module_base(parse_maps(MAPS), "game.exe") == 0x7FF000000000


def test_module_base_missing():
    with pytest.raises(LookupError):
        module_base(parse_maps(MAPS), "x.dll")


def test_read_own_memory():
    buf = ctypes.create_string_buffer(b"HELLO")
    with Process(os.getpid()) as p:
        assert p.read(ctypes.addressof(buf), 5) == b"HELLO"


def test_read_u32_f32_and_follow():
    second = ctypes.create_string_buffer(struct.pack("<If", 7, 1.5), 8)
    first = ctypes.create_string_buffer(struct.pack("<Q", ctypes.addressof(second)), 8)
    base = ctypes.addressof(first)
    with Process(os.getpid()) as p:
        target = p.follow(base, [0, 0])
        assert target == ctypes.addressof(second)
        assert p.read_u32(target) == 7
        assert p.read_f32(target + 4) == 1.5
        assert p.read_u64(base) == ctypes.addressof(second)


def test_scan_in_own_process():
    needle = ctypes.create_string_buffer(b"\xde\xad\xbe\xef\x42\x42", 6)
    with Process(os.getpid()) as p:
        hits = p.scan("DE AD ?? EF 42 42")
    assert ctypes.addressof(needle) in hits


def test_maps_of_own_process_contain_python():
    with Process(os.getpid()) as p:
        assert any("python" in r.path for r in p.maps())


def test_permission_error_hint(monkeypatch):
    real_open = builtins.open

    def denied(path, *a, **kw):
        if str(path).endswith("/mem"):
            raise PermissionError(13, "Permission denied", str(path))
        return real_open(path, *a, **kw)

    monkeypatch.setattr(builtins, "open", denied)
    with pytest.raises(PermissionError) as excinfo:
        Process(os.getpid())
    msg = str(excinfo.value)
    assert "kernel.yama.ptrace_scope" in msg and "sysctl" in msg


def test_find_pid_missing():
    with pytest.raises(LookupError):
        find_pid("NoSuchGame.exe")


NAME = f"FakeGame{os.getpid()}.exe"


def _spawn():
    p = subprocess.Popen(["bash", "-c", f'exec -a "{NAME}" sleep 30'])
    for _ in range(200):
        try:
            if NAME.encode() in Path(f"/proc/{p.pid}/cmdline").read_bytes():
                return p
        except FileNotFoundError:
            pass
    raise RuntimeError("fake game did not start")


def test_find_pid_one_instance_case_insensitive():
    p = _spawn()
    try:
        assert find_pid(NAME.lower()) == p.pid
    finally:
        p.terminate(); p.wait()


def test_find_pid_two_instances():
    a, b = _spawn(), _spawn()
    try:
        with pytest.raises(RuntimeError) as excinfo:
            find_pid(NAME)
        assert str(a.pid) in str(excinfo.value) and str(b.pid) in str(excinfo.value)
    finally:
        for p in (a, b):
            p.terminate(); p.wait()


def test_find_pid_ignores_processes_that_only_mention_the_name():
    # `bash -c 'sleep 30 # FakeGame.exe'` carries the name in an argument, not argv[0]
    p = subprocess.Popen(["bash", "-c", f"sleep 30 # {NAME}"])
    try:
        with pytest.raises(LookupError):
            find_pid(NAME)
    finally:
        p.terminate(); p.wait()
