import json
import os
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import make_fake, tmp_home

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from station import runs, state

INIT = '{"type":"system","subtype":"init","session_id":"sid-1"}'
ASSISTANT = '{"type":"assistant","message":{"content":[{"type":"text","text":"Found it.\\nFRAGE: start the game"}]}}'
RESULT = '{"type":"result","is_error":false,"duration_ms":5,"total_cost_usd":0.01}'
SETTINGS = dict(state.DEFAULT_SETTINGS)


class StationRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = tmp_home()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.re_home = root / "re"
        self.game_dir = self.re_home / "targets" / "Elden"
        self.game_dir.mkdir(parents=True)
        self.fake_bin = root / "fakes"
        self.log = root / "fake.log"
        self.stdin = root / "fake.stdin"
        patcher = mock.patch.object(state, "RE_HOME", self.re_home)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {"PATH": f"{self.fake_bin}:{os.environ['PATH']}"})
        env.start()
        self.addCleanup(env.stop)
        self.fake()
        self.m = runs.Manager()
        self.addCleanup(self.m.shutdown)

    def fake(self, name="claude", pre="", lines=(INIT, ASSISTANT, RESULT), post=""):
        out = "\n".join(f"echo '{x}'" for x in lines)
        make_fake(self.fake_bin, name,
                  f'echo "{name} $*" >> "{self.log}"\ncat > "{self.stdin}"\n{pre}\n{out}\n{post}')

    def run_once(self, backend="claude", prompt="hello", m=None):
        m = m or self.m
        m.start("Elden", backend, prompt)
        self.assertTrue(m.wait("Elden", 10))

    def thread(self):
        return [json.loads(x) for x in (self.game_dir / "station/thread.jsonl").read_text().splitlines()]

    def session(self):
        return json.loads((self.game_dir / "station/session.json").read_text())

    def test_command_claude_flags(self):
        cmd = runs.command("claude", "Elden", None, SETTINGS)
        self.assertEqual(cmd[:8], ["claude", "-p", "--verbose", "--output-format", "stream-json",
                                   "--permission-mode", "bypassPermissions", "--append-system-prompt"])
        self.assertEqual(cmd[8], runs.render_prompt("Elden", SETTINGS))
        self.assertEqual(len(cmd), 9)
        self.assertEqual(runs.command("auto", "Elden", "s", SETTINGS), cmd + ["--resume", "s"])
        self.assertEqual(runs.command("claude-local:qwen", "Elden", None, SETTINGS),
                         ["claude-local", "qwen"] + cmd[1:])

    def test_command_ask_local(self):
        self.assertEqual(runs.command("ask-local:qwen3", "Elden", "s", SETTINGS),
                         ["ask-local", "qwen3", "Answer the request that follows."])
        with self.assertRaises(ValueError):
            self.m.start("Elden", "bash", "x")

    def test_prompt_on_stdin_verbatim(self):
        data = b"-rf \x00 \xc3\xbc \xff"
        self.run_once(prompt=data)
        self.assertEqual(self.stdin.read_bytes(), data)

    def test_run_records_thread_and_session(self):
        self.run_once()
        t = self.thread()
        self.assertEqual([e["role"] for e in t], ["user", "assistant", "system"])
        self.assertEqual(t[0]["text"], "hello")
        self.assertEqual(t[1]["text"], "Found it.\nFRAGE: start the game")
        self.assertEqual(t[2]["text"], "done in 0.0s, $0.010")
        self.assertTrue(all(isinstance(e["t"], float) and isinstance(e["model"], str) for e in t))
        self.assertEqual(self.session(), {"claude": "sid-1"})

    def test_status_waiting_after_frage(self):
        self.assertEqual(self.m.status("Elden"), {"status": "idle", "since": None, "backend": None, "tool": None})
        self.run_once()
        st = self.m.status("Elden")
        self.assertEqual((st["status"], st["backend"]), ("waiting", "claude"))
        self.fake(lines=(INIT, '{"type":"assistant","message":{"content":[{"type":"text","text":"All done."}]}}', RESULT))
        self.run_once()
        self.assertEqual(self.m.status("Elden")["status"], "idle")

    def test_second_message_resumes(self):
        self.run_once()
        self.assertNotIn("--resume", self.log.read_text())
        self.run_once()
        self.assertIn("--resume sid-1", self.log.read_text().splitlines()[-1])

    def test_busy_while_running(self):
        self.fake(pre="sleep 5")
        rid = self.m.start("Elden", "claude", "x")
        self.assertTrue(rid.startswith("Elden:"))
        st = self.m.status("Elden")
        self.assertEqual((st["status"], st["backend"]), ("running", "claude"))
        self.assertIsInstance(st["since"], float)
        with self.assertRaises(runs.Busy):
            self.m.start("Elden", "auto", "y")

    def test_cancel_kills_group(self):
        self.fake(pre="sleep 30 & wait")
        self.m.start("Elden", "claude", "x")
        time.sleep(0.5)
        sid = self.m.runs["Elden"].proc.pid
        self.assertTrue(self.m.cancel("Elden"))
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            r = subprocess.run(["pgrep", "-s", str(sid), "-f", "sleep 30"], capture_output=True)
            if r.returncode != 0:
                break
            time.sleep(0.1)
        else:
            self.fail("sleep 30 still alive after cancel")
        self.assertTrue(self.m.wait("Elden", 6))
        self.assertFalse(self.m.cancel("Elden"))
        self.assertEqual(self.m.status("Elden")["status"], "idle")

    def test_failed_run_has_error_entry(self):
        self.fake(post="echo boom >&2; exit 3")
        self.run_once()
        self.assertEqual(self.m.status("Elden")["status"], "failed")
        self.assertEqual(self.thread()[-1]["role"], "error")
        self.assertIn("boom", self.thread()[-1]["text"])
        self.assertIn("boom", self.m.runs["Elden"].error)
        self.fake(lines=(INIT, '{"type":"result","is_error":true}'))
        self.run_once()
        self.assertEqual(self.m.status("Elden")["status"], "failed")

    def test_timeout_fails_run(self):
        self.fake(pre="sleep 30 & wait")
        with mock.patch.object(runs, "RUN_TIMEOUT", 0.3):
            self.run_once()
        self.assertEqual(self.m.status("Elden")["status"], "failed")
        self.assertIn("timeout after 0.3 s", self.thread()[-1]["text"])

    def test_reader_error_fails_run(self):
        real, calls = runs.append, []

        def flaky(*a):
            calls.append(a)
            if len(calls) == 2:
                raise OSError("disk full")
            return real(*a)

        with mock.patch.object(runs, "append", flaky):
            self.run_once()
        st = self.m.status("Elden")
        self.assertEqual(st["status"], "failed")
        self.assertIn("disk full", self.m.runs["Elden"].error)
        self.assertEqual(self.thread()[-1]["role"], "error")
        self.assertIsNotNone(self.m.runs["Elden"].proc.returncode)
        self.run_once()  # no Busy
        self.assertEqual(self.m.status("Elden")["status"], "waiting")

    def test_missing_binary_records_error(self):
        os.environ["PATH"] = str(self.fake_bin)
        (self.fake_bin / "claude").unlink()
        with self.assertRaises(OSError):
            self.m.start("Elden", "claude", "hi")
        self.assertEqual([e["role"] for e in self.thread()], ["user", "error"])
        self.assertEqual(self.m.status("Elden")["status"], "idle")

    def test_concurrent_session_saves(self):
        errors = []

        def hammer(key):
            try:
                for i in range(200):
                    runs.save_sessions("Elden", {key: str(i)})
            except OSError as e:
                errors.append(e)

        ts = [threading.Thread(target=hammer, args=(k,)) for k in ("a", "b")]
        for x in ts:
            x.start()
        for x in ts:
            x.join()
        self.assertEqual(errors, [])
        self.assertEqual([p.name for p in (self.game_dir / "station").iterdir()], ["session.json"])

    def test_non_json_lines_ignored(self):
        tool = '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"um scan\\nmore"}}]}}'
        self.fake(lines=("not json", INIT, "[1,2]", '{"type":"weird"}', '{"type":"assistant","message":"x"}', tool, ASSISTANT, "{broken", RESULT))
        self.run_once()
        t = self.thread()
        self.assertEqual([e["role"] for e in t], ["user", "tool", "assistant", "system"])
        self.assertEqual(t[1]["text"], "Bash: um scan")

    def test_ask_local_single_assistant_entry(self):
        self.fake("ask-local", lines=("line one", "line two", "FRAGE: which route?"))
        self.run_once("ask-local:qwen", "summarise")
        t = self.thread()
        self.assertEqual([e["role"] for e in t], ["user", "assistant"])
        self.assertEqual(t[1]["text"], "line one\nline two\nFRAGE: which route?")
        self.assertIn("ask-local qwen Answer the request that follows.", self.log.read_text())
        self.assertEqual(self.stdin.read_text(), "summarise")
        self.assertEqual(self.m.status("Elden")["status"], "waiting")
        self.assertFalse((self.game_dir / "station/session.json").exists())

    def test_offline_setting_in_prompt(self):
        self.run_once()
        self.assertNotIn("Offline mode is ON", self.log.read_text())
        state.save_settings({"offline": True, "bulk_model": "llama"})
        self.run_once()
        last = self.log.read_text().split("claude -p")[-1]
        self.assertIn("Offline mode is ON", last)
        self.assertIn("ask-local llama", last)
        self.assertIn("targets/Elden/", last)
        self.assertNotIn("{game}", last)

    def test_restart_keeps_thread_and_session(self):
        self.run_once()
        self.m.shutdown()
        m2 = runs.Manager()
        self.addCleanup(m2.shutdown)
        self.assertEqual(m2.status("Elden")["status"], "idle")
        self.assertEqual(len(self.thread()), 3)
        self.run_once(m=m2)
        self.assertEqual(len(self.thread()), 6)
        self.assertIn("--resume sid-1", self.log.read_text().splitlines()[-1])

    def test_claude_local_own_session_and_reset(self):
        self.run_once()
        self.fake("claude-local", lines=(INIT.replace("sid-1", "sid-2"), RESULT))
        self.run_once("claude-local:llama")
        self.assertEqual(self.session(), {"claude": "sid-1", "claude-local": "sid-2"})
        self.m.reset("Elden")
        self.assertEqual(self.session(), {})
        self.assertEqual(self.thread()[-1]["role"], "system")
        self.assertEqual(self.thread()[-1]["text"], "new conversation")

    def test_child_env_minimal(self):
        envfile = Path(self.tmp.name) / "env.out"
        self.fake(pre=f'env > "{envfile}"')
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "secret", "LANG": "C.UTF-8"}):
            self.run_once()
        env = envfile.read_text()
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertIn("ECC_GATEGUARD=off", env.splitlines())
        self.assertIn("LANG=C.UTF-8", env.splitlines())
        self.assertLessEqual(set(runs.child_env()),
                             {"PATH", "HOME", "XDG_RUNTIME_DIR", "OLLAMA_URL", "TERM", "LANG", "ECC_GATEGUARD"})


if __name__ == "__main__":
    unittest.main()
