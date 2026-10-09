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

    def test_writes_last_file(self):
        r = self.call("--only", "workspace")
        last = (self.re_home / "re-check.last").read_text().splitlines()
        self.assertRegex(last[0], r"^# re-check --only workspace at \d{4}-\d\d-\d\dT")
        self.assertEqual(last[1:], r.stdout.splitlines())

    def test_last_file_is_truncated_each_run(self):
        self.call("--only", "workspace,x64dbg")
        self.call("--only", "workspace")
        self.assertEqual(len((self.re_home / "re-check.last").read_text().splitlines()), 2)

    def test_symlinked_last_is_replaced_not_followed(self):
        other = Path(self.tmp.name) / "other"
        other.write_text("keep me\n")
        last = self.re_home / "re-check.last"
        last.symlink_to(other)
        self.call("--only", "workspace")
        self.assertEqual(other.read_text(), "keep me\n")
        self.assertTrue(last.is_file() and not last.is_symlink())
        self.assertTrue(last.read_text().startswith("# re-check"))

    def test_no_temp_files_left(self):
        self.call("--only", "workspace")
        self.assertEqual(sorted(p.name for p in self.re_home.iterdir()), ["re-check.last"])

    def test_missing_re_home_is_no_error(self):
        self.re_home.rmdir()
        r = self.call("--only", "workspace")
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("No such file", r.stderr)
        self.assertFalse(self.re_home.exists())

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
