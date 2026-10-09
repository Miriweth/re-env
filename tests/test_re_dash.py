import base64
import hashlib
import http.client
import json
import os
import re
import subprocess
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from helpers import BIN, make_fake, run, tmp_home


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
        (t / "notes.md").write_text("# Elden\nnotes here\n")
        (t / "log.md").write_text("".join(f"line {i}\n" for i in range(1, 31)))
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

    def state(self, url):
        with urllib.request.urlopen(url + "/api/state", timeout=5) as r:
            return json.load(r)

    def test_help(self):
        r = run([BIN / "re-dash", "--help"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--port", r.stdout)

    def test_listens_on_loopback(self):
        self.assertTrue(self.start().startswith("http://127.0.0.1:"))

    def test_state_target(self):
        t = self.state(self.start())["targets"]
        self.assertEqual([x["name"] for x in t], ["Elden"])
        self.assertEqual(t[0]["notes"], "# Elden\nnotes here\n")
        self.assertEqual(t[0]["log"].splitlines(), [f"line {i}" for i in range(11, 31)])
        self.assertEqual(t[0]["mods"], ["a"])

    def test_state_tools(self):
        s = self.state(self.start())
        self.assertIn("qwen", s["ollama"])
        self.assertEqual(s["vram"], {"used": 4096, "total": 16384})
        self.assertIsNone(s["recheck"])

    def test_recheck_last(self):
        (self.re_home / "re-check.last").write_text("# re-check\nPASS gpu x\n")
        rc = self.state(self.start())["recheck"]
        self.assertEqual(rc["text"], "# re-check\nPASS gpu x\n")
        self.assertIsInstance(rc["mtime"], int)

    def test_failing_tools(self):
        make_fake(self.fake_bin, "nvidia-smi", "exit 1")
        make_fake(self.fake_bin, "ollama", "exit 1")
        s = self.state(self.start())
        self.assertIsNone(s["vram"])
        self.assertIn("unavailable", s["ollama"])

    def test_unparseable_vram(self):
        make_fake(self.fake_bin, "nvidia-smi", 'echo "garbage"')
        self.assertIsNone(self.state(self.start())["vram"])

    def test_missing_targets_dir(self):
        import shutil
        shutil.rmtree(self.re_home / "targets")
        self.assertEqual(self.state(self.start())["targets"], [])

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

    def test_symlinked_notes_is_empty(self):
        secret = self.re_home / "secret.txt"
        secret.write_text("TOP SECRET")
        t = self.re_home / "targets" / "Elden"
        (t / "notes.md").unlink()
        (t / "notes.md").symlink_to(secret)
        self.assertEqual(self.state(self.start())["targets"][0]["notes"], "")

    def test_symlinked_dirs_skipped(self):
        other = Path(self.tmp.name) / "other"
        (other / "mods/zz").mkdir(parents=True)
        (self.re_home / "targets" / "Linked").symlink_to(other)
        (self.re_home / "targets" / "Elden" / "mods" / "lnk").symlink_to(other)
        t = self.state(self.start())["targets"]
        self.assertEqual([x["name"] for x in t], ["Elden"])
        self.assertEqual(t[0]["mods"], ["a"])

    def test_fifo_notes_does_not_hang(self):
        t = self.re_home / "targets" / "Elden"
        (t / "notes.md").unlink()
        os.mkfifo(t / "notes.md")
        self.assertEqual(self.state(self.start())["targets"][0]["notes"], "")

    def test_symlinked_recheck_last_is_empty(self):
        secret = self.re_home / "secret.txt"
        secret.write_text("TOP SECRET")
        (self.re_home / "re-check.last").symlink_to(secret)
        self.assertEqual(self.state(self.start())["recheck"]["text"], "")

    def test_big_log_last_lines(self):
        t = self.re_home / "targets" / "Elden"
        (t / "log.md").write_text("".join(f"line {i}\n" for i in range(1, 100001)))
        log = self.state(self.start())["targets"][0]["log"]
        self.assertEqual(log.splitlines(), [f"line {i}" for i in range(99981, 100001)])

    def test_big_notes_truncated(self):
        t = self.re_home / "targets" / "Elden"
        (t / "notes.md").write_text("x" * 200000)
        notes = self.state(self.start())["targets"][0]["notes"]
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
        self.assertEqual(self.state(url)["targets"][0]["notes"], "# Elden\nnotes here\n")
        (self.re_home / "targets" / "Elden" / "notes.md").write_text("changed")
        self.assertEqual(self.state(url)["targets"][0]["notes"], "# Elden\nnotes here\n")

    def test_page_keeps_scroll_and_skips_identical(self):
        page = self.get(self.start(), "/").body.decode()
        self.assertIn("scrollTop", page)
        self.assertIn("lastText", page)


if __name__ == "__main__":
    unittest.main()
