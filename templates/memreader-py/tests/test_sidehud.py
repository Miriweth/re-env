import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import jsonschema
import pytest

from memreader.sidehud import Sender, build_packet

SCHEMA = json.loads((Path(__file__).parent / "sidehud_packet.schema.json").read_text())
HERE = Path(__file__).resolve().parents[1]


def validate(packet):
    jsonschema.validate(packet, SCHEMA)


def test_build_packet_full_state_validates():
    p = build_packet(
        game="demo", source="test",
        map={"id": "demo/world", "name": "World", "image": None, "origin_px": [0, 0], "px_per_unit": [1, -1]},
        entities=[{"id": "player", "kind": "player", "x": 1.5, "y": -2.0, "heading": 90, "label": "me"},
                  {"id": "npc:1", "kind": "ally", "x": 3, "y": 4}],
        stats={"hp": 42, "gold": 7},
    )
    validate(p)
    assert p["game"] == "demo" and p["stats"] == {"hp": 42, "gold": 7}
    assert p["entities"][0]["kind"] == "player" and p["entities"][1]["label" if "label" in p["entities"][1] else "id"]


def test_build_packet_drops_none_and_defaults_kind():
    p = build_packet(entities=[{"x": 1, "y": 2, "heading": None, "label": None, "kind": "boss"}])
    validate(p)
    e = p["entities"][0]
    assert "heading" not in e and "label" not in e
    assert e["kind"] == "other"          # unknown kinds are drawn as other, say so explicitly
    assert "game" not in p and "stats" not in p and "map" not in p


def test_build_packet_requires_xy():
    with pytest.raises(ValueError):
        build_packet(entities=[{"x": 1}])


def test_sender_delivers_json_over_udp():
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    rx.settimeout(2)
    port = rx.getsockname()[1]
    with Sender("127.0.0.1", port) as tx:
        n = tx.send(build_packet(source="t", entities=[{"x": 1, "y": 2}]))
    data = rx.recv(65535)
    assert n == len(data)
    assert json.loads(data) == {"source": "t", "entities": [{"id": "player", "kind": "player", "x": 1, "y": 2}]}


def test_sender_refuses_oversized_packet():
    with Sender("127.0.0.1", 1) as tx, pytest.raises(ValueError):
        tx.send(build_packet(stats={"blob": "x" * 9000}))


def test_fake_feed_sends_valid_packets_at_rate():
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    rx.settimeout(5)
    port = rx.getsockname()[1]
    proc = subprocess.run([sys.executable, str(HERE / "feed.py"), "--fake", "--port", str(port), "--seconds", "0.55"],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    packets = []
    rx.settimeout(0.2)
    while True:
        try:
            packets.append(json.loads(rx.recv(65535)))
        except socket.timeout:
            break
    assert 4 <= len(packets) <= 8, len(packets)          # 10 Hz for 0.55 s
    for p in packets:
        validate(p)
    player = packets[-1]["entities"][0]
    assert player["kind"] == "player" and isinstance(player["x"], float)
    assert packets[-1]["source"] == "memreader-fake"
