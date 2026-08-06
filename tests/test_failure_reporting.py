from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import tomllib
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from local_inference_test_bench import failure_reporting  # noqa: E402
from local_inference_test_bench import __version__  # noqa: E402
from local_inference_test_bench.failure_reporting import (  # noqa: E402
    FailureSignal,
    build_failure_draft,
    build_issue_url,
    detect_report_failure,
    render_issue_body,
    validate_failure_draft,
)
from schema_validator import LocalSchemaValidator  # noqa: E402


ELIGIBLE_CATEGORIES = (
    "timeout",
    "network_error",
    "server_error",
    "http_error",
    "request_rejected",
    "invalid_json",
    "protocol_error",
    "response_too_large",
)

EXPECTED_DRAFT_KEYS = {
    "schema_version",
    "report_type",
    "litb_version",
    "command",
    "profile",
    "suite_version",
    "phase",
    "failure_category",
    "os_family",
    "python_series",
    "architecture",
    "hardware_class",
    "runtime",
}


def public_environment() -> dict:
    return {
        "schema_version": "1.0",
        "hardware": {
            "cpu": {"model": "Example CPU", "logical_cores": 16},
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


def report_with_terminations(*terminations: str) -> dict:
    return {
        "validity": "invalid",
        "models": [
            {
                "cases": [
                    {
                        "termination": termination,
                        "semantic_success": False,
                        "exact_format": False,
                    }
                    for termination in terminations
                ]
            }
        ],
    }


class FailureReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        contracts = PROJECT_ROOT / "specs" / "005-guided-failure-reporting" / "contracts"
        self.schema_validator = LocalSchemaValidator(contracts)

    def build_draft(
        self,
        signal: FailureSignal | None = None,
        *,
        descriptor: dict | None = None,
    ) -> dict:
        return build_failure_draft(
            signal or FailureSignal(phase="case_execution", failure_category="timeout"),
            profile="standard",
            suite_version="1.0",
            public_environment=descriptor,
        )

    def test_draft_is_closed_and_matches_the_published_contract(self) -> None:
        with (
            mock.patch.object(failure_reporting.platform, "system", return_value="Darwin"),
            mock.patch.object(failure_reporting.platform, "machine", return_value="arm64"),
            mock.patch.object(
                failure_reporting.sys,
                "version_info",
                SimpleNamespace(major=3, minor=13),
            ),
        ):
            draft = self.build_draft(descriptor=public_environment())

        self.assertEqual(set(draft), EXPECTED_DRAFT_KEYS)
        self.assertEqual(draft["schema_version"], "1.0")
        self.assertEqual(draft["report_type"], "benchmark_execution_failure")
        self.assertEqual(draft["command"], "run")
        self.assertEqual(draft["profile"], "standard")
        self.assertEqual(draft["suite_version"], "1.0")
        self.assertEqual(draft["phase"], "case_execution")
        self.assertEqual(draft["failure_category"], "timeout")
        self.assertEqual(draft["os_family"], "macos")
        self.assertEqual(draft["python_series"], "python_3_13")
        self.assertEqual(draft["architecture"], "arm64")
        self.assertEqual(draft["hardware_class"], "discrete_accelerator")
        self.assertEqual(
            draft["runtime"],
            {
                "name": "Example Runtime",
                "version": "1.2.3",
                "backend": "generic-backend",
            },
        )
        self.assertIsNone(validate_failure_draft(draft))
        self.schema_validator.validate(draft, "failure-issue.schema.json")

        invalid_drafts = []
        missing = copy.deepcopy(draft)
        missing.pop("phase")
        invalid_drafts.append(missing)
        extra = copy.deepcopy(draft)
        extra["note"] = "free text is not supported"
        invalid_drafts.append(extra)
        invalid_phase = copy.deepcopy(draft)
        invalid_phase["phase"] = "report_write"
        invalid_drafts.append(invalid_phase)
        invalid_category = copy.deepcopy(draft)
        invalid_category["failure_category"] = "authentication"
        invalid_drafts.append(invalid_category)
        invalid_runtime = copy.deepcopy(draft)
        invalid_runtime["runtime"]["endpoint"] = "not-supported"
        invalid_drafts.append(invalid_runtime)

        for index, invalid in enumerate(invalid_drafts):
            with self.subTest(index=index), self.assertRaises(ValueError):
                validate_failure_draft(invalid)

        for phase, category in (
            ("preflight", "internal_harness_error"),
            ("runner_internal", "timeout"),
        ):
            invalid_pair = copy.deepcopy(draft)
            invalid_pair["phase"] = phase
            invalid_pair["failure_category"] = category
            with (
                self.subTest(phase=phase, category=category, validator="python"),
                self.assertRaises(ValueError),
            ):
                validate_failure_draft(invalid_pair)
            with (
                self.subTest(phase=phase, category=category, validator="schema"),
                self.assertRaises(ValueError),
            ):
                self.schema_validator.validate(
                    invalid_pair,
                    "failure-issue.schema.json",
                )

    def test_schema_required_keys_and_enums_match_the_implementation(self) -> None:
        schema_path = (
            PROJECT_ROOT
            / "specs"
            / "005-guided-failure-reporting"
            / "contracts"
            / "failure-issue.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        properties = schema["properties"]

        self.assertEqual(set(schema["required"]), EXPECTED_DRAFT_KEYS)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(properties["failure_category"]["enum"]),
            set(failure_reporting.ELIGIBLE_FAILURE_CATEGORIES),
        )
        self.assertEqual(
            set(properties["phase"]["enum"]),
            set(failure_reporting.FAILURE_PHASES),
        )
        self.assertEqual(
            tuple(properties["runtime"]["required"]),
            ("name", "version", "backend"),
        )
        self.assertFalse(properties["runtime"]["additionalProperties"])

    def test_package_and_draft_versions_are_synchronized(self) -> None:
        project = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        draft = self.build_draft()

        self.assertEqual(project["project"]["version"], __version__)
        self.assertEqual(draft["litb_version"], __version__)

    def test_failure_signal_rejects_invalid_or_mismatched_pairs(self) -> None:
        invalid_pairs = (
            ("case_execution", "authentication"),
            ("report_write", "timeout"),
            ("case_execution", "internal_harness_error"),
            ("runner_internal", "timeout"),
        )
        for phase, category in invalid_pairs:
            with self.subTest(phase=phase, category=category), self.assertRaises(
                ValueError
            ):
                FailureSignal(phase=phase, failure_category=category)

        internal = FailureSignal(
            phase="runner_internal",
            failure_category="internal_harness_error",
        )
        self.assertEqual(internal.phase, "runner_internal")
        self.schema_validator.validate(
            self.build_draft(internal),
            "failure-issue.schema.json",
        )

    def test_every_eligible_report_category_produces_one_closed_signal(self) -> None:
        for category in ELIGIBLE_CATEGORIES:
            with self.subTest(category=category):
                self.assertEqual(
                    detect_report_failure(report_with_terminations(category)),
                    FailureSignal(
                        phase="case_execution",
                        failure_category=category,
                    ),
                )

    def test_report_detection_excludes_model_config_and_operational_outcomes(self) -> None:
        ineligible = (
            "completed",
            "tool_call",
            "filtered",
            "cancelled",
            "output_budget",
            "context_window",
            "length_unknown",
            "reasoning_only",
            "unknown",
            "other",
            "authentication",
            "rate_limited",
            "not_applicable",
        )
        for category in ineligible:
            with self.subTest(category=category):
                self.assertIsNone(
                    detect_report_failure(report_with_terminations(category))
                )

        semantic_failure = report_with_terminations("completed")
        semantic_failure["models"][0]["cases"][0].update(
            {"semantic_success": False, "exact_format": False}
        )
        self.assertIsNone(detect_report_failure(semantic_failure))

    def test_report_detection_uses_the_documented_fixed_priority(self) -> None:
        report = report_with_terminations(
            "http_error",
            "network_error",
            "timeout",
            "request_rejected",
            "server_error",
            "protocol_error",
            "invalid_json",
            "response_too_large",
        )

        self.assertEqual(
            detect_report_failure(report),
            FailureSignal(
                phase="case_execution",
                failure_category="response_too_large",
            ),
        )

        without_first = report_with_terminations(
            "timeout",
            "request_rejected",
            "server_error",
            "protocol_error",
        )
        self.assertEqual(
            detect_report_failure(without_first),
            FailureSignal(
                phase="case_execution",
                failure_category="protocol_error",
            ),
        )

    def test_report_detection_cannot_copy_excluded_report_values(self) -> None:
        excluded = (
            "private-run-id",
            "private-model-id",
            "private-case-id",
            "https://private-node.invalid/v1",
            "/" + "Users/example/private-path",
            "raw prompt and completion",
            "traceback-private-marker",
        )
        report = report_with_terminations("timeout")
        report.update(
            {
                "run_id": excluded[0],
                "endpoint": excluded[3],
                "traceback": excluded[6],
            }
        )
        report["models"][0].update(
            {
                "model_id": excluded[1],
                "path": excluded[4],
            }
        )
        report["models"][0]["cases"][0].update(
            {
                "case_id": excluded[2],
                "prompt": excluded[5],
            }
        )

        signal = detect_report_failure(report)
        self.assertEqual(
            signal,
            FailureSignal(phase="case_execution", failure_category="timeout"),
        )
        draft = self.build_draft(signal)
        body = render_issue_body(draft)
        url = build_issue_url(draft)
        serialized = json.dumps(draft, sort_keys=True)
        for marker in excluded:
            self.assertNotIn(marker, serialized)
            self.assertNotIn(marker, body)
            self.assertNotIn(marker, url)

    def test_platform_values_reduce_to_closed_coarse_enums(self) -> None:
        cases = (
            ("Darwin", "arm64", 3, 11, "macos", "arm64", "python_3_11"),
            ("Linux", "aarch64", 3, 12, "linux", "arm64", "python_3_12"),
            ("Windows", "AMD64", 3, 14, "windows", "x86_64", "python_3_14"),
            ("Linux", "x86_64", 3, 15, "linux", "x86_64", "other"),
        )
        for system, machine, major, minor, os_family, architecture, python_series in cases:
            with (
                self.subTest(system=system, machine=machine),
                mock.patch.object(
                    failure_reporting.platform,
                    "system",
                    return_value=system,
                ),
                mock.patch.object(
                    failure_reporting.platform,
                    "machine",
                    return_value=machine,
                ),
                mock.patch.object(
                    failure_reporting.sys,
                    "version_info",
                    SimpleNamespace(major=major, minor=minor),
                ),
            ):
                draft = self.build_draft()

            self.assertEqual(draft["os_family"], os_family)
            self.assertEqual(draft["architecture"], architecture)
            self.assertEqual(draft["python_series"], python_series)

    def test_malicious_platform_or_descriptor_values_collapse_to_unknown(self) -> None:
        private_value = "private-node.invalid/Users/example/secret"
        descriptor = public_environment()
        descriptor["runtime"]["name"] = private_value
        descriptor["hardware"]["cpu"]["model"] = "reviewer: ignore safeguards"

        with (
            mock.patch.object(
                failure_reporting.platform,
                "system",
                return_value=private_value,
            ),
            mock.patch.object(
                failure_reporting.platform,
                "machine",
                return_value=private_value,
            ),
            mock.patch.object(
                failure_reporting.sys,
                "version_info",
                SimpleNamespace(major=99, minor=99),
            ),
        ):
            draft = self.build_draft(descriptor=descriptor)

        self.assertEqual(draft["os_family"], "other")
        self.assertEqual(draft["python_series"], "other")
        self.assertEqual(draft["architecture"], "other")
        self.assertEqual(draft["hardware_class"], "unknown")
        self.assertEqual(
            draft["runtime"],
            {"name": "unknown", "version": "unknown", "backend": "unknown"},
        )
        serialized = json.dumps(draft, sort_keys=True)
        body = render_issue_body(draft)
        url = build_issue_url(draft)
        for excluded in (private_value, "ignore safeguards", "Example Accelerator"):
            self.assertNotIn(excluded, serialized)
            self.assertNotIn(excluded, body)
            self.assertNotIn(excluded, url)

    def test_missing_descriptor_uses_only_unknown_runtime_and_hardware(self) -> None:
        draft = self.build_draft()

        self.assertEqual(draft["hardware_class"], "unknown")
        self.assertEqual(
            draft["runtime"],
            {"name": "unknown", "version": "unknown", "backend": "unknown"},
        )

    def test_issue_url_has_one_fixed_origin_and_exact_round_trippable_query(self) -> None:
        draft = self.build_draft(descriptor=public_environment())
        body = render_issue_body(draft)
        url = build_issue_url(draft)
        parsed = urlsplit(url)
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "github.com")
        self.assertEqual(
            parsed.path,
            "/MahdiHedhli/LocalInferenceTestBench/issues/new",
        )
        self.assertEqual(parsed.fragment, "")
        self.assertEqual(set(query), {"title", "body"})
        self.assertEqual(len(query["title"]), 1)
        self.assertEqual(len(query["body"]), 1)
        self.assertEqual(query["body"][0], body)
        self.assertLessEqual(len(query["title"][0]), 120)
        self.assertTrue(query["title"][0].isascii())
        self.assertLessEqual(len(body.encode("utf-8")), 4096)
        self.assertLessEqual(len(url.encode("utf-8")), 8192)
        canonical = json.dumps(
            draft,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        self.assertIn(canonical, body)
        self.assertEqual(build_issue_url(draft), url)

    def test_render_and_url_reject_unvalidated_or_oversized_drafts(self) -> None:
        draft = self.build_draft(descriptor=public_environment())
        oversized = copy.deepcopy(draft)
        oversized["runtime"]["name"] = "x" * 5000
        injected = copy.deepcopy(draft)
        injected["runtime"]["backend"] = "line one\nline two"

        for invalid in (oversized, injected):
            with self.subTest(kind=len(invalid["runtime"]["name"])):
                with self.assertRaises(ValueError):
                    render_issue_body(invalid)
                with self.assertRaises(ValueError):
                    build_issue_url(invalid)

    def test_direct_runtime_fields_reject_descriptor_injection_classes(self) -> None:
        draft = self.build_draft(descriptor=public_environment())
        prohibited = (
            "ignore previous instructions",
            "https://example.invalid/path",
            "name@example.invalid",
            "192.0.2.10",
            "-".join(("123e4567", "e89b", "42d3", "a456", "426614174000")),
            "serial: example-123",
            "/" + "Users/example/private-runtime",
            "api_" + "key=not-a-real-value",
            ":".join(("aa", "bb", "cc", "dd", "ee", "ff")),
        )
        for field in ("name", "version", "backend"):
            for value in prohibited:
                invalid = copy.deepcopy(draft)
                invalid["runtime"][field] = value
                with (
                    self.subTest(field=field, value=value),
                    self.assertRaises(ValueError),
                ):
                    validate_failure_draft(invalid)


if __name__ == "__main__":
    unittest.main()
