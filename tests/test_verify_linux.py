"""Smoke-check plumbing tests with a fake executable, not a native Aseprite build."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/verify-linux.sh"


class VerifyLinuxTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="linux smoke tests ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.binary = self.root / "aseprite"
        self.scratch = self.root / "temporary config"
        self.scratch.mkdir()
        self.trace = self.root / "invocation.json"
        self.binary.write_text(
            "#!" + sys.executable + "\n"
            "import json, os, pathlib, sys\n"
            "folder = pathlib.Path(os.environ['ASEPRITE_USER_FOLDER'])\n"
            "assert folder.is_dir() and not list(folder.iterdir())\n"
            "(folder / 'test-config').write_text('temporary')\n"
            "pathlib.Path(os.environ['SMOKE_TRACE']).write_text(json.dumps({"
            "'args': sys.argv[1:], 'folder': str(folder)}))\n"
            "print(os.environ.get('SMOKE_VERSION', 'Aseprite 1.3.18.6-dev'))\n"
            "sys.exit(int(os.environ.get('SMOKE_STATUS', '0')))\n"
        )
        self.binary.chmod(0o755)
        self.env = dict(os.environ, RUNNER_TEMP=str(self.scratch),
                        SMOKE_TRACE=str(self.trace),
                        ASEPRITE_USER_FOLDER=str(self.root / "must not use"))

    def verify(self, **environment):
        result = subprocess.run(["bash", str(SCRIPT)], cwd=self.root,
                                env=dict(self.env, **environment),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(list(self.scratch.iterdir()), [], "Temporary user folder leaked")
        self.assertFalse((self.root / "must not use").exists())
        return result

    def test_version_uses_a_fresh_isolated_user_folder(self):
        for _ in range(2):
            result = self.verify()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "Aseprite 1.3.18.6-dev")
            invocation = json.loads(self.trace.read_text())
            self.assertEqual(invocation["args"], ["--version"])
            self.assertEqual(Path(invocation["folder"]).parent, self.scratch)

    def test_nonzero_exit_is_fatal_even_with_valid_output(self):
        self.assertEqual(self.verify(SMOKE_STATUS="41").returncode, 41)

    def test_rejects_invalid_or_empty_version(self):
        for output in ("", "Something else", "Aseprite", "Aseprite invalid"):
            with self.subTest(output=output):
                self.assertNotEqual(self.verify(SMOKE_VERSION=output).returncode, 0)

    def test_rejects_missing_executable(self):
        self.binary.unlink()
        self.assertNotEqual(self.verify().returncode, 0)
        self.assertFalse(self.trace.exists())

    def test_rejects_nonexecutable_file(self):
        self.binary.chmod(0o644)
        self.assertNotEqual(self.verify().returncode, 0)
        self.assertFalse(self.trace.exists())


if __name__ == "__main__":
    unittest.main()
