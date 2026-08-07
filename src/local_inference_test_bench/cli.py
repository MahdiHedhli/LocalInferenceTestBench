"""Command-line interface for safe preflight and baseline execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence
import webbrowser

from .client import ClientError, OpenAICompatibleClient
from .discovery import (
    DiscoveryError,
    discover_local_models,
    inventory_report,
    select_campaign_cohort,
)
from .failure_reporting import (
    ELIGIBLE_FAILURE_CATEGORIES,
    FailureSignal,
    build_failure_draft,
    build_issue_url,
    detect_report_failure,
)
from .measurement import (
    LocalMeasurementSampler,
    MeasurementError,
    build_measurement_evidence,
    write_measurement_evidence,
)
from .models import ManifestError, load_manifest
from .publishing import (
    PublicationError,
    publication_preflight,
    publish_submission,
)
from .reporting import ReportError, new_run_identity, write_report
from .runner import BenchmarkRunner, RunnerError
from .safety import SafetyError, load_credential
from .suites import resolve_public_suite
from .submissions import (
    SubmissionError,
    ensure_submissions,
    load_measurement_evidence_file,
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
                "--failure-report",
                choices=("ask", "none"),
                default="ask",
                help=(
                    "offer a sanitized GitHub issue draft after an eligible interactive "
                    "execution failure (default: ask)"
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
                "--measurement-evidence",
                type=Path,
                default=Path(".local") / "measurement-evidence.json",
                help=(
                    "owner-only ignored categorical quiescence evidence "
                    "(default: .local/measurement-evidence.json)"
                ),
            )
            command.add_argument(
                "--measurement-sampler",
                type=Path,
                help=(
                    "trusted POSIX executable adapter (maximum 16 MiB) that synchronously "
                    "returns closed pre/post categorical evidence for this run"
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
        "--measurement-evidence",
        type=Path,
        default=Path(".local") / "measurement-evidence.json",
        help=(
            "owner-only ignored categorical quiescence evidence "
            "(default: .local/measurement-evidence.json)"
        ),
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
    models_cmd = subparsers.add_parser(
        "models",
        help="discover locally installed models from supported runtimes",
    )
    models_cmd.add_argument(
        "--json",
        action="store_true",
        help="emit a public-safe inventory JSON object",
    )
    models_cmd.add_argument(
        "--eligible-only",
        action="store_true",
        help="show only models that pass the suite eligibility gate",
    )
    campaign = subparsers.add_parser(
        "campaign",
        help="campaign helpers for discovery and metadata-only selection",
    )
    campaign_sub = campaign.add_subparsers(dest="campaign_command", required=True)
    discover_cmd = campaign_sub.add_parser(
        "discover",
        help="discover and classify the local model inventory",
    )
    discover_cmd.add_argument(
        "--json",
        action="store_true",
        help="emit a public-safe inventory JSON object",
    )
    select_cmd = campaign_sub.add_parser(
        "select",
        help="select a metadata-only campaign cohort from the local inventory",
    )
    select_cmd.add_argument(
        "--limit",
        type=_positive_int,
        default=5,
        help="maximum selected models (default: 5)",
    )
    select_cmd.add_argument(
        "--json",
        action="store_true",
        help="emit selected and fallback candidates as JSON",
    )
    select_cmd.add_argument(
        "--represented-source",
        dest="represented_sources",
        action="append",
        default=[],
        help=(
            "model source already present on the public leaderboard; "
            "repeatable; used only for cross-host/novelty metadata flags"
        ),
    )
    return parser


def _eligible_public_report(report: object) -> bool:
    if not isinstance(report, dict) or report.get("validity") != "valid":
        return False
    try:
        resolve_public_suite(
            str(report.get("profile", "")),
            str(report.get("suite_version", "")),
        )
    except ValueError:
        return False
    return True


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


def _runner_failure_signal(error: RunnerError) -> FailureSignal | None:
    category = error.diagnostic_category
    phase = error.diagnostic_phase
    if (
        not isinstance(category, str)
        or category not in ELIGIBLE_FAILURE_CATEGORIES
        or not isinstance(phase, str)
    ):
        return None
    try:
        return FailureSignal(phase=phase, failure_category=category)
    except ValueError:
        return None


def _offer_failure_issue_unchecked(
    signal: FailureSignal,
    *,
    args: argparse.Namespace,
    profile: str,
    suite_version: str,
) -> None:
    """Preview and optionally open one sanitized issue draft without changing status."""

    if getattr(args, "failure_report", "none") != "ask" or not _interactive_terminal():
        return
    try:
        public_environment = load_public_environment_file(args.hardware)
    except Exception:
        # Descriptor access is best effort. Never surface a path or validation detail here.
        public_environment = None
    try:
        draft = build_failure_draft(
            signal,
            profile=profile,
            suite_version=suite_version,
            public_environment=public_environment,
        )
        issue_url = build_issue_url(draft)
    except Exception:
        print(
            "failure report unavailable: sanitized draft validation failed",
            file=sys.stderr,
        )
        return

    print("\nOptional compatibility report (this is not a model score):")
    print(json.dumps(draft, indent=2, sort_keys=True, ensure_ascii=True))
    print("\nExcluded from this draft:")
    print(
        "  logs, exception text, prompts, responses, tool arguments, endpoints, "
        "credentials, paths, host identifiers, model identifiers, and precise timestamps"
    )
    print("\nTransmission disclosure:")
    print(
        "  Opening the composer transmits this draft to GitHub immediately and may retain "
        "it in browser or network history."
    )
    print(
        "  This does not create an issue; GitHub Submit is the separate public-posting "
        "confirmation."
    )
    try:
        choice = input("Open this sanitized draft in GitHub? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        return
    if choice.strip(" \t\r\n\f\v") not in {"y", "Y"}:
        return
    try:
        opened = webbrowser.open_new_tab(issue_url)
    except Exception:
        opened = False
    if opened:
        print("GitHub issue composer opened; no issue exists until you select Submit.")
    else:
        print(
            "failure report handoff not confirmed; transmission status is unknown",
            file=sys.stderr,
        )


def _offer_failure_issue(
    signal: FailureSignal,
    *,
    args: argparse.Namespace,
    profile: str,
    suite_version: str,
) -> None:
    """Contain every optional preview, terminal, and browser handoff failure."""

    try:
        _offer_failure_issue_unchecked(
            signal,
            args=args,
            profile=profile,
            suite_version=suite_version,
        )
    except (Exception, KeyboardInterrupt):
        try:
            print(
                "failure report unavailable: interactive handoff failed",
                file=sys.stderr,
            )
        except (Exception, KeyboardInterrupt):
            pass


def _invoke_failure_offer(
    signal: FailureSignal,
    *,
    args: argparse.Namespace,
    profile: str,
    suite_version: str,
) -> None:
    """Keep the caller's benchmark status authoritative even if the offer regresses."""

    try:
        _offer_failure_issue(
            signal,
            args=args,
            profile=profile,
            suite_version=suite_version,
        )
    except (Exception, KeyboardInterrupt):
        pass


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
    measurement_evidence: dict | None = None,
) -> int:
    hardware_path = _prompt_hardware_path(args.hardware) if interactive else args.hardware
    descriptor = load_public_environment_file(hardware_path)
    if measurement_evidence is None:
        measurement_evidence = load_measurement_evidence_file(args.measurement_evidence)
    selected_models = (args.submission_model,) if args.submission_model else None
    submissions = prepare_submissions(
        report,
        descriptor,
        selected_models,
        measurement_evidence=measurement_evidence,
    )
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


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _print_inventory_table(models: Sequence[object], *, eligible_only: bool) -> None:
    rows = []
    for model in models:
        eligibility = getattr(model, "eligibility", "")
        if eligible_only and eligibility != "eligible":
            continue
        rows.append(model)
    if not rows:
        print("no models matched")
        return
    print(
        f"{'ID':<36} {'Elig':<10} {'Scale':<10} {'Precision':<16} "
        f"{'Backend':<18} {'Reason'}"
    )
    for model in rows:
        total = getattr(model, "parameter_scale_total_billions", None)
        active = getattr(model, "parameter_scale_active_billions", None)
        if total is None:
            scale = "-"
        elif active is not None:
            scale = f"{total:g}B-A{active:g}B"
        else:
            scale = f"{total:g}B"
        reason = getattr(model, "exclusion_reason", None) or "ok"
        print(
            f"{getattr(model, 'runtime_local_id', '')[:36]:<36} "
            f"{getattr(model, 'eligibility', ''):<10} "
            f"{scale:<10} "
            f"{str(getattr(model, 'precision', None) or '-'):<16} "
            f"{str(getattr(model, 'backend', None) or '-'):<18} "
            f"{reason}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare-submission":
            submissions = prepare_submission_file(
                args.report,
                args.hardware,
                tuple(args.models) or None,
                measurement_evidence_path=args.measurement_evidence,
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
        if args.command == "models":
            models = discover_local_models()
            report = inventory_report(models)
            if args.json:
                print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))
            else:
                print(
                    f"discovered={report['discovered_count']} "
                    f"eligible={report['eligible_count']} "
                    f"excluded={report['excluded_count']}"
                )
                _print_inventory_table(models, eligible_only=args.eligible_only)
            return 0
        if args.command == "campaign":
            models = discover_local_models()
            if args.campaign_command == "discover":
                report = inventory_report(models)
                if args.json:
                    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))
                else:
                    print(
                        f"discovered={report['discovered_count']} "
                        f"eligible={report['eligible_count']} "
                        f"excluded={report['excluded_count']} "
                        f"duplicate_groups={report['duplicate_group_count']}"
                    )
                    _print_inventory_table(models, eligible_only=False)
                return 0
            if args.campaign_command == "select":
                represented = {
                    value.strip().lower()
                    for value in args.represented_sources
                    if isinstance(value, str) and value.strip()
                }
                selected, fallback = select_campaign_cohort(
                    models,
                    limit=args.limit,
                    represented_sources=represented,
                )
                report = inventory_report(
                    models,
                    selected=selected,
                    fallback=fallback,
                )
                if args.json:
                    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))
                else:
                    print(
                        f"selected={len(selected)}/{args.limit} "
                        f"eligible={report['eligible_count']} "
                        f"policy={report['selection_policy_version']}"
                    )
                    for index, candidate in enumerate(selected, start=1):
                        model = candidate.model
                        print(
                            f"{index}. {model.runtime_local_id} "
                            f"score={candidate.utility_score:g} "
                            f"({candidate.selection_reason})"
                        )
                    if fallback:
                        print("fallback:")
                        for index, candidate in enumerate(fallback, start=1):
                            print(
                                f"  {index}. {candidate.model.runtime_local_id} "
                                f"score={candidate.utility_score:g}"
                            )
                return 0
        sampler_requested = (
            args.command == "run" and args.measurement_sampler is not None
        )
        sampler = None
        measurement_error: MeasurementError | None = None
        run_identity = new_run_identity() if sampler_requested else None
        if sampler_requested:
            try:
                sampler = LocalMeasurementSampler(args.measurement_sampler)
            except MeasurementError as error:
                measurement_error = error
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
        sampler_model_ids = (
            tuple(model.id for model in runner.models) if sampler is not None else ()
        )
        pre_sample = None
        post_sample = None
        if sampler is not None and run_identity is not None:
            try:
                pre_sample = sampler.sample(
                    phase="pre",
                    source_run_id=run_identity[0],
                    model_ids=sampler_model_ids,
                )
            except MeasurementError as error:
                measurement_error = error
        try:
            report = (
                runner.run(run_identity=run_identity)
                if run_identity is not None
                else runner.run()
            )
        except (ClientError, RunnerError):
            raise
        except Exception:
            # This boundary is intentionally narrow and never retains exception detail.
            raise RunnerError(
                "unexpected internal failure",
                diagnostic_category="internal_harness_error",
                diagnostic_phase="runner_internal",
            ) from None
        if sampler is not None and run_identity is not None and pre_sample is not None:
            try:
                post_sample = sampler.sample(
                    phase="post",
                    source_run_id=run_identity[0],
                    model_ids=sampler_model_ids,
                )
            except MeasurementError as error:
                measurement_error = error
        path = write_report(report, args.artifacts_dir)
        print(f"run complete: {path.name}")
        run_status = 0 if report["validity"] != "invalid" else 1
        try:
            failure_signal = detect_report_failure(report)
        except Exception:
            failure_signal = None
        if failure_signal is not None:
            _invoke_failure_offer(
                failure_signal,
                args=args,
                profile=str(report.get("profile", args.profile)),
                suite_version=str(report.get("suite_version", "1.0")),
            )
        action = args.submission
        interactive = _interactive_terminal()
        eligible = _eligible_public_report(report)
        if action == "ask":
            action = _prompt_submission_action() if eligible and interactive else "none"
        if action == "none":
            return run_status
        if not eligible:
            if run_status != 0:
                return run_status
            raise SubmissionError(
                "only a fully valid registered public-suite run can produce a leaderboard submission"
            )
        if not interactive and not sampler_requested:
            raise MeasurementError(
                "non-interactive run submission requires --measurement-sampler; "
                "private report retained"
            )
        sampled_evidence = None
        if sampler_requested:
            if measurement_error is not None or pre_sample is None or post_sample is None:
                raise MeasurementError(
                    "measurement sampler did not produce complete evidence; private report retained"
                )
            report_model_ids = tuple(model["model_id"] for model in report["models"])
            if (
                run_identity is None
                or report["run_id"] != run_identity[0]
                or report_model_ids != sampler_model_ids
            ):
                raise MeasurementError(
                    "measurement sampler binding did not match the completed run; "
                    "private report retained"
                )
            sampled_evidence = build_measurement_evidence(
                source_run_id=report["run_id"],
                model_ids=report_model_ids,
                pre=pre_sample,
                post=post_sample,
            )
            write_measurement_evidence(sampled_evidence, args.measurement_evidence)
        return _save_post_run_submissions(
            report,
            args,
            action=action,
            interactive=interactive,
            measurement_evidence=sampled_evidence,
        )
    except (ClientError, RunnerError, ReportError) as error:
        print(f"run error: {error}", file=sys.stderr)
        if args.command == "run" and isinstance(error, RunnerError):
            try:
                failure_signal = _runner_failure_signal(error)
            except Exception:
                failure_signal = None
            if failure_signal is not None:
                _invoke_failure_offer(
                    failure_signal,
                    args=args,
                    profile=args.profile,
                    suite_version="1.0",
                )
        return 1
    except SubmissionError as error:
        print(f"submission error: {error}", file=sys.stderr)
        return 2
    except PublicationError as error:
        print(f"publication error: {error}", file=sys.stderr)
        return 3
    except DiscoveryError as error:
        print(f"discovery error: {error}", file=sys.stderr)
        return 2
    except (ManifestError, SafetyError, ValueError) as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return 2
    except Exception:
        # Never echo unexpected exception text: transport libraries can embed URLs or headers.
        print("run error: unexpected internal failure", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
