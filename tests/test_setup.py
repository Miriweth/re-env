import unittest
from pathlib import Path

from helpers import REPO, make_fake, run, tmp_home, read_log

SETUP = REPO / "setup.sh"


class SetupDispatch(unittest.TestCase):
    def test_unknown_phase_exits_2(self):
        r = run([SETUP, "bogus"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown phase", r.stderr)

    def test_help_lists_phases(self):
        r = run([SETUP, "--help"])
        self.assertEqual(r.returncode, 0)
        for p in ("pacman", "system", "user"):
            self.assertIn(p, r.stdout)

    def test_bash_syntax(self):
        files = [REPO / "setup.sh", *sorted((REPO / "lib").glob("*.sh")), *sorted((REPO / "bin").iterdir())]
        self.assertGreater(len(files), 10)
        for f in files:
            if "bash" not in f.open().readline():  # bin/re-dash is Python
                continue
            r = run(["bash", "-n", f])
            self.assertEqual(r.returncode, 0, f"{f}: {r.stderr}")


class FakeSudoMixin:
    def setUp(self):
        self.tmp = tmp_home()
        self.addCleanup(self.tmp.cleanup)
        self.fake_bin = Path(self.tmp.name) / "fakebin"
        self.log = Path(self.tmp.name) / "log"
        make_fake(self.fake_bin, "sudo")
        self.env = {"FAKE_LOG": str(self.log)}

    def run_phase(self, phase):
        return run([SETUP, phase], env=self.env, fake_bin=self.fake_bin)


class PacmanPhase(FakeSudoMixin, unittest.TestCase):
    def test_uses_sudo_pacman_needed_with_all_packages(self):
        r = self.run_phase("pacman")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [l for l in read_log(self.log) if l.startswith("sudo pacman")]
        self.assertEqual(len(lines), 1, read_log(self.log))
        line = lines[0]
        self.assertIn("-S --needed --noconfirm", line)
        for pkg in ("ollama", "ollama-cuda", "ghidra", "jdk21-openjdk", "rizin", "rz-ghidra",
                    "cutter", "radare2", "binwalk", "scanmem", "protontricks", "dotnet-sdk",
                    "mingw-w64-gcc", "cmake", "ninja", "rustup", "uv", "flatpak", "unzip"):
            self.assertIn(f" {pkg}", line + " ")

    def test_mentions_cuda_size(self):
        r = self.run_phase("pacman")
        self.assertIn("cuda package (5.2 GB)", r.stdout)


class SystemPhase(FakeSudoMixin, unittest.TestCase):
    def test_installs_dropins_and_enables_ollama(self):
        r = self.run_phase("system")
        self.assertEqual(r.returncode, 0, r.stderr)
        log = read_log(self.log)
        for s in ("install -Dm644", "system/ollama-re-env.conf",
                  "/etc/systemd/system/ollama.service.d/re-env.conf",
                  "system/10-ptrace.conf", "/etc/sysctl.d/10-ptrace.conf",
                  "sysctl --system", "systemctl daemon-reload", "systemctl enable --now ollama",
                  "systemctl restart ollama"):
            self.assertTrue(any(s in l for l in log), f"{s!r} not in {log}")

    def test_failed_phase_is_named(self):
        make_fake(self.fake_bin, "sudo", 'exit 1')
        r = self.run_phase("system")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("failed in phase system", r.stderr)


class SystemFiles(unittest.TestCase):
    def test_ollama_dropin_exact_values(self):
        txt = (REPO / "system/ollama-re-env.conf").read_text()
        self.assertIn("[Service]", txt)
        for kv in ('Environment="OLLAMA_CONTEXT_LENGTH=32768"',
                   'Environment="OLLAMA_FLASH_ATTENTION=1"',
                   'Environment="OLLAMA_KV_CACHE_TYPE=q8_0"',
                   'Environment="OLLAMA_KEEP_ALIVE=10m"'):
            self.assertIn(kv, txt)

    def test_ptrace_conf(self):
        self.assertIn("kernel.yama.ptrace_scope = 0", (REPO / "system/10-ptrace.conf").read_text())

    def test_gitignore_keeps_root_bin_but_ignores_template_build_dirs(self):
        txt = (REPO / ".gitignore").read_text().splitlines()
        self.assertNotIn("bin/", txt)
        self.assertNotIn("bin/obj/", txt)
        self.assertIn("templates/**/bin/", txt)
        self.assertIn("templates/**/obj/", txt)
        self.assertIn("/downloads/", txt)


class CommonLib(unittest.TestCase):
    def bash(self, snippet, env=None):
        return run(["bash", "-c", f'source "{REPO}/lib/common.sh"; {snippet}'], env=env)

    def test_resolve_model(self):
        for short, tag in (("qwen", "huihui_ai/qwen2.5-coder-abliterate:14b"), ("qwen3", "huihui_ai/qwen3-abliterated:14b"),
                           ("llama", "mannix/llama3.1-8b-abliterated"), ("foo:1b", "foo:1b")):
            r = self.bash(f"resolve_model {short}")
            self.assertEqual(r.stdout.strip(), tag)

    def test_defaults(self):
        r = self.bash('echo "$RE_ENV|$RE_HOME|$LOCAL_BIN|$OLLAMA_URL|$DEFAULT_MODEL"',
                      env={"HOME": "/h"})
        self.assertEqual(r.stdout.strip(),
                         f"{REPO}|/h/re|/h/.local/bin|http://localhost:11434|huihui_ai/qwen2.5-coder-abliterate:14b")

    def test_die_and_usage_die(self):
        r = self.bash("die kaputt")
        self.assertEqual((r.returncode, r.stderr.strip()), (1, "error: kaputt"))
        r = self.bash("usage_die falsch")
        self.assertEqual(r.returncode, 2)
        self.assertIn("falsch", r.stderr)

    def test_ghidra_version_dies_without_properties(self):
        with tmp_home() as tmp:
            r = self.bash("ghidra_version", env={"GHIDRA_ROOT": tmp})
        self.assertEqual(r.returncode, 1)
        self.assertIn("application.properties", r.stderr)

    def test_ghidra_user_dir_from_properties(self):
        with tmp_home() as tmp:
            root = Path(tmp) / "ghidra"
            (root / "Ghidra").mkdir(parents=True)
            (root / "Ghidra/application.properties").write_text(
                "application.name=Ghidra\napplication.version=12.1.2\napplication.release.name=PUBLIC\n")
            r = self.bash("ghidra_version; ghidra_user_dir", env={"GHIDRA_ROOT": str(root), "HOME": "/h"})
        self.assertEqual(r.stdout.split(), ["12.1.2", "/h/.config/ghidra/ghidra_12.1.2_PUBLIC"])



class UserPhase(unittest.TestCase):
    def setUp(self):
        self.tmp = tmp_home()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.re_home = t / "re"
        self.local_bin = t / "lbin"
        self.fake_bin = t / "fakebin"
        self.log = t / "log"
        self.env = {"RE_HOME": str(self.re_home), "LOCAL_BIN": str(self.local_bin),
                    "FAKE_LOG": str(self.log)}

    def test_user_workspace_links_and_renders(self):
        r = run([SETUP, "user:workspace"], env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = __import__("json").loads((self.re_home / ".mcp.json").read_text())
        self.assertEqual(data["mcpServers"]["ghydra"]["args"][1],
                         f"{self.re_home}/tools/ghydra/bridge_mcp_hydra.py")
        claude_md = self.re_home / "CLAUDE.md"
        self.assertTrue(claude_md.is_symlink())
        self.assertEqual(claude_md.resolve(), (REPO / "claude/CLAUDE.md").resolve())
        for script in (REPO / "bin").iterdir():
            link = self.local_bin / script.name
            self.assertTrue(link.is_symlink(), script.name)
            self.assertEqual(link.resolve(), script.resolve())

    def test_setup_pulls_new_tags(self):
        make_fake(self.fake_bin, "ollama")
        r = run([SETUP, "user:models"], env=self.env, fake_bin=self.fake_bin)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("20 GB", r.stdout)
        self.assertEqual(read_log(self.log), ["ollama pull huihui_ai/qwen2.5-coder-abliterate:14b",
                                              "ollama pull huihui_ai/qwen3-abliterated:14b",
                                              "ollama pull mannix/llama3.1-8b-abliterated"])
        for old in ("qwen2.5-coder:14b", "deepseek-coder-v2:16b", "llama3.1:8b"):
            self.assertNotIn(old, "\n".join(read_log(self.log)))

    def test_user_dirs(self):
        r = run([SETUP, "user:dirs"], env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        for d in ("tools", "targets"):
            self.assertTrue((self.re_home / d).is_dir(), d)

    def test_unknown_user_step_exits_2(self):
        r = run([SETUP, "user:bogus"], env=self.env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown step", r.stderr)


class ClaudeMd(unittest.TestCase):
    def test_claude_md_sections(self):
        txt = (REPO / "claude/CLAUDE.md").read_text()
        heads = [l[3:].strip() for l in txt.splitlines() if l.startswith("## ")]
        self.assertEqual(heads, ["Purpose", "Layout", "Requests", "Ghidra via MCP", "Local models", "Mod loop", "Rules"])
        for s in ("MODLOG.md", "ask-local", "llm-off", "re-new", "PROTON_LOG=1", "docs/anti-cheat.md", "anti-cheat"):
            self.assertIn(s, txt)


class Docs(unittest.TestCase):
    def test_docs_exist_with_sections(self):
        for f in ("workflow.md", "anti-cheat.md", "ue4ss.md", "using.md"):
            self.assertTrue((REPO / "docs" / f).is_file(), f)
        heads = [l[3:].strip() for l in (REPO / "docs/workflow.md").read_text().splitlines() if l.startswith("## ")]
        self.assertEqual(heads, ["First start", "New game", "Static analysis", "Dynamic analysis",
                                 "Unity games", "Mods", "Local models", "Maintenance"])
        readme = (REPO / "README.md").read_text()
        for s in ("./setup.sh pacman", "./setup.sh system", "./setup.sh user", "re-check", "docs/workflow.md", "docs/using.md"):
            self.assertIn(s, readme)
        self.assertNotIn("flathub", readme.split("## Install")[0])


if __name__ == "__main__":
    unittest.main()
