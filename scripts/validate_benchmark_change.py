#!/usr/bin/env python3
"""Require benchmark pull requests to contain one append-only record and generated data."""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile


SUBMISSIONS = PurePosixPath("site/data/submissions")
LEADERBOARD = PurePosixPath("site/data/leaderboard.json")
PUBLIC_DATA = PurePosixPath("site/data")
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


def validate_changes(
    changes: list[tuple[str, str]],
    *,
    require_benchmark: bool = False,
) -> bool:
    """Return whether this is a benchmark PR; reject mixed or unsafe benchmark diffs."""

    def touches_public_data(path: str) -> bool:
        candidate = PurePosixPath(path)
        return candidate == PUBLIC_DATA or PUBLIC_DATA in candidate.parents

    if not any(touches_public_data(path) for _status, path in changes):
        if require_benchmark:
            raise ChangeError("benchmark-only change required")
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


def validate_expected_submission(
    changes: list[tuple[str, str]],
    expected_submission_id: str,
) -> None:
    """Bind a deterministic publication branch to its one added content ID."""

    if not re.fullmatch(r"[0-9a-f]{64}", expected_submission_id):
        raise ChangeError("expected submission identifier is malformed")
    expected_path = (SUBMISSIONS / f"{expected_submission_id}.json").as_posix()
    if ("A", expected_path) not in changes:
        raise ChangeError("submission branch identifier does not match the added record")


def _git_bytes(repository: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise ChangeError("benchmark content could not be read") from error
    if completed.returncode != 0:
        raise ChangeError("benchmark content could not be read")
    return completed.stdout


def validate_benchmark_content(repository: Path, head: str, trusted_root: Path) -> None:
    """Run trusted schema, digest, duplicate, and byte-exact rebuild checks on head data."""

    builder = trusted_root / "scripts" / "build_leaderboard.py"
    if builder.is_symlink() or not builder.is_file():
        raise ChangeError("trusted leaderboard builder is unavailable")
    with tempfile.TemporaryDirectory(prefix="litb-trusted-data-") as temporary:
        destination = Path(temporary)
        submissions = destination.joinpath(*SUBMISSIONS.parts)
        submissions.mkdir(parents=True)
        output = destination.joinpath(*LEADERBOARD.parts)
        records = _git_bytes(
            repository,
            "ls-tree",
            "-r",
            "-z",
            head,
            "--",
            SUBMISSIONS.as_posix(),
            LEADERBOARD.as_posix(),
        ).split(b"\0")
        found_leaderboard = False
        for record in records:
            if not record:
                continue
            try:
                metadata, encoded_path = record.split(b"\t", 1)
                mode, kind, object_id = metadata.decode("ascii").split(" ", 2)
                relative = PurePosixPath(encoded_path.decode("utf-8", errors="strict"))
            except (UnicodeError, ValueError) as error:
                raise ChangeError("benchmark content tree is malformed") from error
            if relative == LEADERBOARD:
                found_leaderboard = True
            elif relative.parent != SUBMISSIONS:
                raise ChangeError("benchmark content tree escaped the public dataset")
            if mode != "100644" or kind != "blob":
                raise ChangeError("benchmark content must use ordinary files")
            raw_size = _git_bytes(repository, "cat-file", "-s", object_id)
            try:
                if not raw_size.strip().isdigit():
                    raise ValueError
                blob_size = int(raw_size.strip())
            except ValueError as error:
                raise ChangeError("benchmark content size is malformed") from error
            maximum = 4 * 1024 * 1024 if relative == LEADERBOARD else 256 * 1024
            if blob_size > maximum:
                raise ChangeError("benchmark content exceeds its trusted size limit")
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                blob = _git_bytes(repository, "cat-file", "blob", object_id)
                if len(blob) != blob_size:
                    raise ChangeError("benchmark content size changed while reading")
                target.write_bytes(blob)
            except OSError as error:
                raise ChangeError("benchmark content could not be materialized") from error
        if not found_leaderboard:
            raise ChangeError("generated leaderboard is missing")
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(builder),
                    "--submissions-dir",
                    str(submissions),
                    "--output",
                    str(output),
                    "--check",
                ],
                cwd=trusted_root,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            raise ChangeError("trusted leaderboard validation could not run") from error
        if completed.returncode != 0:
            raise ChangeError("benchmark content failed trusted validation")


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
    parser.add_argument(
        "--require-benchmark",
        action="store_true",
        help="reject general changes instead of classifying them as outside this lane",
    )
    parser.add_argument(
        "--check-content",
        action="store_true",
        help="validate head data with the trusted schema and deterministic builder",
    )
    parser.add_argument(
        "--trusted-root",
        type=Path,
        default=Path.cwd(),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--expected-submission-id",
        help="require the added filename to match a validated publication branch",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        changes = _read_changes(args.repository, args.base, args.head)
        is_benchmark = validate_changes(
            changes,
            require_benchmark=args.require_benchmark,
        )
        if is_benchmark:
            if args.expected_submission_id is not None:
                validate_expected_submission(changes, args.expected_submission_id)
            validate_benchmark_modes(args.repository, args.head)
            if args.check_content:
                validate_benchmark_content(args.repository, args.head, args.trusted_root)
    except ChangeError as error:
        print(f"benchmark change rejected: {error}", file=sys.stderr)
        return 1
    label = "benchmark-only" if is_benchmark else "general"
    print(f"change boundary passed: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
