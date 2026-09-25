import ctypes
import os
import struct

import pytest

from memreader.proc import Process
from feed import read_state, read_value


def buf(fmt, *vals):
    raw = struct.pack(fmt, *vals)
    return ctypes.create_string_buffer(raw, len(raw))


def test_read_value_types_and_chain():
    target = buf("<fIQ", 1.5, 7, 99)
    ptr = buf("<Q", ctypes.addressof(target))
    with Process(os.getpid()) as p:
        assert read_value(p, 0, [ctypes.addressof(target)], "f32") == 1.5
        assert read_value(p, 0, [ctypes.addressof(target) + 4], "u32") == 7
        assert read_value(p, 0, [ctypes.addressof(target) + 8], "u64") == 99
        # one dereference: ptr -> target, then +4
        assert read_value(p, ctypes.addressof(ptr), [0, 4], "u32") == 7


def test_read_value_rejects_unknown_type():
    with Process(os.getpid()) as p, pytest.raises(ValueError):
        read_value(p, 0, [0x10], "f16")


def test_read_state_builds_entities_and_stats():
    pos = buf("<fff", 10.0, -20.0, 90.0)
    hp = buf("<I", 55)
    a = ctypes.addressof(pos)
    config = {
        "game": "demo", "map": None,
        "player": {"module": None, "x": [a], "y": [a + 4], "heading": [a + 8], "type": "f32", "label": "me"},
        "stats": {"hp": {"module": None, "chain": [ctypes.addressof(hp)], "type": "u32"}},
    }
    with Process(os.getpid()) as p:
        entities, stats = read_state(p, config)
    assert entities == [{"id": "player", "kind": "player", "x": 10.0, "y": -20.0, "heading": 90.0, "label": "me"}]
    assert stats == {"hp": 55}


def test_read_value_f64_for_ue5_positions():
    target = buf("<ddd", 1234.5, -9876.25, 42.0)   # an FVector of doubles
    a = ctypes.addressof(target)
    with Process(os.getpid()) as p:
        assert read_value(p, 0, [a], "f64") == 1234.5
        assert read_value(p, 0, [a + 8], "f64") == -9876.25
        assert p.read_f64(a + 16) == 42.0
