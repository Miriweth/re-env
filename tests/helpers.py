"""Shared helpers for the re-env test-suite (stdlib only)."""
import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BIN = REPO / "bin"

FAKE_HEADER = '#!/usr/bin/env bash\nprintf "%s %s\\n" "$(basename "$0")" "$*" >> "${FAKE_LOG:-/dev/null}"\n'


def make_fake(bin_dir: Path, name: str, body: str = "") -> Path:
    """Write an executable bash fake `bin_dir/name`.

    Every fake appends "<name> <args>" to $FAKE_LOG, then runs `body`.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    p = bin_dir / name
    p.write_text(FAKE_HEADER + body + "\n")
    p.chmod(0o755)
    return p


def run(argv, env=None, stdin=None, fake_bin=None, cwd=None):
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    if fake_bin is not None:
        full_env["PATH"] = f"{fake_bin}:{os.environ['PATH']}"
    return subprocess.run(
        [str(a) for a in argv],
        env=full_env,
        cwd=cwd,
        input=stdin,
        stdin=subprocess.DEVNULL if stdin is None else None,
        text=True,
        capture_output=True,
    )


def tmp_home():
    """A fresh temporary directory (caller cleans up via addCleanup)."""
    return tempfile.TemporaryDirectory()


def read_log(path: Path):
    return path.read_text().splitlines() if path.exists() else []
