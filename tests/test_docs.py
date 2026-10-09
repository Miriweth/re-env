import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Docs(unittest.TestCase):
    def test_claude_md_names_station_files(self):
        text = (ROOT / "claude" / "CLAUDE.md").read_text()
        for needle in ("MODDING_PLAN.md", "MODLOG.md", "issues.md", "FRAGE:", "re-dash"):
            self.assertIn(needle, text)
        for gone in ("notes.md", "log.md", "deepseek"):
            self.assertNotIn(gone, text)

    def test_rules_aligned_with_station_prompt(self):
        rule = "Single player, co-op and own servers only; no online competitive advantage."
        for f in ("claude/CLAUDE.md", "docs/anti-cheat.md", "lib/station/prompt.md"):
            self.assertIn(rule, " ".join((ROOT / f).read_text().split()), f)

    def test_scan_json_contract(self):
        prompt = (ROOT / "lib/station/prompt.md").read_text()
        self.assertIn("um scan --json <game>", prompt)
        self.assertIn("station/scan.json", prompt)
        self.assertIn("$RE_HOME", prompt)
        self.assertNotIn("~/re", prompt)
        self.assertIn("except `station/scan.json`", " ".join((ROOT / "claude/CLAUDE.md").read_text().split()))
        page = (ROOT / "lib/station/page.html").read_text()
        for key in ('"engine"', '"anti_cheat"', '"mod_loaders_installed"', ".label"):
            self.assertIn(key, page)

    def test_docs_name_new_models(self):
        files = [ROOT / "README.md", ROOT / "claude" / "CLAUDE.md", *sorted((ROOT / "docs").glob("*.md"))]
        old = re.compile(r"deepseek-coder|qwen2\.5-coder:14b|llama3\.1:8b")
        for f in files:
            for n, line in enumerate(f.read_text().splitlines(), 1):
                if "ollama rm" in line:
                    continue
                self.assertIsNone(old.search(line), f"{f.name}:{n}: {line}")


if __name__ == "__main__":
    unittest.main()
