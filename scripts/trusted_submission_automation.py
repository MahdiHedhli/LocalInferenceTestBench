#!/usr/bin/env python3
"""Fail-closed helpers for trusted benchmark review and auto-merge workflows."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence


REPOSITORY_FULL_NAME = "MahdiHedhli/LocalInferenceTestBench"
REPOSITORY_ID = 1_324_333_809
REPOSITORY_NODE_ID = "R_kgDOTu-68Q"
DEFAULT_BRANCH = "main"
CODEX_LOGIN = "chatgpt-codex-connector[bot]"
CODEX_USER_ID = 199_175_422
CODEX_APP_ID = 1_144_995
CODEX_APP_SLUG = "chatgpt-codex-connector"
GITHUB_ACTIONS_LOGIN = "github-actions[bot]"
GITHUB_ACTIONS_USER_ID = 41_898_282
REVIEWER_LOGIN = "ernestpenfold-bot"
REVIEWER_USER_ID = 275_105_272
GITHUB_ACTIONS_APP_ID = 15_368

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_PREFIX_SHA = re.compile(r"^[0-9a-f]{10}$")
_SUBMISSION_BRANCH = re.compile(r"^litb/submission-([0-9a-f]{64})$")
_NODE_ID = re.compile(r"^[A-Za-z0-9_=-]{4,200}$")
_OUTPUT_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_OUTPUT_VALUE = re.compile(r"^[A-Za-z0-9_./:=+-]{1,300}$")
_CLEAN_OPENINGS = {
    "Codex Review: Didn't find any major issues. :+1:",
    "Codex Review: Didn't find any major issues. Already looking forward to the next diff.",
    "Codex Review: Didn't find any major issues. Bravo.",
}
_REVIEWED_LINE = re.compile(r"^\*\*Reviewed commit:\*\* `(?P<prefix>[0-9a-f]{10})`$")
_REVIEWED_MARKER = "**Reviewed commit:**"
_REVIEW_STATES = frozenset(
    {"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING"}
)
_CLEAN_FOOTER = (
    "\n<details> <summary>ℹ️ About Codex in GitHub</summary>\n"
    "<br/>\n\n"
    "[Your team has set up Codex to review pull requests in this repo]"
    "(https://chatgpt.com/codex/cloud/settings/general). Reviews are triggered when you\n"
    '- Open a pull request for review\n- Mark a draft as ready\n- Comment "@codex review".\n\n'
    "If Codex has suggestions, it will comment; otherwise it will react with 👍.\n\n\n\n\n"
    'Codex can also answer questions or update the PR. Try commenting "@codex address that feedback".\n'
    "            \n</details>"
)


class AutomationError(ValueError):
    """Raised when a trusted automation precondition is not exact."""


@dataclass(frozen=True)
class ReviewSignal:
    pull_request_number: int
    reviewed_commit_prefix: str
    comment_id: int
    created_at: str


@dataclass(frozen=True)
class PullRequestState:
    pull_request_number: int
    pull_request_node_id: str
    base_sha: str
    head_sha: str
    head_ref: str
    submission_id: str
    author_login: str


@dataclass(frozen=True)
class AutoMergeState:
    enabled: bool
    review_decision: str


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AutomationError(f"{path} is not an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise AutomationError(f"{path} is not a list")
    return value


def _string(value: Any, path: str, *, maximum: int = 300) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise AutomationError(f"{path} is not bounded text")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise AutomationError(f"{path} is not valid UTF-8 text") from error
    return value


def _integer(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AutomationError(f"{path} is not a positive integer")
    return value


def _timestamp(value: Any, path: str) -> tuple[str, datetime]:
    rendered = _string(value, path, maximum=40)
    if not rendered.endswith("Z"):
        raise AutomationError(f"{path} is not a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(rendered[:-1] + "+00:00")
    except ValueError as error:
        raise AutomationError(f"{path} is not an ISO timestamp") from error
    if parsed.tzinfo != timezone.utc:
        raise AutomationError(f"{path} is not a UTC timestamp")
    return rendered, parsed


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"unsupported JSON constant: {value}")


def load_json(path: str | Path, *, maximum_bytes: int = 8 * 1024 * 1024) -> Any:
    """Read bounded strict JSON without echoing rejected values."""

    source = Path(path)
    try:
        if source.is_symlink() or not source.is_file():
            raise AutomationError("automation input is not a regular file")
        if source.stat().st_size > maximum_bytes:
            raise AutomationError("automation input exceeds its size limit")
        return json.loads(
            source.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except AutomationError:
        raise
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise AutomationError("automation input is not strict JSON") from error


def _repository_is_exact(repository: Mapping[str, Any]) -> bool:
    return (
        repository.get("id") == REPOSITORY_ID
        and repository.get("node_id") == REPOSITORY_NODE_ID
        and repository.get("full_name") == REPOSITORY_FULL_NAME
    )


def _parse_codex_comment(comment_value: Any) -> tuple[int, str, str]:
    comment = _object(comment_value, "comment")
    comment_id = _integer(comment.get("id"), "comment.id")
    user = _object(comment.get("user"), "comment.user")
    if not _is_codex_identity(comment):
        raise AutomationError("comment author identity is ineligible")
    created_at, _created = _timestamp(comment.get("created_at"), "comment.created_at")
    updated_rendered, _updated = _timestamp(comment.get("updated_at"), "comment.updated_at")
    if updated_rendered != created_at:
        raise AutomationError("edited review comments are ineligible")
    body = _string(comment.get("body"), "comment.body", maximum=20_000)
    if "\r" in body or body.count(_REVIEWED_MARKER) != 1:
        raise AutomationError("review comment shape is ineligible")
    opening, separator, remainder = body.partition("\n\n")
    if not separator or opening not in _CLEAN_OPENINGS:
        raise AutomationError("review comment is not a clean signal")
    reviewed_line, line_break, footer = remainder.partition("\n")
    reviewed_match = _REVIEWED_LINE.fullmatch(reviewed_line)
    if reviewed_match is None or not line_break or footer != _CLEAN_FOOTER:
        raise AutomationError("review comment footer is ineligible")
    return comment_id, created_at, reviewed_match.group("prefix")


def _is_codex_identity(comment: Mapping[str, Any]) -> bool:
    user = comment.get("user")
    app = comment.get("performed_via_github_app")
    return (
        isinstance(user, Mapping)
        and user.get("id") == CODEX_USER_ID
        and user.get("login") == CODEX_LOGIN
        and user.get("type") == "Bot"
        and isinstance(app, Mapping)
        and app.get("id") == CODEX_APP_ID
        and app.get("slug") == CODEX_APP_SLUG
    )


def parse_review_signal(event_value: Any) -> ReviewSignal:
    """Accept only the immutable live Codex clean-comment shape."""

    event = _object(event_value, "event")
    if event.get("action") != "created":
        raise AutomationError("review comment event action is ineligible")
    repository = _object(event.get("repository"), "event.repository")
    if not _repository_is_exact(repository) or repository.get("default_branch") != DEFAULT_BRANCH:
        raise AutomationError("review comment repository is ineligible")
    issue = _object(event.get("issue"), "event.issue")
    number = _integer(issue.get("number"), "event.issue.number")
    repository_url = f"https://api.github.com/repos/{REPOSITORY_FULL_NAME}"
    pull_url = f"{repository_url}/pulls/{number}"
    pull = _object(issue.get("pull_request"), "event.issue.pull_request")
    if issue.get("repository_url") != repository_url or pull.get("url") != pull_url:
        raise AutomationError("review comment is not attached to the expected pull request")
    comment_id, created_at, prefix = _parse_codex_comment(event.get("comment"))
    return ReviewSignal(
        pull_request_number=number,
        reviewed_commit_prefix=prefix,
        comment_id=comment_id,
        created_at=created_at,
    )


def parse_pull_request(
    payload_value: Any,
    *,
    expected_number: int,
    reviewed_commit_prefix: str,
) -> PullRequestState:
    """Validate live PR identity and bind the clean signal to its current head."""

    payload = _object(payload_value, "pull_request")
    if payload.get("number") != expected_number:
        raise AutomationError("pull request number changed")
    if payload.get("state") != "open" or payload.get("draft") is not False:
        raise AutomationError("pull request is not open and ready")
    if payload.get("mergeable") is not True:
        raise AutomationError("pull request mergeability is not established")
    if payload.get("mergeable_state") not in {"blocked", "clean", "unstable"}:
        raise AutomationError("pull request is conflicted, behind, or in an unknown state")
    node_id = _string(payload.get("node_id"), "pull_request.node_id", maximum=200)
    if not _NODE_ID.fullmatch(node_id):
        raise AutomationError("pull request node identity is malformed")
    author = _object(payload.get("user"), "pull_request.user")
    author_login = _string(author.get("login"), "pull_request.user.login", maximum=100)
    if author_login == REVIEWER_LOGIN or author.get("id") == REVIEWER_USER_ID:
        raise AutomationError("reviewer-authored pull requests are ineligible")
    base = _object(payload.get("base"), "pull_request.base")
    base_repository = _object(base.get("repo"), "pull_request.base.repo")
    if base.get("ref") != DEFAULT_BRANCH or not _repository_is_exact(base_repository):
        raise AutomationError("pull request base is ineligible")
    base_sha = _string(base.get("sha"), "pull_request.base.sha", maximum=40)
    if not _FULL_SHA.fullmatch(base_sha):
        raise AutomationError("pull request base commit is malformed")
    head = _object(payload.get("head"), "pull_request.head")
    _object(head.get("repo"), "pull_request.head.repo")
    head_sha = _string(head.get("sha"), "pull_request.head.sha", maximum=40)
    if not _FULL_SHA.fullmatch(head_sha):
        raise AutomationError("pull request head commit is malformed")
    if not _PREFIX_SHA.fullmatch(reviewed_commit_prefix) or not head_sha.startswith(
        reviewed_commit_prefix
    ):
        raise AutomationError("review signal does not match the current head")
    head_ref = _string(head.get("ref"), "pull_request.head.ref", maximum=100)
    branch_match = _SUBMISSION_BRANCH.fullmatch(head_ref)
    if branch_match is None:
        raise AutomationError("pull request does not use a submission branch")
    return PullRequestState(
        pull_request_number=expected_number,
        pull_request_node_id=node_id,
        base_sha=base_sha,
        head_sha=head_sha,
        head_ref=head_ref,
        submission_id=branch_match.group(1),
        author_login=author_login,
    )


def _flatten_pages(value: Any, path: str) -> list[Any]:
    pages = _list(value, path)
    flattened: list[Any] = []
    for index, page in enumerate(pages):
        flattened.extend(_list(page, f"{path}[{index}]"))
    return flattened


def _request_body(base_sha: str, head_sha: str) -> str:
    if not _FULL_SHA.fullmatch(base_sha) or not _FULL_SHA.fullmatch(head_sha):
        raise AutomationError("request commit identity is malformed")
    return (
        "@codex review\n"
        "@coderabbitai review\n\n"
        f"<!-- litb-review-request:base={base_sha};head={head_sha} -->"
    )


def _is_trusted_request(
    comment: Mapping[str, Any],
    *,
    base_sha: str,
    head_sha: str,
) -> bool:
    user = comment.get("user")
    return (
        comment.get("body") == _request_body(base_sha, head_sha)
        and isinstance(user, Mapping)
        and user.get("id") == GITHUB_ACTIONS_USER_ID
        and user.get("login") == GITHUB_ACTIONS_LOGIN
        and user.get("type") == "Bot"
    )


def review_request_exists(comment_pages: Any, *, base_sha: str, head_sha: str) -> bool:
    """Return whether the trusted workflow already requested this exact head."""

    comments = _flatten_pages(comment_pages, "comments")
    for index, value in enumerate(comments):
        comment = _object(value, f"comments[{index}]")
        if _is_trusted_request(comment, base_sha=base_sha, head_sha=head_sha):
            return True
    return False


def validate_comment_chain(
    comment_pages: Any,
    *,
    signal: ReviewSignal,
    base_sha: str,
    head_sha: str,
) -> None:
    """Require a live unedited Codex reply after a trusted full-head request."""

    comments = _flatten_pages(comment_pages, "comments")
    live_matches: list[tuple[str, int]] = []
    requests: list[tuple[str, int]] = []
    codex_comments: list[tuple[str, int]] = []
    for index, value in enumerate(comments):
        comment = _object(value, f"comments[{index}]")
        if comment.get("id") == signal.comment_id:
            comment_id, created_at, prefix = _parse_codex_comment(comment)
            if (
                comment_id != signal.comment_id
                or created_at != signal.created_at
                or prefix != signal.reviewed_commit_prefix
            ):
                raise AutomationError("live review comment changed")
            live_matches.append((created_at, comment_id))
        if _is_codex_identity(comment):
            codex_time, _parsed = _timestamp(
                comment.get("created_at"), "codex_comment.created_at"
            )
            codex_id = _integer(comment.get("id"), "codex_comment.id")
            codex_comments.append((codex_time, codex_id))
        if _is_trusted_request(comment, base_sha=base_sha, head_sha=head_sha):
            request_id = _integer(comment.get("id"), "request_comment.id")
            request_time, _parsed = _timestamp(
                comment.get("created_at"), "request_comment.created_at"
            )
            requests.append((request_time, request_id))
    if len(live_matches) != 1:
        raise AutomationError("live review comment could not be established")
    clean_order = live_matches[0]
    prior_requests = [request for request in requests if request < clean_order]
    if not prior_requests:
        raise AutomationError("trusted full-head review request is missing or stale")
    active_request = max(prior_requests)
    responses = [comment for comment in codex_comments if comment > active_request]
    if not responses or max(responses) != clean_order:
        raise AutomationError("review signal is not the latest Codex response")


def validate_review_threads(page_values: Any) -> int:
    """Require complete pagination and zero unresolved GraphQL review threads."""

    pages = _list(page_values, "review_thread_pages")
    if not pages:
        raise AutomationError("review-thread query returned no pages")
    total = 0
    declared_total: int | None = None
    cursors: set[str] = set()
    thread_ids: set[str] = set()
    for index, page_value in enumerate(pages):
        page = _object(page_value, f"review_thread_pages[{index}]")
        if page.get("errors"):
            raise AutomationError("review-thread query returned an error")
        data = _object(page.get("data"), "review_thread_page.data")
        repository = _object(data.get("repository"), "review_thread_page.repository")
        pull_request = _object(
            repository.get("pullRequest"), "review_thread_page.pullRequest"
        )
        threads = _object(
            pull_request.get("reviewThreads"), "review_thread_page.reviewThreads"
        )
        nodes = _list(threads.get("nodes"), "review_thread_page.nodes")
        page_total = threads.get("totalCount")
        if (
            isinstance(page_total, bool)
            or not isinstance(page_total, int)
            or page_total < 0
        ):
            raise AutomationError("review-thread total is malformed")
        if declared_total is None:
            declared_total = page_total
        elif declared_total != page_total:
            raise AutomationError("review-thread totals disagree across pages")
        page_info = _object(threads.get("pageInfo"), "review_thread_page.pageInfo")
        has_next = page_info.get("hasNextPage")
        expected_has_next = index < len(pages) - 1
        if has_next is not expected_has_next:
            raise AutomationError("review-thread pagination is incomplete")
        if expected_has_next:
            cursor = page_info.get("endCursor")
            if not isinstance(cursor, str) or not cursor or cursor in cursors:
                raise AutomationError("review-thread pagination cursor is missing or repeated")
            cursors.add(cursor)
        for node_index, node_value in enumerate(nodes):
            node = _object(node_value, f"review_thread_page.nodes[{node_index}]")
            thread_id = _string(
                node.get("id"),
                f"review_thread_page.nodes[{node_index}].id",
                maximum=200,
            )
            if not _NODE_ID.fullmatch(thread_id):
                raise AutomationError("review-thread identity is malformed")
            if thread_id in thread_ids:
                raise AutomationError("review-thread pagination contains a duplicate")
            thread_ids.add(thread_id)
            if node.get("isResolved") is not True:
                raise AutomationError("pull request has unresolved review feedback")
            total += 1
    if declared_total != total:
        raise AutomationError("review-thread pagination count is incomplete")
    return total


def validate_review_states(review_pages: Any) -> None:
    """Reject the latest changes-requested or pending state from any reviewer."""

    reviews = _flatten_pages(review_pages, "reviews")
    latest_decisive: dict[tuple[Any, Any], str] = {}
    for index, value in enumerate(reviews):
        review = _object(value, f"reviews[{index}]")
        user = _object(review.get("user"), f"reviews[{index}].user")
        identity = (user.get("id"), user.get("login"))
        state = review.get("state")
        if not isinstance(state, str) or state not in _REVIEW_STATES:
            raise AutomationError("review state is malformed")
        if state == "PENDING":
            raise AutomationError("pull request has an active changes-requested review")
        if state in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            latest_decisive[identity] = state
    if any(state == "CHANGES_REQUESTED" for state in latest_decisive.values()):
        raise AutomationError("pull request has an active changes-requested review")


def exact_approval_exists(review_pages: Any, *, head_sha: str) -> bool:
    """Return whether Ernest's latest decisive review approves this exact head."""

    if not _FULL_SHA.fullmatch(head_sha):
        raise AutomationError("approval head commit is malformed")
    reviews = _flatten_pages(review_pages, "reviews")
    latest_state: str | None = None
    latest_commit: Any = None
    for index, value in enumerate(reviews):
        review = _object(value, f"reviews[{index}]")
        user = review.get("user")
        state = review.get("state")
        if not isinstance(state, str) or state not in _REVIEW_STATES:
            raise AutomationError("review state is malformed")
        if not (
            isinstance(user, Mapping)
            and user.get("id") == REVIEWER_USER_ID
            and user.get("login") == REVIEWER_LOGIN
        ):
            continue
        if state == "PENDING":
            return False
        if state in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            latest_state = state
            latest_commit = review.get("commit_id")
    return latest_state == "APPROVED" and latest_commit == head_sha


def validate_reviewer_identity(value: Any) -> None:
    """Pin the mutation credential to the authorized reviewer account."""

    identity = _object(value, "reviewer_identity")
    if (
        identity.get("id") != REVIEWER_USER_ID
        or identity.get("login") != REVIEWER_LOGIN
        or identity.get("type") != "User"
    ):
        raise AutomationError("reviewer credential identity is ineligible")


def validate_branch_protection(value: Any) -> None:
    """Verify the public protected-branch summary and app-bound required checks."""

    branch = _object(value, "protected_branch")
    if branch.get("name") != DEFAULT_BRANCH or branch.get("protected") is not True:
        raise AutomationError("the default branch is not protected")
    protection = _object(branch.get("protection"), "protected_branch.protection")
    if protection.get("enabled") is not True:
        raise AutomationError("the default branch protection is disabled")
    checks = _object(
        protection.get("required_status_checks"),
        "protected_branch.required_status_checks",
    )
    if checks.get("enforcement_level") != "everyone":
        raise AutomationError("required status checks do not apply to everyone")
    required_checks = _list(checks.get("checks"), "branch_protection.checks")
    required = {
        (item.get("context"), item.get("app_id"))
        for item in required_checks
        if isinstance(item, Mapping)
    }
    for context in (
        "Tests (ubuntu-latest)",
        "Tests (macos-latest)",
        "Tests (windows-latest)",
        "Publication boundary",
        "Trusted benchmark boundary",
    ):
        if (context, GITHUB_ACTIONS_APP_ID) not in required:
            raise AutomationError("a trusted required status check is missing")


def validate_repository_settings(value: Any) -> None:
    """Require the fixed repository identity and native auto-merge capability."""

    repository = _object(value, "repository_settings")
    if not _repository_is_exact(repository):
        raise AutomationError("repository settings identity is ineligible")
    if repository.get("default_branch") != DEFAULT_BRANCH:
        raise AutomationError("repository default branch changed")
    if repository.get("allow_auto_merge") is not True:
        raise AutomationError("repository auto-merge is disabled")


def validate_auto_merge_state(
    value: Any,
    *,
    pull_request_node_id: str,
    head_sha: str,
    submission_id: str,
) -> AutoMergeState:
    """Validate current GraphQL auto-merge state and its fixed squash metadata."""

    response = _object(value, "auto_merge_response")
    if response.get("errors"):
        raise AutomationError("auto-merge state query returned an error")
    data = _object(response.get("data"), "auto_merge_response.data")
    repository = _object(data.get("repository"), "auto_merge_response.repository")
    pull_request = _object(
        repository.get("pullRequest"), "auto_merge_response.pullRequest"
    )
    if (
        pull_request.get("id") != pull_request_node_id
        or pull_request.get("headRefOid") != head_sha
        or pull_request.get("state") != "OPEN"
        or pull_request.get("isDraft") is not False
    ):
        raise AutomationError("auto-merge state does not match the authorized pull request")
    if not re.fullmatch(r"[0-9a-f]{64}", submission_id):
        raise AutomationError("auto-merge submission identity is malformed")
    request = pull_request.get("autoMergeRequest")
    decision = pull_request.get("reviewDecision")
    if decision is None:
        decision = "NONE"
    if decision not in {"APPROVED", "CHANGES_REQUESTED", "REVIEW_REQUIRED", "NONE"}:
        raise AutomationError("pull request review decision is malformed")
    if request is None:
        return AutoMergeState(enabled=False, review_decision=decision)
    request = _object(request, "auto_merge_response.autoMergeRequest")
    enabled_by = _object(
        request.get("enabledBy"), "auto_merge_response.autoMergeRequest.enabledBy"
    )
    if (
        request.get("mergeMethod") != "SQUASH"
        or request.get("commitHeadline")
        != f"data: add benchmark submission {submission_id[:12]}"
        or request.get("commitBody")
        != "Schema-validated self-reported benchmark record; run unverified."
        or enabled_by.get("databaseId") != REVIEWER_USER_ID
        or enabled_by.get("login") != REVIEWER_LOGIN
    ):
        raise AutomationError("existing auto-merge request is not reusable")
    return AutoMergeState(enabled=True, review_decision=decision)


def validate_approval_result(value: Any, *, head_sha: str) -> None:
    """Require GitHub to return the exact reviewer, state, and approved commit."""

    response = _object(value, "approval_response")
    if response.get("errors"):
        raise AutomationError("approval mutation returned an error")
    data = _object(response.get("data"), "approval_response.data")
    mutation = _object(
        data.get("addPullRequestReview"), "approval_response.addPullRequestReview"
    )
    review = _object(
        mutation.get("pullRequestReview"),
        "approval_response.pullRequestReview",
    )
    author = _object(review.get("author"), "approval_response.author")
    commit = _object(review.get("commit"), "approval_response.commit")
    if (
        review.get("state") != "APPROVED"
        or commit.get("oid") != head_sha
        or author.get("databaseId") != REVIEWER_USER_ID
        or author.get("login") != REVIEWER_LOGIN
    ):
        raise AutomationError("approval mutation did not return an exact-head approval")


def _write_outputs(path: Path, values: Mapping[str, str | int | bool]) -> None:
    lines: list[str] = []
    for name, raw_value in values.items():
        value = str(raw_value).lower() if isinstance(raw_value, bool) else str(raw_value)
        if not _OUTPUT_NAME.fullmatch(name) or not _OUTPUT_VALUE.fullmatch(value):
            raise AutomationError("workflow output is not safely encodable")
        lines.append(f"{name}={value}\n")
    try:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.writelines(lines)
    except OSError as error:
        raise AutomationError("workflow output could not be written") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate trusted submission automation state.")
    commands = parser.add_subparsers(dest="command", required=True)

    signal = commands.add_parser("signal")
    signal.add_argument("--event", type=Path, required=True)
    signal.add_argument("--output", type=Path, required=True)

    pull = commands.add_parser("pull-request")
    pull.add_argument("--input", type=Path, required=True)
    pull.add_argument("--number", type=int, required=True)
    pull.add_argument("--prefix", required=True)
    pull.add_argument("--output", type=Path, required=True)

    comments = commands.add_parser("comments")
    comments.add_argument("--input", type=Path, required=True)
    comments.add_argument("--event", type=Path, required=True)
    comments.add_argument("--base", required=True)
    comments.add_argument("--head", required=True)

    request = commands.add_parser("review-request")
    request.add_argument("--input", type=Path, required=True)
    request.add_argument("--base", required=True)
    request.add_argument("--head", required=True)
    request.add_argument("--output", type=Path, required=True)

    threads = commands.add_parser("threads")
    threads.add_argument("--input", type=Path, required=True)

    approvals = commands.add_parser("approvals")
    approvals.add_argument("--input", type=Path, required=True)
    approvals.add_argument("--head", required=True)
    approvals.add_argument("--output", type=Path, required=True)

    review_states = commands.add_parser("review-states")
    review_states.add_argument("--input", type=Path, required=True)

    identity = commands.add_parser("identity")
    identity.add_argument("--input", type=Path, required=True)

    protection = commands.add_parser("protection")
    protection.add_argument("--input", type=Path, required=True)

    repository = commands.add_parser("repository")
    repository.add_argument("--input", type=Path, required=True)

    auto_merge = commands.add_parser("auto-merge-state")
    auto_merge.add_argument("--input", type=Path, required=True)
    auto_merge.add_argument("--pull-request-node-id", required=True)
    auto_merge.add_argument("--head", required=True)
    auto_merge.add_argument("--submission-id", required=True)
    auto_merge.add_argument("--output", type=Path, required=True)

    approval_result = commands.add_parser("approval-result")
    approval_result.add_argument("--input", type=Path, required=True)
    approval_result.add_argument("--head", required=True)
    return parser


def _run(args: argparse.Namespace) -> None:
    if args.command == "signal":
        signal = parse_review_signal(load_json(args.event))
        _write_outputs(
            args.output,
            {
                "pull_request_number": signal.pull_request_number,
                "reviewed_commit_prefix": signal.reviewed_commit_prefix,
                "comment_id": signal.comment_id,
                "comment_created_at": signal.created_at,
            },
        )
        return
    if args.command == "pull-request":
        state = parse_pull_request(
            load_json(args.input),
            expected_number=args.number,
            reviewed_commit_prefix=args.prefix,
        )
        _write_outputs(
            args.output,
            {
                "pull_request_number": state.pull_request_number,
                "pull_request_node_id": state.pull_request_node_id,
                "base_sha": state.base_sha,
                "head_sha": state.head_sha,
                "head_ref": state.head_ref,
                "submission_id": state.submission_id,
                "author_login": state.author_login,
            },
        )
        return
    if args.command == "comments":
        signal = parse_review_signal(load_json(args.event))
        validate_comment_chain(
            load_json(args.input),
            signal=signal,
            base_sha=args.base,
            head_sha=args.head,
        )
        return
    if args.command == "review-request":
        exists = review_request_exists(
            load_json(args.input),
            base_sha=args.base,
            head_sha=args.head,
        )
        _write_outputs(args.output, {"exists": exists})
        return
    if args.command == "threads":
        validate_review_threads(load_json(args.input))
        return
    if args.command == "approvals":
        exists = exact_approval_exists(load_json(args.input), head_sha=args.head)
        _write_outputs(args.output, {"exists": exists})
        return
    if args.command == "review-states":
        validate_review_states(load_json(args.input))
        return
    if args.command == "identity":
        validate_reviewer_identity(load_json(args.input))
        return
    if args.command == "protection":
        validate_branch_protection(load_json(args.input))
        return
    if args.command == "repository":
        validate_repository_settings(load_json(args.input))
        return
    if args.command == "auto-merge-state":
        state = validate_auto_merge_state(
            load_json(args.input),
            pull_request_node_id=args.pull_request_node_id,
            head_sha=args.head,
            submission_id=args.submission_id,
        )
        _write_outputs(
            args.output,
            {
                "enabled": state.enabled,
                "review_decision": state.review_decision,
            },
        )
        return
    if args.command == "approval-result":
        validate_approval_result(load_json(args.input), head_sha=args.head)
        return
    raise AutomationError("automation command is unsupported")


def main() -> int:
    args = _parser().parse_args()
    try:
        _run(args)
    except AutomationError as error:
        print(f"trusted submission automation rejected: {error}", file=sys.stderr)
        return 1
    print(f"trusted submission automation passed: {args.command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
