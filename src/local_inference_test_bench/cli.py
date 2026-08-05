"""Command-line interface for safe preflight and baseline execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .client import ClientError, OpenAICompatibleClient
from .models import ManifestError, load_manifest
from .publishing import (
    PublicationError,
    publication_preflight,
    publish_submission,
)
from .reporting import ReportError, write_report
from .runner import BenchmarkRunner, RunnerError
from .safety import SafetyError, load_credential
from .submissions import (
    SubmissionError,
    ensure_submissions,
    load_saved_submission,
    load_public_environment_file,
    prepare_submissions,
    prepare_submission_file,
    write_submissions,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="litb",
        description="Run aggregate-only synthetic checks against a local inference endpoint.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("check", "validate configuration and query only the local model catalog"),
        ("run", "run a smoke or standard baseline sequentially"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--manifest", required=True, type=Path)
        command.add_argument(
            "--endpoint",
            required=True,
            help="local/private OpenAI-compatible base URL (never include credentials)",
        )
        command.add_argument(
            "--model",
            dest="models",
            action="append",
            default=[],
            help="public manifest model id to select; repeat to select more than one",
        )
        command.add_argument(
            "--env-file",
            type=Path,
            help="optional owner-only, Git-ignored environment file (path only)",
        )
        command.add_argument(
            "--timeout-seconds",
            type=float,
            default=300.0,
            help="per-request timeout (default: 300)",
        )
        if name == "run":
            command.add_argument("--profile", choices=("smoke", "standard"), default="smoke")
            command.add_argument(
                "--artifacts-dir",
                type=Path,
                default=Path("artifacts"),
                help="ignored local output directory (default: artifacts)",
            )
            command.add_argument(
                "--submission",
                choices=("ask", "none", "save", "pr"),
                default="ask",
                help=(
                    "post-run result action; ask prompts only for an eligible interactive "
                    "standard run (default: ask)"
                ),
            )
            command.add_argument(
                "--hardware",
                type=Path,
                default=Path(".local") / "hardware.json",
                help=(
                    "owner-only ignored public hardware/runtime/configuration descriptor "
                    "(default: .local/hardware.json)"
                ),
            )
            command.add_argument(
                "--submission-model",
                help="source report model id to save or publish from a multi-model run",
            )
            command.add_argument(
                "--submission-dir",
                type=Path,
                default=Path(".local") / "leaderboard-submissions",
                help=(
                    "owner-only ignored minimized JSON directory "
                    "(default: .local/leaderboard-submissions)"
                ),
            )
            command.add_argument(
                "--confirm-public",
                action="store_true",
                help="confirm public GitHub account, branch, and pull-request disclosure",
            )
    submission = subparsers.add_parser(
        "prepare-submission",
        help="create an identifier-minimized leaderboard candidate from a valid report",
    )
    submission.add_argument("--report", required=True, type=Path)
    submission.add_argument(
        "--hardware",
        required=True,
        type=Path,
        help="ignored public hardware/runtime/configuration descriptor JSON",
    )
    submission.add_argument(
        "--model",
        dest="models",
        action="append",
        default=[],
        help="source report model id to export; repeat to select more than one",
    )
    submission.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".local") / "leaderboard-submissions",
        help=(
            "owner-only ignored candidate directory "
            "(default: .local/leaderboard-submissions)"
        ),
    )
    publish = subparsers.add_parser(
        "publish-submission",
        help="open a reviewed public PR from a previously saved minimized candidate",
    )
    publish.add_argument(
        "--candidate",
        required=True,
        type=Path,
        help="owner-only ignored canonical minimized JSON candidate",
    )
    publish.add_argument(
        "--confirm-public",
        action="store_true",
        help="confirm public GitHub account, branch, and pull-request disclosure",
    )
    return parser


def _runner_from_args(args: argparse.Namespace) -> BenchmarkRunner:
    manifest = load_manifest(args.manifest)
    credential = load_credential(
        manifest.credential_env,
        env_file=args.env_file,
    )
    client = OpenAICompatibleClient(
        args.endpoint,
        api_key=credential,
        timeout_seconds=args.timeout_seconds,
    )
    return BenchmarkRunner(
        client,
        manifest,
        profile=getattr(args, "profile", "smoke"),
        model_ids=tuple(args.models) or None,
    )


def _interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _prompt_submission_action() -> str:
    try:
        choice = input(
            "Share this result? [Enter] keep private, [s] save minimized JSON, "
            "[p] open public PR: "
        )
    except EOFError:
        return "none"
    return {"s": "save", "p": "pr"}.get(choice.strip().casefold(), "none")


def _prompt_hardware_path(default: Path) -> Path:
    if default.exists():
        return default
    try:
        value = input(f"Public hardware descriptor [{default.as_posix()}]: ").strip()
    except EOFError:
        value = ""
    return Path(value) if value else default


def _choose_public_submission(
    submissions: tuple[dict, ...], *, interactive: bool
) -> dict | None:
    if len(submissions) == 1:
        return submissions[0]
    if not interactive:
        raise SubmissionError(
            "select one result with --submission-model before opening a public PR"
        )
    print("Choose one minimized model result for this public pull request:")
    for index, submission in enumerate(submissions, start=1):
        model = submission["model"]
        print(f"  {index}. {model['display_name']} ({model['source']})")
    try:
        raw = input("Result number [Enter cancels]: ").strip()
    except EOFError:
        raw = ""
    if not raw:
        return None
    try:
        selected = int(raw)
    except ValueError as error:
        raise SubmissionError("public result selection was invalid") from error
    if selected < 1 or selected > len(submissions):
        raise SubmissionError("public result selection was invalid")
    return submissions[selected - 1]


def _save_post_run_submissions(
    report: dict,
    args: argparse.Namespace,
    *,
    action: str,
    interactive: bool,
) -> int:
    hardware_path = _prompt_hardware_path(args.hardware) if interactive else args.hardware
    descriptor = load_public_environment_file(hardware_path)
    selected_models = (args.submission_model,) if args.submission_model else None
    submissions = prepare_submissions(report, descriptor, selected_models)
    paths = ensure_submissions(submissions, args.submission_dir)
    noun = "file" if len(paths) == 1 else "files"
    print(f"identifier-minimized JSON saved: {len(paths)} {noun}")
    if action == "save":
        return 0

    submission = _choose_public_submission(submissions, interactive=interactive)
    if submission is None:
        print("publication cancelled; minimized JSON remains saved")
        return 0
    return _publish_public_submission(
        submission,
        interactive=interactive,
        confirm_public=args.confirm_public,
    )


def _publish_public_submission(
    submission: dict,
    *,
    interactive: bool,
    confirm_public: bool,
) -> int:
    """Disclose and publish one already-validated minimized candidate."""

    print("\nComplete identifier-minimized JSON proposed for publication:")
    print(json.dumps(submission, indent=2, sort_keys=True, ensure_ascii=True))
    if not interactive and not confirm_public:
        raise PublicationError("--confirm-public is required for non-interactive publication")
    identity, denylist_bytes = publication_preflight()
    route = "canonical repository" if identity.can_push_upstream else "public fork"
    pull_target = f"{identity.upstream_owner}/{identity.repository_name}:{identity.base_branch}"
    print("\nPublic GitHub disclosure:")
    print(f"  account: {identity.login}")
    print(
        f"  destination: {identity.target_repository} ({route}), then a reviewed public "
        f"pull request to {pull_target}"
    )
    print(
        "  visible: GitHub account and timestamp, exact model, hardware, runtime, "
        "reported runtime configuration, and performance"
    )
    print("  action: create a submission branch; never write directly to protected main")
    if interactive:
        try:
            confirmation = input("Type PUBLISH to continue: ").strip()
        except EOFError:
            confirmation = ""
        if confirmation != "PUBLISH":
            print("publication cancelled; minimized JSON remains saved")
            return 0
    result = publish_submission(submission, identity, denylist_bytes)
    if result.status == "already_published":
        print(f"result already published: {result.url}")
    elif result.status == "existing_pull_request":
        print(f"existing pull request: {result.url}")
    else:
        print(f"pull request opened: {result.url}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare-submission":
            submissions = prepare_submission_file(
                args.report,
                args.hardware,
                tuple(args.models) or None,
            )
            paths = write_submissions(submissions, args.output_dir)
            noun = "file" if len(paths) == 1 else "files"
            print(f"submission ready: {len(paths)} {noun}")
            return 0
        if args.command == "publish-submission":
            submission = load_saved_submission(args.candidate)
            return _publish_public_submission(
                submission,
                interactive=_interactive_terminal(),
                confirm_public=args.confirm_public,
            )
        runner = _runner_from_args(args)
        if args.command == "check":
            statuses = runner.preflight()
            verified = sum(status == "verified" for status in statuses.values())
            unavailable = sum(status == "metadata_unavailable" for status in statuses.values())
            print(
                f"check passed: {len(statuses)} model(s), {verified} verified, "
                f"{unavailable} metadata unavailable"
            )
            return 0
        report = runner.run()
        path = write_report(report, args.artifacts_dir)
        print(f"run complete: {path.name}")
        run_status = 0 if report["validity"] != "invalid" else 1
        action = args.submission
        interactive = _interactive_terminal()
        eligible = report["validity"] == "valid" and report["profile"] == "standard"
        if action == "ask":
            action = _prompt_submission_action() if eligible and interactive else "none"
        if action == "none":
            return run_status
        if not eligible:
            if run_status != 0:
                return run_status
            raise SubmissionError(
                "only a fully valid standard run can produce a leaderboard submission"
            )
        return _save_post_run_submissions(
            report,
            args,
            action=action,
            interactive=interactive,
        )
    except (ClientError, RunnerError, ReportError) as error:
        print(f"run error: {error}", file=sys.stderr)
        return 1
    except SubmissionError as error:
        print(f"submission error: {error}", file=sys.stderr)
        return 2
    except PublicationError as error:
        print(f"publication error: {error}", file=sys.stderr)
        return 3
    except (ManifestError, SafetyError, ValueError) as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return 2
    except Exception:
        # Never echo unexpected exception text: transport libraries can embed URLs or headers.
        print("run error: unexpected internal failure", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
