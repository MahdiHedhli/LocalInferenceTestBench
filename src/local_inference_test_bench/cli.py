"""Command-line interface for safe preflight and baseline execution."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from .client import ClientError, OpenAICompatibleClient
from .models import ManifestError, load_manifest
from .reporting import ReportError, write_report
from .runner import BenchmarkRunner, RunnerError
from .safety import SafetyError, load_credential


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
            default=60.0,
            help="per-request timeout (default: 60)",
        )
        if name == "run":
            command.add_argument("--profile", choices=("smoke", "standard"), default="smoke")
            command.add_argument(
                "--artifacts-dir",
                type=Path,
                default=Path("artifacts"),
                help="ignored local output directory (default: artifacts)",
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
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
        return 0 if report["validity"] != "invalid" else 1
    except (ClientError, RunnerError, ReportError) as error:
        print(f"run error: {error}", file=sys.stderr)
        return 1
    except (ManifestError, SafetyError, ValueError) as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return 2
    except Exception:
        # Never echo unexpected exception text: transport libraries can embed URLs or headers.
        print("run error: unexpected internal failure", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
