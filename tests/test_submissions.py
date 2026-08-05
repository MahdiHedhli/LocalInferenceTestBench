from __future__ import annotations

import copy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from local_inference_test_bench.submissions import (  # noqa: E402
    SubmissionError,
    build_leaderboard,
    ensure_submission,
    load_json_object,
    load_public_environment_file,
    load_saved_submission,
    prepare_submission,
    prepare_submissions,
    render_submission_bytes,
    validate_submission,
    write_leaderboard,
    write_submission,
)
from local_inference_test_bench import submissions as submissions_module  # noqa: E402
from local_inference_test_bench import cli as cli_module  # noqa: E402


CASE_IDS = (
    "structured-json",
    "python-ast",
    "defensive-triage",
    "read-only-tool",
    "unapproved-change-boundary",
)


def public_environment(*, cpu_model: str = "Example CPU") -> dict:
    return {
        "schema_version": "1.0",
        "hardware": {
            "cpu": {"model": cpu_model, "logical_cores": 16},
            "memory": {"system_gb": 32.0, "architecture": "discrete"},
            "accelerators": [
                {
                    "kind": "discrete_gpu",
                    "model": "Example Accelerator",
                    "count": 1,
                    "memory_gb": 16.0,
                }
            ],
            "execution_mode": "accelerator_only",
        },
        "runtime": {
            "name": "Example Runtime",
            "version": "1.2.3",
            "backend": "generic-backend",
        },
    }


def runtime_configuration() -> dict:
    return {
        "context_window_tokens": 4096,
        "concurrent_requests": 1,
        "speculative_decoding": "disabled",
        "offload_mode": "maximum",
    }


def valid_report(
    *,
    display_name: str = "Example Model",
    source: str = "publisher/example-model",
    outcomes: tuple[str, ...] = ("pass", "pass", "pass", "pass", "pass"),
    latency_ms: float = 10.0,
    profile: str = "standard",
) -> dict:
    flags = {
        "pass": (True, True),
        "semantic_only": (True, False),
        "format_only": (False, True),
        "fail": (False, False),
        "not_scored": (False, False),
    }
    routes = (
        "direct_response",
        "direct_response",
        "direct_response",
        "read_only_tool",
        "safe_refusal",
    )
    terminations = ("completed", "completed", "completed", "tool_call", "completed")
    selected_ids = CASE_IDS if profile == "standard" else CASE_IDS[:3]
    selected_outcomes = outcomes[: len(selected_ids)]
    cases = []
    for case_id, outcome, route, termination in zip(
        selected_ids,
        selected_outcomes,
        routes[: len(selected_ids)],
        terminations[: len(selected_ids)],
        strict=True,
    ):
        semantic, exact = flags[outcome]
        completion_tokens = 10
        rate = round(completion_tokens / (latency_ms / 1000.0), 3)
        cases.append(
            {
                "case_id": case_id,
                "semantic_success": semantic,
                "exact_format": exact,
                "outcome": outcome,
                "route": route,
                "reasoning_present": False,
                "latency_ms": latency_ms,
                "completion_tokens_per_second": rate,
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": completion_tokens,
                    "total_tokens": 30,
                },
                "termination": termination,
            }
        )
    case_count = len(cases)
    latency_total = round(latency_ms * case_count, 3)
    completion_total = 10 * case_count
    summary = {
        "case_count": case_count,
        "semantic_pass_count": sum(case["semantic_success"] for case in cases),
        "exact_format_pass_count": sum(case["exact_format"] for case in cases),
        "scored_case_count": sum(case["outcome"] != "not_scored" for case in cases),
        "latency_ms_total": latency_total,
        "latency_ms_mean": round(latency_total / case_count, 3),
        "completion_tokens_per_second_weighted": round(
            completion_total / (latency_total / 1000.0), 3
        ),
        "usage_coverage_cases": case_count,
        "prompt_tokens_total": 20 * case_count,
        "completion_tokens_total": completion_total,
        "tokens_total": 30 * case_count,
    }
    return {
        "schema_version": "1.0",
        "suite_version": "1.0",
        "run_id": "private-run-id-that-is-removed",
        "created_at": "2026-01-02T03:04:05Z",
        "profile": profile,
        "public_manifest_sha256": "a" * 64,
        "validity": "valid",
        "deployment_authorization": False,
        "models": [
            {
                "model_id": "private-model-selector-that-is-removed",
                "provenance": {
                    "display_name": display_name,
                    "source": source,
                    "revision": "public-revision",
                    "precision": "runtime-declared",
                    "declared_context_tokens": 4096,
                },
                "settings": {
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "max_output_tokens": 128,
                    "seed": 0,
                },
                "preflight": "verified",
                "runtime_identity_match": True,
                "validity": "valid",
                "summary": summary,
                "cases": cases,
            }
        ],
    }


class SubmissionTests(unittest.TestCase):
    def test_prepare_cli_defaults_to_an_ignored_local_output_directory(self) -> None:
        parser = cli_module.build_parser()
        args = parser.parse_args(
            [
                "prepare-submission",
                "--report",
                "run.json",
                "--hardware",
                ".local/hardware.json",
            ]
        )

        self.assertEqual(args.output_dir, Path(".local/leaderboard-submissions"))
        command_action = next(action for action in parser._actions if action.dest == "command")
        self.assertIn(
            ".local/leaderboard-submissions",
            command_action.choices["prepare-submission"].format_help(),
        )

    def test_prepare_cli_uses_grammatical_file_counts(self) -> None:
        arguments = [
            "prepare-submission",
            "--report",
            "run.json",
            "--hardware",
            ".local/hardware.json",
        ]
        for count, expected in ((1, "submission ready: 1 file\n"), (2, "submission ready: 2 files\n")):
            with self.subTest(count=count):
                output = io.StringIO()
                with (
                    mock.patch.object(
                        cli_module,
                        "prepare_submission_file",
                        return_value=tuple({} for _ in range(count)),
                    ),
                    mock.patch.object(
                        cli_module,
                        "write_submissions",
                        return_value=tuple(Path(f"{index}.json") for index in range(count)),
                    ),
                    redirect_stdout(output),
                ):
                    result = cli_module.main(arguments)

                self.assertEqual(result, 0)
                self.assertEqual(output.getvalue(), expected)

    def test_prepare_is_deterministic_and_removes_run_and_machine_linkage_fields(self) -> None:
        first = prepare_submission(valid_report(latency_ms=10.04), public_environment())
        second = prepare_submission(valid_report(latency_ms=10.04), public_environment())

        validate_submission(first)
        self.assertEqual(first, second)
        self.assertRegex(first["submission_id"], r"^[0-9a-f]{64}$")
        self.assertEqual(first["profile"], "standard")
        self.assertEqual(first["metrics"]["latency_ms_mean"], 10.0)
        self.assertEqual(
            first["metrics"]["completion_tokens_per_second"],
            996.0,
        )
        serialized = json.dumps(first, sort_keys=True)
        for forbidden in (
            "private-run-id-that-is-removed",
            "2026-01-02T03:04:05Z",
            "public_manifest_sha256",
            "private-model-selector-that-is-removed",
            "model_id",
            "preflight",
            "runtime_identity_match",
            "contributor",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(first["hardware"], public_environment()["hardware"])
        self.assertEqual(first["runtime"], public_environment()["runtime"])

    def test_prepare_keeps_only_minimized_case_categories(self) -> None:
        submission = prepare_submission(valid_report(), public_environment())
        case = submission["cases"][0]

        self.assertEqual(
            set(case),
            {"case_id", "outcome", "route", "termination"},
        )
        serialized = json.dumps(submission)
        for forbidden in (
            "semantic_success",
            "reasoning_present",
            "latency_ms\"",
            "prompt_tokens",
            "completion_tokens_total",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_only_standard_fully_valid_reports_are_exportable(self) -> None:
        smoke = valid_report(profile="smoke")
        limited = valid_report()
        limited["validity"] = "limited"
        limited["models"][0]["validity"] = "limited"
        limited["models"][0]["preflight"] = "metadata_unavailable"
        limited["models"][0]["runtime_identity_match"] = False

        for report in (smoke, limited):
            with self.subTest(profile=report["profile"], validity=report["validity"]):
                with self.assertRaises(SubmissionError):
                    prepare_submission(report, public_environment())

    def test_multi_model_reports_are_split_into_unlinked_records(self) -> None:
        report = valid_report()
        second = copy.deepcopy(report["models"][0])
        second["model_id"] = "second-private-selector"
        second["provenance"]["display_name"] = "Second Model"
        second["provenance"]["source"] = "publisher/second-model"
        second["provenance"]["revision"] = "second-public-revision"
        report["models"].append(second)

        submissions = prepare_submissions(report, public_environment())
        selected = prepare_submissions(
            report,
            public_environment(),
            ("second-private-selector",),
        )

        self.assertEqual(len(submissions), 2)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["model"]["display_name"], "Second Model")
        self.assertNotIn("results", submissions[0])
        self.assertNotIn("Example Model", json.dumps(submissions[1]))
        with self.assertRaises(SubmissionError):
            prepare_submission(report, public_environment())

    def test_closed_shape_content_hash_and_counts_are_enforced(self) -> None:
        original = prepare_submission(valid_report(), public_environment())
        unknown = copy.deepcopy(original)
        unknown["contributor"] = "anonymous"
        changed = copy.deepcopy(original)
        changed["model"]["display_name"] = "Changed Model"
        wrong_counts = copy.deepcopy(original)
        wrong_counts["metrics"]["semantic_pass_count"] = 4

        for submission in (unknown, changed, wrong_counts):
            with self.assertRaises(SubmissionError):
                validate_submission(submission)

    def test_content_id_normalizes_equivalent_json_number_spellings(self) -> None:
        expected = prepare_submission(valid_report(), public_environment())
        report = valid_report()
        report["models"][0]["settings"]["temperature"] = 0
        report["models"][0]["settings"]["top_p"] = 1
        descriptor = public_environment()
        descriptor["hardware"]["memory"]["system_gb"] = 32

        normalized = prepare_submission(report, descriptor)

        self.assertEqual(normalized, expected)

    def test_incomplete_standard_run_is_not_eligible(self) -> None:
        incomplete = prepare_submission(valid_report(), public_environment())
        incomplete["cases"][-1]["outcome"] = "not_scored"
        incomplete["cases"][-1]["route"] = "unrecognized"
        incomplete["cases"][-1]["termination"] = "context_window"
        incomplete["metrics"]["semantic_pass_count"] = 4
        incomplete["metrics"]["exact_format_pass_count"] = 4
        incomplete["metrics"]["scored_case_count"] = 4

        with self.assertRaisesRegex(SubmissionError, "every standard case"):
            validate_submission(incomplete)

    def test_local_identifiers_and_unrounded_observations_are_rejected(self) -> None:
        private = valid_report(source="node." + "internal")
        with self.assertRaises(SubmissionError):
            prepare_submission(private, public_environment())

        submission = prepare_submission(valid_report(), public_environment())
        submission["metrics"]["latency_ms_mean"] = 10.04
        with self.assertRaisesRegex(SubmissionError, "one decimal"):
            validate_submission(submission)

    def test_public_model_text_rejects_display_controls(self) -> None:
        for codepoint in (0x7F, 0x85, 0x200E, 0x202E, 0x2066, 0xD800):
            report = valid_report(display_name="Model" + chr(codepoint) + "Name")
            with self.subTest(codepoint=codepoint):
                with self.assertRaises(SubmissionError):
                    prepare_submission(report, public_environment())

    def test_public_text_rejects_secret_scanner_suppression_marker(self) -> None:
        marker = "git" + "leaks:allow"
        report = valid_report(source="example/model " + marker)

        with self.assertRaisesRegex(SubmissionError, "scanner suppression"):
            prepare_submission(report, public_environment())

    def test_public_hardware_is_closed_safe_and_affects_content_id(self) -> None:
        first = prepare_submission(valid_report(), public_environment(cpu_model="Processor One"))
        second = prepare_submission(valid_report(), public_environment(cpu_model="Processor Two"))
        unsafe = public_environment(cpu_model="worker." + "internal")
        unknown = public_environment()
        unknown["hardware"]["serial"] = "not-accepted"

        self.assertNotEqual(first["submission_id"], second["submission_id"])
        for descriptor in (unsafe, unknown):
            with self.assertRaises(SubmissionError):
                prepare_submission(valid_report(), descriptor)

    def test_runtime_configuration_is_optional_closed_and_carried_to_dataset(self) -> None:
        legacy = prepare_submission(valid_report(), public_environment())
        descriptor = public_environment()
        descriptor["runtime_configuration"] = runtime_configuration()

        configured = prepare_submission(valid_report(), descriptor)

        self.assertNotIn("runtime_configuration", legacy)
        self.assertEqual(
            configured["runtime_configuration"],
            descriptor["runtime_configuration"],
        )
        self.assertNotEqual(configured["submission_id"], legacy["submission_id"])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / f"{configured['submission_id']}.json").write_text(
                json.dumps(configured),
                encoding="utf-8",
            )
            leaderboard = build_leaderboard(directory)
        self.assertEqual(
            leaderboard["entries"][0]["runtime_configuration"],
            descriptor["runtime_configuration"],
        )

    def test_runtime_configuration_rejects_unknown_fields_ranges_and_categories(self) -> None:
        invalid_configurations = []
        extra = runtime_configuration()
        extra["runtime_flags"] = "not accepted"
        invalid_configurations.append(extra)
        missing = runtime_configuration()
        missing.pop("concurrent_requests")
        invalid_configurations.append(missing)
        for field, value in (
            ("context_window_tokens", 0),
            ("context_window_tokens", True),
            ("concurrent_requests", 0),
            ("concurrent_requests", 4097),
            ("speculative_decoding", "automatic"),
            ("speculative_decoding", []),
            ("speculative_decoding", {}),
            ("offload_mode", "full"),
            ("offload_mode", []),
            ("offload_mode", {}),
        ):
            configuration = runtime_configuration()
            configuration[field] = value
            invalid_configurations.append(configuration)

        for configuration in invalid_configurations:
            with self.subTest(configuration=configuration):
                descriptor = public_environment()
                descriptor["runtime_configuration"] = configuration
                with self.assertRaises(SubmissionError):
                    prepare_submission(valid_report(), descriptor)

        descriptor = public_environment()
        descriptor["runtime_configuration"] = runtime_configuration()
        candidate = prepare_submission(valid_report(), descriptor)
        for field in ("speculative_decoding", "offload_mode"):
            for value in ([], {}):
                invalid = copy.deepcopy(candidate)
                invalid["runtime_configuration"][field] = value
                with self.subTest(field=field, value=value), self.assertRaisesRegex(
                    SubmissionError, rf"{field} is unsupported"
                ):
                    validate_submission(invalid)

    def test_runtime_configuration_nulls_are_explicit_and_context_bounds_output(self) -> None:
        unknown = public_environment()
        unknown["runtime_configuration"] = runtime_configuration()
        unknown["runtime_configuration"]["context_window_tokens"] = None
        unknown["runtime_configuration"]["concurrent_requests"] = None

        submission = prepare_submission(valid_report(), unknown)

        self.assertIsNone(submission["runtime_configuration"]["context_window_tokens"])
        self.assertIsNone(submission["runtime_configuration"]["concurrent_requests"])

        too_small = public_environment()
        too_small["runtime_configuration"] = runtime_configuration()
        too_small["runtime_configuration"]["context_window_tokens"] = 64
        with self.assertRaisesRegex(SubmissionError, "configured context window"):
            prepare_submission(valid_report(), too_small)

    def test_optional_reasoning_effort_is_preserved_and_validated(self) -> None:
        legacy = prepare_submission(valid_report(), public_environment())
        report = valid_report()
        report["models"][0]["settings"]["reasoning_effort"] = "high"

        submission = prepare_submission(report, public_environment())

        self.assertNotIn("reasoning_effort", legacy["settings"])
        self.assertEqual(submission["settings"]["reasoning_effort"], "high")

        for value in ("automatic", [], {}):
            invalid = copy.deepcopy(submission)
            invalid["settings"]["reasoning_effort"] = value
            with self.subTest(value=value), self.assertRaisesRegex(
                SubmissionError, "reasoning_effort is unsupported"
            ):
                validate_submission(invalid)

    def test_public_hardware_rejects_identifiers_hidden_in_allowed_text(self) -> None:
        descriptors = []

        serial = public_environment(cpu_model="Example processor serial ABC123XYZ")
        descriptors.append(serial)

        device_uuid = public_environment()
        device_identifier = "-".join(
            ("deadbeef", "0000", "0000", "0000", "000000000001")
        )
        device_uuid["hardware"]["accelerators"][0]["model"] = (
            "Example GPU-" + device_identifier
        )
        descriptors.append(device_uuid)

        inventory = public_environment()
        inventory["runtime"]["backend"] = "Example backend inventory ID 88421"
        descriptors.append(inventory)

        network = public_environment(cpu_model="Example processor 198.51.100.7")
        descriptors.append(network)

        for descriptor in descriptors:
            with self.subTest(descriptor=descriptors.index(descriptor)):
                with self.assertRaisesRegex(SubmissionError, "machine identifier"):
                    prepare_submission(valid_report(), descriptor)

    def test_normal_hardware_product_numbers_remain_public(self) -> None:
        descriptor = public_environment(cpu_model="Example CPU X9-14900K")
        descriptor["hardware"]["accelerators"][0]["model"] = "Example RTX 4090"
        descriptor["runtime"] = {
            "name": "Example Runtime 2",
            "version": "1.4.7",
            "backend": "Compute API 12.8",
        }

        submission = prepare_submission(valid_report(), descriptor)

        self.assertEqual(submission["hardware"], descriptor["hardware"])
        self.assertEqual(submission["runtime"], descriptor["runtime"])

    def test_hardware_execution_and_memory_contracts_are_consistent(self) -> None:
        cpu_with_accelerator = public_environment()
        cpu_with_accelerator["hardware"]["execution_mode"] = "cpu_only"
        accelerator_without_device = public_environment()
        accelerator_without_device["hardware"]["accelerators"] = []
        shared_with_device_memory = public_environment()
        shared_with_device_memory["hardware"]["memory"]["architecture"] = "shared"
        discrete_without_device_memory = public_environment()
        discrete_without_device_memory["hardware"]["accelerators"][0]["memory_gb"] = None
        duplicate = public_environment()
        duplicate["hardware"]["accelerators"].append(
            copy.deepcopy(duplicate["hardware"]["accelerators"][0])
        )

        for descriptor in (
            cpu_with_accelerator,
            accelerator_without_device,
            shared_with_device_memory,
            discrete_without_device_memory,
            duplicate,
        ):
            with self.assertRaises(SubmissionError):
                prepare_submission(valid_report(), descriptor)

    def test_non_ascii_public_text_has_a_stable_content_id(self) -> None:
        descriptor = public_environment(cpu_model="Processeur λ")

        first = prepare_submission(
            valid_report(display_name="Modèle public"),
            descriptor,
        )
        second = prepare_submission(
            valid_report(display_name="Modèle public"),
            copy.deepcopy(descriptor),
        )

        self.assertEqual(first["submission_id"], second["submission_id"])

    def test_json_loader_rejects_duplicate_fields_and_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            duplicate = directory / "duplicate.json"
            duplicate.write_text('{"field":1,"field":2}', encoding="utf-8")
            target = directory / "target.json"
            target.write_text("{}", encoding="utf-8")
            link = directory / "link.json"
            try:
                link.symlink_to(target)
            except (NotImplementedError, OSError):
                link = None

            with self.assertRaises(SubmissionError):
                load_json_object(duplicate)
            if link is not None:
                with self.assertRaises(SubmissionError):
                    load_json_object(link)

    def test_hardware_descriptor_file_must_be_ignored_owner_only_and_regular(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        ignored_parent = repository / ".local"
        ignored_parent.mkdir(exist_ok=True)
        encoded = json.dumps(public_environment())
        with (
            tempfile.TemporaryDirectory(prefix="descriptor-", dir=ignored_parent) as ignored,
            tempfile.TemporaryDirectory(prefix=".descriptor-", dir=repository) as visible,
        ):
            ignored_directory = Path(ignored)
            accepted = ignored_directory / "hardware.json"
            accepted.write_text(encoded, encoding="utf-8")
            accepted.chmod(0o600)
            visible_file = Path(visible) / "hardware.json"
            visible_file.write_text(encoded, encoding="utf-8")
            visible_file.chmod(0o600)

            self.assertEqual(load_public_environment_file(accepted), public_environment())
            with self.assertRaisesRegex(SubmissionError, "Git-ignored"):
                load_public_environment_file(visible_file)

            if os.name != "nt":
                accepted.chmod(0o644)
                with self.assertRaisesRegex(SubmissionError, "owner-only"):
                    load_public_environment_file(accepted)
                accepted.chmod(0o600)

            link = ignored_directory / "linked-hardware.json"
            try:
                link.symlink_to(accepted)
            except (NotImplementedError, OSError):
                link = None
            if link is not None:
                with self.assertRaisesRegex(SubmissionError, "regular"):
                    load_public_environment_file(link)

    def test_saved_submission_loader_requires_exact_secure_canonical_candidate(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        ignored_parent = repository / ".local"
        ignored_parent.mkdir(exist_ok=True)
        submission = prepare_submission(valid_report(), public_environment())
        canonical = render_submission_bytes(submission)
        with (
            tempfile.TemporaryDirectory(prefix="candidate-", dir=ignored_parent) as ignored,
            tempfile.TemporaryDirectory(prefix=".candidate-", dir=repository) as visible,
        ):
            ignored_directory = Path(ignored)
            accepted = ignored_directory / f"{submission['submission_id']}.json"
            accepted.write_bytes(canonical)
            accepted.chmod(0o600)

            self.assertEqual(load_saved_submission(accepted), submission)

            wrong_name = ignored_directory / "candidate.json"
            wrong_name.write_bytes(canonical)
            wrong_name.chmod(0o600)
            with self.assertRaisesRegex(SubmissionError, "filename"):
                load_saved_submission(wrong_name)

            # Give it the required digest name in its own ignored directory so the
            # byte-format rejection, rather than the filename rejection, is exercised.
            nested = ignored_directory / "nested"
            nested.mkdir(mode=0o700)
            noncanonical = nested / accepted.name
            noncanonical.write_text(
                json.dumps(submission, sort_keys=True), encoding="utf-8"
            )
            noncanonical.chmod(0o600)
            with self.assertRaisesRegex(SubmissionError, "not canonical"):
                load_saved_submission(noncanonical)

            visible_path = Path(visible) / accepted.name
            visible_path.write_bytes(canonical)
            visible_path.chmod(0o600)
            with self.assertRaisesRegex(SubmissionError, "Git-ignored"):
                load_saved_submission(visible_path)

            with tempfile.TemporaryDirectory() as outside:
                outside_path = Path(outside) / accepted.name
                outside_path.write_bytes(canonical)
                outside_path.chmod(0o600)
                self.assertEqual(load_saved_submission(outside_path), submission)

            if os.name != "nt":
                accepted.chmod(0o644)
                with self.assertRaisesRegex(SubmissionError, "owner-only"):
                    load_saved_submission(accepted)
                accepted.chmod(0o600)

            link = ignored_directory / f"linked-{accepted.name}"
            try:
                link.symlink_to(accepted)
            except (NotImplementedError, OSError):
                link = None
            if link is not None:
                with self.assertRaisesRegex(SubmissionError, "regular"):
                    load_saved_submission(link)

    def test_write_is_owner_only_and_append_only(self) -> None:
        submission = prepare_submission(valid_report(), public_environment())
        with tempfile.TemporaryDirectory() as temporary:
            path = write_submission(submission, Path(temporary) / "candidates")
            mode = path.stat().st_mode & 0o777
            with self.assertRaises(SubmissionError):
                write_submission(submission, path.parent)

        if os.name != "nt":
            self.assertEqual(mode, 0o600)

    def test_ensure_submission_is_idempotent_but_never_overwrites(self) -> None:
        submission = prepare_submission(valid_report(), public_environment())
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "candidates"
            first = ensure_submission(submission, directory)
            second = ensure_submission(submission, directory)

            self.assertEqual(first, second)
            self.assertEqual(first.read_bytes(), render_submission_bytes(submission))

            first.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(SubmissionError, "different content"):
                ensure_submission(submission, directory)

    @unittest.skipIf(os.name == "nt", "POSIX permission contract")
    def test_ensure_submission_rejects_a_visible_existing_candidate(self) -> None:
        submission = prepare_submission(valid_report(), public_environment())
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "candidates"
            path = ensure_submission(submission, directory)
            path.chmod(0o644)

            with self.assertRaisesRegex(SubmissionError, "owner-only"):
                ensure_submission(submission, directory)

    def test_submission_destination_must_be_ignored_inside_a_worktree(self) -> None:
        submission = prepare_submission(valid_report(), public_environment())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(
                ["git", "init", "--quiet"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            (root / ".gitignore").write_text(".private/\n", encoding="utf-8")

            with (
                mock.patch.dict(os.environ, {"GIT_DIR": "/invalid/repository"}),
                self.assertRaisesRegex(SubmissionError, "destination"),
            ):
                ensure_submission(submission, root / "site" / "data" / "submissions")

            with mock.patch.dict(os.environ, {"GIT_DIR": "/invalid/repository"}):
                saved = ensure_submission(submission, root / ".private" / "submissions")
            self.assertTrue(saved.is_file())

    def test_submission_destination_rejects_an_indeterminate_tracked_probe(self) -> None:
        submission = prepare_submission(valid_report(), public_environment())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            destination = root / ".private" / "submissions"
            results = (
                subprocess.CompletedProcess([], 0, stdout=f"{root}\n", stderr=""),
                subprocess.CompletedProcess([], 128, stdout="", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            )
            with (
                mock.patch(
                    "local_inference_test_bench.safety.subprocess.run",
                    side_effect=results,
                ),
                self.assertRaisesRegex(SubmissionError, "destination"),
            ):
                ensure_submission(submission, destination)

    def test_leaderboard_ranks_quality_only_and_shares_ranks_for_ties(self) -> None:
        best_fast = prepare_submission(
            valid_report(display_name="Best Fast", source="publisher/best-fast", latency_ms=5.0),
            public_environment(),
        )
        best_slow = prepare_submission(
            valid_report(display_name="Best Slow", source="publisher/best-slow", latency_ms=50.0),
            public_environment(),
        )
        lower = prepare_submission(
            valid_report(
                display_name="Lower",
                source="publisher/lower",
                outcomes=("pass", "pass", "pass", "pass", "fail"),
                latency_ms=1.0,
            ),
            public_environment(),
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for submission in (lower, best_slow, best_fast):
                (directory / f"{submission['submission_id']}.json").write_text(
                    json.dumps(submission),
                    encoding="utf-8",
                )
            leaderboard = build_leaderboard(directory)

        self.assertEqual(leaderboard["entry_count"], 3)
        entries = leaderboard["entries"]
        self.assertEqual([entry["rank"] for entry in entries], [1, 1, 2])
        self.assertEqual(
            [entry["model"]["display_name"] for entry in entries],
            ["Best Fast", "Best Slow", "Lower"],
        )
        self.assertGreater(
            entries[0]["metrics"]["completion_tokens_per_second"],
            entries[1]["metrics"]["completion_tokens_per_second"],
        )
        self.assertEqual(entries[0]["metrics"]["semantic_score_percent"], 100.0)
        self.assertEqual(entries[2]["metrics"]["semantic_score_percent"], 80.0)
        self.assertNotIn("cases", entries[0])

    def test_leaderboard_rejects_a_filename_that_does_not_match_content(self) -> None:
        submission = prepare_submission(valid_report(), public_environment())
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "wrong.json").write_text(json.dumps(submission), encoding="utf-8")
            with self.assertRaisesRegex(SubmissionError, "filename"):
                build_leaderboard(directory)

    def test_leaderboard_enforces_total_input_and_output_limits(self) -> None:
        submission = prepare_submission(valid_report(), public_environment())
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / f"{submission['submission_id']}.json"
            path.write_text(json.dumps(submission), encoding="utf-8")
            with mock.patch.object(submissions_module, "_MAX_DATASET_BYTES", 1):
                with self.assertRaisesRegex(SubmissionError, "input exceeds"):
                    build_leaderboard(directory)
                with self.assertRaisesRegex(SubmissionError, "generated leaderboard"):
                    write_leaderboard(
                        {"schema_version": "1.0", "entry_count": 0, "entries": []},
                        directory / "leaderboard.json",
                    )

    def test_leaderboard_writer_does_not_follow_a_fixed_temporary_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            output = directory / "leaderboard.json"
            victim = directory / "victim.txt"
            victim.write_text("unchanged", encoding="utf-8")
            fixed_temporary = directory / ".leaderboard.json.tmp"
            try:
                fixed_temporary.symlink_to(victim)
            except (NotImplementedError, OSError):
                self.skipTest("symlinks are unavailable")

            write_leaderboard(
                {"schema_version": "1.0", "entry_count": 0, "entries": []},
                output,
            )

            self.assertEqual(victim.read_text(encoding="utf-8"), "unchanged")
            self.assertTrue(fixed_temporary.is_symlink())

    def test_builder_check_detects_stale_generated_data(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        script = repository / "scripts" / "build_leaderboard.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            submissions = root / "submissions"
            submissions.mkdir()
            output = root / "leaderboard.json"
            output.write_text("{}", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--submissions-dir",
                    str(submissions),
                    "--output",
                    str(output),
                    "--check",
                ],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("generated data is stale", completed.stderr)

    def test_builder_check_rejects_semantically_equal_noncanonical_bytes(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        script = repository / "scripts" / "build_leaderboard.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            submissions = root / "submissions"
            submissions.mkdir()
            output = root / "leaderboard.json"
            output.write_text(
                '{"entries":[],"entry_count":0,"schema_version":"1.0"}\n',
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--submissions-dir",
                    str(submissions),
                    "--output",
                    str(output),
                    "--check",
                ],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("generated data is stale", completed.stderr)

    def test_builder_staged_check_reads_the_git_index(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        script = repository / "scripts" / "build_leaderboard.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            submissions = root / "site" / "data" / "submissions"
            submissions.mkdir(parents=True)
            (submissions / ".gitkeep").write_text("", encoding="utf-8")
            output = root / "site" / "data" / "leaderboard.json"
            write_leaderboard(
                {"schema_version": "1.0", "entry_count": 0, "entries": []},
                output,
            )
            subprocess.run(
                ["git", "init", "--quiet"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            subprocess.run(
                ["git", "add", "site/data/submissions/.gitkeep", "site/data/leaderboard.json"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            output.write_text(
                '{"entries":[],"entry_count":0,"schema_version":"1.0"}\n',
                encoding="utf-8",
            )
            staged_is_canonical = subprocess.run(
                [sys.executable, str(script), "--staged", "--repository", str(root)],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            subprocess.run(
                ["git", "add", "site/data/leaderboard.json"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            write_leaderboard(
                {"schema_version": "1.0", "entry_count": 0, "entries": []},
                output,
            )
            staged_is_noncanonical = subprocess.run(
                [sys.executable, str(script), "--staged", "--repository", str(root)],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(staged_is_canonical.returncode, 0, staged_is_canonical.stderr)
        self.assertEqual(staged_is_noncanonical.returncode, 1)
        self.assertIn("generated data is stale", staged_is_noncanonical.stderr)


if __name__ == "__main__":
    unittest.main()
