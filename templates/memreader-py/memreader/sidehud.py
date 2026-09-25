"""Packets and a UDP sender for sidehud.

The contract is docs/plugin-spec.md in the sidehud repo: one JSON object per
datagram to 127.0.0.1:8766, the complete state every time, 5 to 20 packets a
second while the player is in the game.
"""
from __future__ import annotations

import json
import socket

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766
MAX_BYTES = 8192
KINDS = ("player", "ally", "other")
_UNSET = object()


def _entity(e: dict) -> dict:
    if "x" not in e or "y" not in e:
        raise ValueError(f"entity needs x and y: {e!r}")
    kind = e.get("kind") or "player"
    out = {"id": e.get("id") or "player", "kind": kind if kind in KINDS else "other", "x": e["x"], "y": e["y"]}
    for key in ("heading", "label", "z"):
        if e.get(key) is not None:
            out[key] = e[key]
    return out


def build_packet(*, game: str | None = None, source: str = "memreader", map=_UNSET,
                 entities=(), stats: dict | None = None) -> dict:
    """A full-state packet. Keys that are None are left out; map=None sends a grid."""
    p: dict = {"source": source}
    if game is not None:
        p["game"] = game
    if map is not _UNSET:
        p["map"] = map
    ents = [_entity(e) for e in entities]
    if ents:
        p["entities"] = ents
    if stats is not None:
        p["stats"] = stats
    return p


class Sender:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self.sock.close()

    def send(self, packet: dict) -> int:
        data = json.dumps(packet, separators=(",", ":")).encode()
        if len(data) > MAX_BYTES:
            raise ValueError(f"packet is {len(data)} bytes, sidehud wants them under {MAX_BYTES}")
        return self.sock.sendto(data, self.addr)
