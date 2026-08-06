from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_benchmark_change import (  # noqa: E402
    ChangeError,
    _require_current_added_submission,
    validate_benchmark_content,
    validate_benchmark_modes,
    validate_changes,
    validate_expected_submission,
)


SUBMISSION = "site/data/submissions/" + "a" * 64 + ".json"
LEADERBOARD = "site/data/leaderboard.json"


class BenchmarkChangeBoundaryTests(unittest.TestCase):
    def test_new_benchmark_candidate_must_use_schema_1_1(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidate.json"
            path.write_text('{"schema_version":"1.1"}\n', encoding="utf-8")
            _require_current_added_submission(path)

            path.write_text('{"schema_version":"1.0"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ChangeError, "schema 1.1"):
                _require_current_added_submission(path)

            path.write_text(
                '{"schema_version":"1.1","schema_version":"1.1"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ChangeError, "strict JSON"):
                _require_current_added_submission(path)

    def test_general_change_does_not_enter_the_benchmark_only_lane(self) -> None:
        self.assertFalse(validate_changes([("M", "README.md"), ("A", "docs/new.md")]))
        self.assertFalse(
            validate_changes(
                [("R100", "docs/old.md"), ("R100", "docs/new.md")]
            )
        )

    def test_required_benchmark_lane_rejects_a_general_change(self) -> None:
        with self.assertRaisesRegex(ChangeError, "benchmark-only"):
            validate_changes([("M", "README.md")], require_benchmark=True)

    def test_required_benchmark_lane_accepts_the_exact_two_file_change(self) -> None:
        self.assertTrue(
            validate_changes(
                [("A", SUBMISSION), ("M", LEADERBOARD)],
                require_benchmark=True,
            )
        )

    def test_submission_branch_digest_must_match_the_added_filename(self) -> None:
        changes = [("A", SUBMISSION), ("M", LEADERBOARD)]
        validate_expected_submission(changes, "a" * 64)
        with self.assertRaisesRegex(ChangeError, "branch identifier"):
            validate_expected_submission(changes, "b" * 64)

    def test_one_append_only_record_and_generated_data_is_accepted(self) -> None:
        self.assertTrue(validate_changes([("A", SUBMISSION), ("M", LEADERBOARD)]))

    def test_mixed_benchmark_and_code_change_is_rejected(self) -> None:
        with self.assertRaisesRegex(ChangeError, "one submission"):
            validate_changes(
                [("A", SUBMISSION), ("M", LEADERBOARD), ("M", "scripts/public_safety.py")]
            )

    def test_submission_rewrite_delete_and_bad_filename_are_rejected(self) -> None:
        for status, path in (
            ("M", SUBMISSION),
            ("D", SUBMISSION),
            ("A", "site/data/submissions/result.json"),
        ):
            with self.subTest(status=status, path=path):
                with self.assertRaisesRegex(ChangeError, "append-only"):
                    validate_changes([(status, path), ("M", LEADERBOARD)])

    def test_missing_or_extra_leaderboard_change_is_rejected(self) -> None:
        for changes in (
            [("A", SUBMISSION)],
            [("A", SUBMISSION), ("A", LEADERBOARD)],
            [
                ("A", SUBMISSION),
                ("M", LEADERBOARD),
                ("A", "site/data/leaderboard-000001.json"),
            ],
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ChangeError):
                    validate_changes(changes)

    def test_ephemeral_shards_cannot_enter_the_tracked_benchmark_boundary(self) -> None:
        for path in (
            "site/data/leaderboard-000001.json",
            "site/data/shards/leaderboard-00000001.json",
        ):
            with self.subTest(path=path):
                with self.assertRaises(ChangeError):
                    validate_changes(
                        [("A", SUBMISSION), ("M", LEADERBOARD), ("A", path)],
                        require_benchmark=True,
                    )

    def test_trusted_materialization_keeps_per_file_caps_without_an_aggregate_wedge(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "validate_benchmark_change.py"
        ).read_text(encoding="utf-8")

        self.assertIn("256 * 1024", source)
        self.assertNotIn("dataset exceeds its trusted materialization limit", source)
        self.assertNotRegex(source, r"total_bytes\s*>\s*\d+\s*\*\s*1024\s*\*\s*1024")

    def test_every_dataset_tree_change_enters_the_strict_lane(self) -> None:
        for changes in (
            [("M", LEADERBOARD)],
            [("M", "site/data/submissions/.gitkeep")],
            [("A", "site/data/submissions/nested/result.json")],
            [
                ("A", "site/data/submissions/nested/result.json"),
                ("M", "scripts/public_safety.py"),
            ],
        ):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ChangeError, "one submission"):
                    validate_changes(changes)

    def test_workflow_executes_checker_from_the_trusted_base_commit(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "trusted-benchmark-boundary.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("pull_request_target:", workflow)
        self.assertIn(
            'git show "${BASE_SHA}:scripts/validate_benchmark_change.py"',
            workflow,
        )
        self.assertIn("python3 - \\", workflow)
        self.assertIn('--base "${BASE_SHA}"', workflow)
        self.assertIn('--head "${HEAD_SHA}"', workflow)
        self.assertIn("--check-content", workflow)
        self.assertNotIn("python3 scripts/validate_benchmark_change.py", workflow)
        self.assertNotIn("pull_request_target:", (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "public-safety.yml"
        ).read_text(encoding="utf-8"))

    def test_benchmark_files_must_not_be_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            submission = root / SUBMISSION
            submission.parent.mkdir(parents=True)
            submission.write_text("{}\n", encoding="utf-8")
            leaderboard = root / LEADERBOARD
            leaderboard.write_text("{}\n", encoding="utf-8")
            subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "--quiet",
                    "-m",
                    "fixture",
                ],
                cwd=root,
                check=True,
            )
            validate_benchmark_modes(root, "HEAD")
            subprocess.run(
                [
                    "git",
                    "update-index",
                    "--chmod=+x",
                    "--",
                    submission.relative_to(root).as_posix(),
                ],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "--quiet",
                    "-m",
                    "executable",
                ],
                cwd=root,
                check=True,
            )
            with self.assertRaisesRegex(ChangeError, "100644"):
                validate_benchmark_modes(root, "HEAD")

    def test_trusted_content_check_uses_base_code_and_byte_exact_data(self) -> None:
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(project / "site" / "data", root / "site" / "data")
            subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "--quiet",
                    "-m",
                    "fixture",
                ],
                cwd=root,
                check=True,
            )

            validate_benchmark_content(root, "HEAD", project)

            (root / LEADERBOARD).write_text("{}\n", encoding="utf-8")
            subprocess.run(["git", "add", LEADERBOARD], cwd=root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "--quiet",
                    "-m",
                    "stale",
                ],
                cwd=root,
                check=True,
            )
            with self.assertRaisesRegex(ChangeError, "trusted validation"):
                validate_benchmark_content(root, "HEAD", project)

            (root / LEADERBOARD).write_bytes(b" " * ((4 * 1024 * 1024) + 1))
            subprocess.run(["git", "add", LEADERBOARD], cwd=root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "--quiet",
                    "-m",
                    "oversized",
                ],
                cwd=root,
                check=True,
            )
            with self.assertRaisesRegex(ChangeError, "size limit"):
                validate_benchmark_content(root, "HEAD", project)


if __name__ == "__main__":
    unittest.main()
