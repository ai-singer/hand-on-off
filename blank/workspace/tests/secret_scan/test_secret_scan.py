from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from security.secret_scan import scan_targets


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


class SecretScanTests(unittest.TestCase):
    def test_current_workspace_passes(self) -> None:
        findings = scan_targets([WORKSPACE_ROOT])

        self.assertEqual(findings, [])

    def test_forbidden_environment_filename_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("SAFE_SETTING=value\n", encoding="utf-8")

            findings = scan_targets([directory])

        self.assertIn("forbidden-filename", {finding.rule for finding in findings})

    def test_content_finding_does_not_disclose_value(self) -> None:
        value = "sk-" + "LiveLikeValue9Az8By7Cx6Dw5Ev4Fu"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.txt"
            path.write_text("API_KEY=" + value + "\n", encoding="utf-8")

            findings = scan_targets([directory])

        rendered = "\n".join(finding.render() for finding in findings)
        self.assertIn("openai-style-token", {finding.rule for finding in findings})
        self.assertNotIn(value, rendered)

    def test_archive_members_and_nested_git_are_scanned(self) -> None:
        value = "sk-" + "ArchiveValue9Az8By7Cx6Dw5Ev4Fu"
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "payload.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                git_data = b"[core]\nrepositoryformatversion = 0\n"
                git_member = tarfile.TarInfo("workspace/.git/config")
                git_member.size = len(git_data)
                archive.addfile(git_member, io.BytesIO(git_data))

                config_data = ("API_KEY=" + value + "\n").encode("utf-8")
                config_member = tarfile.TarInfo("workspace/config.txt")
                config_member.size = len(config_data)
                archive.addfile(config_member, io.BytesIO(config_data))

            findings = scan_targets([archive_path])

        rules = {finding.rule for finding in findings}
        self.assertIn("nested-git", rules)
        self.assertIn("openai-style-token", rules)

    def test_env_example_with_placeholder_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.example"
            path.write_text("API_KEY=your_api_key_here\n", encoding="utf-8")

            findings = scan_targets([directory])

        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
