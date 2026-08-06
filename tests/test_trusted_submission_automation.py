from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from trusted_submission_automation import (  # noqa: E402
    AutomationError,
    GITHUB_ACTIONS_APP_ID,
    GITHUB_ACTIONS_APP_SLUG,
    GITHUB_ACTIONS_USER_ID,
    REPOSITORY_FULL_NAME,
    REPOSITORY_ID,
    REPOSITORY_NODE_ID,
    REVIEWER_LOGIN,
    REVIEWER_USER_ID,
    exact_approval_exists,
    find_request_marker,
    parse_pull_request,
    review_request_exists,
    validate_branch_protection,
    validate_repository_settings,
    validate_request_marker,
    validate_review_threads,
    validate_reviewer_identity,
    validate_review_states,
    validate_auto_merge_state,
    validate_approval_result,
)


HEAD_SHA = "a" * 40
BASE_SHA = "b" * 40
SUBMISSION_ID = "c" * 64


def pull_fixture() -> dict[str, object]:
    return {
        "number": 42,
        "node_id": "PR_kwDOExample",
        "state": "open",
        "draft": False,
        "mergeable": True,
        "mergeable_state": "blocked",
        "user": {"login": "benchmark-contributor"},
        "base": {
            "ref": "main",
            "sha": BASE_SHA,
            "repo": {
                "id": REPOSITORY_ID,
                "node_id": REPOSITORY_NODE_ID,
                "full_name": REPOSITORY_FULL_NAME,
            },
        },
        "head": {
            "ref": f"litb/submission-{SUBMISSION_ID}",
            "sha": HEAD_SHA,
            "repo": {"full_name": "benchmark-contributor/LocalInferenceTestBench"},
        },
    }


def request_comment(
    *,
    comment_id: int = 8001,
    pull_request_number: int = 42,
    base_sha: str = BASE_SHA,
    head_sha: str = HEAD_SHA,
    created_at: str = "2026-08-06T12:00:00Z",
) -> dict[str, object]:
    return {
        "id": comment_id,
        "body": (
            "@codex review\n@coderabbitai review\n\n"
            f"<!-- litb-review-request:base={base_sha};head={head_sha} -->"
        ),
        "created_at": created_at,
        "updated_at": created_at,
        "issue_url": (
            f"https://api.github.com/repos/{REPOSITORY_FULL_NAME}"
            f"/issues/{pull_request_number}"
        ),
        "html_url": (
            f"https://github.com/{REPOSITORY_FULL_NAME}/pull/{pull_request_number}"
            f"#issuecomment-{comment_id}"
        ),
        "user": {
            "id": GITHUB_ACTIONS_USER_ID,
            "login": "github-actions[bot]",
            "type": "Bot",
        },
        "performed_via_github_app": {
            "id": GITHUB_ACTIONS_APP_ID,
            "slug": GITHUB_ACTIONS_APP_SLUG,
        },
    }


def protection_fixture() -> dict[str, object]:
    return {
        "name": "main",
        "protected": True,
        "protection": {
            "enabled": True,
            "required_status_checks": {
                "enforcement_level": "everyone",
                "checks": [
                    {"context": "Tests (ubuntu-latest)", "app_id": 15368},
                    {"context": "Tests (macos-latest)", "app_id": 15368},
                    {"context": "Tests (windows-latest)", "app_id": 15368},
                    {"context": "Publication boundary", "app_id": 15368},
                    {"context": "Trusted benchmark boundary", "app_id": 15368},
                ],
            },
        },
    }


class PullRequestAuthorizationTests(unittest.TestCase):
    def test_current_open_submission_pull_request_is_accepted(self) -> None:
        state = parse_pull_request(
            pull_fixture(),
            expected_number=42,
            expected_base_sha=BASE_SHA,
            expected_head_sha=HEAD_SHA,
        )

        self.assertEqual(state.base_sha, BASE_SHA)
        self.assertEqual(state.head_sha, HEAD_SHA)
        self.assertEqual(state.submission_id, SUBMISSION_ID)

    def test_stale_commit_draft_wrong_base_and_self_review_are_rejected(self) -> None:
        fixtures = []
        stale = pull_fixture()
        stale["head"]["sha"] = "d" * 40
        fixtures.append(stale)
        draft = pull_fixture()
        draft["draft"] = True
        fixtures.append(draft)
        wrong_base = pull_fixture()
        wrong_base["base"]["ref"] = "release"
        fixtures.append(wrong_base)
        self_review = pull_fixture()
        self_review["user"]["login"] = REVIEWER_LOGIN
        fixtures.append(self_review)

        for payload in fixtures:
            with self.subTest(payload=payload):
                with self.assertRaises(AutomationError):
                    parse_pull_request(
                        payload,
                        expected_number=42,
                        expected_base_sha=BASE_SHA,
                        expected_head_sha=HEAD_SHA,
                    )

    def test_matching_ten_character_prefix_does_not_authorize_another_head(self) -> None:
        collision = HEAD_SHA[:10] + "d" * 30

        with self.assertRaisesRegex(AutomationError, "head commit changed"):
            parse_pull_request(
                pull_fixture(),
                expected_number=42,
                expected_base_sha=BASE_SHA,
                expected_head_sha=collision,
            )

    def test_expected_commits_must_be_full_lowercase_shas(self) -> None:
        for base_sha, head_sha in (
            (BASE_SHA[:-1], HEAD_SHA),
            (BASE_SHA, HEAD_SHA.upper()),
            ("not-a-commit", HEAD_SHA),
        ):
            with self.subTest(base_sha=base_sha, head_sha=head_sha):
                with self.assertRaisesRegex(AutomationError, "identity is malformed"):
                    parse_pull_request(
                        pull_fixture(),
                        expected_number=42,
                        expected_base_sha=base_sha,
                        expected_head_sha=head_sha,
                    )

    def test_non_submission_branch_is_rejected(self) -> None:
        payload = pull_fixture()
        payload["head"]["ref"] = "feature/not-a-submission"

        with self.assertRaisesRegex(AutomationError, "submission branch"):
            parse_pull_request(
                payload,
                expected_number=42,
                expected_base_sha=BASE_SHA,
                expected_head_sha=HEAD_SHA,
            )

    def test_unstable_mergeable_state_is_eligible_but_unsafe_states_are_rejected(self) -> None:
        payload = pull_fixture()
        payload["mergeable_state"] = "unstable"
        self.assertEqual(
            parse_pull_request(
                payload,
                expected_number=42,
                expected_base_sha=BASE_SHA,
                expected_head_sha=HEAD_SHA,
            ).head_sha,
            HEAD_SHA,
        )

        for mergeable_state in ("behind", "dirty", "unknown"):
            with self.subTest(mergeable_state=mergeable_state):
                payload = pull_fixture()
                payload["mergeable_state"] = mergeable_state
                with self.assertRaisesRegex(AutomationError, "conflicted, behind"):
                    parse_pull_request(
                        payload,
                        expected_number=42,
                        expected_base_sha=BASE_SHA,
                        expected_head_sha=HEAD_SHA,
                    )


class RequestMarkerTests(unittest.TestCase):
    def test_exact_live_unedited_actions_marker_is_accepted(self) -> None:
        marker = request_comment()

        state = validate_request_marker(
            marker,
            pull_request_number=42,
            marker_comment_id=8001,
            base_sha=BASE_SHA,
            head_sha=HEAD_SHA,
        )
        self.assertEqual(state.comment_id, 8001)
        self.assertTrue(
            review_request_exists(
                [[marker]],
                pull_request_number=42,
                base_sha=BASE_SHA,
                head_sha=HEAD_SHA,
            )
        )

    def test_direct_and_paginated_marker_inputs_are_equivalent(self) -> None:
        marker = request_comment(created_at="2026-08-06T12:00:00.500Z")

        direct = validate_request_marker(
            marker,
            pull_request_number=42,
            marker_comment_id=8001,
            base_sha=BASE_SHA,
            head_sha=HEAD_SHA,
        )
        paginated = validate_request_marker(
            [[marker]],
            pull_request_number=42,
            marker_comment_id=8001,
            base_sha=BASE_SHA,
            head_sha=HEAD_SHA,
        )

        self.assertEqual(direct, paginated)

    def test_review_request_cli_writes_canonical_bounded_body_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comments = root / "comments.json"
            state = root / "state.env"
            body = root / "body.txt"
            comments.write_text(json.dumps([[]]), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(
                        Path(__file__).resolve().parents[1]
                        / "scripts"
                        / "trusted_submission_automation.py"
                    ),
                    "review-request",
                    "--input",
                    str(comments),
                    "--number",
                    "42",
                    "--base",
                    BASE_SHA,
                    "--head",
                    HEAD_SHA,
                    "--output",
                    str(state),
                    "--body-output",
                    str(body),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(state.read_text(encoding="utf-8"), "exists=false\n")
            self.assertEqual(body.read_text(encoding="utf-8"), request_comment()["body"])
            self.assertLessEqual(body.stat().st_size, 512)

    def test_review_request_cli_returns_the_existing_marker_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comments = root / "comments.json"
            state = root / "state.env"
            body = root / "body.txt"
            comments.write_text(json.dumps([[request_comment()]]), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(
                        Path(__file__).resolve().parents[1]
                        / "scripts"
                        / "trusted_submission_automation.py"
                    ),
                    "review-request",
                    "--input",
                    str(comments),
                    "--number",
                    "42",
                    "--base",
                    BASE_SHA,
                    "--head",
                    HEAD_SHA,
                    "--output",
                    str(state),
                    "--body-output",
                    str(body),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                state.read_text(encoding="utf-8"),
                "exists=true\nmarker_comment_id=8001\n",
            )

    def test_cross_pull_and_stale_head_markers_are_rejected(self) -> None:
        for pull_request_number, head_sha in ((43, HEAD_SHA), (42, "d" * 40)):
            with self.subTest(
                pull_request_number=pull_request_number,
                head_sha=head_sha,
            ):
                with self.assertRaises(AutomationError):
                    validate_request_marker(
                        request_comment(),
                        pull_request_number=pull_request_number,
                        marker_comment_id=8001,
                        base_sha=BASE_SHA,
                        head_sha=head_sha,
                    )

    def test_marker_requires_positive_numeric_call_inputs(self) -> None:
        for pull_request_number, marker_comment_id in (
            (0, 8001),
            (True, 8001),
            (42, 0),
            (42, True),
        ):
            with self.subTest(
                pull_request_number=pull_request_number,
                marker_comment_id=marker_comment_id,
            ):
                with self.assertRaises(AutomationError):
                    validate_request_marker(
                        request_comment(),
                        pull_request_number=pull_request_number,
                        marker_comment_id=marker_comment_id,
                        base_sha=BASE_SHA,
                        head_sha=HEAD_SHA,
                    )

    def test_marker_identity_body_timestamp_url_and_id_mutations_fail_closed(self) -> None:
        mutations = []
        for container, key, value in (
            ("user", "id", GITHUB_ACTIONS_USER_ID + 1),
            ("user", "login", "github-actions"),
            ("user", "type", "User"),
            ("performed_via_github_app", "id", GITHUB_ACTIONS_APP_ID + 1),
            ("performed_via_github_app", "slug", "lookalike"),
        ):
            marker = request_comment()
            marker[container][key] = value
            mutations.append(marker)
        edited = request_comment()
        edited["updated_at"] = "2026-08-06T12:01:00Z"
        mutations.append(edited)
        wrong_issue = request_comment()
        wrong_issue["issue_url"] = wrong_issue["issue_url"].replace("/42", "/43")
        mutations.append(wrong_issue)
        wrong_html = request_comment()
        wrong_html["html_url"] = wrong_html["html_url"].replace("/pull/42", "/pull/43")
        mutations.append(wrong_html)
        wrong_body = request_comment()
        wrong_body["body"] = wrong_body["body"].replace(BASE_SHA, "d" * 40)
        mutations.append(wrong_body)

        for marker in mutations:
            with self.subTest(marker=marker):
                with self.assertRaises(AutomationError):
                    validate_request_marker(
                        marker,
                        pull_request_number=42,
                        marker_comment_id=8001,
                        base_sha=BASE_SHA,
                        head_sha=HEAD_SHA,
                    )

        for marker_id, comments in ((8002, [[request_comment()]]), (8001, [[]])):
            with self.subTest(marker_id=marker_id):
                with self.assertRaises(AutomationError):
                    validate_request_marker(
                        comments,
                        pull_request_number=42,
                        marker_comment_id=marker_id,
                        base_sha=BASE_SHA,
                        head_sha=HEAD_SHA,
                    )

    def test_duplicate_valid_markers_and_duplicate_comment_ids_are_rejected(self) -> None:
        second = request_comment(comment_id=8002)
        with self.assertRaisesRegex(AutomationError, "multiple"):
            find_request_marker(
                [[request_comment(), second]],
                pull_request_number=42,
                base_sha=BASE_SHA,
                head_sha=HEAD_SHA,
            )
        with self.assertRaisesRegex(AutomationError, "duplicate"):
            find_request_marker(
                [[request_comment(), request_comment()]],
                pull_request_number=42,
                base_sha=BASE_SHA,
                head_sha=HEAD_SHA,
            )

    def test_contributor_spoof_and_advisory_bot_prose_do_not_authorize(self) -> None:
        contributor = request_comment()
        contributor["user"] = {"id": 71, "login": "contributor", "type": "User"}
        self.assertIsNone(
            find_request_marker(
                [[contributor]],
                pull_request_number=42,
                base_sha=BASE_SHA,
                head_sha=HEAD_SHA,
            )
        )

        advisory = {
            "id": 9001,
            "body": "Codex unavailable; CodeRabbit rate limit reached; P1 text is advisory.",
            "user": {"id": 99, "login": "review-service[bot]", "type": "Bot"},
        }
        marker = validate_request_marker(
            [[advisory, request_comment()]],
            pull_request_number=42,
            marker_comment_id=8001,
            base_sha=BASE_SHA,
            head_sha=HEAD_SHA,
        )
        self.assertEqual(marker.comment_id, 8001)
        self.assertEqual(marker.head_sha, HEAD_SHA)


class ReviewStateTests(unittest.TestCase):

    def test_unresolved_or_truncated_review_threads_are_rejected(self) -> None:
        empty_page = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [],
                            "totalCount": 0,
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                }
            }
        }
        self.assertEqual(validate_review_threads([empty_page]), 0)

        first_page = copy.deepcopy(empty_page)
        first_page["data"]["repository"]["pullRequest"]["reviewThreads"] = {
            "nodes": [{"id": "THREAD_1", "isResolved": True}],
            "totalCount": 2,
            "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
        }
        second_page = copy.deepcopy(empty_page)
        second_page["data"]["repository"]["pullRequest"]["reviewThreads"] = {
            "nodes": [{"id": "THREAD_2", "isResolved": True}],
            "totalCount": 2,
            "pageInfo": {"hasNextPage": False, "endCursor": "cursor-2"},
        }
        self.assertEqual(validate_review_threads([first_page, second_page]), 2)

        duplicate = copy.deepcopy(second_page)
        duplicate["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"] = [
            {"id": "THREAD_1", "isResolved": True}
        ]
        with self.assertRaisesRegex(AutomationError, "duplicate"):
            validate_review_threads([first_page, duplicate])

        unresolved = copy.deepcopy(empty_page)
        unresolved["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"] = [
            {"id": "THREAD_3", "isResolved": False}
        ]
        unresolved["data"]["repository"]["pullRequest"]["reviewThreads"][
            "totalCount"
        ] = 1
        with self.assertRaisesRegex(AutomationError, "unresolved"):
            validate_review_threads([unresolved])

        truncated = copy.deepcopy(empty_page)
        truncated["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"] = {
            "hasNextPage": True,
            "endCursor": "cursor",
        }
        with self.assertRaisesRegex(AutomationError, "pagination"):
            validate_review_threads([truncated])

    def test_existing_exact_head_approval_makes_retries_idempotent(self) -> None:
        reviews = [[
            {
                "state": "APPROVED",
                "commit_id": HEAD_SHA,
                "user": {"id": REVIEWER_USER_ID, "login": REVIEWER_LOGIN},
            }
        ]]

        self.assertTrue(exact_approval_exists(reviews, head_sha=HEAD_SHA))
        self.assertFalse(exact_approval_exists(reviews, head_sha="d" * 40))
        validate_review_states(reviews)

        blocked = copy.deepcopy(reviews)
        blocked[0][0]["state"] = "CHANGES_REQUESTED"
        with self.assertRaisesRegex(AutomationError, "changes-requested"):
            validate_review_states(blocked)

        pending = copy.deepcopy(reviews)
        pending[0][0]["state"] = "PENDING"
        with self.assertRaisesRegex(AutomationError, "unsubmitted draft review"):
            validate_review_states(pending)

        still_blocked = copy.deepcopy(blocked)
        still_blocked[0].append(
            {
                "state": "COMMENTED",
                "commit_id": HEAD_SHA,
                "user": {"id": REVIEWER_USER_ID, "login": REVIEWER_LOGIN},
            }
        )
        with self.assertRaisesRegex(AutomationError, "changes-requested"):
            validate_review_states(still_blocked)

        cleared = copy.deepcopy(blocked)
        cleared[0].append(
            {
                "state": "APPROVED",
                "commit_id": HEAD_SHA,
                "user": {"id": REVIEWER_USER_ID, "login": REVIEWER_LOGIN},
            }
        )
        validate_review_states(cleared)

        for invalid_state in ("FUTURE_UNKNOWN", []):
            with self.subTest(invalid_state=invalid_state):
                unknown = copy.deepcopy(reviews)
                unknown[0][0]["state"] = invalid_state
                with self.assertRaisesRegex(AutomationError, "malformed"):
                    validate_review_states(unknown)
                with self.assertRaisesRegex(AutomationError, "malformed"):
                    exact_approval_exists(unknown, head_sha=HEAD_SHA)

    def test_only_latest_decisive_reviewer_state_is_reusable(self) -> None:
        approval = {
            "state": "APPROVED",
            "commit_id": HEAD_SHA,
            "user": {"id": REVIEWER_USER_ID, "login": REVIEWER_LOGIN},
        }
        commented = {
            "state": "COMMENTED",
            "commit_id": HEAD_SHA,
            "user": {"id": REVIEWER_USER_ID, "login": REVIEWER_LOGIN},
        }
        self.assertTrue(exact_approval_exists([[approval, commented]], head_sha=HEAD_SHA))

        for state in ("DISMISSED", "CHANGES_REQUESTED", "PENDING"):
            with self.subTest(state=state):
                superseding = {
                    "state": state,
                    "commit_id": HEAD_SHA,
                    "user": {"id": REVIEWER_USER_ID, "login": REVIEWER_LOGIN},
                }
                self.assertFalse(
                    exact_approval_exists([[approval, superseding]], head_sha=HEAD_SHA)
                )

        stale = copy.deepcopy(approval)
        stale["commit_id"] = "d" * 40
        self.assertFalse(exact_approval_exists([[approval, stale]], head_sha=HEAD_SHA))

    def test_reviewer_identity_is_pinned_to_login_and_numeric_id(self) -> None:
        validate_reviewer_identity(
            {"id": REVIEWER_USER_ID, "login": REVIEWER_LOGIN, "type": "User"}
        )
        with self.assertRaises(AutomationError):
            validate_reviewer_identity(
                {"id": REVIEWER_USER_ID + 1, "login": REVIEWER_LOGIN, "type": "User"}
            )

    def test_branch_protection_and_native_auto_merge_are_required(self) -> None:
        validate_branch_protection(protection_fixture())
        validate_repository_settings(
            {
                "id": REPOSITORY_ID,
                "node_id": REPOSITORY_NODE_ID,
                "full_name": REPOSITORY_FULL_NAME,
                "default_branch": "main",
                "allow_auto_merge": True,
            }
        )

        weak = protection_fixture()
        weak["protection"]["required_status_checks"]["enforcement_level"] = "non_admins"
        with self.assertRaises(AutomationError):
            validate_branch_protection(weak)

        with self.assertRaisesRegex(AutomationError, "auto-merge"):
            validate_repository_settings(
                {
                    "id": REPOSITORY_ID,
                    "node_id": REPOSITORY_NODE_ID,
                    "full_name": REPOSITORY_FULL_NAME,
                    "default_branch": "main",
                    "allow_auto_merge": False,
                }
            )

    def test_auto_merge_and_approval_results_are_exact_head_and_fixed_metadata(self) -> None:
        fixed_headline = f"data: add benchmark submission {SUBMISSION_ID[:12]}"
        fixed_body = "Schema-validated self-reported benchmark record; run unverified."
        state = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "id": "PR_kwDOExample",
                        "headRefOid": HEAD_SHA,
                        "state": "OPEN",
                        "isDraft": False,
                        "reviewDecision": "REVIEW_REQUIRED",
                        "autoMergeRequest": {
                            "mergeMethod": "SQUASH",
                            "commitHeadline": fixed_headline,
                            "commitBody": fixed_body,
                            "enabledBy": {
                                "databaseId": REVIEWER_USER_ID,
                                "login": REVIEWER_LOGIN,
                            },
                        },
                    }
                }
            }
        }
        self.assertTrue(
            validate_auto_merge_state(
                state,
                pull_request_node_id="PR_kwDOExample",
                head_sha=HEAD_SHA,
                submission_id=SUBMISSION_ID,
            ).enabled
        )
        state["data"]["repository"]["pullRequest"]["autoMergeRequest"] = None
        self.assertFalse(
            validate_auto_merge_state(
                state,
                pull_request_node_id="PR_kwDOExample",
                head_sha=HEAD_SHA,
                submission_id=SUBMISSION_ID,
            ).enabled
        )

        validate_approval_result(
            {
                "data": {
                    "addPullRequestReview": {
                        "pullRequestReview": {
                            "state": "APPROVED",
                            "commit": {"oid": HEAD_SHA},
                            "author": {
                                "databaseId": REVIEWER_USER_ID,
                                "login": REVIEWER_LOGIN,
                            },
                        }
                    }
                }
            },
            head_sha=HEAD_SHA,
        )

        wrong_commit = {
            "data": {
                "addPullRequestReview": {
                    "pullRequestReview": {
                        "state": "APPROVED",
                        "commit": {"oid": "d" * 40},
                        "author": {
                            "databaseId": REVIEWER_USER_ID,
                            "login": REVIEWER_LOGIN,
                        },
                    }
                }
            }
        }
        with self.assertRaises(AutomationError):
            validate_approval_result(wrong_commit, head_sha=HEAD_SHA)


if __name__ == "__main__":
    unittest.main()
