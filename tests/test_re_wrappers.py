import os
import subprocess
import unittest
from pathlib import Path

from helpers import BIN, make_fake, run, tmp_home, read_log


class GamePid(unittest.TestCase):
    NAME = f"FakeGame{os.getpid()}.exe"

    def spawn(self):
        p = subprocess.Popen(["bash", "-c", f'exec -a "{self.NAME}" sleep 30'])
        self.addCleanup(p.wait)
        self.addCleanup(p.terminate)
        # wait until the exec happened and the cmdline shows the fake name
        import time
        for _ in range(200):
            try:
                argv0 = Path(f"/proc/{p.pid}/cmdline").read_bytes().split(b"\0", 1)[0]
                if argv0.endswith(self.NAME.encode()):
                    return p
            except FileNotFoundError:
                pass
            time.sleep(0.01)
        self.fail("fake game did not start")

    def test_single_match_prints_pid(self):
        p = self.spawn()
        r = run([BIN / "game-pid", self.NAME])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), str(p.pid))

    def test_two_matches_exit_2_lists_both(self):
        a, b = self.spawn(), self.spawn()
        r = run([BIN / "game-pid", self.NAME])
        self.assertEqual(r.returncode, 2)
        self.assertIn(str(a.pid), r.stderr)
        self.assertIn(str(b.pid), r.stderr)

    def test_no_match_exit_1(self):
        r = run([BIN / "game-pid", "NoSuchGame.exe"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("no process", r.stderr)

    def test_no_args_usage(self):
        self.assertEqual(run([BIN / "game-pid"]).returncode, 2)


class ToolsMixin:
    def setUp(self):
        self.tmp = tmp_home()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.re_home = t / "re"
        self.fake_bin = t / "fakebin"
        self.log = t / "log"
        self.env = {"RE_HOME": str(self.re_home), "FAKE_LOG": str(self.log)}

    def call(self, name, *args):
        return run([BIN / name, *args], env=self.env, fake_bin=self.fake_bin)


class X64dbgIn(ToolsMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        make_fake(self.fake_bin, "protontricks-launch")
        self.exe = self.re_home / "tools/x64dbg/release/x64/x64dbg.exe"

    def test_launches_in_prefix(self):
        self.exe.parent.mkdir(parents=True)
        self.exe.touch()
        r = self.call("x64dbg-in", "4242")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read_log(self.log), [f"protontricks-launch --appid 4242 {self.exe}"])

    def test_missing_exe(self):
        r = self.call("x64dbg-in", "4242")
        self.assertEqual(r.returncode, 1)
        self.assertIn("setup.sh user", r.stderr)
        self.assertEqual(read_log(self.log), [])

    def test_missing_appid(self):
        self.assertEqual(self.call("x64dbg-in").returncode, 2)


class Il2CppDumper(ToolsMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        make_fake(self.fake_bin, "dotnet", 'echo "ROLL=$DOTNET_ROLL_FORWARD" >> "$FAKE_LOG"')
        self.dll = self.re_home / "tools/il2cppdumper/Il2CppDumper.dll"

    def test_forwards_args_with_rollforward(self):
        self.dll.parent.mkdir(parents=True)
        self.dll.touch()
        r = self.call("il2cppdumper", "GameAssembly.dll", "global-metadata.dat", "out")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read_log(self.log),
                         [f"dotnet {self.dll} GameAssembly.dll global-metadata.dat out", "ROLL=Major"])

    def test_missing_dll(self):
        r = self.call("il2cppdumper", "x")
        self.assertEqual(r.returncode, 1)
        self.assertIn("setup.sh user", r.stderr)


if __name__ == "__main__":
    unittest.main()
