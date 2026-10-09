import unittest
from pathlib import Path

from helpers import BIN, make_fake, run, tmp_home, read_log

OLLAMA_URL = "http://127.0.0.1:11434"


class FakesMixin:
    def setUp(self):
        self.tmp = tmp_home()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.fake_bin = t / "fakebin"
        self.log = t / "log"
        self.env_file = t / "env"
        self.stdin_file = t / "stdin"
        make_fake(self.fake_bin, "curl", 'exit "${FAKE_CURL_EXIT:-0}"')
        make_fake(self.fake_bin, "claude",
                  'printf "ANTHROPIC_BASE_URL=%s\\nANTHROPIC_AUTH_TOKEN=%s\\nANTHROPIC_API_KEY=%s\\n" '
                  '"$ANTHROPIC_BASE_URL" "$ANTHROPIC_AUTH_TOKEN" "${ANTHROPIC_API_KEY-unset}" > "$FAKE_ENV"')
        make_fake(self.fake_bin, "ollama",
                  'case "$1" in run) cat > "${FAKE_STDIN:-/dev/null}" ;; ps) printf "%s" "${FAKE_PS:-}" ;; esac')
        self.env = {"FAKE_LOG": str(self.log), "FAKE_ENV": str(self.env_file),
                    "FAKE_STDIN": str(self.stdin_file), "OLLAMA_URL": OLLAMA_URL}

    def call(self, name, *args, stdin=None, **extra):
        env = dict(self.env, **extra)
        return run([BIN / name, *args], env=env, stdin=stdin, fake_bin=self.fake_bin)

    def env_lines(self):
        return dict(l.split("=", 1) for l in self.env_file.read_text().splitlines())

    def calls(self):
        """Logged invocations of claude/ollama; the curl reachability probe is noise here."""
        return [l for l in read_log(self.log) if not l.startswith("curl ")]


class ClaudeLocal(FakesMixin, unittest.TestCase):
    def test_default_model_and_env(self):
        r = self.call("claude-local")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(), ["claude --model huihui_ai/qwen2.5-coder-abliterate:14b"])
        env = self.env_lines()
        self.assertEqual(env["ANTHROPIC_BASE_URL"], OLLAMA_URL)
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "ollama")
        self.assertEqual(env["ANTHROPIC_API_KEY"], "")

    def test_shortname_resolves(self):
        self.call("claude-local", "llama")
        self.assertEqual(self.calls(), ["claude --model mannix/llama3.1-8b-abliterated"])

    def test_dash_first_arg_uses_default(self):
        self.call("claude-local", "-p", "hi")
        self.assertEqual(self.calls(), ["claude --model huihui_ai/qwen2.5-coder-abliterate:14b -p hi"])

    def test_qwen3_refused(self):
        r = self.call("claude-local", "qwen3")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ask-local", r.stderr)
        self.assertEqual(self.calls(), [])

    def test_missing_claude_cli_is_named(self):
        (self.fake_bin / "claude").unlink()
        r = run([BIN / "claude-local"], env=dict(self.env, PATH=f"{self.fake_bin}:/usr/bin"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("claude", r.stderr)
        self.assertIn("user:tools", r.stderr)

    def test_unreachable(self):
        r = self.call("claude-local", FAKE_CURL_EXIT="7")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Ollama not reachable", r.stderr)
        self.assertEqual(self.calls(), [])


class AskLocal(FakesMixin, unittest.TestCase):
    def test_single_arg_is_prompt(self):
        r = self.call("ask-local", "erkläre")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(), ["ollama run huihui_ai/qwen2.5-coder-abliterate:14b"])
        self.assertEqual(self.stdin_file.read_text(), "erkläre\n")

    def test_model_prompt_and_stdin(self):
        r = self.call("ask-local", "qwen3", "kommentiere", stdin="int f(){}")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(), ["ollama run huihui_ai/qwen3-abliterated:14b"])
        self.assertEqual(self.stdin_file.read_text(), "kommentiere\n\nint f(){}\n")

    def test_large_stdin_passes(self):
        r = self.call("ask-local", "fasse zusammen", stdin="x" * 300_000)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertGreater(len(self.stdin_file.read_text()), 300_000)

    def test_no_args_usage(self):
        self.assertEqual(self.call("ask-local").returncode, 2)

    def test_too_many_args_usage(self):
        self.assertEqual(self.call("ask-local", "a", "b", "c").returncode, 2)

    def test_unreachable(self):
        r = self.call("ask-local", "hi", FAKE_CURL_EXIT="7")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Ollama not reachable", r.stderr)


class LlmOff(FakesMixin, unittest.TestCase):
    HEADER = "NAME                 ID              SIZE     PROCESSOR    CONTEXT    UNTIL\n"

    def test_stops_each_loaded_model(self):
        ps = (self.HEADER
              + "qwen2.5-coder:14b    abc123          12 GB    100% GPU     32768      4 minutes from now\n"
              + "llama3.1:8b          def456          6 GB     100% GPU     32768      4 minutes from now\n")
        r = self.call("llm-off", FAKE_PS=ps)
        self.assertEqual(r.returncode, 0, r.stderr)
        log = self.calls()
        self.assertIn("ollama stop qwen2.5-coder:14b", log)
        self.assertIn("ollama stop llama3.1:8b", log)
        self.assertIn("unloaded: qwen2.5-coder:14b", r.stdout)
        self.assertIn("unloaded: llama3.1:8b", r.stdout)

    def test_unreachable(self):
        r = self.call("llm-off", FAKE_CURL_EXIT="7")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Ollama not reachable", r.stderr)
        self.assertEqual(self.calls(), [])

    def test_nothing_loaded(self):
        r = self.call("llm-off", FAKE_PS=self.HEADER)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nothing loaded", r.stdout)
        self.assertFalse(any(l.startswith("ollama stop") for l in self.calls()))


if __name__ == "__main__":
    unittest.main()
