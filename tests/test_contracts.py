from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = PROJECT_ROOT / "specs" / "002-anonymized-leaderboard" / "contracts"
RUNNER_CONTRACTS = PROJECT_ROOT / "specs" / "001-local-inference-testbench" / "contracts"
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from local_inference_test_bench.submissions import (  # noqa: E402
    build_leaderboard,
    prepare_submission,
    validate_submission,
)
from schema_validator import LocalSchemaValidator, SchemaValidationError  # noqa: E402
from test_models import valid_manifest_data  # noqa: E402
from test_submissions import public_environment, runtime_configuration, valid_report  # noqa: E402


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

    def test_example_descriptor_matches_its_published_schema(self) -> None:
        descriptor = json.loads(
            (PROJECT_ROOT / "config" / "hardware.example.json").read_text(encoding="utf-8")
        )

        self.validator.validate(descriptor, "hardware-descriptor.schema.json")

    def test_export_and_dataset_match_the_published_schemas(self) -> None:
        report = valid_report()
        report["models"][0]["settings"]["reasoning_effort"] = "high"
        environment = public_environment()
        environment["runtime_configuration"] = runtime_configuration()
        submission = prepare_submission(report, environment)
        self.validator.validate(submission, "leaderboard-submission.schema.json")

        with tempfile.TemporaryDirectory() as temporary:
            submissions = Path(temporary)
            path = submissions / f"{submission['submission_id']}.json"
            path.write_text(json.dumps(submission), encoding="utf-8")
            dataset = build_leaderboard(submissions)

        self.validator.validate(dataset, "leaderboard-dataset.schema.json")

    def test_every_accepted_record_matches_runtime_and_published_contracts(self) -> None:
        submissions = PROJECT_ROOT / "site" / "data" / "submissions"
        for path in sorted(submissions.glob("*.json")):
            with self.subTest(file=path.name):
                submission = json.loads(path.read_text(encoding="utf-8"))
                validate_submission(submission)
                self.validator.validate(submission, "leaderboard-submission.schema.json")
                self.assertEqual(path.name, f"{submission['submission_id']}.json")

        dataset = json.loads(
            (PROJECT_ROOT / "site" / "data" / "leaderboard.json").read_text(encoding="utf-8")
        )
        self.validator.validate(dataset, "leaderboard-dataset.schema.json")

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
        dataset["entries"][0]["metrics"]["usage_coverage_cases"] = 4
        with self.assertRaises(SchemaValidationError):
            self.validator.validate(dataset, "leaderboard-dataset.schema.json")

    def test_dataset_contract_caps_entries(self) -> None:
        submission = prepare_submission(valid_report(), public_environment())
        with tempfile.TemporaryDirectory() as temporary:
            submissions = Path(temporary)
            path = submissions / f"{submission['submission_id']}.json"
            path.write_text(json.dumps(submission), encoding="utf-8")
            dataset = build_leaderboard(submissions)

        oversized_count = copy.deepcopy(dataset)
        oversized_count["entry_count"] = 10001
        with self.assertRaises(SchemaValidationError):
            self.validator.validate(oversized_count, "leaderboard-dataset.schema.json")

        oversized_entries = copy.deepcopy(dataset)
        oversized_entries["entry_count"] = 10000
        oversized_entries["entries"] *= 10001
        with self.assertRaises(SchemaValidationError):
            self.validator.validate(oversized_entries, "leaderboard-dataset.schema.json")


if __name__ == "__main__":
    unittest.main()
