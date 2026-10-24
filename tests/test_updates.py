import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from speak import updates


class UpdatesTest(unittest.TestCase):
    """Updates target supported packages, validate releases and hashes, and recover failed swaps."""

    def test_package_suffix_matches_supported_platform_architectures(self):
        with patch.object(updates, "IS_WINDOWS", True), \
                patch.object(updates.platform, "machine", return_value="AMD64"):
            self.assertEqual("-windows-x64.exe", updates.package_suffix())

        with patch.object(updates, "IS_WINDOWS", False), patch.object(updates, "IS_MAC", True), \
                patch.object(updates.platform, "machine", return_value="arm64"):
            self.assertEqual("-macos-arm64.zip", updates.package_suffix())

        with patch.object(updates, "IS_MAC", True), patch.object(updates, "IS_WINDOWS", False), \
                patch.object(updates.platform, "machine", return_value="x86_64"):
            self.assertEqual("-macos-x64.zip", updates.package_suffix())

        with patch.object(updates, "IS_MAC", False), patch.object(updates, "IS_WINDOWS", False):
            self.assertIsNone(updates.package_suffix())

    def test_semver_and_release_selection_filter_invalid_and_wrong_platform_assets(self):
        self.assertLess(updates.parse("v1.2.0-beta.1"), updates.parse("1.2.0"))
        self.assertIsNone(updates.parse("dev-abcd123"))
        releases = [
            {"tag_name": "v2.0.0", "draft": True, "assets": []},
            {"tag_name": "v1.5.0", "assets": [{"name": "Speak-1.5.0-macos-arm64.zip"}]},
            {"tag_name": "v1.4.0", "assets": [{"name": "Speak-1.4.0-windows-x64.exe"}]},
        ]

        release = updates.pick(releases, updates.parse("1.0.0"), suffix="-windows-x64.exe")

        self.assertEqual("1.4.0", release.version)

    def test_download_checks_digest_and_reports_progress(self):
        content = b"verified update"

        class Response(io.BytesIO):
            headers = {"Content-Length": str(len(content))}

            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.close()

        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / "Speak.exe"
            exe.touch()
            release = updates.Release("1.1.0", "", "https://example.invalid/update",
                                      f"sha256:{hashlib.sha256(content).hexdigest()}")
            progress = []
            with patch.object(updates, "exe_path", return_value=exe), \
                    patch.object(updates, "_get", return_value=Response(content)):
                downloaded = updates.download(release, progress.append)

            self.assertEqual(content, downloaded.read_bytes())
            self.assertEqual([100], progress)

    def test_download_removes_corrupt_partial(self):
        content = b"corrupt update"

        class Response(io.BytesIO):
            headers = {"Content-Length": str(len(content))}

            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.close()

        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / "Speak.exe"
            release = updates.Release("1.1.0", "", "https://example.invalid/update", "sha256:" + "0" * 64)
            with patch.object(updates, "exe_path", return_value=exe), \
                    patch.object(updates, "_get", return_value=Response(content)):
                with self.assertRaisesRegex(ValueError, "corrupt"):
                    updates.download(release)

            self.assertFalse(Path(str(exe) + ".new.part").exists())
            self.assertFalse(Path(str(exe) + ".new").exists())

    def test_failed_update_swap_restores_current_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / "Speak.exe"
            new = Path(directory) / "Speak.exe.new"
            exe.write_text("current", encoding="utf-8")
            new.write_text("update", encoding="utf-8")
            replace = updates.os.replace
            calls = 0

            def fail_second_move(source, target):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("locked")
                replace(source, target)

            with patch.object(updates.os, "replace", side_effect=fail_second_move):
                with self.assertRaisesRegex(OSError, "locked"):
                    updates.install(new, exe)

            self.assertEqual("current", exe.read_text(encoding="utf-8"))
            self.assertTrue(new.exists())


if __name__ == "__main__":
    unittest.main()
