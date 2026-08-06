from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = PROJECT_ROOT / "specs" / "002-anonymized-leaderboard" / "contracts"
RUNNER_CONTRACTS = PROJECT_ROOT / "specs" / "001-local-inference-testbench" / "contracts"
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from local_inference_test_bench.submissions import (  # noqa: E402
    FacetSelector,
    SubmissionError,
    build_leaderboard,
    build_leaderboard_bundle,
    build_persisted_leaderboard,
    validate_accepted_submission,
)
from local_inference_test_bench import runner as runner_module  # noqa: E402
from local_inference_test_bench.reporting import validate_report  # noqa: E402
from local_inference_test_bench.suites import (  # noqa: E402
    PUBLIC_SUITE_REGISTRY,
    SuiteCase,
)
from schema_validator import LocalSchemaValidator, SchemaValidationError  # noqa: E402
from test_models import valid_manifest_data  # noqa: E402
from test_submissions import (  # noqa: E402
    legacy_submission_fixture,
    prepare_submission,
    public_environment,
    runtime_configuration,
    valid_report,
)


class PublishedContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = LocalSchemaValidator(CONTRACTS)
        self.runner_validator = LocalSchemaValidator(RUNNER_CONTRACTS)

    def test_reasoning_effort_matches_manifest_and_run_record_schemas(self) -> None:
        manifest = valid_manifest_data()
        manifest["models"][0]["settings"]["reasoning_effort"] = "none"
        report = valid_report()
        report["models"][0]["settings"]["reasoning_effort"] = "none"

        self.runner_validator.validate(manifest, "manifest.schema.json")
        self.runner_validator.validate(report, "run-record.schema.json")

    def test_optional_parameter_scale_matches_manifest_and_run_record_schemas(self) -> None:
        scale = {"total_billions": 30.0, "active_billions": 3.0}
        manifest = valid_manifest_data()
        manifest["models"][0]["parameter_scale"] = scale
        report = valid_report()
        report["models"][0]["provenance"]["parameter_scale"] = scale

        self.runner_validator.validate(manifest, "manifest.schema.json")
        self.runner_validator.validate(report, "run-record.schema.json")

        invalid = copy.deepcopy(report)
        invalid["models"][0]["provenance"]["parameter_scale"] = {
            "total_billions": None,
            "active_billions": 3.0,
        }
        with self.assertRaises(SchemaValidationError):
            self.runner_validator.validate(invalid, "run-record.schema.json")

    def test_registered_synthetic_suite_matches_runtime_and_run_record_contract(self) -> None:
        report = valid_report()
        report["profile"] = "synthetic-two"
        report["suite_version"] = "9.0"
        report["models"][0]["cases"] = report["models"][0]["cases"][:2]
        report["models"][0]["summary"] = runner_module._summarize(
            report["models"][0]["cases"]
        )
        suite = (
            SuiteCase("structured-json", "structured_output"),
            SuiteCase("python-ast", "coding"),
        )

        with mock.patch.dict(
            PUBLIC_SUITE_REGISTRY,
            {("synthetic-two", "9.0"): suite},
        ):
            validate_report(report)
            self.runner_validator.validate(report, "run-record.schema.json")

    def test_example_descriptor_matches_its_published_schema(self) -> None:
        descriptor = json.loads(
            (PROJECT_ROOT / "config" / "hardware.example.json").read_text(encoding="utf-8")
        )

        self.validator.validate(descriptor, "hardware-descriptor.schema.json")

    def test_example_manifest_matches_its_published_schema(self) -> None:
        manifest = json.loads(
            (PROJECT_ROOT / "config" / "models.example.json").read_text(encoding="utf-8")
        )

        self.runner_validator.validate(manifest, "manifest.schema.json")

    def test_public_descriptor_contracts_require_visible_ascii(self) -> None:
        descriptor = public_environment()
        descriptor["hardware"]["cpu"]["model"] = "Processeur " + chr(0x03BB)
        with self.assertRaises(SchemaValidationError):
            self.validator.validate(descriptor, "hardware-descriptor.schema.json")

        submission = prepare_submission(valid_report(), public_environment())
        submission["model"]["revision"] = "r" + chr(0x03BB)
        with self.assertRaises(SchemaValidationError):
            self.validator.validate(submission, "leaderboard-submission.schema.json")

    def test_example_measurement_evidence_matches_its_published_schema(self) -> None:
        evidence = json.loads(
            (PROJECT_ROOT / "config" / "measurement-evidence.example.json").read_text(
                encoding="utf-8"
            )
        )

        self.validator.validate(evidence, "measurement-evidence.schema.json")

    def test_export_and_dataset_match_the_published_schemas(self) -> None:
        report = valid_report()
        report["models"][0]["settings"]["reasoning_effort"] = "high"
        environment = public_environment()
        environment["runtime_configuration"] = runtime_configuration()
        submission = prepare_submission(report, environment)
        self.assertEqual(submission["schema_version"], "1.1")
        self.validator.validate(submission, "leaderboard-submission.schema.json")
        self.assertEqual(
            submission["runtime_configuration"], environment["runtime_configuration"]
        )

        with tempfile.TemporaryDirectory() as temporary:
            submissions = Path(temporary)
            path = submissions / f"{submission['submission_id']}.json"
            path.write_text(json.dumps(submission), encoding="utf-8")
            dataset = build_leaderboard(submissions)

        self.validator.validate(dataset, "leaderboard-dataset.schema.json")
        self.assertEqual(
            dataset["entries"][0]["runtime_configuration"],
            environment["runtime_configuration"],
        )
        index, shards = build_leaderboard_bundle(dataset)
        self.validator.validate(index, "leaderboard-index.schema.json")
        self.assertEqual(index["entry_count"], dataset["entry_count"])
        self.assertEqual(index["shard_count"], len(shards))
        for shard in shards:
            self.validator.validate(shard, "leaderboard-shard.schema.json")
        self.assertEqual(
            sum(shard["entry_count"] for shard in shards),
            index["entry_count"],
        )

    def test_subset_facet_contract_requires_unavailable_performance(self) -> None:
        submission = prepare_submission(valid_report(), public_environment())
        facet = FacetSelector(
            facet_id="coding-text",
            capabilities=frozenset({"coding"}),
            modalities=frozenset({"text"}),
        )
        with tempfile.TemporaryDirectory() as temporary:
            submissions = Path(temporary)
            path = submissions / f"{submission['submission_id']}.json"
            path.write_text(json.dumps(submission), encoding="utf-8")
            dataset = build_leaderboard(submissions, facet=facet)

        self.validator.validate(dataset, "leaderboard-dataset.schema.json")
        metrics = dataset["entries"][0]["metrics"]
        self.assertEqual(metrics["usage_coverage_cases"], 0)
        self.assertIsNone(metrics["latency_ms_mean"])
        self.assertIsNone(metrics["completion_tokens_per_second"])

        inconsistent = copy.deepcopy(dataset)
        inconsistent["entries"][0]["metrics"]["usage_coverage_cases"] = 1
        with self.assertRaises(SchemaValidationError):
            self.validator.validate(inconsistent, "leaderboard-dataset.schema.json")

        mislabeled = copy.deepcopy(dataset)
        mislabeled["entries"][0]["metrics"]["latency_ms_mean"] = 10.0
        with self.assertRaises(SchemaValidationError):
            self.validator.validate(mislabeled, "leaderboard-dataset.schema.json")

    def test_full_suite_contract_requires_observed_latency(self) -> None:
        submission = prepare_submission(valid_report(), public_environment())
        with tempfile.TemporaryDirectory() as temporary:
            submissions = Path(temporary)
            path = submissions / f"{submission['submission_id']}.json"
            path.write_text(json.dumps(submission), encoding="utf-8")
            dataset = build_leaderboard(submissions)

        dataset["entries"][0]["metrics"].update(
            {
                "usage_coverage_cases": 0,
                "latency_ms_mean": None,
                "completion_tokens_per_second": None,
            }
        )
        with self.assertRaises(SchemaValidationError):
            self.validator.validate(dataset, "leaderboard-dataset.schema.json")

    def test_legacy_subset_projection_matches_the_versioned_contract(self) -> None:
        legacy_path, _ = legacy_submission_fixture()
        facet = FacetSelector(
            facet_id="legacy-coding-text",
            capabilities=frozenset({"coding"}),
            modalities=frozenset({"text"}),
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / legacy_path.name).write_bytes(legacy_path.read_bytes())
            dataset = build_leaderboard(directory, facet=facet)

        self.assertEqual(dataset["schema_version"], "1.1")
        self.validator.validate(dataset, "leaderboard-dataset.schema.json")

    def test_not_applicable_contracts_require_matching_route_and_termination(self) -> None:
        report = valid_report()
        report_case = report["models"][0]["cases"][-1]
        report_case.update(
            {
                "semantic_success": False,
                "exact_format": False,
                "outcome": "not_applicable",
                "route": "not_applicable",
                "termination": "not_applicable",
            }
        )
        self.runner_validator.validate(report, "run-record.schema.json")

        mismatched_report = copy.deepcopy(report)
        mismatched_report["models"][0]["cases"][-1]["route"] = "safe_refusal"
        with self.assertRaises(SchemaValidationError):
            self.runner_validator.validate(mismatched_report, "run-record.schema.json")
        for field in ("route", "termination"):
            reverse_mismatch = valid_report()
            reverse_mismatch["models"][0]["cases"][0][field] = "not_applicable"
            with self.subTest(report_reverse=field), self.assertRaises(
                SchemaValidationError
            ):
                self.runner_validator.validate(
                    reverse_mismatch,
                    "run-record.schema.json",
                )

        submission = prepare_submission(valid_report(), public_environment())
        submission_case = submission["cases"][-1]
        submission_case.update(
            {
                "outcome": "not_applicable",
                "route": "not_applicable",
                "termination": "not_applicable",
            }
        )
        self.validator.validate(submission, "leaderboard-submission.schema.json")

        mismatched_submission = copy.deepcopy(submission)
        mismatched_submission["cases"][-1]["termination"] = "completed"
        with self.assertRaises(SchemaValidationError):
            self.validator.validate(
                mismatched_submission,
                "leaderboard-submission.schema.json",
            )
        for field in ("route", "termination"):
            reverse_mismatch = prepare_submission(valid_report(), public_environment())
            reverse_mismatch["cases"][0][field] = "not_applicable"
            with self.subTest(submission_reverse=field), self.assertRaises(
                SchemaValidationError
            ):
                self.validator.validate(
                    reverse_mismatch,
                    "leaderboard-submission.schema.json",
                )

    def test_public_model_descriptor_contract_uses_field_specific_ascii_limits(self) -> None:
        maximums = {
            "display_name": 160,
            "source": 240,
            "precision": 80,
        }
        for field, maximum in maximums.items():
            accepted = prepare_submission(valid_report(), public_environment())
            accepted["model"][field] = "x" * maximum
            with self.subTest(field=field, boundary="accepted"):
                self.validator.validate(accepted, "leaderboard-submission.schema.json")

            oversized = copy.deepcopy(accepted)
            oversized["model"][field] += "x"
            with self.subTest(field=field, boundary="oversized"):
                with self.assertRaises(SchemaValidationError):
                    self.validator.validate(oversized, "leaderboard-submission.schema.json")

            non_ascii = copy.deepcopy(accepted)
            non_ascii["model"][field] = "Model " + chr(0x03BB)
            with self.subTest(field=field, boundary="non_ascii"):
                with self.assertRaises(SchemaValidationError):
                    self.validator.validate(non_ascii, "leaderboard-submission.schema.json")

    def test_every_accepted_record_matches_runtime_and_published_contracts(self) -> None:
        submissions = PROJECT_ROOT / "site" / "data" / "submissions"
        for path in sorted(submissions.glob("*.json")):
            with self.subTest(file=path.name):
                submission = json.loads(path.read_text(encoding="utf-8"))
                validate_accepted_submission(submission)
                schema = {
                    "1.0": "leaderboard-submission-v1.0.schema.json",
                    "1.1": "leaderboard-submission.schema.json",
                }.get(submission["schema_version"])
                self.assertIsNotNone(schema)
                self.validator.validate(submission, schema)
                self.assertEqual(path.name, f"{submission['submission_id']}.json")

        dataset = json.loads(
            (PROJECT_ROOT / "site" / "data" / "leaderboard.json").read_text(encoding="utf-8")
        )
        if "entries" in dataset:
            self.validator.validate(dataset, "leaderboard-dataset.schema.json")
            self.assertEqual(dataset["entry_count"], len(dataset["entries"]))
        else:
            self.validator.validate(dataset, "leaderboard-index.schema.json")
            self.assertEqual(dataset["entry_count"] == 0, dataset["shard_count"] == 0)
            self.assertLessEqual(dataset["shard_count"], dataset["entry_count"])

    def test_closed_schema_rejects_unknown_and_inconsistent_fields(self) -> None:
        submission = prepare_submission(valid_report(), public_environment())
        unknown = copy.deepcopy(submission)
        unknown["contributor"] = "Example Contributor"
        bad_hardware = public_environment()
        bad_hardware["hardware"]["execution_mode"] = "cpu_only"

        with self.assertRaises(SchemaValidationError):
            self.validator.validate(unknown, "leaderboard-submission.schema.json")
        with self.assertRaises(SchemaValidationError):
            self.validator.validate(bad_hardware, "hardware-descriptor.schema.json")

        with tempfile.TemporaryDirectory() as temporary:
            submissions = Path(temporary)
            path = submissions / f"{submission['submission_id']}.json"
            path.write_text(json.dumps(submission), encoding="utf-8")
            dataset = build_leaderboard(submissions)
        dataset["entries"][0]["metrics"]["usage_coverage_cases"] = "4"
        with self.assertRaises(SchemaValidationError):
            self.validator.validate(dataset, "leaderboard-dataset.schema.json")

    def test_mixed_legacy_and_current_dataset_matches_transport_contracts(self) -> None:
        current = prepare_submission(valid_report(), public_environment())
        _legacy_path, legacy = legacy_submission_fixture()
        self.assertEqual(legacy["schema_version"], "1.0")

        with tempfile.TemporaryDirectory() as temporary:
            submissions = Path(temporary)
            for submission in (legacy, current):
                path = submissions / f"{submission['submission_id']}.json"
                path.write_text(json.dumps(submission), encoding="utf-8")
            dataset = build_leaderboard(submissions)

        self.assertEqual(dataset["schema_version"], "1.1")
        self.assertEqual(
            {entry["submission_schema_version"] for entry in dataset["entries"]},
            {"1.0", "1.1"},
        )
        self.validator.validate(dataset, "leaderboard-dataset.schema.json")

        index, shards = build_leaderboard_bundle(dataset)
        self.validator.validate(index, "leaderboard-index.schema.json")
        for shard in shards:
            self.validator.validate(shard, "leaderboard-shard.schema.json")

    def test_transport_contracts_reject_unknown_keys_and_wrong_types(self) -> None:
        submission = prepare_submission(valid_report(), public_environment())
        with tempfile.TemporaryDirectory() as temporary:
            submissions = Path(temporary)
            path = submissions / f"{submission['submission_id']}.json"
            path.write_text(json.dumps(submission), encoding="utf-8")
            dataset = build_leaderboard(submissions)
        index, shards = build_leaderboard_bundle(dataset)
        self.assertEqual(len(shards), 1)
        shard = shards[0]

        rejected = (
            ("leaderboard-index.schema.json", {**index, "path": "not-accepted"}),
            ("leaderboard-index.schema.json", {**index, "entry_count": True}),
            ("leaderboard-index.schema.json", {**index, "shard_count": "1"}),
            (
                "leaderboard-index.schema.json",
                {**index, "entry_count": 1, "shard_count": 0},
            ),
            (
                "leaderboard-index.schema.json",
                {**index, "entry_count": 0, "shard_count": 1},
            ),
            ("leaderboard-shard.schema.json", {**shard, "url": "not-accepted"}),
            ("leaderboard-shard.schema.json", {**shard, "shard_id": "00001"}),
            ("leaderboard-shard.schema.json", {**shard, "entry_count": "1"}),
            ("leaderboard-shard.schema.json", {**shard, "entries": {}}),
        )
        for schema, payload in rejected:
            with self.subTest(schema=schema, keys=sorted(payload)):
                with self.assertRaises(SchemaValidationError):
                    self.validator.validate(payload, schema)

        inconsistent = copy.deepcopy(dataset)
        inconsistent["entry_count"] += 1
        with self.assertRaisesRegex(SubmissionError, "transport contract"):
            build_leaderboard_bundle(inconsistent)

    def test_logical_dataset_contract_does_not_reintroduce_the_old_volume_cap(self) -> None:
        submission = prepare_submission(valid_report(), public_environment())
        with tempfile.TemporaryDirectory() as temporary:
            submissions = Path(temporary)
            path = submissions / f"{submission['submission_id']}.json"
            path.write_text(json.dumps(submission), encoding="utf-8")
            dataset = build_leaderboard(submissions)

        large = copy.deepcopy(dataset)
        large["entries"] *= 10001
        large["entry_count"] = len(large["entries"])
        self.validator.validate(large, "leaderboard-dataset.schema.json")

        persisted = build_persisted_leaderboard(large)
        self.assertEqual(
            set(persisted),
            {"index_version", "schema_version", "entry_count", "shard_count"},
        )
        self.validator.validate(persisted, "leaderboard-index.schema.json")

        index = {
            "index_version": "1.0",
            "schema_version": large["schema_version"],
            "entry_count": large["entry_count"],
            "shard_count": 2,
        }
        self.validator.validate(index, "leaderboard-index.schema.json")

        # Standard JSON Schema cannot compare sibling numeric values. Runtime
        # validators separately reject shard_count values above entry_count.
        schema_only_upper_bound = {
            **index,
            "entry_count": 1,
            "shard_count": 2,
        }
        self.validator.validate(schema_only_upper_bound, "leaderboard-index.schema.json")


if __name__ == "__main__":
    unittest.main()
