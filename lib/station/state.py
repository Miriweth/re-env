"""Read side of the station: per-game files and system state under $RE_HOME."""
import json
import os
import re
import stat
import subprocess
import tempfile
import threading
import time
from pathlib import Path

RE_HOME = Path(os.environ.get("RE_HOME") or Path.home() / "re")
LOG_LINES = 20
THREAD_LINES = 200
NOTES_CAP = 64 * 1024
LOG_TAIL_BYTES = 16 * 1024
THREAD_TAIL_BYTES = 256 * 1024
STATE_TTL = 1.5

ALIASES = {
    "qwen": "huihui_ai/qwen2.5-coder-abliterate:14b",
    "qwen3": "huihui_ai/qwen3-abliterated:14b",
    "llama": "mannix/llama3.1-8b-abliterated",
}
AGENT_ALIASES = ("qwen", "llama")
BACKENDS = ("auto", "claude", "claude-local:qwen", "claude-local:llama",
            "ask-local:qwen", "ask-local:qwen3", "ask-local:llama")
DEFAULT_SETTINGS = {"bulk_model": "qwen", "offline": False, "default_backend": "auto"}

ISSUE = re.compile(r"^- \[( |x)\] (.*)$")
FACTS = re.compile(r"^## Facts[ \t]*\n(.*?)(?=^## Journal|\Z)", re.S | re.M)


def sh(*argv):
    """stdout of a command, or None on any failure."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=2, stdin=subprocess.DEVNULL)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def read(path, cap, tail=False):
    """At most cap bytes of a regular file (never a symlink, FIFO or device), or "" otherwise.
    Head mode marks a cut with a truncated line; tail mode reads the last cap bytes, minus the partial first line."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except OSError:
        return ""
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return ""
        size = st.st_size
        start = max(0, size - cap) if tail else 0
        os.lseek(fd, start, os.SEEK_SET)
        with os.fdopen(os.dup(fd), "rb") as f:
            data = f.read(cap + 1)
    except OSError:
        return ""
    finally:
        os.close(fd)
    if tail:
        return (data.split(b"\n", 1)[-1] if start else data).decode(errors="replace")
    return data[:cap].decode(errors="replace") + ("\n… truncated" if len(data) > cap else "")


def mtime(path):
    try:
        return path.stat().st_mtime
    except OSError:
        return 0


def size(path):
    try:
        return os.stat(path).st_size
    except OSError:
        return 0


def is_real_dir(p):
    return p.is_dir() and not p.is_symlink()


def load_settings():
    try:
        d = json.loads(read(RE_HOME / "station.json", NOTES_CAP))
    except ValueError:
        d = None
    if not isinstance(d, dict):
        d = {}
    return {**DEFAULT_SETTINGS, **{k: d[k] for k in DEFAULT_SETTINGS if k in d}}


def save_settings(d):
    merged = {**load_settings(), **d}
    if set(merged) != set(DEFAULT_SETTINGS):
        raise ValueError("unknown setting")
    if merged["bulk_model"] not in ALIASES:
        raise ValueError("bulk_model must be one of " + ", ".join(ALIASES))
    if not isinstance(merged["offline"], bool):
        raise ValueError("offline must be a boolean")
    if merged["default_backend"] not in BACKENDS:
        raise ValueError("default_backend must be one of " + ", ".join(BACKENDS))
    fd, tmp = tempfile.mkstemp(dir=RE_HOME, prefix=".station.json.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(merged))
        os.replace(tmp, RE_HOME / "station.json")
    except OSError:
        os.unlink(tmp)
        raise
    return merged


def games():
    try:
        return sorted(d.name for d in (RE_HOME / "targets").iterdir() if is_real_dir(d))
    except OSError:
        return []


def game_files(name):
    d = RE_HOME / "targets" / name
    modlog = read(d / "MODLOG.md", NOTES_CAP)
    m = FACTS.search(modlog)
    mods = d / "mods"
    thread_lines = read(d / "station/thread.jsonl", THREAD_TAIL_BYTES, tail=True).splitlines()
    thread = []
    for line in thread_lines[-THREAD_LINES:]:
        try:
            thread.append(json.loads(line))
        except ValueError:
            pass
    try:
        scan = json.loads(read(d / "station/scan.json", NOTES_CAP))
    except ValueError:
        scan = None
    files = [d / "MODDING_PLAN.md", d / "MODLOG.md", d / "issues.md", d / "station/scan.json", d / "station/thread.jsonl"]
    issues = (ISSUE.match(line) for line in read(d / "issues.md", NOTES_CAP).splitlines())
    return {
        "plan": read(d / "MODDING_PLAN.md", NOTES_CAP),
        "modlog_facts": m.group(1).strip() if m else modlog,
        "modlog_tail": "\n".join(read(d / "MODLOG.md", LOG_TAIL_BYTES, tail=True).splitlines()[-LOG_LINES:]),
        "issues": [{"done": i.group(1) == "x", "text": i.group(2)} for i in issues if i],
        "mods": sorted(x.name for x in mods.iterdir() if is_real_dir(x) and not x.name.startswith(".")) if is_real_dir(mods) else [],
        "scan": scan,
        "thread": thread,
        # ponytail: line count covers the last THREAD_TAIL_BYTES only; size and mtime still move on every append
        "version": f"{len(thread_lines)}:{size(d / 'station/thread.jsonl')}:{int(max(mtime(f) for f in files))}",
    }


def vram():
    out = sh("nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits")
    try:
        used, total = (int(x) for x in out.splitlines()[0].split(","))
        return {"used": used, "total": total}
    except (AttributeError, IndexError, ValueError):
        return None


_cache = (0.0, None)
_cache_lock = threading.Lock()


def system_state():
    """One scan shared by all clients per STATE_TTL (the lock makes concurrent requests wait for it)."""
    global _cache
    with _cache_lock:
        t, st = _cache
        if st is None or time.monotonic() - t > STATE_TTL:
            last = RE_HOME / "re-check.last"
            st = {
                "ollama": sh("ollama", "ps") or "ollama unavailable",
                "vram": vram(),
                "recheck": {"text": read(last, NOTES_CAP), "mtime": int(mtime(last))} if last.is_file() else None,
                "settings": load_settings(),
                "games": games(),
            }
            _cache = (time.monotonic(), st)
        return st
