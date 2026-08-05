#!/usr/bin/env python3
"""Validate accepted submissions and generate the static leaderboard payload."""

from __future__ import annotations

import argparse
from pathlib import Path
from pathlib import PurePosixPath
import subprocess
import sys
import tempfile


REPOSITORY = Path(__file__).resolve().parents[1]
SUBMISSIONS_PATH = PurePosixPath("site/data/submissions")
LEADERBOARD_PATH = PurePosixPath("site/data/leaderboard.json")
sys.path.insert(0, str(REPOSITORY / "src"))

from local_inference_test_bench.submissions import (  # noqa: E402
    SubmissionError,
    build_leaderboard,
    load_json_object,
    render_leaderboard_bytes,
    write_leaderboard,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build deterministic GitHub Pages leaderboard data.",
    )
    parser.add_argument(
        "--submissions-dir",
        type=Path,
        default=REPOSITORY / "site" / "data" / "submissions",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY / "site" / "data" / "leaderboard.json",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="fail when the committed leaderboard is not the deterministic build output",
    )
    mode.add_argument(
        "--staged",
        action="store_true",
        help="check the exact Git index instead of working-tree leaderboard data",
    )
    parser.add_argument(
        "--repository",
        type=Path,
        default=REPOSITORY,
        help=argparse.SUPPRESS,
    )
    return parser


def _git(repository: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise SubmissionError("Git index could not be read") from error
    if completed.returncode != 0:
        raise SubmissionError("Git index could not be read")
    return completed.stdout


def _materialize_staged_data(repository: Path, destination: Path) -> tuple[Path, Path]:
    records = _git(
        repository,
        "ls-files",
        "--stage",
        "-z",
        "--",
        SUBMISSIONS_PATH.as_posix(),
        LEADERBOARD_PATH.as_posix(),
    ).split(b"\0")
    submissions = destination.joinpath(*SUBMISSIONS_PATH.parts)
    submissions.mkdir(parents=True, exist_ok=True)
    output = destination.joinpath(*LEADERBOARD_PATH.parts)
    for record in records:
        if not record:
            continue
        metadata, separator, encoded_path = record.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3 or fields[0] != b"100644" or fields[2] != b"0":
            raise SubmissionError("staged leaderboard data has an unsupported Git entry")
        try:
            relative = PurePosixPath(encoded_path.decode("utf-8", errors="strict"))
        except UnicodeError as error:
            raise SubmissionError("staged leaderboard path is not public text") from error
        if relative != LEADERBOARD_PATH and relative.parts[: len(SUBMISSIONS_PATH.parts)] != SUBMISSIONS_PATH.parts:
            raise SubmissionError("staged leaderboard path is outside the public dataset")
        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_git(repository, "cat-file", "blob", fields[1].decode("ascii")))
    return submissions, output


def _check_bytes(submissions: Path, output: Path) -> dict[str, object]:
    leaderboard = build_leaderboard(submissions)
    load_json_object(output, maximum_bytes=4 * 1024 * 1024)
    try:
        actual = output.read_bytes()
    except OSError as error:
        raise SubmissionError("committed leaderboard data could not be read") from error
    if actual != render_leaderboard_bytes(leaderboard):
        raise SubmissionError("generated data is stale")
    return leaderboard


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.staged:
            if (
                args.submissions_dir != REPOSITORY / SUBMISSIONS_PATH
                or args.output != REPOSITORY / LEADERBOARD_PATH
            ):
                raise SubmissionError("staged checks use the repository data paths")
            with tempfile.TemporaryDirectory(prefix="litb-staged-") as temporary:
                submissions, output = _materialize_staged_data(
                    args.repository,
                    Path(temporary),
                )
                leaderboard = _check_bytes(submissions, output)
        elif args.check:
            leaderboard = _check_bytes(args.submissions_dir, args.output)
        else:
            leaderboard = build_leaderboard(args.submissions_dir)
        if args.check or args.staged:
            print(
                "leaderboard check passed: "
                f"{leaderboard['entry_count']} "
                f"{'entry' if leaderboard['entry_count'] == 1 else 'entries'}"
            )
            return 0
        write_leaderboard(leaderboard, args.output)
        print(
            "leaderboard built: "
            f"{leaderboard['entry_count']} "
            f"{'entry' if leaderboard['entry_count'] == 1 else 'entries'}"
        )
        return 0
    except (OSError, SubmissionError) as error:
        category = "leaderboard check failed" if args.check or args.staged else "leaderboard error"
        print(f"{category}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
