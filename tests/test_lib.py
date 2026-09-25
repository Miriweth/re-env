import hashlib
import json
import re
import unittest
from pathlib import Path

from helpers import REPO, run, tmp_home

VARS = ["GHYDRA_ZIP", "GHYDRA_BRIDGE", "X64DBG", "IL2CPPDUMPER", "BEPINEX"]


def bash(snippet, env=None):
    return run(["bash", "-c",
                f'source "{REPO}/lib/common.sh"; source "{REPO}/lib/fetch.sh"; '
                f'source "{REPO}/lib/render.sh"; {snippet}'], env=env)


class FetchVerified(unittest.TestCase):
    def setUp(self):
        self.tmp = tmp_home()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.src = t / "artifact.bin"
        self.src.write_bytes(b"re-env fixture\n" * 100)
        self.sha = hashlib.sha256(self.src.read_bytes()).hexdigest()
        self.url = f"file://{self.src}"
        self.dest = t / "downloads/artifact.bin"
        self.dest.parent.mkdir()

    def fetch(self, sha):
        return bash(f'fetch_verified "{self.url}" {sha} "{self.dest}"')

    def test_fetch_downloads_and_verifies(self):
        r = self.fetch(self.sha)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.dest.read_bytes(), self.src.read_bytes())

    def test_fetch_skips_when_present(self):
        self.fetch(self.sha)
        r = self.fetch(self.sha)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("present:", r.stdout)

    def test_fetch_bad_sha_leaves_nothing(self):
        r = self.fetch("0" * 64)
        self.assertEqual(r.returncode, 1)
        self.assertIn("checksum", r.stderr)
        self.assertFalse(self.dest.exists())
        self.assertFalse(Path(str(self.dest) + ".part").exists())

    def test_extract_zip(self):
        t = Path(self.tmp.name)
        import zipfile
        with zipfile.ZipFile(t / "a.zip", "w") as z:
            z.writestr("hello.txt", "hi")
        r = bash(f'extract_zip "{t}/a.zip" "{t}/out/sub"')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((t / "out/sub/hello.txt").read_text(), "hi")


class Render(unittest.TestCase):
    def test_render_replaces_re_home_and_is_json(self):
        with tmp_home() as tmp:
            dest = Path(tmp) / ".mcp.json"
            r = bash(f'render_template "$RE_ENV/mcp/mcp.json.tmpl" "{dest}"', env={"RE_HOME": "/x/y re"})
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads(dest.read_text())
        srv = data["mcpServers"]["ghydra"]
        self.assertEqual(srv["command"], "uv")
        self.assertEqual(srv["args"], ["run", "/x/y re/tools/ghydra/bridge_mcp_hydra.py"])
        self.assertEqual(srv["env"]["GHIDRA_HYDRA_HOST"], "localhost")


class VersionsEnv(unittest.TestCase):
    def test_versions_env_complete(self):
        kv = dict(l.split("=", 1) for l in (REPO / "versions.env").read_text().splitlines()
                  if l and not l.startswith("#"))
        for v in VARS:
            self.assertRegex(kv[f"{v}_URL"], r"^https://github\.com/[^/]+/[^/]+/releases/download/")
            self.assertRegex(kv[f"{v}_SHA256"], r"^[0-9a-f]{64}$")
        self.assertEqual(len(kv), 10)
        self.assertIn("ghidra12.1.2", kv["GHYDRA_ZIP_URL"])
        self.assertIn("snapshot_2026-05-27_12-11.zip", kv["X64DBG_URL"])
        self.assertIn("Il2CppDumper-net7-v6.7.46.zip", kv["IL2CPPDUMPER_URL"])
        self.assertIn("BepInEx_win_x64_5.4.23.5.zip", kv["BEPINEX_URL"])


if __name__ == "__main__":
    unittest.main()
