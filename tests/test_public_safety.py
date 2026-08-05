from __future__ import annotations

import getpass
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCANNER = PROJECT_ROOT / "scripts" / "public_safety.py"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from local_inference_test_bench.safety import SafetyError, load_credential  # noqa: E402


class TemporaryGitRepository:
    def __init__(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self._temporary_directory.name)
        self.git("init", "--quiet")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Public Safety Test")

    def close(self) -> None:
        self._temporary_directory.cleanup()

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", os.fspath(self.path), *arguments],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def write(self, relative_path: str, content: str | bytes) -> Path:
        destination = self.path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            destination.write_bytes(content)
        else:
            destination.write_text(content, encoding="utf-8")
        return destination

    def add(self, *relative_paths: str) -> None:
        self.git("add", "--", *relative_paths)

    def scan(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, os.fspath(SCANNER), *arguments],
            cwd=self.path,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )


class PublicSafetyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = TemporaryGitRepository()

    def tearDown(self) -> None:
        self.repository.close()

    def assertRules(self, completed: subprocess.CompletedProcess[str], *rules: str) -> None:
        self.assertNotEqual(completed.returncode, 0, completed.stdout)
        reported = {line.split("\t", 1)[0] for line in completed.stdout.splitlines()}
        self.assertTrue(set(rules).issubset(reported), completed.stdout)

    def installIgnoredDenylist(self, content: str) -> None:
        self.repository.write(".gitignore", ".local/privacy-denylist.txt\n")
        denylist = self.repository.write(".local/privacy-denylist.txt", content)
        if os.name != "nt":
            denylist.chmod(0o600)
        self.repository.add(".gitignore")

    def test_staged_mode_reads_index_not_worktree(self) -> None:
        self.repository.write("guide.txt", "clean public text\n")
        self.repository.add("guide.txt")

        private_address = "192" + ".168" + ".40" + ".12"
        self.repository.write("guide.txt", f"endpoint={private_address}\n")

        staged = self.repository.scan("--staged")
        self.assertEqual(staged.returncode, 0, staged.stdout)

        full_tree = self.repository.scan("--full-tree")
        self.assertRules(full_tree, "private-ipv4")

        self.repository.add("guide.txt")
        staged_after_add = self.repository.scan("--staged")
        self.assertRules(staged_after_add, "private-ipv4")

    def test_force_added_ignored_artifact_is_still_scanned(self) -> None:
        self.repository.write(".gitignore", "artifacts/\n")
        private_address = "10" + ".33" + ".44" + ".55"
        self.repository.write("artifacts/run.json", "endpoint=" + private_address + "\n")
        self.repository.add(".gitignore")
        self.repository.git("add", "--force", "--", "artifacts/run.json")

        completed = self.repository.scan("--staged")

        self.assertRules(completed, "generated-artifact")
        self.assertIn("generated-artifact\tartifacts/run.json\t1", completed.stdout)
        self.assertNotIn(private_address, completed.stdout)

    def test_force_added_generated_directories_and_local_manifests_are_categorical(self) -> None:
        generated_paths = (
            "artifacts/run.json",
            "reports/report.json",
            "results/result.json",
            "runs/run.json",
        )
        local_paths = (
            ".local/models.json",
            "config/models.json",
            "config/models.local.json",
        )
        minimized_but_forbidden = '{"raw_prompt":"synthetic","runtime_model":"selector"}\n'
        for path in (*generated_paths, *local_paths):
            self.repository.write(path, minimized_but_forbidden)
        self.repository.add(*generated_paths, *local_paths)

        completed = self.repository.scan("--staged")

        self.assertRules(completed, "generated-artifact", "local-configuration")
        for path in generated_paths:
            self.assertIn("generated-artifact\t" + path + "\t1", completed.stdout)
        for path in local_paths:
            self.assertIn("local-configuration\t" + path + "\t1", completed.stdout)

    def test_findings_are_deterministic_ordered_relative_and_redacted(self) -> None:
        first_private = "10" + ".9" + ".8" + ".7"
        second_private = "172" + ".20" + ".8" + ".7"
        self.repository.write("zeta.txt", "clean\nvalue=" + first_private + "\n")
        self.repository.write("alpha.txt", "value=" + second_private + "\n")
        self.repository.add("zeta.txt", "alpha.txt")

        first = self.repository.scan("--staged")
        second = self.repository.scan("--staged")

        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(
            first.stdout.splitlines(),
            ["private-ipv4\talpha.txt\t1", "private-ipv4\tzeta.txt\t2"],
        )
        self.assertNotIn(first_private, first.stdout)
        self.assertNotIn(second_private, first.stdout)

    def test_full_tree_scans_only_files_known_to_git(self) -> None:
        self.repository.write("tracked.txt", "clean\n")
        self.repository.add("tracked.txt")
        private_address = "10" + ".20" + ".30" + ".40"
        self.repository.write("untracked.txt", private_address)

        completed = self.repository.scan("--full-tree")

        self.assertEqual(completed.returncode, 0, completed.stdout)

    def test_history_scans_removed_blobs_and_commit_messages(self) -> None:
        private_address = "10" + ".44" + ".55" + ".66"
        private_hostname = "historic-node" + ".internal"
        self.repository.write("retired.txt", "endpoint=" + private_address + "\n")
        self.repository.add("retired.txt")
        self.repository.git("commit", "--quiet", "-m", "retire " + private_hostname)

        self.repository.write("retired.txt", "sanitized\n")
        self.repository.add("retired.txt")
        self.repository.git("commit", "--quiet", "-m", "sanitize historical material")

        current_tree = self.repository.scan("--full-tree")
        history = self.repository.scan("--history")

        self.assertEqual(current_tree.returncode, 0, current_tree.stdout)
        self.assertRules(history, "private-ipv4", "private-hostname")
        self.assertIn("private-ipv4\tretired.txt\t1", history.stdout)
        self.assertIn("private-hostname\t.git/COMMIT_MESSAGE\t1", history.stdout)

    def test_history_commit_root_scans_an_unreferenced_pushed_object(self) -> None:
        private_address = "10" + ".72" + ".8" + ".9"
        self.repository.write("detached.txt", "endpoint=" + private_address + "\n")
        self.repository.add("detached.txt")
        tree = self.repository.git("write-tree").stdout.strip()
        commit = self.repository.git("commit-tree", tree, "-m", "detached publication").stdout.strip()

        reachable = self.repository.scan("--history")
        pushed = self.repository.scan("--history", "--commit", commit)

        self.assertEqual(reachable.returncode, 0, reachable.stdout)
        self.assertRules(pushed, "private-ipv4")
        self.assertNotIn(private_address, pushed.stdout)

    def test_history_commit_root_scans_annotated_tag_message(self) -> None:
        private_hostname = "tag-node" + ".local"
        self.repository.write("clean.txt", "clean\n")
        self.repository.add("clean.txt")
        self.repository.git("commit", "--quiet", "-m", "clean commit")
        self.repository.git("tag", "--annotate", "v1", "-m", "publish " + private_hostname)
        tag_object = self.repository.git("rev-parse", "v1").stdout.strip()

        completed = self.repository.scan("--history", "--commit", tag_object)

        self.assertRules(completed, "private-hostname")
        self.assertIn("private-hostname\t.git/TAG_MESSAGE\t1", completed.stdout)
        self.assertNotIn(private_hostname, completed.stdout)

    def test_network_identifiers_paths_macs_credentials_and_keys_are_rejected(self) -> None:
        bad_lines = [
            "private=" + "10" + ".2" + ".3" + ".4",
            "carrier=" + "100" + ".64" + ".8" + ".9",
            "ula=" + "fd12" + ":3456::9",
            "mac=" + "aa:bb" + ":cc:dd:ee:ff",
            "path=" + "/" + "home" + "/alice/project",
            "host=" + "inference-node" + ".local",
            "pass" + "word=" + "correct-horse-battery-staple",
            "LOCAL_INFERENCE_" + "API_" + "KEY" + "=" + "another-hardcoded-value",
            "-----BEGIN " + "PRIVATE KEY-----",
        ]
        self.repository.write("identifiers.txt", "\n".join(bad_lines) + "\n")
        self.repository.add("identifiers.txt")

        completed = self.repository.scan("--staged")

        self.assertRules(
            completed,
            "private-ipv4",
            "cgnat-ipv4",
            "private-ipv6",
            "mac-address",
            "absolute-user-path",
            "private-hostname",
            "credential-assignment",
            "private-key",
        )
        self.assertIn("private-ipv4\tidentifiers.txt\t1", completed.stdout)
        self.assertIn("credential-assignment\tidentifiers.txt\t8", completed.stdout)
        self.assertIn("private-key\tidentifiers.txt\t9", completed.stdout)

    def test_loopback_and_documentation_addresses_are_allowed(self) -> None:
        content = "\n".join(
            (
                "127.0.0.1",
                "::1",
                "192.0.2.20",
                "198.51.100.20",
                "203.0.113.20",
                "api_key=${LOCAL_INFERENCE_API_KEY}",
            )
        )
        self.repository.write("examples.txt", content + "\n")
        self.repository.add("examples.txt")

        completed = self.repository.scan("--staged")

        self.assertEqual(completed.returncode, 0, completed.stdout)

    def test_risky_tracked_types_binary_files_and_symlinks_are_rejected(self) -> None:
        self.repository.write("identity" + ".pem", "public-looking text\n")
        self.repository.write("opaque.data", b"prefix\x01suffix")
        self.repository.add("identity.pem", "opaque.data")

        completed = self.repository.scan("--staged")

        self.assertRules(completed, "risky-file-type", "binary-file")

        if os.name == "nt":
            return
        self.repository.write("target.txt", "clean\n")
        link = self.repository.path / "shortcut"
        link.symlink_to("target.txt")
        self.repository.add("shortcut")

        completed_with_link = self.repository.scan("--staged")
        self.assertRules(completed_with_link, "symlink")

        self.repository.write("folder/file.txt", "clean\n")
        self.repository.add("folder/file.txt")
        original_directory = self.repository.path / "folder"
        moved_directory = self.repository.path / "real-folder"
        original_directory.rename(moved_directory)
        original_directory.symlink_to("real-folder", target_is_directory=True)

        full_tree_with_linked_parent = self.repository.scan("--full-tree")
        self.assertRules(full_tree_with_linked_parent, "symlink")
        self.assertIn("symlink\tfolder/file.txt\t1", full_tree_with_linked_parent.stdout)

    def test_ascii_document_suffix_and_oversized_blob_are_rejected_before_decode(self) -> None:
        self.repository.write("diagram" + ".pdf", "plain ASCII is still a risky publication type\n")
        oversized = self.repository.write("oversized.txt", b"")
        with oversized.open("wb") as handle:
            handle.truncate((5 * 1024 * 1024) + 1)
        self.repository.add("diagram.pdf", "oversized.txt")

        staged = self.repository.scan("--staged")
        full_tree = self.repository.scan("--full-tree")

        self.assertRules(staged, "risky-file-type", "oversized-file")
        self.assertRules(full_tree, "risky-file-type", "oversized-file")

    def test_strict_mode_requires_local_denylist(self) -> None:
        self.repository.write("guide.txt", "clean\n")
        self.repository.add("guide.txt")

        ordinary = self.repository.scan("--staged")
        strict = self.repository.scan("--staged", "--strict")

        self.assertEqual(ordinary.returncode, 0, ordinary.stdout)
        self.assertRules(strict, "denylist-required")
        self.assertEqual(strict.stdout, "denylist-required\t.local/privacy-denylist.txt\t1\n")

    def test_strict_mode_rejects_fresh_comment_only_denylist_template(self) -> None:
        self.repository.write("guide.txt", "clean\n")
        template = (PROJECT_ROOT / ".local" / "privacy-denylist.example").read_text(encoding="utf-8")
        self.installIgnoredDenylist(template)
        self.repository.add("guide.txt")

        completed = self.repository.scan("--full-tree", "--strict")

        self.assertRules(completed, "denylist-empty")
        self.assertEqual(completed.stdout, "denylist-empty\t.local/privacy-denylist.txt\t1\n")

    def test_custom_denylist_is_literal_case_insensitive_and_redacted(self) -> None:
        literal = "lab[" + "marker]+"
        self.installIgnoredDenylist("# local only\n" + literal + "\n")
        self.repository.write("guide.txt", "value=" + literal.upper() + "\n")
        self.repository.add("guide.txt")

        completed = self.repository.scan("--staged", "--strict")

        self.assertRules(completed, "custom-denylist")
        self.assertNotIn(literal.casefold(), completed.stdout.casefold())
        self.assertEqual(completed.stderr, "")

    def test_strict_mode_requires_ignored_owner_only_denylist(self) -> None:
        self.repository.write("guide.txt", "clean\n")
        denylist = self.repository.write(".local/privacy-denylist.txt", "local-identifier\n")
        if os.name != "nt":
            denylist.chmod(0o600)
        self.repository.add("guide.txt")

        not_ignored = self.repository.scan("--full-tree", "--strict")
        self.assertRules(not_ignored, "denylist-not-ignored")

        self.repository.write(".gitignore", ".local/privacy-denylist.txt\n")
        self.repository.add(".gitignore")
        if os.name != "nt":
            denylist.chmod(0o644)
            broad_permissions = self.repository.scan("--full-tree", "--strict")
            self.assertRules(broad_permissions, "denylist-permissions")

    def test_environment_file_absence_tracking_permissions_and_safe_ignore(self) -> None:
        missing = self.repository.path / ".env"
        with self.assertRaisesRegex(SafetyError, "could not be inspected"):
            load_credential("INFERENCE_TEST_TOKEN", env_file=missing, environ={})

        self.repository.write(".gitignore", ".env*\n")
        safe_file = self.repository.write(
            ".env.safe", "INFERENCE_TEST_TOKEN=placeholder\n"
        )
        self.repository.add(".gitignore")
        if os.name != "nt":
            for mode in (0o640, 0o644):
                safe_file.chmod(mode)
                with self.subTest(mode=oct(mode)), self.assertRaisesRegex(
                    SafetyError, "owner-only"
                ):
                    load_credential(
                        "INFERENCE_TEST_TOKEN", env_file=safe_file, environ={}
                    )
            safe_file.chmod(0o600)

        self.assertEqual(
            load_credential("INFERENCE_TEST_TOKEN", env_file=safe_file, environ={}),
            "placeholder",
        )

        self.repository.git("add", "--force", "--", ".env.safe")
        with self.assertRaisesRegex(SafetyError, "ignored by Git"):
            load_credential("INFERENCE_TEST_TOKEN", env_file=safe_file, environ={})

    def test_sensitive_filename_is_redacted(self) -> None:
        literal = "asset" + "-marker"
        self.installIgnoredDenylist(literal + "\n")
        relative_path = "notes-" + literal + ".txt"
        self.repository.write(relative_path, "clean\n")
        self.repository.add(relative_path)

        completed = self.repository.scan("--staged", "--strict")

        self.assertRules(completed, "custom-denylist")
        self.assertNotIn(literal, completed.stdout)
        self.assertIn("notes-[redacted].txt", completed.stdout)

    def test_unicode_casefold_denylist_match_is_redacted(self) -> None:
        literal = "stra" + "\u00dfe"
        variant = "STRASSE"
        self.installIgnoredDenylist(literal + "\n")
        relative_path = "notes-" + variant + ".txt"
        self.repository.write(relative_path, "clean\n")
        self.repository.add(relative_path)

        completed = self.repository.scan("--staged", "--strict")

        self.assertRules(completed, "custom-denylist")
        self.assertNotIn(variant, completed.stdout)
        self.assertIn("notes-[redacted].txt", completed.stdout)

    def test_credential_value_in_nested_filename_is_redacted(self) -> None:
        literal = "hardcoded" + "-credential-value"
        relative_path = "folder/" + "pass" + "word=" + literal + ".txt"
        self.repository.write(relative_path, "clean\n")
        self.repository.add(relative_path)

        completed = self.repository.scan("--staged")

        self.assertRules(completed, "credential-assignment")
        self.assertNotIn(literal, completed.stdout)
        self.assertIn("folder/password=[redacted]", completed.stdout)

    def test_tracked_local_denylist_is_rejected(self) -> None:
        literal = "site" + "-identifier"
        self.repository.write(".local/privacy-denylist.txt", literal + "\n")
        self.repository.add(".local/privacy-denylist.txt")

        completed = self.repository.scan("--staged")

        self.assertRules(completed, "tracked-local-file")

    def test_current_home_and_non_generic_username_are_detected_without_echo(self) -> None:
        home = os.fspath(Path.home())
        self.repository.write("home.txt", "location=" + home + "\n")
        self.repository.add("home.txt")

        completed = self.repository.scan("--staged")

        self.assertRules(completed, "current-home")
        self.assertNotIn(home, completed.stdout)

        username = getpass.getuser().strip()
        if not username or username.casefold() in {
            "admin",
            "administrator",
            "nobody",
            "root",
            "runner",
            "ubuntu",
            "user",
        }:
            return
        self.repository.write("home.txt", "account_owner=" + username + "\n")
        self.repository.add("home.txt")

        username_result = self.repository.scan("--staged")
        self.assertRules(username_result, "current-username")
        self.assertNotIn(username.casefold(), username_result.stdout.casefold())

    def test_current_hostname_is_detected_without_echo(self) -> None:
        hostname = socket.gethostname().strip().rstrip(".")
        if len(hostname) < 3 or hostname.casefold() in {"localhost", "localhost.localdomain"}:
            self.skipTest("host has no identifying hostname")
        self.repository.write("machine.txt", "machine=" + hostname + "\n")
        self.repository.add("machine.txt")

        completed = self.repository.scan("--staged")

        self.assertRules(completed, "current-hostname")
        self.assertNotIn(hostname.casefold(), completed.stdout.casefold())

    def test_named_experiments_are_allowed_only_in_experiment_docs(self) -> None:
        names = ("op" + "ik", "poly" + "range")
        self.repository.write("docs/guide.md", " and ".join(names) + "\n")
        self.repository.add("docs/guide.md")

        outside = self.repository.scan("--staged")
        self.assertRules(outside, "experimental-name-scope")

        self.repository.write("docs/guide.md", "general guidance\n")
        self.repository.write("docs/experiments/note.md", " and ".join(names) + "\n")
        self.repository.add("docs/guide.md", "docs/experiments/note.md")

        inside = self.repository.scan("--staged")
        self.assertEqual(inside.returncode, 0, inside.stdout)

    def test_output_has_only_rule_path_and_line_fields(self) -> None:
        private_address = "172" + ".20" + ".3" + ".9"
        self.repository.write("guide.txt", "do not publish " + private_address + "\n")
        self.repository.add("guide.txt")

        completed = self.repository.scan("--staged")

        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, "")
        self.assertNotIn(private_address, completed.stdout)
        for line in completed.stdout.splitlines():
            self.assertRegex(line, re.compile(r"^[a-z0-9-]+\t[^\t\r\n]+\t[1-9][0-9]*$"))


if __name__ == "__main__":
    unittest.main()
