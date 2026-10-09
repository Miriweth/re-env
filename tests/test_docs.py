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
