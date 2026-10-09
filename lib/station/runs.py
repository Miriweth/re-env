"""Run side of the station: one claude / claude-local / ask-local child per game, recorded to thread.jsonl."""
import json
import os
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from station import state

PROMPT = (Path(__file__).parent / "prompt.md").read_text()
OFFLINE_RULE = "Offline mode is ON: run everything through claude-local or ask-local and say so."
ENV_VARS = ("PATH", "HOME", "XDG_RUNTIME_DIR", "OLLAMA_URL", "TERM", "LANG")
# ponytail: fixed limit, make it a setting if a recon ever needs longer
RUN_TIMEOUT = 60 * 60
KILL_GRACE = 5
LINE_CAP = 4 * 1024 * 1024
STDERR_TAIL = 2048
QUESTION_MARKS = ("FRAGE:", "QUESTION:")


class Busy(Exception):
    pass


class Run:
    def __init__(self, game, backend, proc):
        self.game, self.backend, self.proc = game, backend, proc
        self.started = time.time()
        self.status = "running"
        self.tool = None
        self.error = ""
        self.last_text = ""
        self.stopped = None  # "cancelled" | "timeout"
        self.thread = None


def render_prompt(game, settings):
    return (PROMPT.replace("{game}", game)
            .replace("{bulk_model}", settings["bulk_model"])
            .replace("{offline_rule}", OFFLINE_RULE if settings["offline"] else ""))


def command(backend, game, session_id, settings):
    kind, _, alias = backend.partition(":")
    if kind == "ask-local":
        return ["ask-local", alias, "Answer the request that follows."]
    opts = ["-p", "--verbose", "--output-format", "stream-json", "--permission-mode", "bypassPermissions",
            "--append-system-prompt", render_prompt(game, settings)] + (["--resume", session_id] if session_id else [])
    return ["claude-local", alias, *opts] if kind == "claude-local" else ["claude", *opts]


def child_env():
    return {**{k: os.environ[k] for k in ENV_VARS if k in os.environ}, "ECC_GATEGUARD": "off"}


def station_dir(game):
    d = state.RE_HOME / "targets" / game / "station"
    d.mkdir(exist_ok=True)
    return d


def append(game, role, model, text):
    line = json.dumps({"t": time.time(), "role": role, "model": model, "text": text}) + "\n"
    fd = os.open(station_dir(game) / "thread.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o644)
    try:
        os.write(fd, line.encode())
    finally:
        os.close(fd)


def session_key(backend):
    return "claude-local" if backend.startswith("claude-local:") else "claude"


def load_sessions(game):
    try:
        d = json.loads(state.read(station_dir(game) / "session.json", state.NOTES_CAP))
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def save_sessions(game, sessions):
    d = station_dir(game)
    tmp = d / f".session.json.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(sessions))
    os.replace(tmp, d / "session.json")


def killpg(proc, sig):
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def tool_line(block):
    inp = block.get("input")
    first = (inp.get("command") if isinstance(inp, dict) else None) or json.dumps(inp)
    return f"{block.get('name')}: {str(first).splitlines()[0] if first else ''}"


def result_line(ev):
    text = "failed" if ev.get("is_error") else "done"
    if isinstance(ev.get("duration_ms"), (int, float)):
        text += f" in {ev['duration_ms'] / 1000:.1f}s"
    if isinstance(ev.get("total_cost_usd"), (int, float)):
        text += f", ${ev['total_cost_usd']:.3f}"
    return text


class Manager:
    def __init__(self):
        self.runs = {}
        self._lock = threading.Lock()

    def start(self, game, backend, prompt):
        if backend not in state.BACKENDS:
            raise ValueError(f"unknown backend: {backend}")
        if not state.is_real_dir(state.RE_HOME / "targets" / game):
            raise ValueError(f"unknown game: {game}")
        data = prompt if isinstance(prompt, bytes) else prompt.encode()
        with self._lock:
            old = self.runs.get(game)
            if old and old.status == "running":
                raise Busy(game)
            sid = None if backend.startswith("ask-local:") else load_sessions(game).get(session_key(backend))
            argv = command(backend, game, sid, state.load_settings())
            append(game, "user", backend, data.decode(errors="replace"))
            stderr = tempfile.TemporaryFile()
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
                                    cwd=state.RE_HOME, env=child_env(), start_new_session=True)
            run = Run(game, backend, proc)
            run.thread = threading.Thread(target=self._follow, args=(run, data, stderr), daemon=True)
            self.runs[game] = run
            run.thread.start()
        return f"{game}:{int(run.started)}"

    def _follow(self, run, data, stderr):
        timer = threading.Timer(RUN_TIMEOUT, self._stop, (run, "timeout"))
        timer.daemon = True
        timer.start()
        try:
            try:
                run.proc.stdin.write(data)
            except BrokenPipeError:
                pass
            finally:
                try:
                    run.proc.stdin.close()
                except BrokenPipeError:
                    pass
            failed = self._read(run)
            rc = run.proc.wait()
            self._finish(run, failed or rc != 0, rc, stderr)
        finally:
            timer.cancel()
            stderr.close()
            run.proc.stdout.close()

    def _read(self, run):
        """Stream stdout into the thread; returns True if a result event reported is_error."""
        game, model, failed = run.game, run.backend, False
        if run.backend.startswith("ask-local:"):
            run.last_text = run.proc.stdout.read(LINE_CAP).decode(errors="replace").rstrip("\n")
            run.proc.stdout.read()  # ponytail: output past LINE_CAP is dropped
            if run.last_text:
                append(game, "assistant", model, run.last_text)
            return False
        while line := run.proc.stdout.readline(LINE_CAP):
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            if ev.get("type") == "system" and ev.get("subtype") == "init" and isinstance(ev.get("session_id"), str):
                model = ev.get("model") or model
                sessions = load_sessions(game)
                save_sessions(game, {**sessions, session_key(run.backend): ev["session_id"]})
            elif ev.get("type") == "assistant":
                content = (ev.get("message") or {}).get("content") or []
                for block in content if isinstance(content, list) else []:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text" and block.get("text"):
                        run.last_text = block["text"]
                        append(game, "assistant", model, block["text"])
                    elif block.get("type") == "tool_use":
                        run.tool = block.get("name")
                        append(game, "tool", model, tool_line(block))
            elif ev.get("type") == "result":
                failed = bool(ev.get("is_error"))
                append(game, "system", model, result_line(ev))
        return failed

    def _finish(self, run, failed, rc, stderr):
        if run.stopped == "cancelled":
            append(run.game, "system", run.backend, "cancelled")
            run.status = "done"
            return
        if failed or run.stopped:
            stderr.seek(max(0, stderr.seek(0, os.SEEK_END) - STDERR_TAIL))
            tail = stderr.read().decode(errors="replace").strip()
            run.error = "\n".join(x for x in (f"timeout after {RUN_TIMEOUT} s" if run.stopped else "",
                                              tail, f"exit {rc}") if x)
            append(run.game, "error", run.backend, run.error)
            run.status = "failed"
            return
        lines = (x.lstrip() for x in run.last_text.splitlines())
        run.status = "waiting" if any(x.startswith(QUESTION_MARKS) for x in lines) else "done"

    def _stop(self, run, reason):
        run.stopped = reason
        killpg(run.proc, signal.SIGTERM)
        try:
            run.proc.wait(KILL_GRACE)
        except subprocess.TimeoutExpired:
            pass
        killpg(run.proc, signal.SIGKILL)  # also reaps stragglers left in the group

    def cancel(self, game):
        with self._lock:
            run = self.runs.get(game)
        if not run or run.status != "running":
            return False
        threading.Thread(target=self._stop, args=(run, "cancelled"), daemon=True).start()
        return True

    def reset(self, game):
        save_sessions(game, {})
        append(game, "system", "station", "new conversation")

    def status(self, game):
        with self._lock:
            run = self.runs.get(game)
        if not run or run.status == "done":
            return {"status": "idle", "since": None, "backend": None, "tool": None}
        return {"status": run.status, "since": run.started, "backend": run.backend,
                "tool": run.tool if run.status == "running" else None}

    def wait(self, game, timeout):
        """Join the run's reader thread; True when it has finished."""
        with self._lock:
            run = self.runs.get(game)
        if run:
            run.thread.join(timeout)
        return not (run and run.thread.is_alive())

    def shutdown(self):
        with self._lock:
            live = [r for r in self.runs.values() if r.status == "running"]
        for run in live:
            run.stopped = "cancelled"
            killpg(run.proc, signal.SIGKILL)
        for run in live:
            run.thread.join(KILL_GRACE)
