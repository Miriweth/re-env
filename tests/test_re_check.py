import re
import unittest
from pathlib import Path

from helpers import BIN, run, tmp_home


class ReCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tmp_home()
        self.addCleanup(self.tmp.cleanup)
        self.re_home = Path(self.tmp.name) / "re"
        self.re_home.mkdir()
        self.env = {"RE_HOME": str(self.re_home)}

    def call(self, *args):
        return run([BIN / "re-check", *args], env=self.env)

    def test_help(self):
        r = self.call("--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        for s in ("--full", "--only", "--gamedir"):
            self.assertIn(s, r.stdout)

    def test_only_workspace_fail_then_pass(self):
        r = self.call("--only", "workspace")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stdout.startswith("FAIL"), r.stdout)
        (self.re_home / "CLAUDE.md").touch()
        (self.re_home / ".mcp.json").touch()
        r = self.call("--only", "workspace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith("PASS"), r.stdout)

    def test_unknown_only(self):
        r = self.call("--only", "nope")
        self.assertEqual(r.returncode, 2)
        self.assertIn("workspace", r.stderr)

    def test_line_format(self):
        line = self.call("--only", "workspace").stdout.splitlines()[0]
        self.assertRegex(line, r"^(PASS|WARN|FAIL) {1,4}workspace\s+\S")

    def test_dotnet_fails_without_il2cppdumper(self):
        r = self.call("--only", "dotnet")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(r.stdout.startswith("FAIL"), r.stdout)
        self.assertIn("user:downloads", r.stdout)

    def test_options_need_values(self):
        for args in (("--only",), ("--gamedir",), ("--full", "--gamedir")):
            r = self.call(*args)
            self.assertEqual(r.returncode, 2, args)

    def test_only_accepts_several_names(self):
        r = self.call("--only", "workspace,x64dbg")
        names = [l.split()[1] for l in r.stdout.splitlines()]
        self.assertEqual(names, ["workspace", "x64dbg"])


if __name__ == "__main__":
    unittest.main()
