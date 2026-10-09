"""HTTP side of the station: page, read API, token-guarded POST API on 127.0.0.1."""
import atexit
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import signal
import sys
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from station import runs, state

MAX_BODY = 16 * 1024
manager = None  # set by serve()
TOKEN = ""


class Reject(Exception):
    def __init__(self, code, msg=None):
        super().__init__(msg)
        self.code, self.msg = code, msg


def make_token():
    """A fresh token, also written mode 0600 to $XDG_RUNTIME_DIR/re-dash.token (or $RE_HOME/.re-dash.token)."""
    token = secrets.token_urlsafe(32)
    run_dir = os.environ.get("XDG_RUNTIME_DIR")
    path = Path(run_dir) / "re-dash.token" if run_dir and Path(run_dir).is_dir() else state.RE_HOME / ".re-dash.token"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    try:
        os.chmod(fd, 0o600)
        os.write(fd, (token + "\n").encode())
    finally:
        os.close(fd)
    return token


def valid_game(body):
    game = body.get("game")
    if not isinstance(game, str) or game not in state.games():
        raise Reject(400, "unknown game")
    return game


def api_state(query):
    game = urllib.parse.parse_qs(query).get("game", [""])[0]
    known = game in state.games()
    return {
        "system": state.system_state(),
        "game": state.game_files(game) if known else None,
        "status": manager.status(game)["status"] if known else "idle",
    }


def api_run(body):
    game = valid_game(body)
    if body.get("backend") not in state.BACKENDS:
        raise Reject(400, "unknown backend")
    prompt = body.get("prompt")
    if not isinstance(prompt, str) or not prompt or len(prompt.encode()) > MAX_BODY:
        raise Reject(400, "prompt must be a non-empty string up to 16 KiB")
    try:
        return 202, {"id": manager.start(game, body["backend"], prompt)}
    except runs.Busy:
        raise Reject(409, "a run is already active for this game")


def api_reset(body):
    manager.reset(valid_game(body))
    return 200, {"ok": True}


def api_settings(body):
    try:
        return 200, state.save_settings(body)
    except ValueError as e:
        raise Reject(400, str(e))


POST_ROUTES = {
    "/api/run": api_run,
    "/api/cancel": lambda b: (200, {"ok": manager.cancel(valid_game(b))}),
    "/api/reset": api_reset,
    "/api/settings": api_settings,
}


class Handler(BaseHTTPRequestHandler):
    timeout = 10  # drop idle or slow clients

    def guarded(self, route):
        """Host check, then route; Reject maps to its status, anything unexpected to 500."""
        try:
            port = self.server.server_address[1]
            host = (self.headers.get("Host") or "").lower()
            if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                raise Reject(403)  # DNS rebinding
            route(urllib.parse.urlsplit(self.path), host)
        except Reject as e:
            self.send_error(e.code, e.msg)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:  # never let a request kill the server
            traceback.print_exc()
            self.send_error(500)

    def do_GET(self):
        self.guarded(self.get)

    def do_POST(self):
        self.guarded(self.post)

    def get(self, url, host):
        if url.path == "/":
            self.send(200, "text/html; charset=utf-8", PAGE.encode())
        elif url.path == "/api/state":
            self.send_json(200, api_state(url.query))
        elif url.path == "/api/settings":
            self.send_json(200, state.load_settings())
        else:
            raise Reject(404)

    def post(self, url, host):
        if self.headers.get("Origin") != f"http://{host}":
            raise Reject(403)  # cross-site request
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            raise Reject(403)  # no simple (preflight-free) cross-origin form posts
        try:
            length = int(self.headers.get("Content-Length") or "")
        except ValueError:
            raise Reject(400, "Content-Length required")
        if length > MAX_BODY:
            raise Reject(413)
        if length < 0:
            raise Reject(400)
        auth = (self.headers.get("Authorization") or "").encode()
        if not hmac.compare_digest(auth, f"Bearer {TOKEN}".encode()):
            raise Reject(403)
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise Reject(400, "body must be a JSON object")
        if url.path not in POST_ROUTES:
            raise Reject(404)
        self.send_json(*POST_ROUTES[url.path](body))

    def send_json(self, code, obj):
        self.send(code, "application/json", json.dumps(obj).encode())

    def send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):  # every response, errors included
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        super().end_headers()

    def log_message(self, *args):
        pass


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>re-dash</title>
<style>
:root{
  color-scheme:dark;
  --page:#0d0d0d; --surface:#1a1a19; --border:rgba(255,255,255,.10);
  --ink:#ffffff; --ink-2:#c3c2b7; --muted:#898781; --grid:#2c2c2a;
  --gpu:#3987e5; --good:#0ca30c; --warn:#fab219; --crit:#d03b3b;
}
*{box-sizing:border-box}
html,body{margin:0;background:var(--page);color:var(--ink)}
body{font:16px/1.35 system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-text-size-adjust:100%;padding:10px 16px 16px}
header{display:flex;align-items:baseline;gap:10px;padding:2px 2px 12px}
header .brand{font-weight:600}
header .conn{margin-left:auto;font-size:12px;color:var(--muted);display:flex;align-items:center;gap:6px}
header .conn::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--muted)}
body.online header .conn::before{background:var(--good)}
body.offline header .conn::before{background:var(--crit)}
main{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));transition:opacity .3s}
body.offline main{opacity:.55}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:14px 16px 12px;min-width:0}
.tile.hero{grid-column:1/-1}
.label{font-size:13px;color:var(--ink-2);display:flex;justify-content:space-between;gap:8px}
.label .sub{color:var(--muted);text-align:right}
.value{font-size:40px;font-weight:600;letter-spacing:-.02em;line-height:1.1;margin-top:4px}
.meter{--c:var(--gpu);height:6px;border-radius:3px;background:rgba(255,255,255,.08);margin:10px 0 4px;overflow:hidden}
.meter .fill{height:100%;border-radius:3px;background:var(--c);width:0;transition:width .4s}
.meter.warn .fill{background:var(--warn)}
.meter.crit .fill{background:var(--crit)}
.kv{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:6px 0;border-top:1px solid var(--grid);font-size:15px}
.kv .k{color:var(--muted)}
.kv .v{font-variant-numeric:tabular-nums;text-align:right}
pre{margin:8px 0 0;font:12px/1.4 ui-monospace,Menlo,Consolas,monospace;color:var(--ink-2);white-space:pre-wrap;overflow-wrap:anywhere;max-height:16em;overflow:auto}
pre .warn{color:var(--warn)}
pre .crit{color:var(--crit)}
summary{font-size:13px;color:var(--ink-2);cursor:pointer;margin-top:10px}
</style></head><body class="offline">
<header><span class="brand">re-dash</span><span class="conn">live</span></header>
<main>
<section class="tile hero" id="vram">
  <div class="label"><span>VRAM</span><span class="sub"></span></div>
  <div class="value">-</div>
  <div class="meter"><div class="fill"></div></div>
</section>
<section class="tile"><div class="label"><span>ollama ps</span></div><pre id="ollama" data-key="ollama"></pre></section>
<section class="tile"><div class="label"><span>last re-check</span><span class="sub" id="age"></span></div><pre id="recheck" data-key="recheck"></pre></section>
<div id="targets" style="display:contents"></div>
</main>
<script>
const $ = id => document.getElementById(id);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};
const GIB = 1024;

function ago(mtime) {
  const s = Math.max(0, Date.now() / 1000 - mtime);
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + " min ago";
  if (s < 86400) return Math.floor(s / 3600) + " h ago";
  return Math.floor(s / 86400) + " d ago";
}

function renderVram(v) {
  const t = $("vram"), meter = t.querySelector(".meter");
  const pct = v ? v.used / v.total * 100 : 0;
  t.querySelector(".value").textContent = v ? (v.used / GIB).toFixed(1) + " / " + (v.total / GIB).toFixed(1) + " GiB" : "n/a";
  t.querySelector(".sub").textContent = v ? Math.round(pct) + " %" : "nvidia-smi unavailable";
  meter.className = "meter" + (pct > 95 ? " crit" : pct > 80 ? " warn" : "");
  meter.firstChild.style.width = pct + "%";
}

function renderRecheck(rc) {
  const pre = $("recheck");
  pre.textContent = "";
  $("age").textContent = rc ? ago(rc.mtime) : "";
  if (!rc) { pre.textContent = "no re-check run yet"; return; }
  for (const line of rc.text.split("\n")) {
    const cls = line.startsWith("FAIL") ? "crit" : line.startsWith("WARN") ? "warn" : "";
    pre.appendChild(el("div", cls, line));
  }
}

function renderTarget(t, name) {
  const tile = el("section", "tile");
  const label = el("div", "label");
  label.append(el("span", "", name), el("span", "sub", t.mods.length + " mods"));
  tile.append(label);
  for (const m of t.mods) {
    const kv = el("div", "kv");
    kv.append(el("span", "k", "mod"), el("span", "v", m));
    tile.append(kv);
  }
  const log = el("pre", "", t.modlog_tail || "no modlog yet");
  log.dataset.key = t.name + ":modlog";
  tile.append(log);
  const d = el("details");
  d.dataset.name = name;
  const notes = el("pre", "", (t.plan || t.modlog_facts) || "no plan yet");
  notes.dataset.key = t.name + ":plan";
  d.append(el("summary", "", "plan"), notes);
  tile.append(d);
  return tile;
}

function renderTargets(targets) { // [[name, game], ...]
  const box = $("targets");
  const open = new Set([...box.querySelectorAll("details[open]")].map(d => d.dataset.name));
  const tiles = targets.map(([name, g]) => renderTarget(g, name));
  tiles.forEach((tile, i) => { if (open.has(targets[i][0])) tile.querySelector("details").open = true; });
  box.replaceChildren(...tiles);
}

let lastText = "", lastRecheck = null, game = "";

function render(s) {
  const scroll = new Map([...document.querySelectorAll("pre[data-key]")].map(p => [p.dataset.key, p.scrollTop]));
  renderVram(s.system.vram);
  $("ollama").textContent = s.system.ollama;
  renderRecheck(s.system.recheck);
  renderTargets(s.game ? [[game, s.game]] : []);
  document.querySelectorAll("pre[data-key]").forEach(p => { p.scrollTop = scroll.get(p.dataset.key) || 0; });
}

async function tick() {
  try {
    const r = await fetch("/api/state?game=" + encodeURIComponent(game), {cache: "no-store"});
    if (!r.ok) throw new Error(r.status);
    const text = await r.text();
    if (text !== lastText) {
      const s = JSON.parse(text);
      if (!game && s.system.games.length) { game = s.system.games[0]; lastText = ""; return tick(); }
      render(s);
      lastText = text;
      lastRecheck = s.system.recheck;
    } else if (lastRecheck) {
      $("age").textContent = ago(lastRecheck.mtime);
    }
    document.body.className = "online";
  } catch (e) {
    document.body.className = "offline";
  }
}
tick();
setInterval(tick, 2000);
</script></body></html>
"""

SCRIPT = re.search(r"<script>(.*?)</script>", PAGE, re.S).group(1)
CSP = ("default-src 'none'; style-src 'unsafe-inline'; "
       f"script-src 'sha256-{base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()}'; "
       "connect-src 'self'; frame-ancestors 'none'")


def serve(port, token):
    global manager, TOKEN
    TOKEN = token
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        raise SystemExit(f"error: {e}")
    srv.daemon_threads = True
    manager = runs.Manager()
    atexit.register(manager.shutdown)  # children die with the station
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # SystemExit runs atexit
    print(f"re-dash on http://127.0.0.1:{srv.server_address[1]}/#{token}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
