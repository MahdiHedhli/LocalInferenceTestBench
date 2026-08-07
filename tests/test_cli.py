from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import traceback
from types import SimpleNamespace
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from local_inference_test_bench import cli  # noqa: E402
from local_inference_test_bench.failure_reporting import FailureSignal  # noqa: E402
from local_inference_test_bench.measurement import MeasurementError  # noqa: E402
from local_inference_test_bench.publishing import (  # noqa: E402
    PublicationIdentity,
    PublicationResult,
)
from local_inference_test_bench.runner import RunnerError  # noqa: E402
from local_inference_test_bench.submissions import SubmissionError  # noqa: E402


VALID_RUN_ID = "-".join(("11111111", "2222", "4333", "8444", "555555555555"))
MISMATCHED_RUN_ID = "-".join(("aaaaaaaa", "bbbb", "4ccc", "8ddd", "eeeeeeeeeeee"))


def run_arguments(*extra: str) -> list[str]:
    return [
        "run",
        "--manifest",
        "models.json",
        "--endpoint",
        "http://127.0.0.1:1234/v1",
        "--profile",
        "standard",
        *extra,
    ]


class StubRunner:
    def __init__(self, report: dict) -> None:
        self.report = report

    def run(self) -> dict:
        return self.report


class PostRunCliTests(unittest.TestCase):
    def test_public_run_eligibility_uses_suite_registry_membership(self) -> None:
        self.assertTrue(
            cli._eligible_public_report(
                {"validity": "valid", "profile": "standard", "suite_version": "1.0"}
            )
        )
        for report in (
            {"validity": "valid", "profile": "smoke", "suite_version": "1.0"},
            {"validity": "valid", "profile": "standard", "suite_version": "9.9"},
            {"validity": "limited", "profile": "standard", "suite_version": "1.0"},
        ):
            with self.subTest(report=report):
                self.assertFalse(cli._eligible_public_report(report))

    def test_run_parser_defaults_to_safe_interactive_ask(self) -> None:
        args = cli.build_parser().parse_args(run_arguments())

        self.assertEqual(args.submission, "ask")
        self.assertEqual(args.failure_report, "ask")
        self.assertEqual(args.timeout_seconds, 300.0)
        self.assertEqual(args.hardware, Path(".local/hardware.json"))
        self.assertEqual(
            args.measurement_evidence,
            Path(".local/measurement-evidence.json"),
        )
        self.assertIsNone(args.measurement_sampler)
        self.assertEqual(args.submission_dir, Path(".local/leaderboard-submissions"))
        self.assertFalse(args.confirm_public)

    def test_failure_report_option_exists_only_on_run(self) -> None:
        parser = cli.build_parser()
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(
                    [
                        "check",
                        "--manifest",
                        "models.json",
                        "--endpoint",
                        "http://127.0.0.1:1234/v1",
                        "--failure-report",
                        "none",
                    ]
                )
            with self.assertRaises(SystemExit):
                parser.parse_args(
                    [
                        "prepare-submission",
                        "--report",
                        "report.json",
                        "--hardware",
                        "hardware.json",
                        "--failure-report",
                        "none",
                    ]
                )
            with self.assertRaises(SystemExit):
                parser.parse_args(
                    [
                        "publish-submission",
                        "--candidate",
                        "candidate.json",
                        "--failure-report",
                        "none",
                    ]
                )

        args = parser.parse_args(run_arguments("--failure-report", "none"))
        self.assertEqual(args.failure_report, "none")

    def test_interactive_terminal_requires_both_input_and_output_tty(self) -> None:
        for stdin_tty, stdout_tty, expected in (
            (False, False, False),
            (True, False, False),
            (False, True, False),
            (True, True, True),
        ):
            with (
                self.subTest(stdin=stdin_tty, stdout=stdout_tty),
                mock.patch.object(
                    cli.sys,
                    "stdin",
                    SimpleNamespace(isatty=lambda value=stdin_tty: value),
                ),
                mock.patch.object(
                    cli.sys,
                    "stdout",
                    SimpleNamespace(isatty=lambda value=stdout_tty: value),
                ),
            ):
                self.assertEqual(cli._interactive_terminal(), expected)

    def test_interactive_terminal_preserves_stream_probe_errors(self) -> None:
        def unavailable() -> bool:
            raise OSError("private-stream-detail")

        with (
            mock.patch.object(
                cli.sys,
                "stdin",
                SimpleNamespace(isatty=unavailable),
            ),
            self.assertRaises(OSError),
        ):
            cli._interactive_terminal()
        with (
            mock.patch.object(
                cli.sys,
                "stdin",
                SimpleNamespace(isatty=lambda: True),
            ),
            mock.patch.object(
                cli.sys,
                "stdout",
                SimpleNamespace(isatty=unavailable),
            ),
            self.assertRaises(OSError),
        ):
            cli._interactive_terminal()

    def test_interactive_terminal_preserves_existing_operator_interrupts(self) -> None:
        def interrupted() -> bool:
            raise KeyboardInterrupt

        with (
            mock.patch.object(
                cli.sys,
                "stdin",
                SimpleNamespace(isatty=interrupted),
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            cli._interactive_terminal()

    def test_failure_offer_contains_stream_probe_errors(self) -> None:
        def unavailable() -> bool:
            raise OSError("private-stream-detail")

        signal = FailureSignal(phase="case_execution", failure_category="timeout")
        for stream in ("stdin", "stdout"):
            errors = io.StringIO()
            stdin = SimpleNamespace(
                isatty=unavailable if stream == "stdin" else lambda: True
            )
            stdout = SimpleNamespace(
                isatty=unavailable if stream == "stdout" else lambda: True
            )
            with (
                self.subTest(stream=stream),
                mock.patch.object(cli.sys, "stdin", stdin),
                mock.patch.object(cli.sys, "stdout", stdout),
                mock.patch("builtins.input") as prompt,
                mock.patch.object(cli.webbrowser, "open_new_tab") as opened,
                redirect_stderr(errors),
            ):
                cli._offer_failure_issue(
                    signal,
                    args=self._failure_args(),
                    profile="standard",
                    suite_version="1.0",
                )

            prompt.assert_not_called()
            opened.assert_not_called()
            self.assertIn("interactive handoff failed", errors.getvalue())
            self.assertNotIn("private-stream-detail", errors.getvalue())

    def test_publish_parser_requires_a_candidate_and_defaults_to_unconfirmed(self) -> None:
        args = cli.build_parser().parse_args(
            ["publish-submission", "--candidate", ".local/candidate.json"]
        )

        self.assertEqual(args.candidate, Path(".local/candidate.json"))
        self.assertFalse(args.confirm_public)

    def test_publish_stream_probe_error_preserves_existing_abort(self) -> None:
        def unavailable() -> bool:
            raise OSError("private-stream-detail")

        errors = io.StringIO()
        with (
            mock.patch.object(cli, "load_saved_submission", return_value={}),
            mock.patch.object(
                cli.sys,
                "stdin",
                SimpleNamespace(isatty=unavailable),
            ),
            mock.patch.object(cli, "_publish_public_submission") as publish,
            redirect_stderr(errors),
        ):
            result = cli.main(
                [
                    "publish-submission",
                    "--candidate",
                    ".local/candidate.json",
                    "--confirm-public",
                ]
            )

        self.assertEqual(result, 1)
        publish.assert_not_called()
        self.assertIn("unexpected internal failure", errors.getvalue())
        self.assertNotIn("private-stream-detail", errors.getvalue())

    def test_default_ask_is_silent_for_noninteractive_runs(self) -> None:
        report = {"validity": "valid", "profile": "standard", "suite_version": "1.0"}
        with (
            mock.patch.object(cli, "_runner_from_args", return_value=StubRunner(report)),
            mock.patch.object(cli, "write_report", return_value=Path("private.json")),
            mock.patch.object(cli, "_interactive_terminal", return_value=False),
            mock.patch.object(cli, "_prompt_submission_action") as prompt,
            mock.patch.object(cli, "_save_post_run_submissions") as post_run,
            redirect_stdout(io.StringIO()),
        ):
            result = cli.main(run_arguments())

        self.assertEqual(result, 0)
        prompt.assert_not_called()
        post_run.assert_not_called()

    def test_interactive_valid_standard_run_offers_post_action(self) -> None:
        report = {"validity": "valid", "profile": "standard", "suite_version": "1.0"}
        with (
            mock.patch.object(cli, "_runner_from_args", return_value=StubRunner(report)),
            mock.patch.object(cli, "write_report", return_value=Path("private.json")),
            mock.patch.object(cli, "_interactive_terminal", return_value=True),
            mock.patch.object(cli, "_prompt_submission_action", return_value="save"),
            mock.patch.object(cli, "_save_post_run_submissions", return_value=0) as post_run,
            redirect_stdout(io.StringIO()),
        ):
            result = cli.main(run_arguments())

        self.assertEqual(result, 0)
        self.assertEqual(post_run.call_args.kwargs["action"], "save")
        self.assertTrue(post_run.call_args.kwargs["interactive"])

    def test_invalid_run_is_saved_but_never_exported(self) -> None:
        report = {"validity": "invalid", "profile": "standard", "suite_version": "1.0"}
        with (
            mock.patch.object(cli, "_runner_from_args", return_value=StubRunner(report)),
            mock.patch.object(cli, "write_report", return_value=Path("private.json")) as writer,
            mock.patch.object(cli, "_interactive_terminal", return_value=False),
            mock.patch.object(cli, "_save_post_run_submissions") as post_run,
            redirect_stdout(io.StringIO()),
        ):
            result = cli.main(run_arguments("--submission", "save"))

        self.assertEqual(result, 1)
        writer.assert_called_once()
        post_run.assert_not_called()

    def test_eligible_case_failure_is_offered_only_after_private_report_save(self) -> None:
        events: list[str] = []
        report = {
            "validity": "invalid",
            "profile": "standard",
            "suite_version": "1.0",
            "models": [
                {
                    "cases": [
                        {
                            "termination": "invalid_json",
                            "semantic_success": False,
                            "exact_format": False,
                        }
                    ]
                }
            ],
        }

        def save_report(*_: object) -> Path:
            events.append("report")
            return Path("private.json")

        def offer(*_: object, **__: object) -> None:
            events.append("offer")

        with (
            mock.patch.object(cli, "_runner_from_args", return_value=StubRunner(report)),
            mock.patch.object(cli, "write_report", side_effect=save_report),
            mock.patch.object(cli, "_offer_failure_issue", side_effect=offer) as offered,
            mock.patch.object(cli, "_interactive_terminal", return_value=False),
            redirect_stdout(io.StringIO()),
        ):
            result = cli.main(run_arguments())

        self.assertEqual(result, 1)
        self.assertEqual(events, ["report", "offer"])
        self.assertEqual(
            offered.call_args.args[0],
            FailureSignal(
                phase="case_execution",
                failure_category="invalid_json",
            ),
        )

    def test_semantic_failure_never_offers_a_compatibility_issue(self) -> None:
        report = {
            "validity": "valid",
            "profile": "standard",
            "suite_version": "1.0",
            "models": [
                {
                    "cases": [
                        {
                            "termination": "completed",
                            "semantic_success": False,
                            "exact_format": False,
                        }
                    ]
                }
            ],
        }
        with (
            mock.patch.object(cli, "_runner_from_args", return_value=StubRunner(report)),
            mock.patch.object(cli, "write_report", return_value=Path("private.json")),
            mock.patch.object(cli, "_offer_failure_issue") as offered,
            mock.patch.object(cli, "_interactive_terminal", return_value=False),
            redirect_stdout(io.StringIO()),
        ):
            result = cli.main(run_arguments())

        self.assertEqual(result, 0)
        offered.assert_not_called()

    def test_structured_preflight_diagnostic_is_offered_without_parsing_message(self) -> None:
        class FailedRunner:
            models = ()

            def run(self) -> dict:
                raise RunnerError(
                    "runtime preflight failed (timeout)",
                    diagnostic_category="timeout",
                    diagnostic_phase="preflight",
                )

        errors = io.StringIO()
        with (
            mock.patch.object(cli, "_runner_from_args", return_value=FailedRunner()),
            mock.patch.object(cli, "_offer_failure_issue") as offered,
            redirect_stdout(io.StringIO()),
            redirect_stderr(errors),
        ):
            result = cli.main(run_arguments())

        self.assertEqual(result, 1)
        self.assertIn("runtime preflight failed", errors.getvalue())
        self.assertEqual(
            offered.call_args.args[0],
            FailureSignal(phase="preflight", failure_category="timeout"),
        )

    def test_ineligible_preflight_diagnostic_is_not_offered(self) -> None:
        class FailedRunner:
            models = ()

            def run(self) -> dict:
                raise RunnerError(
                    "runtime preflight failed (authentication)",
                    diagnostic_category="authentication",
                    diagnostic_phase="preflight",
                )

        with (
            mock.patch.object(cli, "_runner_from_args", return_value=FailedRunner()),
            mock.patch.object(cli, "_offer_failure_issue") as offered,
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            result = cli.main(run_arguments())

        self.assertEqual(result, 1)
        offered.assert_not_called()

    def test_unexpected_runner_exception_is_fixed_and_never_echoed(self) -> None:
        private_marker = "private-runtime-marker.invalid/secret-path"

        class FailedRunner:
            models = ()

            def run(self) -> dict:
                raise RuntimeError(private_marker)

        errors = io.StringIO()
        with (
            mock.patch.object(cli, "_runner_from_args", return_value=FailedRunner()),
            mock.patch.object(cli, "_offer_failure_issue") as offered,
            redirect_stdout(io.StringIO()),
            redirect_stderr(errors),
        ):
            result = cli.main(run_arguments())

        self.assertEqual(result, 1)
        self.assertIn("unexpected internal failure", errors.getvalue())
        self.assertNotIn(private_marker, errors.getvalue())
        self.assertEqual(
            offered.call_args.args[0],
            FailureSignal(
                phase="runner_internal",
                failure_category="internal_harness_error",
            ),
        )

    def _failure_args(self, **overrides: object) -> SimpleNamespace:
        values = {
            "failure_report": "ask",
            "hardware": Path(".local/hardware.json"),
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_failure_offer_declines_and_disabled_paths_never_open_browser(self) -> None:
        signal = FailureSignal(phase="case_execution", failure_category="timeout")
        decline_effects = ("", "n", "yes", "ｙ", EOFError(), KeyboardInterrupt())
        for effect in decline_effects:
            input_kwargs = (
                {"side_effect": effect}
                if isinstance(effect, BaseException)
                else {"return_value": effect}
            )
            with (
                self.subTest(effect=repr(effect)),
                mock.patch.object(cli, "_interactive_terminal", return_value=True),
                mock.patch.object(
                    cli,
                    "load_public_environment_file",
                    side_effect=SubmissionError("descriptor unavailable"),
                ),
                mock.patch("builtins.input", **input_kwargs),
                mock.patch.object(cli.webbrowser, "open_new_tab") as opened,
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                cli._offer_failure_issue(
                    signal,
                    args=self._failure_args(),
                    profile="standard",
                    suite_version="1.0",
                )

            opened.assert_not_called()

        for args, interactive in (
            (self._failure_args(failure_report="none"), True),
            (self._failure_args(), False),
        ):
            with (
                mock.patch.object(cli, "_interactive_terminal", return_value=interactive),
                mock.patch.object(cli, "load_public_environment_file") as loader,
                mock.patch.object(cli.webbrowser, "open_new_tab") as opened,
            ):
                cli._offer_failure_issue(
                    signal,
                    args=args,
                    profile="standard",
                    suite_version="1.0",
                )

            loader.assert_not_called()
            opened.assert_not_called()

    def test_exact_y_opens_one_previewed_fixed_issue_url(self) -> None:
        signal = FailureSignal(phase="case_execution", failure_category="protocol_error")
        output = io.StringIO()
        events: list[str] = []

        def consent(prompt: str) -> str:
            events.append("input")
            self.assertEqual(prompt, "Open this sanitized draft in GitHub? [y/N] ")
            prior_output = output.getvalue()
            self.assertIn("Excluded from this draft", prior_output)
            self.assertIn("transmits this draft to GitHub", prior_output)
            self.assertIn("browser or network history", prior_output)
            self.assertIn("GitHub Submit", prior_output)
            return " Y "

        def open_browser(_: str) -> bool:
            events.append("open")
            return True

        with (
            mock.patch.object(cli, "_interactive_terminal", return_value=True),
            mock.patch.object(
                cli,
                "load_public_environment_file",
                side_effect=SubmissionError("descriptor unavailable"),
            ),
            mock.patch("builtins.input", side_effect=consent),
            mock.patch.object(
                cli.webbrowser,
                "open_new_tab",
                side_effect=open_browser,
            ) as opened,
            redirect_stdout(output),
        ):
            cli._offer_failure_issue(
                signal,
                args=self._failure_args(),
                profile="standard",
                suite_version="1.0",
            )

        opened.assert_called_once()
        self.assertEqual(events, ["input", "open"])
        opened_url = opened.call_args.args[0]
        self.assertTrue(
            opened_url.startswith(
                "https://github.com/MahdiHedhli/LITB/issues/new?"
            )
        )
        disclosure = output.getvalue()
        self.assertIn('"failure_category": "protocol_error"', disclosure)
        self.assertIn("transmits this draft to GitHub", disclosure)
        self.assertIn("GitHub Submit", disclosure)
        preview_start = disclosure.index("{")
        preview_end = disclosure.index("\n\nExcluded from this draft:")
        previewed_draft = json.loads(disclosure[preview_start:preview_end])
        query = parse_qs(urlsplit(opened_url).query, strict_parsing=True)
        issue_body = query["body"][0]
        canonical = issue_body.split("```json\n", 1)[1].split("\n```", 1)[0]
        self.assertEqual(json.loads(canonical), previewed_draft)

    def test_main_preserves_failure_status_across_browser_outcomes(self) -> None:
        report = {
            "validity": "invalid",
            "profile": "standard",
            "suite_version": "1.0",
            "models": [{"cases": [{"termination": "timeout"}]}],
        }
        cases = (
            ("", None, 0),
            ("y", True, 1),
            ("y", False, 1),
            ("y", RuntimeError("private-browser-detail"), 1),
        )
        for response, browser_effect, expected_calls in cases:
            browser_kwargs = (
                {"side_effect": browser_effect}
                if isinstance(browser_effect, BaseException)
                else {"return_value": browser_effect}
            )
            output = io.StringIO()
            errors = io.StringIO()
            with (
                self.subTest(response=response, browser=repr(browser_effect)),
                mock.patch.object(cli, "_runner_from_args", return_value=StubRunner(report)),
                mock.patch.object(cli, "write_report", return_value=Path("private.json")),
                mock.patch.object(cli, "_interactive_terminal", return_value=True),
                mock.patch.object(
                    cli,
                    "load_public_environment_file",
                    side_effect=SubmissionError("private-descriptor-detail"),
                ),
                mock.patch("builtins.input", return_value=response),
                mock.patch.object(
                    cli.webbrowser,
                    "open_new_tab",
                    **browser_kwargs,
                ) as opened,
                redirect_stdout(output),
                redirect_stderr(errors),
            ):
                result = cli.main(run_arguments())

            self.assertEqual(result, 1)
            self.assertEqual(opened.call_count, expected_calls)
            combined = output.getvalue() + errors.getvalue()
            self.assertNotIn("private-browser-detail", combined)
            self.assertNotIn("private-descriptor-detail", combined)

    def test_report_write_failure_never_scans_or_offers_a_draft(self) -> None:
        report = {
            "validity": "invalid",
            "profile": "standard",
            "suite_version": "1.0",
            "models": [{"cases": [{"termination": "timeout"}]}],
        }
        with (
            mock.patch.object(cli, "_runner_from_args", return_value=StubRunner(report)),
            mock.patch.object(
                cli,
                "write_report",
                side_effect=cli.ReportError("private report write failed"),
            ),
            mock.patch.object(cli, "detect_report_failure") as detector,
            mock.patch.object(cli, "_offer_failure_issue") as offered,
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            result = cli.main(run_arguments())

        self.assertEqual(result, 1)
        detector.assert_not_called()
        offered.assert_not_called()

    def test_exceptions_outside_runner_run_are_never_classified_as_internal(self) -> None:
        private_marker = "private-construction-detail"
        with (
            mock.patch.object(
                cli,
                "_runner_from_args",
                side_effect=RuntimeError(private_marker),
            ),
            mock.patch.object(cli, "_offer_failure_issue") as offered,
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()) as errors,
        ):
            result = cli.main(run_arguments())

        self.assertEqual(result, 1)
        offered.assert_not_called()
        self.assertNotIn(private_marker, errors.getvalue())

    def test_browser_false_or_exception_is_fixed_and_never_retried(self) -> None:
        signal = FailureSignal(phase="case_execution", failure_category="network_error")
        private_marker = "browser-private-marker"
        for effect in (False, RuntimeError(private_marker)):
            errors = io.StringIO()
            with (
                self.subTest(effect=repr(effect)),
                mock.patch.object(cli, "_interactive_terminal", return_value=True),
                mock.patch.object(
                    cli,
                    "load_public_environment_file",
                    side_effect=SubmissionError("descriptor unavailable"),
                ),
                mock.patch("builtins.input", return_value="y"),
                mock.patch.object(
                    cli.webbrowser,
                    "open_new_tab",
                    side_effect=effect if isinstance(effect, Exception) else None,
                    return_value=effect if not isinstance(effect, Exception) else None,
                ) as opened,
                redirect_stdout(io.StringIO()),
                redirect_stderr(errors),
            ):
                cli._offer_failure_issue(
                    signal,
                    args=self._failure_args(),
                    profile="standard",
                    suite_version="1.0",
                )

            opened.assert_called_once()
            self.assertIn("transmission status is unknown", errors.getvalue())
            self.assertNotIn(private_marker, errors.getvalue())

    def test_failure_offer_projects_only_the_validated_public_descriptor(self) -> None:
        descriptor = {
            "schema_version": "1.0",
            "hardware": {
                "cpu": {"model": "Example CPU", "logical_cores": 16},
                "memory": {"system_gb": 32.0, "architecture": "shared"},
                "accelerators": [
                    {
                        "kind": "integrated_gpu",
                        "model": "Example Accelerator",
                        "count": 1,
                        "memory_gb": None,
                    }
                ],
                "execution_mode": "accelerator_only",
            },
            "runtime": {
                "name": "Example Runtime",
                "version": "1.2.3",
                "backend": "example-backend",
            },
        }
        output = io.StringIO()
        with (
            mock.patch.object(cli, "_interactive_terminal", return_value=True),
            mock.patch.object(
                cli,
                "load_public_environment_file",
                return_value=descriptor,
            ) as loader,
            mock.patch("builtins.input", return_value=""),
            mock.patch.object(cli.webbrowser, "open_new_tab") as opened,
            redirect_stdout(output),
        ):
            cli._offer_failure_issue(
                FailureSignal(
                    phase="case_execution",
                    failure_category="server_error",
                ),
                args=self._failure_args(),
                profile="standard",
                suite_version="1.0",
            )

        loader.assert_called_once_with(Path(".local/hardware.json"))
        opened.assert_not_called()
        preview = output.getvalue()
        self.assertIn('"hardware_class": "shared_accelerator"', preview)
        self.assertIn('"name": "Example Runtime"', preview)
        self.assertNotIn("Example CPU", preview)
        self.assertNotIn("Example Accelerator", preview)

    def test_failure_draft_error_is_best_effort_and_preserves_main_status(self) -> None:
        report = {
            "validity": "invalid",
            "profile": "standard",
            "suite_version": "1.0",
            "models": [{"cases": [{"termination": "timeout"}]}],
        }
        private_marker = "private-draft-detail"
        errors = io.StringIO()
        with (
            mock.patch.object(cli, "_runner_from_args", return_value=StubRunner(report)),
            mock.patch.object(cli, "write_report", return_value=Path("private.json")),
            mock.patch.object(cli, "_interactive_terminal", return_value=True),
            mock.patch.object(
                cli,
                "load_public_environment_file",
                side_effect=SubmissionError("descriptor unavailable"),
            ),
            mock.patch.object(
                cli,
                "build_failure_draft",
                side_effect=ValueError(private_marker),
            ),
            mock.patch("builtins.input") as prompt,
            mock.patch.object(cli.webbrowser, "open_new_tab") as opened,
            redirect_stdout(io.StringIO()),
            redirect_stderr(errors),
        ):
            result = cli.main(run_arguments())

        self.assertEqual(result, 1)
        prompt.assert_not_called()
        opened.assert_not_called()
        self.assertIn("sanitized draft validation failed", errors.getvalue())
        self.assertNotIn(private_marker, errors.getvalue())

    def test_failure_offer_contains_input_and_output_stream_errors(self) -> None:
        signal = FailureSignal(phase="case_execution", failure_category="timeout")
        for failure_stage in ("input", "print"):
            input_effect = OSError("private-input-detail") if failure_stage == "input" else ""
            print_effect = OSError("private-output-detail") if failure_stage == "print" else None
            with (
                self.subTest(stage=failure_stage),
                mock.patch.object(cli, "_interactive_terminal", return_value=True),
                mock.patch.object(
                    cli,
                    "load_public_environment_file",
                    side_effect=SubmissionError("descriptor unavailable"),
                ),
                mock.patch(
                    "builtins.input",
                    side_effect=input_effect
                    if isinstance(input_effect, BaseException)
                    else None,
                    return_value=input_effect
                    if not isinstance(input_effect, BaseException)
                    else None,
                ),
                mock.patch(
                    "builtins.print",
                    side_effect=print_effect,
                ),
                mock.patch.object(cli.webbrowser, "open_new_tab") as opened,
            ):
                cli._offer_failure_issue(
                    signal,
                    args=self._failure_args(),
                    profile="standard",
                    suite_version="1.0",
                )

            opened.assert_not_called()

    def test_main_contains_an_unexpected_offer_failure_and_suppresses_runner_cause(self) -> None:
        private_marker = "private-runner-cause"
        captured: list[RunnerError] = []

        class FailedRunner:
            models = ()

            def run(self) -> dict:
                raise RuntimeError(private_marker)

        def capture(error: RunnerError) -> FailureSignal | None:
            captured.append(error)
            return FailureSignal(
                phase="runner_internal",
                failure_category="internal_harness_error",
            )

        with (
            mock.patch.object(cli, "_runner_from_args", return_value=FailedRunner()),
            mock.patch.object(cli, "_runner_failure_signal", side_effect=capture),
            mock.patch.object(
                cli,
                "_offer_failure_issue",
                side_effect=OSError("private-offer-detail"),
            ),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()) as errors,
        ):
            result = cli.main(run_arguments())

        self.assertEqual(result, 1)
        self.assertEqual(len(captured), 1)
        formatted = "".join(
            traceback.format_exception(captured[0])
        )
        self.assertNotIn(private_marker, formatted)
        self.assertNotIn("private-offer-detail", errors.getvalue())

    def test_limited_explicit_export_is_a_submission_error_after_report_save(self) -> None:
        report = {"validity": "limited", "profile": "standard", "suite_version": "1.0"}
        errors = io.StringIO()
        with (
            mock.patch.object(cli, "_runner_from_args", return_value=StubRunner(report)),
            mock.patch.object(cli, "write_report", return_value=Path("private.json")) as writer,
            mock.patch.object(cli, "_interactive_terminal", return_value=False),
            redirect_stdout(io.StringIO()),
            redirect_stderr(errors),
        ):
            result = cli.main(run_arguments("--submission", "save"))

        self.assertEqual(result, 2)
        writer.assert_called_once()
        self.assertIn("only a fully valid registered public-suite run", errors.getvalue())

    def test_sampler_binds_pre_and_post_to_the_run_before_export(self) -> None:
        run_id = VALID_RUN_ID
        created_at = "2026-08-06T12:00:00Z"
        events: list[tuple[str, str]] = []
        report = {
            "run_id": run_id,
            "validity": "valid",
            "profile": "standard",
            "suite_version": "1.0",
            "models": [{"model_id": "public-model"}],
        }

        class BoundRunner:
            models = (SimpleNamespace(id="public-model"),)

            def run(self, *, run_identity: tuple[str, str]) -> dict:
                events.append(("run", run_identity[0]))
                return report

        class Sampler:
            def sample(self, *, phase: str, source_run_id: str, model_ids: tuple[str, ...]):
                events.append((phase, source_run_id))
                return {"outcome": "within_thresholds", "categories": []}

        def allocate_identity() -> tuple[str, str]:
            events.append(("identity", run_id))
            return run_id, created_at

        def build_runner(_: object) -> BoundRunner:
            events.append(("runner", run_id))
            return BoundRunner()

        evidence = {"source_run_id": run_id, "models": []}
        with (
            mock.patch.object(cli, "_runner_from_args", side_effect=build_runner),
            mock.patch.object(cli, "LocalMeasurementSampler", return_value=Sampler()),
            mock.patch.object(cli, "new_run_identity", side_effect=allocate_identity),
            mock.patch.object(cli, "write_report", return_value=Path("private.json")),
            mock.patch.object(cli, "_interactive_terminal", return_value=False),
            mock.patch.object(
                cli, "build_measurement_evidence", return_value=evidence
            ) as builder,
            mock.patch.object(cli, "write_measurement_evidence") as evidence_writer,
            mock.patch.object(
                cli, "_save_post_run_submissions", return_value=0
            ) as post_run,
            redirect_stdout(io.StringIO()),
        ):
            result = cli.main(
                run_arguments(
                    "--submission",
                    "save",
                    "--measurement-sampler",
                    ".local/sampler",
                )
            )

        self.assertEqual(result, 0)
        self.assertEqual(
            events,
            [
                ("identity", run_id),
                ("runner", run_id),
                ("pre", run_id),
                ("run", run_id),
                ("post", run_id),
            ],
        )
        self.assertEqual(builder.call_args.kwargs["source_run_id"], run_id)
        self.assertEqual(builder.call_args.kwargs["model_ids"], ("public-model",))
        evidence_writer.assert_called_once_with(
            evidence, Path(".local/measurement-evidence.json")
        )
        self.assertIs(post_run.call_args.kwargs["measurement_evidence"], evidence)

    def test_failed_run_skips_the_unused_post_sample(self) -> None:
        run_id = VALID_RUN_ID
        events: list[str] = []

        class FailedRunner:
            models = (SimpleNamespace(id="public-model"),)

            def run(self, *, run_identity: tuple[str, str]) -> dict:
                events.append("run")
                raise RunnerError("preflight failed")

        class Sampler:
            def sample(self, *, phase: str, **_: object) -> dict:
                events.append(phase)
                return {"outcome": "within_thresholds", "categories": []}

        errors = io.StringIO()
        with (
            mock.patch.object(cli, "_runner_from_args", return_value=FailedRunner()),
            mock.patch.object(cli, "LocalMeasurementSampler", return_value=Sampler()),
            mock.patch.object(
                cli,
                "new_run_identity",
                return_value=(run_id, "2026-08-06T12:00:00Z"),
            ),
            mock.patch.object(cli, "write_report") as report_writer,
            redirect_stdout(io.StringIO()),
            redirect_stderr(errors),
        ):
            result = cli.main(
                run_arguments(
                    "--submission",
                    "save",
                    "--measurement-sampler",
                    ".local/sampler",
                )
            )

        self.assertEqual(result, 1)
        self.assertEqual(events, ["pre", "run"])
        report_writer.assert_not_called()
        self.assertIn("run error: preflight failed", errors.getvalue())

    def test_sampler_failure_preserves_private_report_and_blocks_export(self) -> None:
        run_id = VALID_RUN_ID
        report = {
            "run_id": run_id,
            "validity": "valid",
            "profile": "standard",
            "suite_version": "1.0",
            "models": [{"model_id": "public-model"}],
        }

        class BoundRunner:
            models = (SimpleNamespace(id="public-model"),)

            def run(self, *, run_identity: tuple[str, str]) -> dict:
                return report

        class Sampler:
            def sample(self, **_: object) -> dict:
                raise MeasurementError("categorical sampler failed")

        errors = io.StringIO()
        with (
            mock.patch.object(cli, "_runner_from_args", return_value=BoundRunner()),
            mock.patch.object(cli, "LocalMeasurementSampler", return_value=Sampler()),
            mock.patch.object(
                cli,
                "new_run_identity",
                return_value=(run_id, "2026-08-06T12:00:00Z"),
            ),
            mock.patch.object(
                cli, "write_report", return_value=Path("private.json")
            ) as writer,
            mock.patch.object(cli, "_interactive_terminal", return_value=False),
            mock.patch.object(cli, "_save_post_run_submissions") as post_run,
            redirect_stdout(io.StringIO()),
            redirect_stderr(errors),
        ):
            result = cli.main(
                run_arguments(
                    "--submission",
                    "save",
                    "--measurement-sampler",
                    ".local/sampler",
                )
            )

        self.assertEqual(result, 2)
        writer.assert_called_once_with(report, Path("artifacts"))
        post_run.assert_not_called()
        self.assertIn("private report retained", errors.getvalue())

    def test_sampler_binding_mismatch_preserves_report_and_blocks_export(self) -> None:
        sampled_run_id = VALID_RUN_ID
        report = {
            "run_id": MISMATCHED_RUN_ID,
            "validity": "valid",
            "profile": "standard",
            "suite_version": "1.0",
            "models": [{"model_id": "public-model"}],
        }

        class MismatchedRunner:
            models = (SimpleNamespace(id="public-model"),)

            def run(self, *, run_identity: tuple[str, str]) -> dict:
                return report

        class Sampler:
            def sample(self, **_: object) -> dict:
                return {"outcome": "within_thresholds", "categories": []}

        errors = io.StringIO()
        with (
            mock.patch.object(cli, "_runner_from_args", return_value=MismatchedRunner()),
            mock.patch.object(cli, "LocalMeasurementSampler", return_value=Sampler()),
            mock.patch.object(
                cli,
                "new_run_identity",
                return_value=(sampled_run_id, "2026-08-06T12:00:00Z"),
            ),
            mock.patch.object(
                cli, "write_report", return_value=Path("private.json")
            ) as writer,
            mock.patch.object(cli, "_interactive_terminal", return_value=False),
            mock.patch.object(cli, "build_measurement_evidence") as builder,
            mock.patch.object(cli, "_save_post_run_submissions") as post_run,
            redirect_stdout(io.StringIO()),
            redirect_stderr(errors),
        ):
            result = cli.main(
                run_arguments(
                    "--submission",
                    "save",
                    "--measurement-sampler",
                    ".local/sampler",
                )
            )

        self.assertEqual(result, 2)
        writer.assert_called_once_with(report, Path("artifacts"))
        builder.assert_not_called()
        post_run.assert_not_called()
        self.assertIn("binding did not match", errors.getvalue())
        self.assertIn("private report retained", errors.getvalue())

    def test_post_build_and_write_failures_preserve_report_and_block_export(self) -> None:
        run_id = VALID_RUN_ID
        report = {
            "run_id": run_id,
            "validity": "valid",
            "profile": "standard",
            "suite_version": "1.0",
            "models": [{"model_id": "public-model"}],
        }

        class BoundRunner:
            models = (SimpleNamespace(id="public-model"),)

            def run(self, *, run_identity: tuple[str, str]) -> dict:
                return report

        for failure_stage in ("post", "build", "write"):
            phases: list[str] = []

            class Sampler:
                def sample(self, *, phase: str, **_: object) -> dict:
                    phases.append(phase)
                    if failure_stage == "post" and phase == "post":
                        raise MeasurementError("post sample failed; private report retained")
                    return {"outcome": "within_thresholds", "categories": []}

            evidence = {"source_run_id": run_id, "models": []}
            build_effect = (
                MeasurementError("evidence build failed; private report retained")
                if failure_stage == "build"
                else None
            )
            write_effect = (
                MeasurementError("evidence write failed; private report retained")
                if failure_stage == "write"
                else None
            )
            errors = io.StringIO()
            with (
                self.subTest(failure_stage=failure_stage),
                mock.patch.object(cli, "_runner_from_args", return_value=BoundRunner()),
                mock.patch.object(cli, "LocalMeasurementSampler", return_value=Sampler()),
                mock.patch.object(
                    cli,
                    "new_run_identity",
                    return_value=(run_id, "2026-08-06T12:00:00Z"),
                ),
                mock.patch.object(
                    cli, "write_report", return_value=Path("private.json")
                ) as report_writer,
                mock.patch.object(cli, "_interactive_terminal", return_value=False),
                mock.patch.object(
                    cli,
                    "build_measurement_evidence",
                    return_value=evidence,
                    side_effect=build_effect,
                ) as builder,
                mock.patch.object(
                    cli,
                    "write_measurement_evidence",
                    side_effect=write_effect,
                ) as evidence_writer,
                mock.patch.object(cli, "_save_post_run_submissions") as post_run,
                redirect_stdout(io.StringIO()),
                redirect_stderr(errors),
            ):
                result = cli.main(
                    run_arguments(
                        "--submission",
                        "save",
                        "--measurement-sampler",
                        ".local/sampler",
                    )
                )

            self.assertEqual(result, 2)
            report_writer.assert_called_once_with(report, Path("artifacts"))
            post_run.assert_not_called()
            self.assertIn("private report retained", errors.getvalue())
            if failure_stage == "post":
                self.assertEqual(phases, ["pre", "post"])
                builder.assert_not_called()
                evidence_writer.assert_not_called()
            elif failure_stage == "build":
                builder.assert_called_once()
                evidence_writer.assert_not_called()
            else:
                builder.assert_called_once()
                evidence_writer.assert_called_once()

    def test_noninteractive_submission_without_sampler_preserves_report(self) -> None:
        report = {
            "run_id": VALID_RUN_ID,
            "validity": "valid",
            "profile": "standard",
            "suite_version": "1.0",
            "models": [{"model_id": "public-model"}],
        }
        errors = io.StringIO()
        with (
            mock.patch.object(cli, "_runner_from_args", return_value=StubRunner(report)),
            mock.patch.object(
                cli, "write_report", return_value=Path("private.json")
            ) as writer,
            mock.patch.object(cli, "_interactive_terminal", return_value=False),
            mock.patch.object(cli, "_save_post_run_submissions") as post_run,
            redirect_stdout(io.StringIO()),
            redirect_stderr(errors),
        ):
            result = cli.main(run_arguments("--submission", "save"))

        self.assertEqual(result, 2)
        writer.assert_called_once_with(report, Path("artifacts"))
        post_run.assert_not_called()
        self.assertIn("requires --measurement-sampler", errors.getvalue())
        self.assertIn("private report retained", errors.getvalue())

    def test_unsafe_sampler_path_still_preserves_private_report(self) -> None:
        run_id = VALID_RUN_ID
        report = {
            "run_id": run_id,
            "validity": "valid",
            "profile": "standard",
            "suite_version": "1.0",
            "models": [{"model_id": "public-model"}],
        }

        class BoundRunner:
            models = (SimpleNamespace(id="public-model"),)

            def run(self, *, run_identity: tuple[str, str]) -> dict:
                return report

        with (
            mock.patch.object(cli, "_runner_from_args", return_value=BoundRunner()),
            mock.patch.object(
                cli,
                "LocalMeasurementSampler",
                side_effect=MeasurementError("unsafe adapter"),
            ),
            mock.patch.object(
                cli,
                "new_run_identity",
                return_value=(run_id, "2026-08-06T12:00:00Z"),
            ),
            mock.patch.object(
                cli, "write_report", return_value=Path("private.json")
            ) as writer,
            mock.patch.object(cli, "_interactive_terminal", return_value=False),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            result = cli.main(
                run_arguments(
                    "--submission",
                    "save",
                    "--measurement-sampler",
                    ".local/unsafe-sampler",
                )
            )

        self.assertEqual(result, 2)
        writer.assert_called_once_with(report, Path("artifacts"))

    def test_prompt_defaults_to_private_on_enter_or_eof(self) -> None:
        with mock.patch("builtins.input", return_value=""):
            self.assertEqual(cli._prompt_submission_action(), "none")
        with mock.patch("builtins.input", side_effect=EOFError):
            self.assertEqual(cli._prompt_submission_action(), "none")

    def _post_args(self, **overrides: object) -> SimpleNamespace:
        values = {
            "hardware": Path(".local/hardware.json"),
            "measurement_evidence": Path(".local/measurement-evidence.json"),
            "submission_model": None,
            "submission_dir": Path(".local/leaderboard-submissions"),
            "confirm_public": False,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_save_action_has_no_github_dependency(self) -> None:
        candidate = {"submission_id": "a" * 64}
        with (
            mock.patch.object(cli, "load_public_environment_file", return_value={}),
            mock.patch.object(cli, "load_measurement_evidence_file", return_value={}),
            mock.patch.object(cli, "prepare_submissions", return_value=(candidate,)),
            mock.patch.object(
                cli, "ensure_submissions", return_value=(Path("candidate.json"),)
            ),
            mock.patch.object(cli, "publication_preflight") as preflight,
            redirect_stdout(io.StringIO()),
        ):
            result = cli._save_post_run_submissions(
                {"private": "never-published"},
                self._post_args(),
                action="save",
                interactive=False,
            )

        self.assertEqual(result, 0)
        preflight.assert_not_called()

    def test_publication_decline_saves_but_does_not_mutate_github(self) -> None:
        candidate = {"submission_id": "a" * 64, "model": {}}
        identity = PublicationIdentity("example", "owner", "repo", "main", False)
        output = io.StringIO()
        with (
            mock.patch.object(
                cli, "_prompt_hardware_path", return_value=Path("hardware.json")
            ),
            mock.patch.object(cli, "load_public_environment_file", return_value={}),
            mock.patch.object(cli, "load_measurement_evidence_file", return_value={}),
            mock.patch.object(cli, "prepare_submissions", return_value=(candidate,)),
            mock.patch.object(
                cli, "ensure_submissions", return_value=(Path("candidate.json"),)
            ) as saver,
            mock.patch.object(
                cli, "publication_preflight", return_value=(identity, b"local-id\n")
            ),
            mock.patch.object(cli, "publish_submission") as publisher,
            mock.patch("builtins.input", return_value="keep private"),
            redirect_stdout(output),
        ):
            result = cli._save_post_run_submissions(
                {"private": "must-not-appear"},
                self._post_args(),
                action="pr",
                interactive=True,
            )

        self.assertEqual(result, 0)
        saver.assert_called_once()
        publisher.assert_not_called()
        self.assertIn("publication cancelled", output.getvalue())
        self.assertNotIn("must-not-appear", output.getvalue())

    def test_confirmed_publication_uses_only_selected_candidate(self) -> None:
        candidate = {"submission_id": "a" * 64, "model": {}}
        identity = PublicationIdentity("example", "owner", "repo", "main", True)
        opened = PublicationResult("https://github.com/owner/repo/pull/1", "opened", "branch")
        with (
            mock.patch.object(cli, "load_public_environment_file", return_value={}),
            mock.patch.object(cli, "load_measurement_evidence_file", return_value={}),
            mock.patch.object(cli, "prepare_submissions", return_value=(candidate,)),
            mock.patch.object(
                cli, "ensure_submissions", return_value=(Path("candidate.json"),)
            ),
            mock.patch.object(
                cli, "publication_preflight", return_value=(identity, b"local-id\n")
            ),
            mock.patch.object(cli, "publish_submission", return_value=opened) as publisher,
            redirect_stdout(io.StringIO()),
        ):
            result = cli._save_post_run_submissions(
                {"private": "must-not-be-passed"},
                self._post_args(confirm_public=True),
                action="pr",
                interactive=False,
            )

        self.assertEqual(result, 0)
        publisher.assert_called_once_with(candidate, identity, b"local-id\n")

    def test_interactive_confirmation_flag_still_requires_literal_publish(self) -> None:
        candidate = {"submission_id": "a" * 64, "model": {}}
        identity = PublicationIdentity("example", "owner", "repo", "main", True)
        with (
            mock.patch.object(
                cli, "_prompt_hardware_path", return_value=Path("hardware.json")
            ),
            mock.patch.object(cli, "load_public_environment_file", return_value={}),
            mock.patch.object(cli, "load_measurement_evidence_file", return_value={}),
            mock.patch.object(cli, "prepare_submissions", return_value=(candidate,)),
            mock.patch.object(
                cli, "ensure_submissions", return_value=(Path("candidate.json"),)
            ),
            mock.patch.object(
                cli, "publication_preflight", return_value=(identity, b"local-id\n")
            ),
            mock.patch.object(cli, "publish_submission") as publisher,
            mock.patch("builtins.input", return_value="not publish") as prompt,
            redirect_stdout(io.StringIO()),
        ):
            result = cli._save_post_run_submissions(
                {},
                self._post_args(confirm_public=True),
                action="pr",
                interactive=True,
            )

        self.assertEqual(result, 0)
        prompt.assert_called_once_with("Type PUBLISH to continue: ")
        publisher.assert_not_called()

    def test_noninteractive_multi_model_pr_requires_selection_after_safe_save(self) -> None:
        candidates = (
            {"submission_id": "a" * 64, "model": {}},
            {"submission_id": "b" * 64, "model": {}},
        )
        with (
            mock.patch.object(cli, "load_public_environment_file", return_value={}),
            mock.patch.object(cli, "load_measurement_evidence_file", return_value={}),
            mock.patch.object(cli, "prepare_submissions", return_value=candidates),
            mock.patch.object(
                cli,
                "ensure_submissions",
                return_value=(Path("first.json"), Path("second.json")),
            ) as saver,
            mock.patch.object(cli, "publication_preflight") as preflight,
            self.assertRaisesRegex(SubmissionError, "select one result"),
            redirect_stdout(io.StringIO()),
        ):
            cli._save_post_run_submissions(
                {},
                self._post_args(confirm_public=True),
                action="pr",
                interactive=False,
            )

        saver.assert_called_once()
        preflight.assert_not_called()

    def test_saved_candidate_noninteractive_requires_confirmation_before_github(self) -> None:
        candidate = {"submission_id": "a" * 64, "model": {}}
        errors = io.StringIO()
        with (
            mock.patch.object(cli, "load_saved_submission", return_value=candidate) as loader,
            mock.patch.object(cli, "_interactive_terminal", return_value=False),
            mock.patch.object(cli, "publication_preflight") as preflight,
            mock.patch.object(cli, "publish_submission") as publisher,
            redirect_stdout(io.StringIO()),
            redirect_stderr(errors),
        ):
            result = cli.main(
                ["publish-submission", "--candidate", ".local/candidate.json"]
            )

        self.assertEqual(result, 3)
        loader.assert_called_once_with(Path(".local/candidate.json"))
        preflight.assert_not_called()
        publisher.assert_not_called()
        self.assertIn("--confirm-public", errors.getvalue())

    def test_saved_candidate_interactive_decline_never_mutates_github(self) -> None:
        candidate = {"submission_id": "a" * 64, "model": {}}
        identity = PublicationIdentity("example", "owner", "repo", "main", False)
        output = io.StringIO()
        with (
            mock.patch.object(cli, "load_saved_submission", return_value=candidate),
            mock.patch.object(cli, "_interactive_terminal", return_value=True),
            mock.patch.object(
                cli, "publication_preflight", return_value=(identity, b"local-id\n")
            ),
            mock.patch.object(cli, "publish_submission") as publisher,
            mock.patch("builtins.input", return_value="no") as prompt,
            redirect_stdout(output),
        ):
            result = cli.main(
                [
                    "publish-submission",
                    "--candidate",
                    ".local/candidate.json",
                    "--confirm-public",
                ]
            )

        self.assertEqual(result, 0)
        prompt.assert_called_once_with("Type PUBLISH to continue: ")
        publisher.assert_not_called()
        disclosure = output.getvalue()
        self.assertIn('"submission_id":', disclosure)
        self.assertIn("account: example", disclosure)
        self.assertIn("destination: example/repo (public fork)", disclosure)
        self.assertIn("pull request to owner/repo:main", disclosure)
        self.assertIn("visible: GitHub account and timestamp", disclosure)
        self.assertIn("action: create a submission branch", disclosure)
        self.assertIn("publication cancelled", disclosure)

    def test_saved_candidate_confirmed_publish_uses_no_runner(self) -> None:
        candidate = {"submission_id": "a" * 64, "model": {}}
        identity = PublicationIdentity("example", "owner", "repo", "main", True)
        opened = PublicationResult("https://github.com/owner/repo/pull/1", "opened", "branch")
        with (
            mock.patch.object(cli, "load_saved_submission", return_value=candidate),
            mock.patch.object(cli, "_interactive_terminal", return_value=False),
            mock.patch.object(
                cli, "publication_preflight", return_value=(identity, b"local-id\n")
            ),
            mock.patch.object(cli, "publish_submission", return_value=opened) as publisher,
            mock.patch.object(cli, "_runner_from_args") as runner,
            redirect_stdout(io.StringIO()),
        ):
            result = cli.main(
                [
                    "publish-submission",
                    "--candidate",
                    ".local/candidate.json",
                    "--confirm-public",
                ]
            )

        self.assertEqual(result, 0)
        runner.assert_not_called()
        publisher.assert_called_once_with(candidate, identity, b"local-id\n")


if __name__ == "__main__":
    unittest.main()
