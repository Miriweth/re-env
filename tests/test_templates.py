import shutil
import subprocess
import unittest

from helpers import REPO, run

T = REPO / "templates"


def has(*tools):
    return all(shutil.which(t) for t in tools)


def has_rust_windows_target():
    if not shutil.which("cargo") or not shutil.which("rustup"):
        return False
    r = subprocess.run(["rustup", "target", "list", "--installed"], capture_output=True, text=True)
    return "x86_64-pc-windows-gnu" in r.stdout


class Templates(unittest.TestCase):
    @unittest.skipUnless(has("uv"), "uv not installed")
    def test_memreader_suite(self):
        r = run(["uv", "run", "pytest", "-q"], cwd=T / "memreader-py")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    @unittest.skipUnless(has("x86_64-w64-mingw32-gcc", "cmake", "ninja"), "mingw toolchain not installed")
    def test_dll_proxy_c_builds(self):
        r = run(["bash", T / "dll-proxy-c/test.sh"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    @unittest.skipUnless(has("dotnet"), "dotnet not installed")
    def test_bepinex_restores(self):
        r = run(["bash", T / "bepinex-plugin/test.sh"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    @unittest.skipUnless(has_rust_windows_target(), "rust windows-gnu target not installed")
    def test_dll_proxy_rust_builds(self):
        r = run(["bash", T / "dll-proxy-rust/test.sh"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
