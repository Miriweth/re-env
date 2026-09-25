import shutil
import subprocess
import unittest
from pathlib import Path

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

    @unittest.skipUnless(has("dotnet"), "dotnet not installed")
    def test_bepinex_gamedir_reference(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # a stand-in game: <game>/Foo_Data/Managed/Assembly-CSharp.dll built from a one-class library
            lib = tmp / "lib"; lib.mkdir()
            (lib / "Stub.csproj").write_text(
                '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>netstandard2.0</TargetFramework>'
                '<AssemblyName>Assembly-CSharp</AssemblyName></PropertyGroup></Project>')
            (lib / "PlayerHealth.cs").write_text("public class PlayerHealth { public void TakeDamage(int d) {} }")
            managed = tmp / "game/Foo_Data/Managed"; managed.mkdir(parents=True)
            r = run(["dotnet", "build", "-c", "Release", "--nologo", "-v", "quiet", "-o", str(managed)], cwd=lib)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue((managed / "Assembly-CSharp.dll").is_file())
            # with the assembly: build passes and csc really got the reference
            r = run(["bash", T / "bepinex-plugin/test.sh", str(tmp / "game")])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            # without it: the build must fail instead of silently dropping the reference
            (tmp / "empty").mkdir()
            r = run(["bash", T / "bepinex-plugin/test.sh", str(tmp / "empty")])
            self.assertNotEqual(r.returncode, 0, "build passed although Assembly-CSharp.dll is missing")

    @unittest.skipUnless(has_rust_windows_target(), "rust windows-gnu target not installed")
    def test_dll_proxy_rust_builds(self):
        r = run(["bash", T / "dll-proxy-rust/test.sh"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
