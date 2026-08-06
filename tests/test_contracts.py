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
    SubmissionError,
    build_leaderboard,
    build_leaderboard_bundle,
    build_persisted_leaderboard,
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
                validate_submission(submission)
                self.validator.validate(submission, "leaderboard-submission.schema.json")
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
        dataset["entries"][0]["metrics"]["usage_coverage_cases"] = 4
        with self.assertRaises(SchemaValidationError):
            self.validator.validate(dataset, "leaderboard-dataset.schema.json")

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
            "schema_version": "1.0",
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
