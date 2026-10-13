"""Portable regression tests for the macOS packaging shell script.

These are plumbing tests, not real code-signature or native macOS application
tests. Linux stubs model uname, otool, ditto's layout/modes/symlinks, and codesign's failures;
the release job must still perform the real signing and relocated smoke tests
on macOS. Run with: python3 -m unittest discover -s tests -v
"""

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/package-macos.sh"


TOOL_STUB = r'''
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import zipfile

name = Path(sys.argv[0]).name
args = sys.argv[1:]
trace = Path(os.environ["PACKAGING_TEST_TRACE"])
previous = [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
event = {"tool": name, "args": args, "cwd": os.getcwd(),
         "output_exists": Path(os.environ["PACKAGING_TEST_OUTPUT"]).exists()}
if name == "codesign" and "--verify" in args:
    event["verify_number"] = 1 + sum(
        row["tool"] == "codesign" and "--verify" in row["args"] for row in previous)
with trace.open("a") as log:
    log.write(json.dumps(event) + "\n")

def fail(message):
    print(message, file=sys.stderr)
    sys.exit(37)

if name == "uname":
    print(os.environ.get("FAKE_UNAME", "Darwin"))
elif name == "otool":
    if os.environ.get("FAKE_FAIL_OTOOL"):
        fail("injected dependency inspection failure")
    print(args[-1] + ":")
    dependency = os.environ.get("FAKE_DEPENDENCY", "/usr/lib/libc++.1.dylib")
    print("\t" + dependency + " (compatibility version 1.0.0, current version 1.0.0)")
    print("\t/System/Library/Frameworks/Cocoa.framework/Versions/A/Cocoa (compatibility version 1.0.0, current version 1.0.0)")
elif name == "codesign":
    app = Path(args[-1])
    binary = app / "Contents/MacOS/aseprite"
    signature = app / "Contents/.plumbing-test-signature"
    if "--sign" in args:
        if os.environ.get("FAKE_FAIL_SIGN"):
            fail("injected signing failure")
        signature.write_text(hashlib.sha256(binary.read_bytes()).hexdigest())
    elif "--verify" in args:
        if str(event["verify_number"]) == os.environ.get("FAKE_FAIL_VERIFY_N"):
            fail("injected signature-verification failure")
        if not signature.is_file() or signature.read_text() != hashlib.sha256(binary.read_bytes()).hexdigest():
            fail("application bytes differ from the signed bytes")
    else:
        fail("unexpected codesign invocation: " + repr(args))
elif name == "ditto":
    source, destination = map(Path, args[-2:])
    if "-c" in args:
        if os.environ.get("FAKE_FAIL_ARCHIVE"):
            destination.write_bytes(b"partial ZIP")
            fail("injected archive failure")
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(source.rglob("*")):
                relative = path.relative_to(source)
                if "--keepParent" in args:
                    relative = Path(source.name) / relative
                label = relative.as_posix()
                mode = path.lstat().st_mode
                info = zipfile.ZipInfo(label + ("/" if stat.S_ISDIR(mode) else ""))
                info.create_system = 3
                info.external_attr = mode << 16
                if path.is_symlink():
                    data = os.readlink(path).encode()
                elif path.is_dir():
                    data = b""
                else:
                    data = path.read_bytes()
                archive.writestr(info, data)
    elif "-x" in args:
        destination.mkdir(parents=True, exist_ok=True)
        if os.environ.get("FAKE_FAIL_EXTRACT"):
            fail("injected extraction failure")
        with zipfile.ZipFile(source) as archive:
            for info in archive.infolist():
                path = destination / info.filename
                mode = info.external_attr >> 16
                path.parent.mkdir(parents=True, exist_ok=True)
                if stat.S_ISLNK(mode):
                    path.symlink_to(archive.read(info).decode())
                elif info.is_dir():
                    path.mkdir(exist_ok=True)
                    path.chmod(stat.S_IMODE(mode))
                else:
                    path.write_bytes(archive.read(info))
                    path.chmod(stat.S_IMODE(mode))
        fault = os.environ.get("FAKE_EXTRACT_FAULT")
        if fault == "binary_corruption":
            with (destination / "Aseprite.app/Contents/MacOS/aseprite").open("a") as binary:
                binary.write("\n# archive extraction damaged signed content\n")
        elif fault == "launcher_not_executable":
            (destination / "aseprite").chmod(0o644)
        elif fault == "absolute_symlink":
            (destination / "archive-only-unsafe-link").symlink_to(destination / "aseprite.ini")
    else:
        if source.is_dir():
            shutil.copytree(source, destination, symlinks=True, dirs_exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination, follow_symlinks=False)
else:
    fail("unexpected stub name: " + name)
'''


APP_STUB = r'''
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
if args == ["--version"]:
    trace = Path(os.environ["PACKAGING_TEST_TRACE"])
    previous = [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
    count = 1 + sum(row["tool"] == "application" for row in previous)
    event = {"tool": "application", "args": args, "binary": str(Path(__file__).absolute()),
             "cwd": os.getcwd(), "version_number": count,
             "user_folder": os.environ.get("ASEPRITE_USER_FOLDER"),
             "output_exists": Path(os.environ["PACKAGING_TEST_OUTPUT"]).exists()}
    with trace.open("a") as log:
        log.write(json.dumps(event) + "\n")
    if str(count) == os.environ.get("FAKE_FAIL_VERSION_N"):
        print("Aseprite 1.0 test binary")
        sys.exit(41)
    if str(count) == os.environ.get("FAKE_BAD_VERSION_N"):
        print("An unrelated executable")
    else:
        print("Aseprite 1.0 test binary")
else:
    print(json.dumps(args))
'''


class PackageMacOSTests(unittest.TestCase):
    """Contract tests with intentionally non-native application/signature stubs."""

    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "macOS packaging script is missing: " + str(SCRIPT))
        self.temporary = tempfile.TemporaryDirectory(prefix="macos packaging tests ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "build with spaces/bin"
        self.bin.mkdir(parents=True)
        self.app = self.bin / "Aseprite.app"
        self.binary = self.app / "Contents/MacOS/aseprite"
        self.binary.parent.mkdir(parents=True)
        self.binary.write_text("#!" + sys.executable + "\n" + textwrap.dedent(APP_STUB))
        self.binary.chmod(0o755)
        self.original_binary = self.binary.read_bytes()
        self.resources = self.app / "Contents/Resources/data"
        self.resources.mkdir(parents=True)
        (self.resources / "asset.txt").write_text("packaged resource\n")
        (self.resources / "relative-link").symlink_to("asset.txt")
        (self.bin / "aseprite.ini").write_text("[configuration]\nportable=true\n")
        # These old build-tree links must never be copied into the archive.
        (self.bin / "aseprite").symlink_to(self.binary)
        (self.bin / "data").symlink_to(self.resources)
        self.output = self.bin / "Aseprite macOS test.zip"
        self.trace = self.root / "tool-trace.jsonl"
        self.tool_directory = self.root / "stub tools"
        self.tool_directory.mkdir()
        for name in ("uname", "ditto", "codesign", "otool"):
            tool = self.tool_directory / name
            tool.write_text("#!" + sys.executable + "\n" + textwrap.dedent(TOOL_STUB))
            tool.chmod(0o755)
        self.scratch = self.root / "temporary staging"
        self.scratch.mkdir()
        self.env = dict(os.environ, PATH=str(self.tool_directory) + os.pathsep + os.environ["PATH"],
                        TMPDIR=str(self.scratch), RUNNER_TEMP=str(self.scratch),
                        PACKAGING_TEST_TRACE=str(self.trace),
                        PACKAGING_TEST_OUTPUT=str(self.output))

    def package(self, **environment):
        return subprocess.run(["bash", str(SCRIPT), self.output.name], cwd=self.bin,
                              env=dict(self.env, **environment), capture_output=True, text=True,
                              timeout=30)

    def events(self):
        return [json.loads(line) for line in self.trace.read_text().splitlines()] if self.trace.exists() else []

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.output.is_file())

    def assert_failure(self, result):
        self.assertNotEqual(result.returncode, 0, "Packaging unexpectedly succeeded:\n" + result.stdout)
        self.assertFalse(self.output.exists(), "An unverified archive was published")
        self.assertEqual(list(self.scratch.iterdir()), [], "Temporary staging directories leaked")
        self.assertEqual(self.binary.read_bytes(), self.original_binary, "Build-tree executable was modified")

    def test_relocatable_layout_modes_links_and_argument_forwarding(self):
        self.assert_success(self.package())
        self.assertEqual(self.binary.read_bytes(), self.original_binary)
        self.assertTrue((self.bin / "aseprite").is_symlink())
        self.assertEqual(os.readlink(self.bin / "aseprite"), str(self.binary))
        self.assertTrue((self.bin / "data").is_symlink())
        self.assertFalse((self.app / "Contents/.plumbing-test-signature").exists())
        self.assertEqual(list(self.scratch.iterdir()), [], "Temporary staging directories leaked")
        with zipfile.ZipFile(self.output) as archive:
            names = set(archive.namelist())
            self.assertIn("Aseprite.app/Contents/MacOS/aseprite", names)
            self.assertIn("aseprite.ini", names)
            self.assertIn("README-macOS.txt", names)
            self.assertNotIn("data", names)
            self.assertNotIn("data/", names)
            self.assertEqual(archive.read("aseprite.ini"), (self.bin / "aseprite.ini").read_bytes())
            self.assertRegex(archive.read("README-macOS.txt").decode(), r"(?i)trust|信任|可信")
            for name in ("aseprite", "Aseprite.app/Contents/MacOS/aseprite"):
                mode = archive.getinfo(name).external_attr >> 16
                self.assertTrue(stat.S_ISREG(mode), name + " must be a regular file")
                self.assertTrue(mode & 0o111, name + " must be executable")
            link = archive.getinfo("Aseprite.app/Contents/Resources/data/relative-link")
            self.assertTrue(stat.S_ISLNK(link.external_attr >> 16))
            self.assertEqual(archive.read(link).decode(), "asset.txt")
            self.assertNotIn(str(self.bin), archive.read("aseprite").decode())

        # A second, independent relocation also contains spaces and is launched
        # from an unrelated directory. Empty and shell-special arguments matter.
        relocated = self.root / "another location with spaces/portable archive"
        extracted = subprocess.run([str(self.tool_directory / "ditto"), "-x", "-k", str(self.output), str(relocated)],
                                   env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(extracted.returncode, 0, extracted.stderr)
        outside = self.root / "outside working directory"
        outside.mkdir()
        args = ["two words", "", "*", "'quoted'", '"double"', "semi;colon", "$HOME", "--flag=value"]
        invoked = subprocess.run([str(relocated / "aseprite"), *args], cwd=outside, env=self.env,
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(invoked.returncode, 0, invoked.stderr)
        self.assertEqual(json.loads(invoked.stdout), args)
        relative_invocation = subprocess.run(["../another location with spaces/portable archive/aseprite", *args],
                                            cwd=outside, env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(relative_invocation.returncode, 0, relative_invocation.stderr)
        self.assertEqual(json.loads(relative_invocation.stdout), args)
        self.assertEqual((relocated / "Aseprite.app/Contents/Resources/data/relative-link").read_text(),
                         "packaged resource\n")

    def test_sign_verify_archive_and_smoke_tests_precede_publication(self):
        self.assert_success(self.package())
        events = self.events()
        self.assertTrue(events)
        self.assertTrue(all(not row["output_exists"] for row in events),
                        "Destination archive appeared before verification completed")
        signed = [row for row in events if row["tool"] == "codesign" and "--sign" in row["args"]]
        self.assertEqual(len(signed), 1)
        sign_args = signed[0]["args"]
        self.assertIn("--force", sign_args)
        self.assertEqual(sign_args[sign_args.index("--sign") + 1], "-")
        self.assertIn("--timestamp=none", sign_args)
        self.assertNotIn("--deep", sign_args, "Do not recursively sign the app")
        self.assertNotEqual(Path(sign_args[-1]), self.app)
        verified = [row for row in events if row["tool"] == "codesign" and "--verify" in row["args"]]
        self.assertGreaterEqual(len(verified), 3)
        for row in verified:
            self.assertIn("--deep", row["args"])
            self.assertIn("--strict", row["args"])
        archives = [row for row in events if row["tool"] == "ditto" and "-c" in row["args"]]
        self.assertEqual(len(archives), 1)
        self.assertIn("-k", archives[0]["args"])
        self.assertIn("--sequesterRsrc", archives[0]["args"])
        self.assertNotIn("--keepParent", archives[0]["args"])
        self.assertNotEqual(Path(archives[0]["args"][-1]), self.output)
        extractions = [row for row in events if row["tool"] == "ditto" and "-x" in row["args"]]
        self.assertEqual(len(extractions), 1)
        self.assertIn("-k", extractions[0]["args"])
        extracted_root = Path(extractions[0]["args"][-1])
        self.assertIn(" ", str(extracted_root))
        applications = [row for row in events if row["tool"] == "application"]
        self.assertGreaterEqual(len(applications), 2)
        self.assertEqual(len({row["user_folder"] for row in applications}), len(applications),
                         "Each smoke test must use its own fresh user folder")
        for row in applications:
            self.assertEqual(row["args"], ["--version"])
            self.assertTrue(Path(row["binary"]).is_relative_to(extracted_root))
            self.assertFalse(Path(row["cwd"]).is_relative_to(extracted_root),
                             "Smoke tests must run from outside the extracted archive")
            self.assertTrue(row["user_folder"], "A smoke test used the real user's configuration")
            self.assertFalse(Path(row["user_folder"]).is_relative_to(extracted_root))
        self.assertLess(events.index(signed[0]), events.index(verified[0]))
        self.assertLess(events.index(verified[0]), events.index(archives[0]))
        self.assertLess(events.index(extractions[0]), events.index(verified[1]))
        self.assertLess(events.index(verified[1]), events.index(applications[0]))
        self.assertLess(events.index(applications[-1]), events.index(verified[-1]))

    def test_rejects_non_macos(self):
        self.assert_failure(self.package(FAKE_UNAME="Linux"))
        self.assertFalse(any(row["tool"] in ("codesign", "ditto") for row in self.events()))

    def test_requires_one_zip_basename(self):
        for args in ([], ["bad.tar"], ["../elsewhere.zip"], [str(self.root / "absolute.zip")],
                     ["first.zip", "second.zip"]):
            with self.subTest(args=args):
                result = subprocess.run(["bash", str(SCRIPT), *args], cwd=self.bin, env=self.env,
                                        capture_output=True, text=True, timeout=30)
                self.assert_failure(result)

    def test_requires_executable_application(self):
        self.binary.chmod(0o644)
        self.assert_failure(self.package())

    def test_requires_application_binary(self):
        self.binary.rename(self.binary.with_name("missing-binary"))
        result = self.package()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_requires_regular_configuration_file(self):
        (self.bin / "aseprite.ini").unlink()
        self.assert_failure(self.package())
        (self.bin / "aseprite.ini").mkdir()
        self.assert_failure(self.package())

    def test_rejects_symlink_configuration_file(self):
        (self.bin / "aseprite.ini").unlink()
        target = self.root / "other-config.ini"
        target.write_text("[configuration]\n")
        (self.bin / "aseprite.ini").symlink_to(target)
        self.assert_failure(self.package())

    def test_rejects_absolute_bundle_symlinks(self):
        (self.resources / "unsafe-link").symlink_to(self.resources / "asset.txt")
        self.assert_failure(self.package())

    def test_rejects_broken_bundle_symlinks(self):
        (self.resources / "unsafe-link").symlink_to("missing-resource")
        self.assert_failure(self.package())

    def test_rejects_relative_symlinks_escaping_stage(self):
        outside = self.root / "outside-resource.txt"
        outside.write_text("not part of the package")
        # The target remains valid after staging, so this tests containment,
        # rather than merely rejecting a link that became broken on copying.
        (self.resources / "unsafe-link").symlink_to("../" * 32 + str(outside).lstrip("/"))
        self.assert_failure(self.package())

    def test_rejects_symlink_chain_to_absolute_target(self):
        (self.resources / "target-link").symlink_to(self.resources / "asset.txt")
        (self.resources / "unsafe-link").symlink_to("target-link")
        self.assert_failure(self.package())

    def test_signing_failure_is_fatal(self):
        self.assert_failure(self.package(FAKE_FAIL_SIGN="1"))

    def test_rejects_non_system_runtime_dependencies(self):
        for dependency in ("/opt/homebrew/lib/libtest.dylib", "@rpath/libtest.dylib"):
            with self.subTest(dependency=dependency):
                self.trace.unlink(missing_ok=True)
                self.assert_failure(self.package(FAKE_DEPENDENCY=dependency))
                self.assertFalse(any(row["tool"] == "codesign" for row in self.events()))

    def test_dependency_inspection_failure_is_fatal(self):
        self.assert_failure(self.package(FAKE_FAIL_OTOOL="1"))

    def test_each_signature_verification_failure_is_fatal(self):
        for verification in (1, 2, 3):
            with self.subTest(verification=verification):
                self.trace.unlink(missing_ok=True)
                self.assert_failure(self.package(FAKE_FAIL_VERIFY_N=str(verification)))

    def test_archive_creation_failure_is_fatal(self):
        self.assert_failure(self.package(FAKE_FAIL_ARCHIVE="1"))

    def test_archive_extraction_failure_is_fatal(self):
        self.assert_failure(self.package(FAKE_FAIL_EXTRACT="1"))

    def test_extracted_binary_corruption_is_fatal(self):
        self.assert_failure(self.package(FAKE_EXTRACT_FAULT="binary_corruption"))

    def test_extracted_unsafe_symlink_is_fatal(self):
        self.assert_failure(self.package(FAKE_EXTRACT_FAULT="absolute_symlink"))

    def test_extracted_launcher_permission_loss_is_fatal(self):
        self.assert_failure(self.package(FAKE_EXTRACT_FAULT="launcher_not_executable"))

    def test_direct_and_launcher_nonzero_version_status_is_fatal(self):
        for version in (1, 2):
            with self.subTest(version=version):
                self.trace.unlink(missing_ok=True)
                self.assert_failure(self.package(FAKE_FAIL_VERSION_N=str(version)))

    def test_direct_and_launcher_unexpected_version_output_is_fatal(self):
        for version in (1, 2):
            with self.subTest(version=version):
                self.trace.unlink(missing_ok=True)
                self.assert_failure(self.package(FAKE_BAD_VERSION_N=str(version)))

    def test_failure_preserves_preexisting_destination(self):
        previous = b"previously published archive must not be replaced"
        self.output.write_bytes(previous)
        result = self.package(FAKE_FAIL_VERSION_N="2")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), previous)
        self.assertEqual(list(self.scratch.iterdir()), [])
        self.assertEqual(self.binary.read_bytes(), self.original_binary)


if __name__ == "__main__":
    unittest.main()
