"""Fail-closed GitHub pull-request publication for minimized submissions."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence
from urllib.parse import quote

from .safety import SafetyError, validate_env_file
from .submissions import render_submission_bytes, validate_submission


UPSTREAM_REPOSITORY = "MahdiHedhli/LocalInferenceTestBench"
UPSTREAM_CLONE = f"github.com/{UPSTREAM_REPOSITORY}"
BASE_BRANCH = "main"
LEADERBOARD_URL = "https://mahdihedhli.github.io/LocalInferenceTestBench/"
DEFAULT_DENYLIST = Path(".local") / "privacy-denylist.txt"
_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_MINIMUM_GITLEAKS = (8, 30, 1)
_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40,64}$")
_SAFE_ENVIRONMENT_KEYS = (
    "PATH",
    "HOME",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "SystemRoot",
    "WINDIR",
    "PATHEXT",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "XDG_CONFIG_HOME",
)
_GITHUB_AUTH_ENVIRONMENT_KEYS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_CONFIG_DIR")


class PublicationError(ValueError):
    """Raised when a result cannot be published without weakening a safety gate."""


@dataclass(frozen=True)
class PublicationIdentity:
    """Read-only GitHub identity and upstream routing decision."""

    login: str
    upstream_owner: str
    repository_name: str
    base_branch: str
    can_push_upstream: bool

    @property
    def target_repository(self) -> str:
        owner = self.upstream_owner if self.can_push_upstream else self.login
        return f"{owner}/{self.repository_name}"


@dataclass(frozen=True)
class PublicationResult:
    """Public result of an idempotent publication attempt."""

    url: str
    status: str
    branch: str | None = None


@dataclass(frozen=True)
class _CommandResult:
    returncode: int
    stdout: str


@dataclass(frozen=True)
class _BinaryCommandResult:
    returncode: int
    stdout: bytes


@dataclass(frozen=True)
class _PreparedChange:
    base_sha: str
    base_tree: str
    submission_bytes: bytes
    leaderboard_bytes: bytes


def _command_environment(
    *,
    extra_environment: Mapping[str, str] | None = None,
    github_auth: bool = False,
) -> dict[str, str]:
    allowed = _SAFE_ENVIRONMENT_KEYS + (
        _GITHUB_AUTH_ENVIRONMENT_KEYS if github_auth else ()
    )
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    if extra_environment:
        environment.update(extra_environment)
    return environment


def _run_command(
    arguments: Sequence[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    timeout: float = 120.0,
    extra_environment: Mapping[str, str] | None = None,
    github_auth: bool = False,
) -> _CommandResult:
    environment = _command_environment(
        extra_environment=extra_environment,
        github_auth=github_auth,
    )
    try:
        completed = subprocess.run(
            list(arguments),
            cwd=cwd,
            input=input_text,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise PublicationError("publication helper could not run safely") from error
    return _CommandResult(completed.returncode, completed.stdout)


def _run_binary_command(
    arguments: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: float = 120.0,
    extra_environment: Mapping[str, str] | None = None,
    github_auth: bool = False,
) -> _BinaryCommandResult:
    environment = _command_environment(
        extra_environment=extra_environment,
        github_auth=github_auth,
    )
    try:
        completed = subprocess.run(
            list(arguments),
            cwd=cwd,
            text=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise PublicationError("publication helper could not run safely") from error
    return _BinaryCommandResult(completed.returncode, completed.stdout)


def _must_run(
    arguments: Sequence[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    timeout: float = 120.0,
    extra_environment: Mapping[str, str] | None = None,
    github_auth: bool = False,
    error_message: str,
) -> str:
    result = _run_command(
        arguments,
        cwd=cwd,
        input_text=input_text,
        timeout=timeout,
        extra_environment=extra_environment,
        github_auth=github_auth,
    )
    if result.returncode != 0:
        raise PublicationError(error_message)
    return result.stdout


def _must_run_bytes(
    arguments: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: float = 120.0,
    extra_environment: Mapping[str, str] | None = None,
    github_auth: bool = False,
    error_message: str,
) -> bytes:
    result = _run_binary_command(
        arguments,
        cwd=cwd,
        timeout=timeout,
        extra_environment=extra_environment,
        github_auth=github_auth,
    )
    if result.returncode != 0:
        raise PublicationError(error_message)
    return result.stdout


def _parse_json_object(raw: str, error_message: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise PublicationError(error_message) from error
    if not isinstance(value, dict):
        raise PublicationError(error_message)
    return value


def _gh_api(
    endpoint: str,
    *,
    method: str = "GET",
    payload: Mapping[str, Any] | None = None,
    error_message: str,
) -> dict[str, Any]:
    arguments = ["gh", "api", "--hostname", "github.com", "--method", method, endpoint]
    encoded = None
    if payload is not None:
        arguments.extend(["--input", "-"])
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    raw = _must_run(
        arguments,
        input_text=encoded,
        github_auth=True,
        error_message=error_message,
    )
    return _parse_json_object(raw, error_message)


def _gh_api_list(endpoint: str, *, error_message: str) -> list[dict[str, Any]]:
    raw = _must_run(
        ["gh", "api", "--hostname", "github.com", "--method", "GET", endpoint],
        github_auth=True,
        error_message=error_message,
    )
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise PublicationError(error_message) from error
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise PublicationError(error_message)
    return value


def _try_gh_api(endpoint: str) -> dict[str, Any] | None:
    result = _run_command(
        ["gh", "api", "--hostname", "github.com", "--method", "GET", endpoint],
        github_auth=True,
    )
    if result.returncode != 0:
        return None
    return _parse_json_object(result.stdout, "GitHub returned an invalid response")


def _load_strict_denylist(path: Path) -> bytes:
    try:
        approved = validate_env_file(path)
        contents = approved.read_bytes()
        decoded = contents.decode("utf-8")
    except (OSError, UnicodeError, SafetyError) as error:
        raise PublicationError(
            "the owner-only ignored privacy denylist is required before publication"
        ) from error
    terms = [
        line.strip()
        for line in decoded.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not terms:
        raise PublicationError("the privacy denylist must contain at least one local identifier")
    return contents


def _check_gitleaks() -> None:
    if shutil.which("gitleaks") is None:
        raise PublicationError("Gitleaks 8.30.1 or newer is required before publication")
    raw = _must_run(
        ["gitleaks", "version"],
        error_message="the installed Gitleaks version could not be verified",
    ).strip()
    match = _VERSION.fullmatch(raw)
    if match is None or tuple(int(part) for part in match.groups()) < _MINIMUM_GITLEAKS:
        raise PublicationError("Gitleaks 8.30.1 or newer is required before publication")


def publication_preflight(
    *, denylist_path: Path = DEFAULT_DENYLIST
) -> tuple[PublicationIdentity, bytes]:
    """Verify local gates and return the public GitHub identity without mutating GitHub."""

    if shutil.which("gh") is None:
        raise PublicationError("GitHub CLI is required to open a benchmark pull request")
    denylist_bytes = _load_strict_denylist(denylist_path)
    _check_gitleaks()
    user = _gh_api("user", error_message="GitHub CLI is not authenticated to github.com")
    repository = _gh_api(
        f"repos/{UPSTREAM_REPOSITORY}",
        error_message="the canonical benchmark repository could not be inspected",
    )
    login = user.get("login")
    owner = repository.get("owner")
    permissions = repository.get("permissions")
    repository_name = repository.get("name")
    default_branch = repository.get("default_branch")
    if (
        not isinstance(login, str)
        or not login
        or not isinstance(owner, dict)
        or not isinstance(owner.get("login"), str)
        or not isinstance(permissions, dict)
        or not isinstance(repository_name, str)
        or not isinstance(default_branch, str)
    ):
        raise PublicationError("GitHub returned incomplete repository identity data")
    if default_branch != BASE_BRANCH:
        raise PublicationError("the canonical repository default branch is not main")
    return (
        PublicationIdentity(
            login=login,
            upstream_owner=owner["login"],
            repository_name=repository_name,
            base_branch=BASE_BRANCH,
            can_push_upstream=permissions.get("push") is True,
        ),
        denylist_bytes,
    )


def _validate_fork(repository: Mapping[str, Any]) -> bool:
    source = repository.get("source")
    return (
        repository.get("fork") is True
        and isinstance(source, dict)
        and source.get("full_name") == UPSTREAM_REPOSITORY
    )


def _ensure_target_repository(identity: PublicationIdentity) -> str:
    if identity.can_push_upstream:
        return UPSTREAM_REPOSITORY
    target = identity.target_repository
    existing = _try_gh_api(f"repos/{target}")
    if existing is not None:
        if not _validate_fork(existing):
            raise PublicationError(
                "a same-named GitHub repository exists but is not a fork of the benchmark"
            )
        return target
    _gh_api(
        f"repos/{UPSTREAM_REPOSITORY}/forks",
        method="POST",
        payload={},
        error_message="a public GitHub fork could not be created",
    )
    for _ in range(15):
        created = _try_gh_api(f"repos/{target}")
        if created is not None:
            if not _validate_fork(created):
                break
            return target
        time.sleep(1)
    raise PublicationError("the new GitHub fork was not ready in time; retry publication later")


def _git(repository: Path, *arguments: str, error_message: str) -> str:
    return _must_run(
        ["git", "-C", os.fspath(repository), *arguments],
        error_message=error_message,
    ).strip()


def _assert_exact_index(repository: Path, expected: set[str]) -> None:
    status = _git(
        repository,
        "diff",
        "--cached",
        "--name-status",
        error_message="the isolated publication change could not be inspected",
    ).splitlines()
    if set(status) != expected or len(status) != len(expected):
        raise PublicationError("publication attempted to change files outside the public dataset")


def _read_staged_bytes(repository: Path, relative: Path) -> bytes:
    return _must_run_bytes(
        [
            "git",
            "-C",
            os.fspath(repository),
            "cat-file",
            "blob",
            f":{relative.as_posix()}",
        ],
        error_message="the staged publication payload could not be read",
    )


def _prepare_change(
    submission: Mapping[str, Any],
    submission_bytes: bytes,
    denylist_bytes: bytes,
    base_branch: str,
) -> _PreparedChange | None:
    submission_id = submission["submission_id"]
    candidate_relative = Path("site") / "data" / "submissions" / f"{submission_id}.json"
    with tempfile.TemporaryDirectory(prefix="litb-publish-") as temporary:
        root = Path(temporary)
        repository = root / "repository"
        _must_run(
            [
                "gh",
                "repo",
                "clone",
                UPSTREAM_CLONE,
                os.fspath(repository),
                "--",
                "--depth=1",
                "--branch",
                base_branch,
            ],
            timeout=180,
            github_auth=True,
            error_message="the canonical benchmark repository could not be cloned",
        )
        candidate = repository / candidate_relative
        if candidate.exists():
            try:
                existing = candidate.read_bytes()
            except OSError as error:
                raise PublicationError("the accepted submission could not be inspected") from error
            if existing == submission_bytes:
                return None
            raise PublicationError("the submission identifier already has different public content")
        try:
            candidate.write_bytes(submission_bytes)
        except OSError as error:
            raise PublicationError("the isolated submission could not be written") from error
        denylist = repository / DEFAULT_DENYLIST
        try:
            denylist.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            denylist.write_bytes(denylist_bytes)
            if os.name != "nt":
                denylist.chmod(0o600)
        except OSError as error:
            raise PublicationError("the isolated privacy boundary could not be created") from error
        environment = {"PYTHONPATH": os.fspath(repository / "src")}
        _must_run(
            [sys.executable, "scripts/build_leaderboard.py"],
            cwd=repository,
            extra_environment=environment,
            error_message="the deterministic leaderboard could not be rebuilt",
        )
        leaderboard_relative = Path("site") / "data" / "leaderboard.json"
        _git(
            repository,
            "add",
            "--",
            candidate_relative.as_posix(),
            leaderboard_relative.as_posix(),
            error_message="the isolated publication change could not be staged",
        )
        expected = {
            f"A\t{candidate_relative.as_posix()}",
            f"M\t{leaderboard_relative.as_posix()}",
        }
        _assert_exact_index(repository, expected)
        _git(
            repository,
            "diff",
            "--cached",
            "--check",
            error_message="the publication diff failed validation",
        )
        checks = (
            (
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                "the benchmark test suite rejected the publication",
            ),
            (
                [sys.executable, "scripts/build_leaderboard.py", "--staged"],
                "the staged leaderboard is not deterministic",
            ),
            (
                [
                    sys.executable,
                    "scripts/public_safety.py",
                    "--staged",
                    "--strict",
                ],
                "the strict privacy gate rejected the publication",
            ),
            (
                [
                    "gitleaks",
                    "git",
                    "--staged",
                    ".",
                    "--ignore-gitleaks-allow",
                    "--redact",
                    "--no-banner",
                    "--no-color",
                    "--log-level",
                    "error",
                ],
                "the secret scan rejected the publication",
            ),
        )
        for command, error_message in checks:
            _must_run(
                command,
                cwd=repository,
                timeout=300,
                extra_environment=environment,
                error_message=error_message,
            )
        _assert_exact_index(repository, expected)
        _git(
            repository,
            "diff",
            "--cached",
            "--check",
            error_message="the publication diff failed validation after local checks",
        )
        staged_submission_bytes = _read_staged_bytes(repository, candidate_relative)
        if staged_submission_bytes != submission_bytes:
            raise PublicationError("the staged submission changed during local checks")
        leaderboard_bytes = _read_staged_bytes(repository, leaderboard_relative)
        base_sha = _git(
            repository,
            "rev-parse",
            "HEAD",
            error_message="the upstream publication base could not be resolved",
        )
        base_tree = _git(
            repository,
            "show",
            "-s",
            "--format=%T",
            "HEAD",
            error_message="the upstream publication tree could not be resolved",
        )
        return _PreparedChange(
            base_sha=base_sha,
            base_tree=base_tree,
            submission_bytes=staged_submission_bytes,
            leaderboard_bytes=leaderboard_bytes,
        )


def _current_upstream_sha(base_branch: str) -> str:
    reference = _gh_api(
        f"repos/{UPSTREAM_REPOSITORY}/git/ref/heads/{quote(base_branch, safe='/')}",
        error_message="the upstream publication base could not be rechecked",
    )
    target = reference.get("object")
    if not isinstance(target, dict) or not isinstance(target.get("sha"), str):
        raise PublicationError("GitHub returned an invalid upstream reference")
    return target["sha"]


def _create_blob(repository: str, contents: bytes) -> str:
    blob = _gh_api(
        f"repos/{repository}/git/blobs",
        method="POST",
        payload={
            "content": base64.b64encode(contents).decode("ascii"),
            "encoding": "base64",
        },
        error_message="a public Git blob could not be created",
    )
    sha = blob.get("sha")
    if not isinstance(sha, str):
        raise PublicationError("GitHub returned an invalid Git blob")
    return sha


def _verify_existing_publication_branch(
    repository: str,
    branch: str,
    reference: Mapping[str, Any],
    prepared: _PreparedChange,
    submission_id: str,
) -> str:
    target = reference.get("object")
    expected_ref = f"refs/heads/{branch}"
    if (
        reference.get("ref") != expected_ref
        or not isinstance(target, dict)
        or target.get("type") != "commit"
        or not isinstance(target.get("sha"), str)
        or _COMMIT_SHA.fullmatch(target["sha"]) is None
    ):
        raise PublicationError(
            "the existing deterministic publication branch has unexpected identity"
        )
    commit_sha = target["sha"]
    commit = _gh_api(
        f"repos/{repository}/git/commits/{quote(commit_sha, safe='')}",
        error_message="the existing deterministic publication branch could not be inspected",
    )
    tree = commit.get("tree")
    parents = commit.get("parents")
    tree_sha = tree.get("sha") if isinstance(tree, dict) else None
    if (
        commit.get("sha") != commit_sha
        or commit.get("message") != f"data: submit benchmark {submission_id}"
        or not isinstance(tree_sha, str)
        or _COMMIT_SHA.fullmatch(tree_sha) is None
        or not isinstance(parents, list)
        or len(parents) != 1
        or not isinstance(parents[0], dict)
        or parents[0].get("sha") != prepared.base_sha
    ):
        raise PublicationError(
            "the existing deterministic publication branch has unexpected content"
        )
    comparison = _gh_api(
        f"repos/{repository}/compare/{prepared.base_sha}...{commit_sha}?per_page=100",
        error_message="the existing deterministic publication branch could not be compared",
    )
    base_commit = comparison.get("base_commit")
    merge_base = comparison.get("merge_base_commit")
    commits = comparison.get("commits")
    files = comparison.get("files")
    submission_path = f"site/data/submissions/{submission_id}.json"
    expected_files = {
        ("added", submission_path),
        ("modified", "site/data/leaderboard.json"),
    }
    observed_files = (
        {(item.get("status"), item.get("filename")) for item in files}
        if isinstance(files, list) and all(isinstance(item, dict) for item in files)
        else set()
    )
    if (
        comparison.get("status") != "ahead"
        or comparison.get("ahead_by") != 1
        or comparison.get("behind_by") != 0
        or comparison.get("total_commits") != 1
        or not isinstance(base_commit, dict)
        or base_commit.get("sha") != prepared.base_sha
        or not isinstance(merge_base, dict)
        or merge_base.get("sha") != prepared.base_sha
        or not isinstance(commits, list)
        or len(commits) != 1
        or not isinstance(commits[0], dict)
        or commits[0].get("sha") != commit_sha
        or observed_files != expected_files
        or not isinstance(files, list)
        or len(files) != 2
    ):
        raise PublicationError(
            "the existing deterministic publication branch has unexpected content"
        )
    _verify_publication_tree(
        repository,
        tree_sha,
        submission_path,
        prepared,
        subject="publication branch",
    )
    return commit_sha


def _verify_branch_head(repository: str, branch: str, expected_sha: str) -> None:
    reference = _gh_api(
        f"repos/{repository}/git/ref/heads/{quote(branch, safe='/')}",
        error_message="the publication branch could not be rechecked",
    )
    target = reference.get("object")
    if (
        reference.get("ref") != f"refs/heads/{branch}"
        or not isinstance(target, dict)
        or target.get("type") != "commit"
        or target.get("sha") != expected_sha
    ):
        raise PublicationError("the publication branch changed before PR creation")


def _existing_pull_request(
    identity: PublicationIdentity, branch: str
) -> dict[str, Any] | None:
    head_owner = identity.target_repository.split("/", 1)[0]
    endpoint = (
        f"repos/{UPSTREAM_REPOSITORY}/pulls?state=open"
        f"&head={quote(head_owner + ':' + branch, safe='')}"
        f"&base={quote(identity.base_branch, safe='')}"
    )
    pulls = _gh_api_list(endpoint, error_message="existing pull requests could not be checked")
    if not pulls:
        return None
    if len(pulls) != 1:
        raise PublicationError("GitHub returned multiple matching pull requests")
    return pulls[0]


def _repository_blob_bytes(repository: str, blob_sha: str) -> bytes:
    payload = _gh_api(
        f"repos/{repository}/git/blobs/{quote(blob_sha, safe='')}",
        error_message="an existing public payload could not be inspected",
    )
    content = payload.get("content")
    if payload.get("encoding") != "base64" or not isinstance(content, str):
        raise PublicationError("GitHub returned an invalid public payload")
    compact = "".join(content.split())
    if len(compact) > 4 * 1024 * 1024:
        raise PublicationError("an existing public payload was too large")
    try:
        return base64.b64decode(compact, validate=True)
    except (ValueError, binascii.Error) as error:
        raise PublicationError("GitHub returned an invalid public payload") from error


def _verify_publication_tree(
    repository: str,
    tree_sha: str,
    submission_path: str,
    prepared: _PreparedChange,
    *,
    subject: str,
) -> None:
    tree = _gh_api(
        f"repos/{repository}/git/trees/{quote(tree_sha, safe='')}?recursive=1",
        error_message=f"an existing {subject} tree could not be inspected",
    )
    entries = tree.get("tree")
    if tree.get("truncated") is True or not isinstance(entries, list):
        raise PublicationError(f"GitHub returned an incomplete {subject} tree")
    expected_paths = {submission_path, "site/data/leaderboard.json"}
    selected = {
        item.get("path"): item
        for item in entries
        if isinstance(item, dict) and item.get("path") in expected_paths
    }
    if set(selected) != expected_paths:
        raise PublicationError(f"an existing deterministic {subject} is missing public files")
    blob_shas: dict[str, str] = {}
    for path, item in selected.items():
        sha = item.get("sha")
        if (
            item.get("mode") != "100644"
            or item.get("type") != "blob"
            or not isinstance(sha, str)
            or _COMMIT_SHA.fullmatch(sha) is None
        ):
            raise PublicationError(f"an existing deterministic {subject} has unsafe file modes")
        blob_shas[path] = sha
    if (
        _repository_blob_bytes(repository, blob_shas[submission_path])
        != prepared.submission_bytes
        or _repository_blob_bytes(
            repository,
            blob_shas["site/data/leaderboard.json"],
        )
        != prepared.leaderboard_bytes
    ):
        raise PublicationError(f"an existing deterministic {subject} has unexpected content")


def _verified_existing_pull_request(
    identity: PublicationIdentity,
    branch: str,
    prepared: _PreparedChange,
    *,
    expected_head_sha: str | None = None,
) -> str | None:
    pull = _existing_pull_request(identity, branch)
    if pull is None:
        return None
    url = pull.get("html_url")
    number = pull.get("number")
    base = pull.get("base")
    head = pull.get("head")
    if (
        not isinstance(url, str)
        or isinstance(number, bool)
        or not isinstance(number, int)
        or not isinstance(base, dict)
        or not isinstance(head, dict)
        or not isinstance(base.get("repo"), dict)
        or not isinstance(head.get("repo"), dict)
        or base.get("ref") != identity.base_branch
        or base.get("sha") != prepared.base_sha
        or base["repo"].get("full_name") != UPSTREAM_REPOSITORY
        or head.get("ref") != branch
        or head["repo"].get("full_name") != identity.target_repository
        or not isinstance(head.get("sha"), str)
        or _COMMIT_SHA.fullmatch(head["sha"]) is None
        or (expected_head_sha is not None and head["sha"] != expected_head_sha)
    ):
        raise PublicationError("an existing deterministic pull request has unexpected identity")
    files = _gh_api_list(
        f"repos/{UPSTREAM_REPOSITORY}/pulls/{number}/files?per_page=100",
        error_message="existing pull-request files could not be inspected",
    )
    submission_path = f"site/data/submissions/{branch.removeprefix('litb/submission-')}.json"
    observed = {(item.get("status"), item.get("filename")) for item in files}
    expected = {
        ("added", submission_path),
        ("modified", "site/data/leaderboard.json"),
    }
    if observed != expected or len(files) != 2:
        raise PublicationError("an existing deterministic pull request has unexpected files")
    commit = _gh_api(
        f"repos/{identity.target_repository}/git/commits/{quote(head['sha'], safe='')}",
        error_message="an existing pull-request commit could not be inspected",
    )
    commit_tree = commit.get("tree")
    tree_sha = commit_tree.get("sha") if isinstance(commit_tree, dict) else None
    if not isinstance(tree_sha, str) or _COMMIT_SHA.fullmatch(tree_sha) is None:
        raise PublicationError("GitHub returned an invalid pull-request tree")
    _verify_publication_tree(
        identity.target_repository,
        tree_sha,
        submission_path,
        prepared,
        subject="pull request",
    )
    _verify_branch_head(identity.target_repository, branch, head["sha"])
    return url


def _pull_request_body(submission_id: str, suite_version: str) -> str:
    return "\n".join(
        (
            "## Benchmark submission",
            "",
            f"Submission ID: `{submission_id}`",
            "",
            f"Suite version: `{suite_version}`",
            "",
            "## Automated contributor checks",
            "",
            "- [x] Prepared from a valid current-standard report.",
            "- [x] Identifier-minimized JSON reviewed before publication.",
            "- [x] Hardware descriptor contains only the inference path.",
            "- [x] Deterministic leaderboard rebuilt and checked.",
            "- [x] Unit, privacy, and redacted secret scans passed locally.",
            "",
            "This public pull request is eligible for base-controlled exact-head review and protected auto-merge; findings or stale data leave it open.",
        )
    )


def publish_submission(
    submission: Mapping[str, Any],
    identity: PublicationIdentity,
    denylist_bytes: bytes,
) -> PublicationResult:
    """Publish minimized data, reusing a publication PR when one already exists.

    A new PR contains only the minimized submission and generated leaderboard.
    """

    validate_submission(submission)
    submission_id = submission.get("submission_id")
    if not isinstance(submission_id, str) or not _HEX_DIGEST.fullmatch(submission_id):
        raise PublicationError("submission identifier is invalid")
    submission_bytes = render_submission_bytes(submission)
    branch = f"litb/submission-{submission_id}"
    prepared = _prepare_change(
        submission,
        submission_bytes,
        denylist_bytes,
        identity.base_branch,
    )
    if prepared is None:
        return PublicationResult(LEADERBOARD_URL, "already_published")
    if _current_upstream_sha(identity.base_branch) != prepared.base_sha:
        raise PublicationError("the leaderboard changed during preparation; retry publication")
    existing_pr = _verified_existing_pull_request(identity, branch, prepared)
    if existing_pr is not None:
        return PublicationResult(existing_pr, "existing_pull_request", branch)
    target = _ensure_target_repository(identity)
    existing_ref = _try_gh_api(
        f"repos/{target}/git/ref/heads/{quote(branch, safe='/')}"
    )
    candidate_path = f"site/data/submissions/{submission_id}.json"
    if existing_ref is not None:
        expected_head_sha = _verify_existing_publication_branch(
            target,
            branch,
            existing_ref,
            prepared,
            submission_id,
        )
    else:
        candidate_blob = _create_blob(target, prepared.submission_bytes)
        leaderboard_blob = _create_blob(target, prepared.leaderboard_bytes)
        tree = _gh_api(
            f"repos/{target}/git/trees",
            method="POST",
            payload={
                "base_tree": prepared.base_tree,
                "tree": [
                    {
                        "path": candidate_path,
                        "mode": "100644",
                        "type": "blob",
                        "sha": candidate_blob,
                    },
                    {
                        "path": "site/data/leaderboard.json",
                        "mode": "100644",
                        "type": "blob",
                        "sha": leaderboard_blob,
                    },
                ],
            },
            error_message="the isolated publication tree could not be created",
        )
        tree_sha = tree.get("sha")
        if not isinstance(tree_sha, str) or _COMMIT_SHA.fullmatch(tree_sha) is None:
            raise PublicationError("GitHub returned an invalid publication tree")
        commit = _gh_api(
            f"repos/{target}/git/commits",
            method="POST",
            payload={
                "message": f"data: submit benchmark {submission_id}",
                "tree": tree_sha,
                "parents": [prepared.base_sha],
            },
            error_message="the isolated publication commit could not be created",
        )
        commit_sha = commit.get("sha")
        if not isinstance(commit_sha, str) or _COMMIT_SHA.fullmatch(commit_sha) is None:
            raise PublicationError("GitHub returned an invalid publication commit")
        _gh_api(
            f"repos/{target}/git/refs",
            method="POST",
            payload={"ref": f"refs/heads/{branch}", "sha": commit_sha},
            error_message="the public publication branch could not be created",
        )
        expected_head_sha = commit_sha
    head_owner = target.split("/", 1)[0]
    try:
        _verify_branch_head(target, branch, expected_head_sha)
        _gh_api(
            f"repos/{UPSTREAM_REPOSITORY}/pulls",
            method="POST",
            payload={
                "title": f"benchmarks: submit {submission_id[:12]}",
                "body": _pull_request_body(
                    submission_id,
                    str(submission["suite_version"]),
                ),
                "head": f"{head_owner}:{branch}",
                "base": identity.base_branch,
                "maintainer_can_modify": True,
            },
            error_message="the public pull request could not be opened",
        )
        verified_url = _verified_existing_pull_request(
            identity,
            branch,
            prepared,
            expected_head_sha=expected_head_sha,
        )
        if verified_url is None:
            raise PublicationError("the created pull request could not be verified")
        # The PR inspection above is pinned to the expected commit, but its source
        # branch remains mutable. Recheck the ref after inspecting the PR files and
        # tree so a concurrent branch update cannot be reported as a safe success.
        _verify_branch_head(target, branch, expected_head_sha)
    except PublicationError as error:
        raise PublicationError(
            f"the PR could not be opened or verified; public PR/branch "
            f"{target}:{branch} may remain"
        ) from error
    return PublicationResult(verified_url, "opened", branch)
