import unittest
from pathlib import Path

from helpers import BIN, run, tmp_home


class ReNew(unittest.TestCase):
    def setUp(self):
        self.tmp = tmp_home()
        self.addCleanup(self.tmp.cleanup)
        self.re_home = Path(self.tmp.name) / "re"
        self.env = {"RE_HOME": str(self.re_home)}

    def call(self, *args):
        return run([BIN / "re-new", *args], env=self.env)

    def target(self, game="Elden"):
        return self.re_home / "targets" / game

    def test_creates_layout_and_notes(self):
        r = self.call("Elden")
        self.assertEqual(r.returncode, 0, r.stderr)
        for d in ("ghidra", "dumps", "mods"):
            self.assertTrue((self.target() / d).is_dir(), d)
        notes = (self.target() / "notes.md").read_text()
        self.assertTrue(notes.startswith("# Elden\n"), notes[:40])
        for h in ("## Binary", "## Findings", "## Offsets", "## Mods"):
            self.assertIn(h, notes)
        self.assertIn(str(self.target()), r.stdout)

    def test_never_overwrites_notes(self):
        self.call("Elden")
        (self.target() / "notes.md").write_text("KEEP")
        r = self.call("Elden")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.target() / "notes.md").read_text(), "KEEP")

    def test_copies_template(self):
        r = self.call("G", "memreader-py")
        self.assertEqual(r.returncode, 0, r.stderr)
        mod = self.target("G") / "mods/memreader-py"
        self.assertTrue((mod / "pyproject.toml").is_file())
        self.assertFalse((mod / ".venv").exists())
        self.assertIn(str(mod), r.stdout)

    def test_custom_modname(self):
        r = self.call("G", "dll-proxy-c", "hud")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.target("G") / "mods/hud/CMakeLists.txt").is_file())

    def test_refuses_existing_mod(self):
        self.call("G", "dll-proxy-c", "hud")
        r = self.call("G", "dll-proxy-c", "hud")
        self.assertEqual(r.returncode, 1)
        self.assertIn("already exists", r.stderr)

    def test_unknown_template_lists_available(self):
        r = self.call("G", "nope")
        self.assertEqual(r.returncode, 2)
        self.assertIn("memreader-py", r.stderr)
        self.assertIn("dll-proxy-c", r.stderr)

    def test_needs_no_cpio(self):
        # cpio is not in base and not installed by setup.sh; tar is
        self.assertNotIn("cpio", (BIN / "re-new").read_text())

    def test_no_args_usage(self):
        self.assertEqual(self.call().returncode, 2)


if __name__ == "__main__":
    unittest.main()
