import base64
import hashlib
import http.client
import json
import os
import re
import subprocess
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from unittest import mock

from helpers import BIN, make_fake, run, tmp_home

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from station import state


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

    def start(self, *args):
        env = dict(os.environ, RE_HOME=str(self.re_home), PATH=f"{self.fake_bin}:{os.environ['PATH']}")
        p = subprocess.Popen([str(BIN / "re-dash"), "--port", "0", *args], env=env,
                             stdout=subprocess.PIPE, text=True)
        self.addCleanup(p.wait)
        self.addCleanup(p.terminate)
        line = p.stdout.readline().strip()
        m = re.fullmatch(r"re-dash on (http://127\.0\.0\.1:(\d+))", line)
        self.assertIsNotNone(m, line)
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


if __name__ == "__main__":
    unittest.main()
