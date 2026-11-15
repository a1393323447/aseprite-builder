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
        self.host_home = self.root / "inherited home"
        self.host_config = self.root / "inherited xdg config"
        self.sentinels = {
            self.host_home / ".asepriterc": b"legacy configuration must stay here\n",
            self.host_home / ".config/aseprite/data/strings/en.ini": b"home resource sentinel\n",
            self.host_config / "aseprite/data/strings/en.ini": b"xdg resource sentinel\n",
        }
        for path, data in self.sentinels.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.binary.write_text(
            "#!" + sys.executable + "\n"
            "import json, os, pathlib, sys\n"
            "folder = pathlib.Path(os.environ['ASEPRITE_USER_FOLDER'])\n"
            "assert folder.is_dir() and not list(folder.iterdir())\n"
            # Model v1.3.18.6 ConfigModule migration and ResourceFinder lookups.
            # All inherited locations are fixtures; never use the real HOME.
            "home = pathlib.Path(os.environ['HOME'])\n"
            "config = pathlib.Path(os.environ.get('XDG_CONFIG_HOME') or home / '.config')\n"
            "legacy = home / '.asepriterc'\n"
            "migrated = legacy.is_file()\n"
            "if migrated: legacy.rename(folder / 'aseprite.ini')\n"
            "resource = config / 'aseprite/data/strings/en.ini'\n"
            "loaded_resource = resource.read_text() if resource.is_file() else None\n"
            "(folder / 'test-config').write_text('temporary')\n"
            "pathlib.Path(os.environ['SMOKE_TRACE']).write_text(json.dumps({"
            "'args': sys.argv[1:], 'folder': str(folder), 'home': str(home),"
            "'config': str(config), 'migrated': migrated, 'resource': loaded_resource}))\n"
            "print(os.environ.get('SMOKE_VERSION', 'Aseprite 1.3.18.6-dev'))\n"
            "sys.exit(int(os.environ.get('SMOKE_STATUS', '0')))\n"
        )
        self.binary.chmod(0o755)
        self.env = dict(os.environ, RUNNER_TEMP=str(self.scratch),
                        SMOKE_TRACE=str(self.trace),
                        HOME=str(self.host_home), XDG_CONFIG_HOME=str(self.host_config),
                        ASEPRITE_USER_FOLDER=str(self.root / "must not use"))

    def verify(self, *, omit_xdg=False, **environment):
        env = dict(self.env, **environment)
        if omit_xdg:
            env.pop("XDG_CONFIG_HOME", None)
        result = subprocess.run(["bash", str(SCRIPT)], cwd=self.root,
                                env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(list(self.scratch.iterdir()), [], "Temporary user folder leaked")
        self.assertFalse((self.root / "must not use").exists())
        for path, data in self.sentinels.items():
            self.assertTrue(path.is_file(), "Inherited file moved or removed: " + str(path))
            self.assertEqual(path.read_bytes(), data, "Inherited file changed: " + str(path))
        return result

    def test_version_uses_a_fresh_isolated_user_folder(self):
        previous = None
        for _ in range(2):
            result = self.verify()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "Aseprite 1.3.18.6-dev")
            invocation = json.loads(self.trace.read_text())
            self.assertEqual(invocation["args"], ["--version"])
            paths = [Path(invocation[key]) for key in ("folder", "home", "config")]
            self.assertEqual(len(set(paths)), 3)
            for path in paths:
                self.assertEqual(path.parent.parent, self.scratch)
                self.assertFalse(path.exists(), "Temporary environment directory leaked")
            self.assertEqual(len({path.parent for path in paths}), 1)
            self.assertNotEqual(paths[0].parent, previous)
            previous = paths[0].parent
            self.assertFalse(invocation["migrated"])
            self.assertIsNone(invocation["resource"])

    def test_legacy_config_and_xdg_resources_are_not_used(self):
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        invocation = json.loads(self.trace.read_text())
        self.assertFalse(invocation["migrated"])
        self.assertIsNone(invocation["resource"])

    def test_unset_xdg_does_not_expose_inherited_home_resources(self):
        result = self.verify(omit_xdg=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        invocation = json.loads(self.trace.read_text())
        self.assertFalse(invocation["migrated"])
        self.assertIsNone(invocation["resource"])
        self.assertNotEqual(Path(invocation["home"]), self.host_home)

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
