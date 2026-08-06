#!/usr/bin/env python3
"""Require benchmark pull requests to contain one append-only record and generated data."""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


SUBMISSIONS = PurePosixPath("site/data/submissions")
LEADERBOARD = PurePosixPath("site/data/leaderboard.json")
SUBMISSION_NAME = re.compile(r"^[0-9a-f]{64}\.json$")


class ChangeError(ValueError):
    """Raised when a benchmark PR crosses the append-only data boundary."""


def _read_changes(repository: Path, base: str, head: str) -> list[tuple[str, str]]:
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "diff",
                "--name-status",
                "-z",
                base,
                head,
                "--",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise ChangeError("Git changes could not be inspected") from error
    if completed.returncode != 0:
        raise ChangeError("Git changes could not be inspected")
    fields = completed.stdout.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    changes: list[tuple[str, str]] = []
    index = 0
    while index < len(fields):
        try:
            status = fields[index].decode("ascii")
        except UnicodeError as error:
            raise ChangeError("Git change status is invalid") from error
        index += 1
        path_count = 2 if status.startswith(("R", "C")) else 1
        if index + path_count > len(fields):
            raise ChangeError("Git change list is malformed")
        for _ in range(path_count):
            try:
                path = fields[index].decode("utf-8", errors="strict")
            except UnicodeError as error:
                raise ChangeError("Git change path is not UTF-8") from error
            index += 1
            changes.append((status, path))
    return changes


def validate_changes(changes: list[tuple[str, str]]) -> bool:
    """Return whether this is a benchmark PR; reject mixed or unsafe benchmark diffs."""

    def touches_submission_tree(path: str) -> bool:
        candidate = PurePosixPath(path)
        return candidate == SUBMISSIONS or SUBMISSIONS in candidate.parents

    if not any(
        PurePosixPath(path) == LEADERBOARD or touches_submission_tree(path)
        for _status, path in changes
    ):
        return False
    submission_changes = [
        change
        for change in changes
        if PurePosixPath(change[1]).parent == SUBMISSIONS
    ]
    if len(changes) != 2 or len(submission_changes) != 1:
        raise ChangeError(
            "benchmark PRs may add one submission and update only the generated leaderboard"
        )
    status, submission_path = submission_changes[0]
    submission_name = PurePosixPath(submission_path).name
    if status != "A" or not SUBMISSION_NAME.fullmatch(submission_name):
        raise ChangeError("benchmark submissions must be append-only digest-named JSON files")
    leaderboard_changes = [
        change for change in changes if PurePosixPath(change[1]) == LEADERBOARD
    ]
    if leaderboard_changes != [("M", LEADERBOARD.as_posix())]:
        raise ChangeError("benchmark PRs must update the deterministic leaderboard")
    return True


def validate_benchmark_modes(repository: Path, head: str) -> None:
    """Require both public data files to remain ordinary non-executable blobs."""

    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "ls-tree",
                "-r",
                "-z",
                head,
                "--",
                SUBMISSIONS.as_posix(),
                LEADERBOARD.as_posix(),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise ChangeError("benchmark file modes could not be inspected") from error
    if completed.returncode != 0:
        raise ChangeError("benchmark file modes could not be inspected")
    for record in completed.stdout.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, kind, _object_id = metadata.decode("ascii").split(" ", 2)
            path = raw_path.decode("utf-8", errors="strict")
        except (UnicodeError, ValueError) as error:
            raise ChangeError("benchmark file mode data is malformed") from error
        candidate = PurePosixPath(path)
        if (
            candidate == LEADERBOARD
            or (candidate.parent == SUBMISSIONS and candidate.name != ".gitkeep")
        ) and (mode != "100644" or kind != "blob"):
            raise ChangeError("benchmark files must use mode 100644")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a benchmark pull-request diff.")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        is_benchmark = validate_changes(_read_changes(args.repository, args.base, args.head))
        if is_benchmark:
            validate_benchmark_modes(args.repository, args.head)
    except ChangeError as error:
        print(f"benchmark change rejected: {error}", file=sys.stderr)
        return 1
    label = "benchmark-only" if is_benchmark else "general"
    print(f"change boundary passed: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
