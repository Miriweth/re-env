"""Byte-pattern scanning with wildcards ("48 8B ?? 05").

Patterns compile to a bytes regex so the inner loop runs in C; a pure-Python
byte loop takes ~30 s per 100 MB, far too slow for a game process.
"""
from __future__ import annotations

import re

Pattern = list[int | None]


def parse_pattern(s: str) -> Pattern:
    out: Pattern = []
    for tok in s.split():
        if tok in ("?", "??"):
            out.append(None)
            continue
        if len(tok) != 2:
            raise ValueError(f"bad pattern token: {tok!r}")
        try:
            out.append(int(tok, 16))
        except ValueError:
            raise ValueError(f"bad pattern token: {tok!r}") from None
    return out


def _regex(pat: Pattern) -> re.Pattern[bytes]:
    body = b"".join(b"." if b is None else re.escape(bytes([b])) for b in pat)
    return re.compile(body, re.DOTALL)


def find(hay: bytes, pat: Pattern, start: int = 0) -> int | None:
    m = _regex(pat).search(hay, start)
    return m.start() if m else None


def find_all(hay: bytes, pat: Pattern) -> list[int]:
    # lookahead so overlapping hits are all reported
    return [m.start() for m in re.finditer(b"(?=" + _regex(pat).pattern + b")", hay, re.DOTALL)]
