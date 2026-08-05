from __future__ import annotations

from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_benchmark_change import (  # noqa: E402
    ChangeError,
    validate_benchmark_modes,
    validate_changes,
)


SUBMISSION = "site/data/submissions/" + "a" * 64 + ".json"
LEADERBOARD = "site/data/leaderboard.json"


class BenchmarkChangeBoundaryTests(unittest.TestCase):
    def test_general_change_does_not_enter_the_benchmark_only_lane(self) -> None:
        self.assertFalse(validate_changes([("M", "README.md"), ("A", "docs/new.md")]))
        self.assertFalse(
            validate_changes(
                [("R100", "docs/old.md"), ("R100", "docs/new.md")]
            )
        )

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
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ChangeError):
                    validate_changes(changes)

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
        self.assertIn('python3 - --base "${BASE_SHA}" --head "${HEAD_SHA}"', workflow)
        self.assertNotIn("python3 scripts/validate_benchmark_change.py", workflow)
        self.assertNotIn("pull_request_target:", (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "public-safety.yml"
        ).read_text(encoding="utf-8"))

    def test_benchmark_files_must_not_be_executable(self) -> None:
        import subprocess
        import tempfile

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


if __name__ == "__main__":
    unittest.main()
