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
SUBMISSION = {"submission_id": SUBMISSION_ID, "suite_version": "1.0"}
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
    def test_pull_request_body_uses_the_validated_suite_version(self) -> None:
        body = publishing._pull_request_body("a" * 64, "9.0")

        self.assertIn("Suite version: `9.0`", body)
        self.assertNotIn("Suite version: `1.0`", body)

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
            if "/git/ref/heads/" in endpoint:
                return {
                    "ref": f"refs/heads/litb/submission-{SUBMISSION_ID}",
                    "object": {"type": "commit", "sha": "5" * 40},
                }
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
                publishing,
                "_verified_existing_pull_request",
                side_effect=(
                    None,
                    "https://github.com/MahdiHedhli/LocalInferenceTestBench/pull/8",
                ),
            ) as verifier,
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
        self.assertEqual(verifier.call_count, 2)
        self.assertEqual(
            verifier.call_args_list[1].kwargs["expected_head_sha"],
            "5" * 40,
        )

    def test_ref_mutation_before_pull_request_fails_closed(self) -> None:
        branch = f"litb/submission-{SUBMISSION_ID}"
        expected_sha = "5" * 40
        pull_calls: list[object] = []

        def api(
            endpoint: str,
            *,
            method: str = "GET",
            payload: object = None,
            error_message: str,
        ) -> dict:
            if endpoint.endswith("/git/trees"):
                return {"sha": "4" * 40}
            if endpoint.endswith("/git/commits"):
                return {"sha": expected_sha}
            if endpoint.endswith("/git/refs"):
                return {"ref": f"refs/heads/{branch}"}
            if "/git/ref/heads/" in endpoint:
                return {
                    "ref": f"refs/heads/{branch}",
                    "object": {"type": "commit", "sha": "6" * 40},
                }
            if endpoint.endswith("/pulls"):
                pull_calls.append(payload)
            self.fail(f"unexpected GitHub API endpoint: {endpoint}")

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
            ) as verifier,
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
            self.assertRaisesRegex(PublicationError, "public PR/branch .* may remain"),
        ):
            publish_submission(SUBMISSION, IDENTITY, b"private-literal\n")

        self.assertEqual(pull_calls, [])
        self.assertEqual(verifier.call_count, 1)

    def test_created_pull_request_rejects_mutated_head_sha(self) -> None:
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
        with (
            mock.patch.object(publishing, "_existing_pull_request", return_value=pull),
            mock.patch.object(publishing, "_gh_api_list") as files,
            self.assertRaisesRegex(PublicationError, "unexpected identity"),
        ):
            publishing._verified_existing_pull_request(
                IDENTITY,
                branch,
                PREPARED,
                expected_head_sha="5" * 40,
            )

        files.assert_not_called()

    def test_retry_resumes_after_branch_creation_when_pr_creation_failed(self) -> None:
        branch = f"litb/submission-{SUBMISSION_ID}"
        commit_sha = "5" * 40
        tree_sha = "4" * 40
        state = {"branch_created": False, "pull_attempts": 0}
        api_calls: list[tuple[str, str, object]] = []

        def try_api(endpoint: str) -> dict | None:
            if not state["branch_created"]:
                return None
            return {
                "ref": f"refs/heads/{branch}",
                "object": {"type": "commit", "sha": commit_sha},
            }

        def create_blob(_: str, contents: bytes) -> str:
            if contents == PREPARED.submission_bytes:
                return "candidate-blob"
            self.assertEqual(contents, PREPARED.leaderboard_bytes)
            return "leaderboard-blob"

        def api(
            endpoint: str,
            *,
            method: str = "GET",
            payload: object = None,
            error_message: str,
        ) -> dict:
            api_calls.append((endpoint, method, payload))
            if endpoint.endswith("/git/trees"):
                return {"sha": tree_sha}
            if endpoint.endswith(f"/git/commits/{commit_sha}"):
                return {
                    "sha": commit_sha,
                    "message": f"data: submit benchmark {SUBMISSION_ID}",
                    "tree": {"sha": tree_sha},
                    "parents": [{"sha": PREPARED.base_sha}],
                }
            if "/compare/" in endpoint:
                return {
                    "status": "ahead",
                    "ahead_by": 1,
                    "behind_by": 0,
                    "total_commits": 1,
                    "base_commit": {"sha": PREPARED.base_sha},
                    "merge_base_commit": {"sha": PREPARED.base_sha},
                    "commits": [{"sha": commit_sha}],
                    "files": [
                        {
                            "status": "added",
                            "filename": f"site/data/submissions/{SUBMISSION_ID}.json",
                        },
                        {
                            "status": "modified",
                            "filename": "site/data/leaderboard.json",
                        },
                    ],
                }
            if "/git/trees/" in endpoint:
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
            if endpoint.endswith("/git/commits"):
                return {"sha": commit_sha}
            if endpoint.endswith("/git/refs"):
                state["branch_created"] = True
                return {"ref": f"refs/heads/{branch}"}
            if "/git/ref/heads/" in endpoint:
                return {
                    "ref": f"refs/heads/{branch}",
                    "object": {"type": "commit", "sha": commit_sha},
                }
            if endpoint.endswith("/pulls"):
                state["pull_attempts"] += 1
                if state["pull_attempts"] == 1:
                    raise PublicationError("simulated PR API failure")
                return {
                    "html_url": "https://github.com/MahdiHedhli/LocalInferenceTestBench/pull/8"
                }
            self.fail(f"unexpected GitHub API endpoint: {endpoint}")

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
                publishing,
                "_verified_existing_pull_request",
                side_effect=(
                    None,
                    None,
                    "https://github.com/MahdiHedhli/LocalInferenceTestBench/pull/8",
                ),
            ),
            mock.patch.object(
                publishing,
                "_ensure_target_repository",
                return_value=publishing.UPSTREAM_REPOSITORY,
            ),
            mock.patch.object(publishing, "_try_gh_api", side_effect=try_api),
            mock.patch.object(
                publishing, "_create_blob", side_effect=create_blob
            ) as blob_creator,
            mock.patch.object(
                publishing,
                "_repository_blob_bytes",
                side_effect=(PREPARED.submission_bytes, PREPARED.leaderboard_bytes),
            ) as blob_reader,
            mock.patch.object(publishing, "_gh_api", side_effect=api),
        ):
            with self.assertRaisesRegex(PublicationError, "public PR/branch .* may remain"):
                publish_submission(SUBMISSION, IDENTITY, b"private-literal\n")
            result = publish_submission(SUBMISSION, IDENTITY, b"private-literal\n")

        self.assertEqual(result.status, "opened")
        self.assertEqual(result.branch, branch)
        self.assertEqual(state["pull_attempts"], 2)
        self.assertEqual(blob_creator.call_count, 2)
        self.assertEqual(blob_reader.call_count, 2)
        self.assertEqual(
            sum(endpoint.endswith("/git/commits") for endpoint, _, _ in api_calls),
            1,
        )
        self.assertEqual(
            sum(endpoint.endswith("/git/refs") for endpoint, _, _ in api_calls),
            1,
        )
        self.assertEqual(
            sum(
                endpoint.endswith("/git/trees") and method == "POST"
                for endpoint, method, _ in api_calls
            ),
            1,
        )

    def test_retry_rejects_existing_branch_with_mismatched_tree(self) -> None:
        branch = f"litb/submission-{SUBMISSION_ID}"
        commit_sha = "5" * 40
        pull_calls: list[object] = []
        api_calls: list[tuple[str, str, object]] = []

        def api(
            endpoint: str,
            *,
            method: str = "GET",
            payload: object = None,
            error_message: str,
        ) -> dict:
            api_calls.append((endpoint, method, payload))
            if endpoint.endswith(f"/git/commits/{commit_sha}"):
                return {
                    "sha": commit_sha,
                    "message": f"data: submit benchmark {SUBMISSION_ID}",
                    "tree": {"sha": "7" * 40},
                    "parents": [{"sha": PREPARED.base_sha}],
                }
            if "/compare/" in endpoint:
                return {
                    "status": "ahead",
                    "ahead_by": 1,
                    "behind_by": 0,
                    "total_commits": 1,
                    "base_commit": {"sha": PREPARED.base_sha},
                    "merge_base_commit": {"sha": PREPARED.base_sha},
                    "commits": [{"sha": commit_sha}],
                    "files": [
                        {
                            "status": "added",
                            "filename": f"site/data/submissions/{SUBMISSION_ID}.json",
                        },
                        {
                            "status": "modified",
                            "filename": "site/data/leaderboard.json",
                        },
                    ],
                }
            if "/git/trees/" in endpoint:
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
            if endpoint.endswith("/pulls"):
                pull_calls.append(payload)
            self.fail(f"unexpected GitHub API endpoint: {endpoint}")

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
            mock.patch.object(
                publishing,
                "_try_gh_api",
                return_value={
                    "ref": f"refs/heads/{branch}",
                    "object": {"type": "commit", "sha": commit_sha},
                },
            ),
            mock.patch.object(publishing, "_create_blob") as blob_creator,
            mock.patch.object(
                publishing,
                "_repository_blob_bytes",
                side_effect=(b"corrupted", PREPARED.leaderboard_bytes),
            ),
            mock.patch.object(publishing, "_gh_api", side_effect=api),
            self.assertRaisesRegex(PublicationError, "branch has unexpected content"),
        ):
            publish_submission(SUBMISSION, IDENTITY, b"private-literal\n")

        self.assertEqual(pull_calls, [])
        blob_creator.assert_not_called()
        self.assertFalse(
            any(method != "GET" for _, method, _ in api_calls),
            api_calls,
        )

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
            subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
            subprocess.run(
                ["git", "config", "core.autocrlf", "false"],
                cwd=repository,
                check=True,
            )
            staged_bytes = b"safe\r\nstaged\rbytes\n"
            payload.write_bytes(staged_bytes)
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            payload.write_text("unsafe worktree bytes\n", encoding="utf-8")

            staged = publishing._read_staged_bytes(
                repository, Path("site/data/leaderboard.json")
            )

        self.assertEqual(staged, staged_bytes)

    def test_staged_reader_preserves_missing_blob_error(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
            with self.assertRaisesRegex(
                PublicationError, "staged publication payload could not be read"
            ):
                publishing._read_staged_bytes(repository, Path("missing.json"))


if __name__ == "__main__":
    unittest.main()
