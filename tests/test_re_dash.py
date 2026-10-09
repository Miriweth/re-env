import base64
import hashlib
import http.client
import json
import os
import re
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from unittest import mock

from helpers import BIN, make_fake, read_log, run, tmp_home

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from station import state


INIT = '{"type":"system","subtype":"init","session_id":"sid-1"}'
ASSISTANT = '{"type":"assistant","message":{"content":[{"type":"text","text":"All done."}]}}'
RESULT = '{"type":"result","is_error":false,"duration_ms":5}'
OK = object()


class ReDash(unittest.TestCase):
    def setUp(self):
        self.tmp = tmp_home()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.re_home = root / "re"
        self.fake_bin = root / "fakes"
        t = self.re_home / "targets" / "Elden"
        (t / "mods/a").mkdir(parents=True)
        (t / "mods/.hidden").mkdir()
        (t / "MODDING_PLAN.md").write_text("# Plan\nstep 1\n")
        (t / "MODLOG.md").write_text("# Elden\n## Facts\nfact one\n## Journal\n" + "".join(f"line {i}\n" for i in range(1, 31)))
        make_fake(self.fake_bin, "ollama", 'echo "NAME  ID"; echo "qwen  abc"')
        make_fake(self.fake_bin, "nvidia-smi", 'echo "4096, 16384"; echo "1, 2"')
        self.log = root / "claude.log"
        self.fake_claude()

    def fake_claude(self, pre=""):
        # the station passes children a minimal env (no FAKE_LOG), so the log path is baked in
        out = "\n".join(f"echo '{x}'" for x in (INIT, ASSISTANT, RESULT))
        make_fake(self.fake_bin, "claude", f'echo "claude $*" >> "{self.log}"\ncat > /dev/null\n{pre}\n{out}')

    def start(self, *args):
        self.runtime = Path(self.tmp.name) / "run"
        self.runtime.mkdir(exist_ok=True)
        env = dict(os.environ, RE_HOME=str(self.re_home), PATH=f"{self.fake_bin}:{os.environ['PATH']}",
                   XDG_RUNTIME_DIR=str(self.runtime))
        p = subprocess.Popen([str(BIN / "re-dash"), "--port", "0", *args], env=env,
                             stdout=subprocess.PIPE, text=True)
        self.addCleanup(p.stdout.close)
        self.addCleanup(p.wait)
        self.addCleanup(p.terminate)
        line = p.stdout.readline().strip()
        m = re.fullmatch(r"re-dash on (http://127\.0\.0\.1:(\d+))/#([A-Za-z0-9_-]+)", line)
        self.assertIsNotNone(m, line)
        self.token = m.group(3)
        return m.group(1)

    def state(self, url, game="Elden"):
        with urllib.request.urlopen(f"{url}/api/state?game={game}", timeout=5) as r:
            return json.load(r)

    def game(self, url=None):
        return self.state(url or self.start())["game"]

    def test_help(self):
        r = run([BIN / "re-dash", "--help"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--port", r.stdout)

    def test_listens_on_loopback(self):
        self.assertTrue(self.start().startswith("http://127.0.0.1:"))

    def test_state_game(self):
        s = self.state(self.start())
        self.assertEqual(s["status"], "idle")
        self.assertEqual(s["system"]["games"], ["Elden"])
        g = s["game"]
        self.assertEqual(g["plan"], "# Plan\nstep 1\n")
        self.assertEqual(g["modlog_tail"].splitlines(), [f"line {i}" for i in range(11, 31)])
        self.assertEqual(g["mods"], ["a"])
        self.assertIsNone(g["scan"])
        self.assertEqual(g["thread"], [])

    def test_issues_parsed(self):
        (self.re_home / "targets/Elden/issues.md").write_text("# Issues\n- [ ] open one\n- [x] done one\nnot an issue\n- [X] nope\n")
        self.assertEqual(self.game()["issues"], [{"done": False, "text": "open one"}, {"done": True, "text": "done one"}])

    def test_modlog_split_facts_tail(self):
        g = self.game()
        self.assertEqual(g["modlog_facts"], "fact one")
        self.assertNotIn("line 1\n", g["modlog_facts"])

    def test_thread_tail_200_and_bad_lines_skipped(self):
        st = self.re_home / "targets/Elden/station"
        st.mkdir()
        (st / "thread.jsonl").write_text("".join(json.dumps({"n": i}) + "\n" for i in range(1, 251)) + "{oops\n")
        th = self.game()["thread"]
        self.assertEqual([e["n"] for e in th], list(range(52, 251)))

    def test_scan_loaded(self):
        st = self.re_home / "targets/Elden/station"
        st.mkdir()
        (st / "scan.json").write_text('{"files": 3}')
        self.assertEqual(self.game()["scan"], {"files": 3})

    def test_version_changes_when_thread_grows(self):
        st = self.re_home / "targets/Elden/station"
        st.mkdir()
        (st / "thread.jsonl").write_text('{"n": 1}\n')
        os.utime(st / "thread.jsonl", (1000, 1000))
        url = self.start()
        v1 = self.state(url)["game"]["version"]
        with open(st / "thread.jsonl", "a") as f:
            f.write('{"n": 2}\n')
        os.utime(st / "thread.jsonl", (1000, 1000))
        v2 = self.state(url)["game"]["version"]
        self.assertEqual(v1.split(":")[0], "1")
        self.assertEqual(v2.split(":")[0], "2")
        self.assertNotEqual(v1, v2)

    def test_settings_default_on_corrupt_file(self):
        (self.re_home / "station.json").write_text("{")
        s = self.state(self.start())
        self.assertEqual(s["system"]["settings"], {"bulk_model": "qwen", "offline": False, "default_backend": "auto"})

    def test_settings_merged_from_file(self):
        (self.re_home / "station.json").write_text('{"offline": true, "bogus": 1}')
        s = self.state(self.start())["system"]["settings"]
        self.assertEqual(s, {"bulk_model": "qwen", "offline": True, "default_backend": "auto"})

    def test_unknown_game_gives_null_game(self):
        s = self.state(self.start(), "nope")
        self.assertIsNone(s["game"])
        self.assertIn("system", s)

    def test_state_tools(self):
        s = self.state(self.start())["system"]
        self.assertIn("qwen", s["ollama"])
        self.assertEqual(s["vram"], {"used": 4096, "total": 16384})
        self.assertIsNone(s["recheck"])

    def test_recheck_last(self):
        (self.re_home / "re-check.last").write_text("# re-check\nPASS gpu x\n")
        rc = self.state(self.start())["system"]["recheck"]
        self.assertEqual(rc["text"], "# re-check\nPASS gpu x\n")
        self.assertIsInstance(rc["mtime"], int)

    def test_failing_tools(self):
        make_fake(self.fake_bin, "nvidia-smi", "exit 1")
        make_fake(self.fake_bin, "ollama", "exit 1")
        s = self.state(self.start())["system"]
        self.assertIsNone(s["vram"])
        self.assertIn("unavailable", s["ollama"])

    def test_unparseable_vram(self):
        make_fake(self.fake_bin, "nvidia-smi", 'echo "garbage"')
        self.assertIsNone(self.state(self.start())["system"]["vram"])

    def test_missing_targets_dir(self):
        import shutil
        shutil.rmtree(self.re_home / "targets")
        s = self.state(self.start())
        self.assertEqual(s["system"]["games"], [])
        self.assertIsNone(s["game"])

    def test_page_and_404(self):
        url = self.start()
        with urllib.request.urlopen(url + "/", timeout=5) as r:
            self.assertIn("text/html", r.headers["Content-Type"])
            self.assertIn("re-dash", r.read().decode())
        for path in ("/other", "/api/state/x", "/../etc/passwd"):
            with self.assertRaises(urllib.error.HTTPError, msg=path) as c:
                urllib.request.urlopen(url + path, timeout=5)
            self.assertEqual(c.exception.code, 404, path)
            c.exception.close()

    def get(self, url, path, host=None):
        c = http.client.HTTPConnection("127.0.0.1", int(url.rsplit(":", 1)[1]), timeout=5)
        c.request("GET", path, headers={"Host": host} if host else {})
        r = c.getresponse()
        r.body = r.read()
        c.close()
        return r

    def test_host_check(self):
        url = self.start()
        port = url.rsplit(":", 1)[1]
        for path in ("/", "/api/state"):
            self.assertEqual(self.get(url, path, f"evil.example:{port}").status, 403, path)
            self.assertEqual(self.get(url, path, "127.0.0.1").status, 403, path)
            self.assertEqual(self.get(url, path).status, 200, path)
            self.assertEqual(self.get(url, path, f"localhost:{port}").status, 200, path)

    def test_query_string(self):
        url = self.start()
        self.assertEqual(self.get(url, "/api/state?t=1").status, 200)
        self.assertEqual(self.get(url, "/?x=1").status, 200)

    def test_symlinked_modlog_is_empty(self):
        secret = self.re_home / "secret.txt"
        secret.write_text("TOP SECRET")
        t = self.re_home / "targets" / "Elden"
        (t / "MODLOG.md").unlink()
        (t / "MODLOG.md").symlink_to(secret)
        g = self.game()
        self.assertEqual((g["modlog_facts"], g["modlog_tail"]), ("", ""))

    def test_symlinked_dirs_skipped(self):
        other = Path(self.tmp.name) / "other"
        (other / "mods/zz").mkdir(parents=True)
        (self.re_home / "targets" / "Linked").symlink_to(other)
        (self.re_home / "targets" / "Elden" / "mods" / "lnk").symlink_to(other)
        s = self.state(self.start())
        self.assertEqual(s["system"]["games"], ["Elden"])
        self.assertEqual(s["game"]["mods"], ["a"])
        self.assertIsNone(self.state(self.start(), "Linked")["game"])

    def test_fifo_modlog_does_not_hang(self):
        t = self.re_home / "targets" / "Elden"
        (t / "MODLOG.md").unlink()
        os.mkfifo(t / "MODLOG.md")
        self.assertEqual(self.game()["modlog_facts"], "")

    def test_symlinked_recheck_last_is_empty(self):
        secret = self.re_home / "secret.txt"
        secret.write_text("TOP SECRET")
        (self.re_home / "re-check.last").symlink_to(secret)
        self.assertEqual(self.state(self.start())["system"]["recheck"]["text"], "")

    def test_big_modlog_last_lines(self):
        t = self.re_home / "targets" / "Elden"
        (t / "MODLOG.md").write_text("".join(f"line {i}\n" for i in range(1, 100001)))
        log = self.game()["modlog_tail"]
        self.assertEqual(log.splitlines(), [f"line {i}" for i in range(99981, 100001)])

    def test_big_modlog_truncated(self):
        t = self.re_home / "targets" / "Elden"
        (t / "MODLOG.md").write_text("x" * 200000)
        notes = self.game()["modlog_facts"]
        self.assertTrue(notes.startswith("x" * 65536))
        self.assertTrue(notes.endswith("\n… truncated"))
        self.assertLess(len(notes), 65600)

    def test_security_headers_and_csp_hash(self):
        url = self.start()
        for path in ("/", "/api/state", "/nope"):
            r = self.get(url, path)
            self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff", path)
            self.assertEqual(r.getheader("X-Frame-Options"), "DENY", path)
            self.assertEqual(r.getheader("Cache-Control"), "no-store", path)
            self.assertIn("default-src 'none'", r.getheader("Content-Security-Policy"), path)
        r = self.get(url, "/")
        script = re.search(rb"<script>(.*?)</script>", r.body, re.S).group(1)
        h = base64.b64encode(hashlib.sha256(script).digest()).decode()
        csp = r.getheader("Content-Security-Policy")
        self.assertIn(f"script-src 'sha256-{h}'", csp)
        self.assertIn("connect-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)

    def test_state_is_cached(self):
        url = self.start()
        self.assertEqual(self.state(url)["system"]["games"], ["Elden"])
        (self.re_home / "targets" / "Other").mkdir()
        self.assertEqual(self.state(url)["system"]["games"], ["Elden"])

    def test_page_keeps_scroll_and_skips_identical(self):
        page = self.get(self.start(), "/").body.decode()
        self.assertIn("scrollTop", page)
        self.assertIn("lastText", page)

    def post(self, url, path, body, token=OK, origin=OK, host=OK, ctype=OK):
        port = url.rsplit(":", 1)[1]
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        headers = {"Host": f"127.0.0.1:{port}" if host is OK else host,
                   "Origin": f"http://127.0.0.1:{port}" if origin is OK else origin,
                   "Content-Type": "application/json" if ctype is OK else ctype,
                   "Authorization": f"Bearer {self.token}" if token is OK else token and f"Bearer {token}"}
        headers = {k: v for k, v in headers.items() if v is not None}
        c = http.client.HTTPConnection("127.0.0.1", int(port), timeout=5)
        c.request("POST", path, body=data, headers=headers)
        r = c.getresponse()
        raw = r.read()
        c.close()
        self.assertFalse(any(k.lower().startswith("access-control-") for k in r.headers), r.headers)
        try:
            return r.status, json.loads(raw)
        except ValueError:
            return r.status, None

    def until(self, cond, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cond():
                return
            time.sleep(0.1)
        self.fail("condition not reached")

    def run_body(self, **kw):
        return {"game": "Elden", "backend": "claude", "prompt": "hello", **kw}

    def assert_rejected(self, code, **kw):
        url = self.start()
        body = kw.pop("body", self.run_body())
        self.assertEqual(self.post(url, "/api/run", body, **kw)[0], code)
        time.sleep(0.2)
        self.assertEqual(read_log(self.log), [])

    def test_token_file_private(self):
        self.start()
        f = self.runtime / "re-dash.token"
        self.assertEqual(f.stat().st_mode & 0o777, 0o600)
        self.assertEqual(f.read_text().strip(), self.token)

    def test_run_starts_fake_claude(self):
        url = self.start()
        code, body = self.post(url, "/api/run", self.run_body())
        self.assertEqual(code, 202)
        self.assertTrue(body["id"].startswith("Elden:"))
        self.until(lambda: len(self.state(url)["game"]["thread"]) >= 3)
        self.assertEqual(self.state(url)["game"]["thread"][1]["text"], "All done.")
        self.assertEqual(self.log.read_text().count("claude -p"), 1)

    def test_post_without_token(self):
        self.assert_rejected(403, token=None)

    def test_post_wrong_token(self):
        self.assert_rejected(403, token="x" * 43)

    def test_post_wrong_origin(self):
        self.assert_rejected(403, origin="http://evil.example")

    def test_post_without_origin(self):
        self.assert_rejected(403, origin=None)

    def test_post_wrong_content_type(self):
        self.assert_rejected(403, ctype="text/plain")

    def test_post_foreign_host(self):
        self.assert_rejected(403, host="evil.example", origin="http://evil.example")

    def test_post_too_large(self):
        self.assert_rejected(413, body=self.run_body(prompt="x" * 17000))

    def test_post_bad_json(self):
        self.assert_rejected(400, body=b"[1, 2]")

    def test_post_unknown_game(self):
        self.assert_rejected(400, body=self.run_body(game="nope"))

    def test_post_symlinked_game(self):
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        (self.re_home / "targets" / "Linked").symlink_to(other)
        self.assert_rejected(400, body=self.run_body(game="Linked"))

    def test_post_unknown_backend(self):
        self.assert_rejected(400, body=self.run_body(backend="bash"))

    def test_post_empty_prompt(self):
        self.assert_rejected(400, body=self.run_body(prompt=""))

    def test_settings_roundtrip(self):
        url = self.start()
        code, saved = self.post(url, "/api/settings", {"offline": True, "bulk_model": "llama"})
        self.assertEqual(code, 200)
        self.assertEqual(saved, {"bulk_model": "llama", "offline": True, "default_backend": "auto"})
        with urllib.request.urlopen(url + "/api/settings", timeout=5) as r:
            self.assertEqual(json.load(r), saved)

    def test_settings_rejects_bad_backend(self):
        url = self.start()
        self.assertEqual(self.post(url, "/api/settings", {"default_backend": "bash"})[0], 400)
        self.assertEqual(self.post(url, "/api/settings", {"default_backend": "auto"}, token="x")[0], 403)
        self.assertFalse((self.re_home / "station.json").exists())

    def test_cancel_and_reset(self):
        self.fake_claude(pre="sleep 30 & wait")
        url = self.start()
        self.assertEqual(self.post(url, "/api/run", self.run_body())[0], 202)
        self.assertEqual(self.post(url, "/api/run", self.run_body())[0], 409)
        self.assertEqual(self.post(url, "/api/cancel", {"game": "Elden"}), (200, {"ok": True}))
        self.until(lambda: self.state(url)["status"] == "idle")
        self.assertEqual(self.post(url, "/api/cancel", {"game": "Elden"}), (200, {"ok": False}))
        self.assertEqual(self.post(url, "/api/cancel", {"game": "nope"})[0], 400)
        self.assertEqual(self.post(url, "/api/reset", {"game": "Elden"}), (200, {"ok": True}))
        thread = self.state(url)["game"]["thread"]
        self.assertEqual([e["text"] for e in thread[-2:]], ["cancelled", "new conversation"])
        self.assertEqual(self.post(url, "/api/reset", {"game": "nope"})[0], 400)

    def test_state_status_running(self):
        self.fake_claude(pre="sleep 30 & wait")
        url = self.start()
        self.assertEqual(self.state(url)["status"], "idle")
        self.assertEqual(self.post(url, "/api/run", self.run_body())[0], 202)
        self.assertEqual(self.state(url)["status"], "running")
        self.assertEqual(self.state(url, "nope")["status"], "idle")

    def test_post_unknown_route(self):
        self.assertEqual(self.post(self.start(), "/api/nope", {})[0], 404)

    def raw_post(self, url, path, data, **headers):
        """POST with exactly the given headers (plus correct Host/Origin/Content-Type/token unless overridden)."""
        port = url.rsplit(":", 1)[1]
        hdrs = {"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}",
                "Content-Type": "application/json", "Authorization": f"Bearer {self.token}", **headers}
        c = http.client.HTTPConnection("127.0.0.1", int(port), timeout=5)
        c.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
        for k, v in hdrs.items():
            if v is not None:
                c.putheader(k, v)
        c.endheaders(data)
        r = c.getresponse()
        r.read()
        c.close()
        return r

    def test_post_missing_content_length(self):
        url = self.start()
        self.assertEqual(self.raw_post(url, "/api/run", None).status, 400)

    def test_post_non_digit_content_length(self):
        url = self.start()
        data = json.dumps(self.run_body()).encode()
        for cl in (f"+{len(data)}", f"{len(data) // 10}_{len(data) % 10}", "-1"):
            self.assertEqual(self.raw_post(url, "/api/run", data, **{"Content-Length": cl}).status, 400, cl)
        time.sleep(0.2)
        self.assertEqual(read_log(self.log), [])

    def test_post_origin_null(self):
        self.assert_rejected(403, origin="null")

    def test_post_host_wrong_port(self):
        url = self.start()
        port = int(url.rsplit(":", 1)[1])
        code, _ = self.post(url, "/api/run", self.run_body(), host=f"127.0.0.1:{port + 1}")
        self.assertEqual(code, 403)

    def test_post_dotdot_game(self):
        self.assert_rejected(400, body=self.run_body(game=".."))

    def test_post_content_type_exact(self):
        self.assert_rejected(403, ctype="application/jsonx")

    def test_post_content_type_with_charset(self):
        url = self.start()
        self.assertEqual(self.post(url, "/api/run", self.run_body(), ctype="application/json; charset=utf-8")[0], 202)

    def test_post_lone_surrogate_prompt(self):
        self.assert_rejected(400, body=b'{"game": "Elden", "backend": "claude", "prompt": "a\\ud800"}')

    def test_settings_rejects_wrong_types(self):
        url = self.start()
        for bad in ({"bulk_model": []}, {"default_backend": {}}, {"offline": "yes"}):
            self.assertEqual(self.post(url, "/api/settings", bad)[0], 400, bad)
        self.assertFalse((self.re_home / "station.json").exists())

    def test_error_reason_is_fixed(self):
        url = self.start()
        r = self.raw_post(url, "/api/settings", b'{"evil reason": 1}')
        self.assertEqual((r.status, r.reason), (400, "Bad Request"))

    def test_state_lists_backends(self):
        self.assertEqual(self.state(self.start())["system"]["backends"], list(state.BACKENDS))

    def test_page_has_csp_hash_matching_script(self):
        r = self.get(self.start(), "/")
        page = r.body.decode()
        self.assertEqual(page, (Path(__file__).resolve().parent.parent / "lib/station/page.html").read_text(encoding="utf-8"))
        scripts = re.findall(r"<script>(.*?)</script>", page, re.S)
        self.assertEqual(len(scripts), 1)
        self.assertEqual(page.count("<script"), 1)
        h = base64.b64encode(hashlib.sha256(scripts[0].encode()).digest()).decode()
        self.assertIn(f"script-src 'sha256-{h}'", r.getheader("Content-Security-Policy"))
        self.assertIsNone(re.search(r"<[^>]*\s(on\w+|style)\s*=", page, re.I))
        self.assertNotIn("innerHTML", page)

    def test_page_token_survives_reload_and_polls_do_not_overlap(self):
        page = self.get(self.start(), "/").body.decode()
        self.assertIn('sessionStorage.getItem("re-dash-token")', page)
        self.assertIn('sessionStorage.setItem("re-dash-token"', page)
        self.assertNotIn('localStorage.setItem("re-dash-token"', page)
        self.assertNotIn("document.cookie", page)
        self.assertIn("token missing or stale: restart re-dash and open the printed URL", page)
        self.assertIn("if (my !== seq) return", page)
        self.assertIn("if (!inflight) tick()", page)

    def test_page_has_station_controls(self):
        page = self.get(self.start(), "/").body.decode()
        for id_ in "thread prompt backend send cancel reset settings recon mod fieldnote".split():
            self.assertIn(f'id="{id_}"', page, id_)


class StateUnit(unittest.TestCase):
    def setUp(self):
        self.tmp = tmp_home()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(state, "RE_HOME", Path(self.tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_save_settings_roundtrip(self):
        out = state.save_settings({"bulk_model": "llama", "offline": True})
        self.assertEqual(out, {"bulk_model": "llama", "offline": True, "default_backend": "auto"})
        self.assertEqual(state.load_settings(), out)

    def test_save_settings_rejects_invalid(self):
        for bad in ({"bulk_model": "gpt"}, {"offline": "yes"}, {"default_backend": "x"}, {"other": 1}):
            with self.assertRaises(ValueError, msg=bad):
                state.save_settings(bad)
        self.assertFalse((Path(self.tmp.name) / "station.json").exists())

    def test_unknown_setting_message_does_not_echo_keys(self):
        with self.assertRaises(ValueError) as c:
            state.save_settings({"<evil>": 1})
        self.assertEqual(str(c.exception), "unknown setting")

    def test_make_token_unwritable_exits(self):
        from station import server
        with mock.patch.object(state, "RE_HOME", Path(self.tmp.name) / "missing"), \
                mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": ""}):
            with self.assertRaises(SystemExit) as c:
                server.make_token()
        self.assertIn("token", str(c.exception.code))


if __name__ == "__main__":
    unittest.main()
