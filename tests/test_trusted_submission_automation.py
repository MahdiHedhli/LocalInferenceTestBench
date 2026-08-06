from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from trusted_submission_automation import (  # noqa: E402
    AutomationError,
    CODEX_APP_ID,
    CODEX_APP_SLUG,
    CODEX_USER_ID,
    GITHUB_ACTIONS_USER_ID,
    REPOSITORY_FULL_NAME,
    REPOSITORY_ID,
    REPOSITORY_NODE_ID,
    REVIEWER_LOGIN,
    REVIEWER_USER_ID,
    ReviewSignal,
    exact_approval_exists,
    parse_pull_request,
    parse_review_signal,
    review_request_exists,
    validate_comment_chain,
    validate_branch_protection,
    validate_repository_settings,
    validate_review_threads,
    validate_reviewer_identity,
    validate_review_states,
    validate_auto_merge_state,
    validate_approval_result,
)


HEAD_SHA = "a" * 40
BASE_SHA = "b" * 40
SUBMISSION_ID = "c" * 64
REVIEW_PREFIX = HEAD_SHA[:10]


def clean_body(prefix: str = REVIEW_PREFIX) -> str:
    return (
        "Codex Review: Didn't find any major issues. Bravo.\n\n"
        f"**Reviewed commit:** `{prefix}`\n\n"
        "<details> <summary>ℹ️ About Codex in GitHub</summary>\n"
        "<br/>\n\n"
        "[Your team has set up Codex to review pull requests in this repo]"
        "(https://chatgpt.com/codex/cloud/settings/general). Reviews are triggered when you\n"
        '- Open a pull request for review\n- Mark a draft as ready\n- Comment "@codex review".\n\n'
        "If Codex has suggestions, it will comment; otherwise it will react with 👍.\n\n\n\n\n"
        'Codex can also answer questions or update the PR. Try commenting "@codex address that feedback".\n'
        "            \n</details>"
    )


def event_fixture() -> dict[str, object]:
    return {
        "action": "created",
        "repository": {
            "id": REPOSITORY_ID,
            "node_id": REPOSITORY_NODE_ID,
            "full_name": REPOSITORY_FULL_NAME,
            "default_branch": "main",
        },
        "issue": {
            "number": 42,
            "repository_url": f"https://api.github.com/repos/{REPOSITORY_FULL_NAME}",
            "pull_request": {
                "url": f"https://api.github.com/repos/{REPOSITORY_FULL_NAME}/pulls/42"
            },
        },
        "comment": {
            "id": 9001,
            "body": clean_body(),
            "created_at": "2026-08-06T12:01:00Z",
            "updated_at": "2026-08-06T12:01:00Z",
            "user": {
                "id": CODEX_USER_ID,
                "login": "chatgpt-codex-connector[bot]",
                "type": "Bot",
            },
            "performed_via_github_app": {
                "id": CODEX_APP_ID,
                "slug": CODEX_APP_SLUG,
            },
        },
    }


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


def request_comment(created_at: str = "2026-08-06T12:00:00Z") -> dict[str, object]:
    return {
        "id": 8001,
        "body": (
            "@codex review\n@coderabbitai review\n\n"
            f"<!-- litb-review-request:base={BASE_SHA};head={HEAD_SHA} -->"
        ),
        "created_at": created_at,
        "user": {
            "id": GITHUB_ACTIONS_USER_ID,
            "login": "github-actions[bot]",
            "type": "Bot",
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


class ReviewSignalTests(unittest.TestCase):
    def test_exact_codex_clean_comment_is_accepted(self) -> None:
        signal = parse_review_signal(event_fixture())

        self.assertEqual(signal.pull_request_number, 42)
        self.assertEqual(signal.reviewed_commit_prefix, REVIEW_PREFIX)
        self.assertEqual(signal.comment_id, 9001)

    def test_variable_plain_ascii_clean_suffix_is_accepted(self) -> None:
        event = event_fixture()
        event["comment"]["body"] = clean_body().replace(
            "Bravo.", "Already looking forward to the next diff."
        )

        self.assertEqual(parse_review_signal(event).reviewed_commit_prefix, REVIEW_PREFIX)

    def test_spoofed_bot_identity_or_app_is_rejected(self) -> None:
        mutations = (
            ("login", "chatgpt-codex-connector"),
            ("id", CODEX_USER_ID + 1),
            ("type", "User"),
        )
        for key, value in mutations:
            with self.subTest(key=key):
                event = event_fixture()
                event["comment"]["user"][key] = value
                with self.assertRaises(AutomationError):
                    parse_review_signal(event)

        for key, value in (("id", CODEX_APP_ID + 1), ("slug", "lookalike")):
            with self.subTest(app_key=key):
                event = event_fixture()
                event["comment"]["performed_via_github_app"][key] = value
                with self.assertRaises(AutomationError):
                    parse_review_signal(event)

    def test_wrong_repository_action_or_issue_kind_is_rejected(self) -> None:
        fixtures = []
        wrong_repository = event_fixture()
        wrong_repository["repository"]["id"] = REPOSITORY_ID + 1
        fixtures.append(wrong_repository)
        edited = event_fixture()
        edited["action"] = "edited"
        fixtures.append(edited)
        issue_only = event_fixture()
        del issue_only["issue"]["pull_request"]
        fixtures.append(issue_only)

        for event in fixtures:
            with self.subTest(event=event):
                with self.assertRaises(AutomationError):
                    parse_review_signal(event)

    def test_findings_malformed_markers_and_uppercase_prefix_are_rejected(self) -> None:
        bodies = (
            "### 💡 Codex Review\n\nP1 finding",
            clean_body().replace("Didn't find any major issues", "Found an issue"),
            clean_body().replace("Bravo.", "However P1 vulnerability remains!"),
            clean_body().replace(
                "Codex can also answer questions",
                "P0 exploit remains. Codex can also answer questions",
            ),
            clean_body().replace(REVIEW_PREFIX, REVIEW_PREFIX.upper()),
            clean_body() + f"\n**Reviewed commit:** `{REVIEW_PREFIX}`",
            clean_body().replace("\n\n**Reviewed", "\n**Reviewed"),
            clean_body().split("\n\n<details>", 1)[0],
            clean_body().split("\n<details>", 1)[0] + "P1 follow-up finding",
        )
        for body in bodies:
            with self.subTest(body=body[:60]):
                event = event_fixture()
                event["comment"]["body"] = body
                with self.assertRaises(AutomationError):
                    parse_review_signal(event)


class PullRequestAuthorizationTests(unittest.TestCase):
    def test_current_open_submission_pull_request_is_accepted(self) -> None:
        state = parse_pull_request(
            pull_fixture(),
            expected_number=42,
            reviewed_commit_prefix=REVIEW_PREFIX,
        )

        self.assertEqual(state.base_sha, BASE_SHA)
        self.assertEqual(state.head_sha, HEAD_SHA)
        self.assertEqual(state.submission_id, SUBMISSION_ID)

    def test_stale_prefix_draft_wrong_base_and_self_review_are_rejected(self) -> None:
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
                        reviewed_commit_prefix=REVIEW_PREFIX,
                    )

    def test_non_submission_branch_is_rejected(self) -> None:
        payload = pull_fixture()
        payload["head"]["ref"] = "feature/not-a-submission"

        with self.assertRaisesRegex(AutomationError, "submission branch"):
            parse_pull_request(
                payload,
                expected_number=42,
                reviewed_commit_prefix=REVIEW_PREFIX,
            )

    def test_unstable_mergeable_state_is_eligible_but_unsafe_states_are_rejected(self) -> None:
        payload = pull_fixture()
        payload["mergeable_state"] = "unstable"
        self.assertEqual(
            parse_pull_request(
                payload,
                expected_number=42,
                reviewed_commit_prefix=REVIEW_PREFIX,
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
                        reviewed_commit_prefix=REVIEW_PREFIX,
                    )


class ReviewStateTests(unittest.TestCase):
    def test_request_marker_and_live_clean_comment_form_a_valid_chain(self) -> None:
        signal = parse_review_signal(event_fixture())
        comments = [[request_comment(), copy.deepcopy(event_fixture()["comment"])]]

        validate_comment_chain(
            comments,
            signal=signal,
            base_sha=BASE_SHA,
            head_sha=HEAD_SHA,
        )
        self.assertTrue(
            review_request_exists(comments, base_sha=BASE_SHA, head_sha=HEAD_SHA)
        )

    def test_contributor_marker_missing_marker_and_marker_after_review_are_rejected(self) -> None:
        signal = parse_review_signal(event_fixture())
        contributor_marker = request_comment()
        contributor_marker["user"] = {
            "id": 71,
            "login": "benchmark-contributor",
            "type": "User",
        }
        late_marker = request_comment("2026-08-06T12:02:00Z")
        wrong_base_marker = request_comment()
        wrong_base_marker["body"] = wrong_base_marker["body"].replace(BASE_SHA, "d" * 40)
        clean = copy.deepcopy(event_fixture()["comment"])
        for comments in (
            [[contributor_marker, clean]],
            [[clean]],
            [[late_marker, clean]],
            [[wrong_base_marker, clean]],
        ):
            with self.subTest(comments=comments):
                with self.assertRaises(AutomationError):
                    validate_comment_chain(
                        comments,
                        signal=signal,
                        base_sha=BASE_SHA,
                        head_sha=HEAD_SHA,
                    )

    def test_selected_clean_signal_must_be_the_latest_codex_response(self) -> None:
        signal = parse_review_signal(event_fixture())
        clean = copy.deepcopy(event_fixture()["comment"])
        later_finding = copy.deepcopy(clean)
        later_finding.update(
            {
                "id": 9002,
                "body": "### Codex Review\n\nP1 issue remains.",
                "created_at": "2026-08-06T12:02:00Z",
                "updated_at": "2026-08-06T12:02:00Z",
            }
        )
        with self.assertRaisesRegex(AutomationError, "latest Codex"):
            validate_comment_chain(
                [[request_comment(), clean, later_finding]],
                signal=signal,
                base_sha=BASE_SHA,
                head_sha=HEAD_SHA,
            )

        earlier_finding = copy.deepcopy(later_finding)
        earlier_finding.update(
            {
                "id": 8999,
                "created_at": "2026-08-06T12:00:30Z",
                "updated_at": "2026-08-06T12:00:30Z",
            }
        )
        validate_comment_chain(
            [[request_comment(), earlier_finding, clean]],
            signal=signal,
            base_sha=BASE_SHA,
            head_sha=HEAD_SHA,
        )

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
