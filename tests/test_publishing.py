from __future__ import annotations

import base64
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from local_inference_test_bench import publishing  # noqa: E402
from local_inference_test_bench.publishing import (  # noqa: E402
    PublicationError,
    PublicationIdentity,
    publication_preflight,
    publish_submission,
)


SUBMISSION_ID = "a" * 64
SUBMISSION = {"submission_id": SUBMISSION_ID}
IDENTITY = PublicationIdentity(
    login="contributor",
    upstream_owner="MahdiHedhli",
    repository_name="LocalInferenceTestBench",
    base_branch="main",
    can_push_upstream=True,
)
PREPARED = publishing._PreparedChange(
    base_sha="1" * 40,
    base_tree="2" * 40,
    submission_bytes=b'{"public":"candidate"}\n',
    leaderboard_bytes=b'{"public":"leaderboard"}\n',
)


class PublishingTests(unittest.TestCase):
    def test_subprocess_boundary_uses_argv_and_discards_stderr(self) -> None:
        completed = subprocess.CompletedProcess(["gh", "api", "user"], 0, "{}", "")
        github_auth_key = "_".join(("GH", "TOKEN"))
        environment = {
            "PATH": "/safe/bin",
            "HOME": "/safe/home",
            "LLMAPI": "private-inference-token",
            "GITLEAKS_CONFIG": "/unsafe/config.toml",
            github_auth_key: "github-token",
        }
        with (
            mock.patch.dict(publishing.os.environ, environment, clear=True),
            mock.patch.object(subprocess, "run", return_value=completed) as runner,
        ):
            result = publishing._run_command(["gh", "api", "user"])

        self.assertEqual(result.returncode, 0)
        arguments, keywords = runner.call_args
        self.assertEqual(arguments[0], ["gh", "api", "user"])
        self.assertNotIn("shell", keywords)
        self.assertIs(keywords["stderr"], subprocess.DEVNULL)
        self.assertEqual(keywords["env"], {"PATH": "/safe/bin", "HOME": "/safe/home"})

        with (
            mock.patch.dict(publishing.os.environ, environment, clear=True),
            mock.patch.object(subprocess, "run", return_value=completed) as runner,
        ):
            publishing._run_command(["gh", "api", "user"], github_auth=True)
        github_environment = runner.call_args.kwargs["env"]
        self.assertEqual(github_environment[github_auth_key], "github-token")
        self.assertNotIn("LLMAPI", github_environment)
        self.assertNotIn("GITLEAKS_CONFIG", github_environment)

    def test_preflight_discloses_authenticated_identity_without_mutation(self) -> None:
        def api(endpoint: str, **_: object) -> dict:
            if endpoint == "user":
                return {"login": "contributor"}
            return {
                "name": "LocalInferenceTestBench",
                "default_branch": "main",
                "owner": {"login": "MahdiHedhli"},
                "permissions": {"push": False},
            }

        with (
            mock.patch.object(publishing.shutil, "which", return_value="/tool"),
            mock.patch.object(
                publishing, "_load_strict_denylist", return_value=b"private-literal\n"
            ),
            mock.patch.object(publishing, "_check_gitleaks"),
            mock.patch.object(publishing, "_gh_api", side_effect=api) as github,
        ):
            identity, denylist = publication_preflight()

        self.assertEqual(identity.login, "contributor")
        self.assertFalse(identity.can_push_upstream)
        self.assertEqual(identity.target_repository, "contributor/LocalInferenceTestBench")
        self.assertEqual(denylist, b"private-literal\n")
        self.assertEqual(
            [call.args[0] for call in github.call_args_list],
            ["user", "repos/MahdiHedhli/LocalInferenceTestBench"],
        )

    def test_preflight_requires_local_tools_before_github(self) -> None:
        with (
            mock.patch.object(publishing.shutil, "which", return_value=None),
            mock.patch.object(publishing, "_gh_api") as github,
            self.assertRaisesRegex(PublicationError, "GitHub CLI"),
        ):
            publication_preflight()

        github.assert_not_called()

    def test_preflight_rejects_canonical_default_branch_drift(self) -> None:
        def api(endpoint: str, **_: object) -> dict:
            if endpoint == "user":
                return {"login": "contributor"}
            return {
                "name": "LocalInferenceTestBench",
                "default_branch": "release",
                "owner": {"login": "MahdiHedhli"},
                "permissions": {"push": True},
            }

        with (
            mock.patch.object(publishing.shutil, "which", return_value="/tool"),
            mock.patch.object(
                publishing, "_load_strict_denylist", return_value=b"private-literal\n"
            ),
            mock.patch.object(publishing, "_check_gitleaks"),
            mock.patch.object(publishing, "_gh_api", side_effect=api),
            self.assertRaisesRegex(PublicationError, "default branch is not main"),
        ):
            publication_preflight()

    def test_existing_repository_must_be_the_canonical_fork(self) -> None:
        self.assertTrue(
            publishing._validate_fork(
                {
                    "fork": True,
                    "source": {"full_name": publishing.UPSTREAM_REPOSITORY},
                }
            )
        )
        self.assertFalse(
            publishing._validate_fork(
                {"fork": True, "source": {"full_name": "someone/other"}}
            )
        )

    def test_existing_pull_request_is_idempotent_and_creates_nothing(self) -> None:
        with (
            mock.patch.object(publishing, "validate_submission"),
            mock.patch.object(publishing, "render_submission_bytes", return_value=b"candidate"),
            mock.patch.object(
                publishing,
                "_verified_existing_pull_request",
                return_value="https://github.com/MahdiHedhli/LocalInferenceTestBench/pull/7",
            ),
            mock.patch.object(publishing, "_prepare_change", return_value=PREPARED) as prepare,
            mock.patch.object(
                publishing, "_current_upstream_sha", return_value=PREPARED.base_sha
            ),
            mock.patch.object(publishing, "_ensure_target_repository") as target,
        ):
            result = publish_submission(SUBMISSION, IDENTITY, b"private-literal\n")

        self.assertEqual(result.status, "existing_pull_request")
        prepare.assert_called_once()
        target.assert_not_called()

    def test_already_accepted_submission_is_idempotent(self) -> None:
        with (
            mock.patch.object(publishing, "validate_submission"),
            mock.patch.object(publishing, "render_submission_bytes", return_value=b"candidate"),
            mock.patch.object(publishing, "_prepare_change", return_value=None),
            mock.patch.object(publishing, "_ensure_target_repository") as target,
        ):
            result = publish_submission(SUBMISSION, IDENTITY, b"private-literal\n")

        self.assertEqual(result.status, "already_published")
        target.assert_not_called()

    def test_stale_base_fails_before_any_remote_mutation(self) -> None:
        with (
            mock.patch.object(publishing, "validate_submission"),
            mock.patch.object(publishing, "render_submission_bytes", return_value=b"candidate"),
            mock.patch.object(publishing, "_prepare_change", return_value=PREPARED),
            mock.patch.object(publishing, "_current_upstream_sha", return_value="3" * 40),
            mock.patch.object(publishing, "_ensure_target_repository") as target,
            self.assertRaisesRegex(PublicationError, "changed during preparation"),
        ):
            publish_submission(SUBMISSION, IDENTITY, b"private-literal\n")

        target.assert_not_called()

    def test_success_creates_only_candidate_leaderboard_branch_and_pr(self) -> None:
        api_calls: list[tuple[str, str, object]] = []

        def api(
            endpoint: str,
            *,
            method: str = "GET",
            payload: object = None,
            error_message: str,
        ) -> dict:
            api_calls.append((endpoint, method, payload))
            if endpoint.endswith("/git/trees"):
                return {"sha": "4" * 40}
            if endpoint.endswith("/git/commits"):
                return {"sha": "5" * 40}
            if endpoint.endswith("/pulls"):
                return {
                    "html_url": "https://github.com/MahdiHedhli/LocalInferenceTestBench/pull/8"
                }
            return {"ref": f"refs/heads/litb/submission-{SUBMISSION_ID}"}

        with (
            mock.patch.object(publishing, "validate_submission"),
            mock.patch.object(
                publishing, "render_submission_bytes", return_value=PREPARED.submission_bytes
            ),
            mock.patch.object(publishing, "_prepare_change", return_value=PREPARED),
            mock.patch.object(
                publishing, "_current_upstream_sha", return_value=PREPARED.base_sha
            ),
            mock.patch.object(
                publishing, "_verified_existing_pull_request", return_value=None
            ),
            mock.patch.object(
                publishing,
                "_ensure_target_repository",
                return_value=publishing.UPSTREAM_REPOSITORY,
            ),
            mock.patch.object(publishing, "_try_gh_api", return_value=None),
            mock.patch.object(
                publishing, "_create_blob", side_effect=("candidate-blob", "leaderboard-blob")
            ),
            mock.patch.object(publishing, "_gh_api", side_effect=api),
        ):
            result = publish_submission(SUBMISSION, IDENTITY, b"private-literal\n")

        self.assertEqual(result.status, "opened")
        tree_payload = next(payload for endpoint, _, payload in api_calls if endpoint.endswith("/git/trees"))
        self.assertEqual(
            {entry["path"] for entry in tree_payload["tree"]},
            {
                f"site/data/submissions/{SUBMISSION_ID}.json",
                "site/data/leaderboard.json",
            },
        )
        serialized_calls = json.dumps(api_calls, sort_keys=True)
        self.assertNotIn("private-literal", serialized_calls)
        self.assertNotIn("hardware.json", serialized_calls)
        pull_payload = next(payload for endpoint, _, payload in api_calls if endpoint.endswith("/pulls"))
        self.assertEqual(pull_payload["base"], "main")
        self.assertNotEqual(pull_payload["head"], "main")

    def test_existing_pull_request_bytes_must_match_prepared_payload(self) -> None:
        branch = f"litb/submission-{SUBMISSION_ID}"
        head_sha = "6" * 40
        pull = {
            "html_url": "https://github.com/MahdiHedhli/LocalInferenceTestBench/pull/7",
            "number": 7,
            "base": {
                "ref": "main",
                "sha": PREPARED.base_sha,
                "repo": {"full_name": publishing.UPSTREAM_REPOSITORY},
            },
            "head": {
                "ref": branch,
                "sha": head_sha,
                "repo": {"full_name": IDENTITY.target_repository},
            },
        }
        files = [
            {
                "status": "added",
                "filename": f"site/data/submissions/{SUBMISSION_ID}.json",
            },
            {"status": "modified", "filename": "site/data/leaderboard.json"},
        ]

        def api(endpoint: str, **_: object) -> dict:
            if "/git/commits/" in endpoint:
                return {"tree": {"sha": "7" * 40}}
            return {
                "truncated": False,
                "tree": [
                    {
                        "path": f"site/data/submissions/{SUBMISSION_ID}.json",
                        "mode": "100644",
                        "type": "blob",
                        "sha": "8" * 40,
                    },
                    {
                        "path": "site/data/leaderboard.json",
                        "mode": "100644",
                        "type": "blob",
                        "sha": "9" * 40,
                    },
                ],
            }

        with (
            mock.patch.object(publishing, "_existing_pull_request", return_value=pull),
            mock.patch.object(publishing, "_gh_api_list", return_value=files),
            mock.patch.object(publishing, "_gh_api", side_effect=api),
            mock.patch.object(
                publishing,
                "_repository_blob_bytes",
                side_effect=(b"corrupted", PREPARED.leaderboard_bytes),
            ),
            self.assertRaisesRegex(PublicationError, "unexpected content"),
        ):
            publishing._verified_existing_pull_request(IDENTITY, branch, PREPARED)

    def test_existing_pull_request_rejects_executable_public_file(self) -> None:
        branch = f"litb/submission-{SUBMISSION_ID}"
        pull = {
            "html_url": "https://github.com/example/pull/7",
            "number": 7,
            "base": {
                "ref": "main",
                "sha": PREPARED.base_sha,
                "repo": {"full_name": publishing.UPSTREAM_REPOSITORY},
            },
            "head": {
                "ref": branch,
                "sha": "6" * 40,
                "repo": {"full_name": IDENTITY.target_repository},
            },
        }
        files = [
            {
                "status": "added",
                "filename": f"site/data/submissions/{SUBMISSION_ID}.json",
            },
            {"status": "modified", "filename": "site/data/leaderboard.json"},
        ]

        def api(endpoint: str, **_: object) -> dict:
            if "/git/commits/" in endpoint:
                return {"tree": {"sha": "7" * 40}}
            return {
                "truncated": False,
                "tree": [
                    {
                        "path": f"site/data/submissions/{SUBMISSION_ID}.json",
                        "mode": "100755",
                        "type": "blob",
                        "sha": "8" * 40,
                    },
                    {
                        "path": "site/data/leaderboard.json",
                        "mode": "100644",
                        "type": "blob",
                        "sha": "9" * 40,
                    },
                ],
            }

        with (
            mock.patch.object(publishing, "_existing_pull_request", return_value=pull),
            mock.patch.object(publishing, "_gh_api_list", return_value=files),
            mock.patch.object(publishing, "_gh_api", side_effect=api),
            mock.patch.object(publishing, "_repository_blob_bytes") as reader,
            self.assertRaisesRegex(PublicationError, "unsafe file modes"),
        ):
            publishing._verified_existing_pull_request(IDENTITY, branch, PREPARED)
        reader.assert_not_called()

    def test_git_blob_reader_supports_payloads_over_one_megabyte(self) -> None:
        payload = b"x" * (1024 * 1024 + 1)
        with mock.patch.object(
            publishing,
            "_gh_api",
            return_value={
                "encoding": "base64",
                "content": base64.b64encode(payload).decode("ascii"),
            },
        ):
            observed = publishing._repository_blob_bytes(
                IDENTITY.target_repository, "8" * 40
            )

        self.assertEqual(observed, payload)

    def test_staged_reader_ignores_worktree_mutation(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            payload = repository / "site" / "data" / "leaderboard.json"
            payload.parent.mkdir(parents=True)
            payload.write_text("safe staged bytes\n", encoding="utf-8")
            subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            payload.write_text("unsafe worktree bytes\n", encoding="utf-8")

            staged = publishing._read_staged_bytes(
                repository, Path("site/data/leaderboard.json")
            )

        self.assertEqual(staged, b"safe staged bytes\n")


if __name__ == "__main__":
    unittest.main()
