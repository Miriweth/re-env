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
PAGE = ""  # page.html, read by serve()
CSP = "default-src 'none'"


class Reject(Exception):
    def __init__(self, code, msg=None):
        super().__init__(msg)
        self.code, self.msg = code, msg


def make_token():
    """A fresh token, also written mode 0600 to $XDG_RUNTIME_DIR/re-dash.token (or $RE_HOME/.re-dash.token)."""
    token = secrets.token_urlsafe(32)
    run_dir = os.environ.get("XDG_RUNTIME_DIR")
    path = Path(run_dir) / "re-dash.token" if run_dir and Path(run_dir).is_dir() else state.RE_HOME / ".re-dash.token"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        try:
            os.chmod(fd, 0o600)
            os.write(fd, (token + "\n").encode())
        finally:
            os.close(fd)
    except OSError as e:
        raise SystemExit(f"error: cannot write token file {path}: {e.strerror}")
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
        "system": {**state.system_state(), "backends": state.BACKENDS},
        "game": state.game_files(game) if known else None,
        "status": manager.status(game)["status"] if known else "idle",
    }


def api_run(body):
    game = valid_game(body)
    if body.get("backend") not in state.BACKENDS:
        raise Reject(400, "unknown backend")
    prompt = body.get("prompt")
    try:
        size = len(prompt.encode()) if isinstance(prompt, str) else 0
    except UnicodeEncodeError:  # lone surrogate from a \udxxx escape
        size = 0
    if not size or size > MAX_BODY:
        raise Reject(400, "prompt must be a non-empty string up to 16 KiB")
    try:
        return 202, {"id": manager.start(game, body["backend"], prompt)}
    except runs.Busy:
        raise Reject(409, "a run is already active for this game")


def api_reset(body):
    manager.reset(valid_game(body))
    return 200, {"ok": True}


SETTING_TYPES = {"bulk_model": str, "offline": bool, "default_backend": str}


def api_settings(body):
    if any(k in SETTING_TYPES and not isinstance(v, SETTING_TYPES[k]) for k, v in body.items()):
        raise Reject(400, "wrong setting type")  # [] in ALIASES would raise TypeError
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
            self.send_error(e.code, None, e.msg)  # fixed reason line, message only in the escaped body
        except (BrokenPipeError, ConnectionResetError, TimeoutError):  # client gone; other OSErrors are 500s
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
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            raise Reject(403)  # no simple (preflight-free) cross-origin form posts
        cl = self.headers.get("Content-Length") or ""
        if not (cl.isascii() and cl.isdigit()):
            raise Reject(400, "Content-Length required")
        length = int(cl)
        if length > MAX_BODY:
            raise Reject(413)
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


def csp_for(page):
    """CSP that allows exactly the page's one inline script, by hash."""
    script = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    return ("default-src 'none'; style-src 'unsafe-inline'; "
            f"script-src 'sha256-{digest}'; connect-src 'self'; frame-ancestors 'none'")


def serve(port, token):
    global manager, TOKEN, PAGE, CSP
    TOKEN = token
    PAGE = Path(__file__).with_name("page.html").read_text()
    CSP = csp_for(PAGE)
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
