from __future__ import annotations

from datetime import datetime, timezone
import json
import copy
import ipaddress
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import traceback
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from local_inference_test_bench.client import (  # noqa: E402
    ClientError,
    Completion,
    ToolCall,
    Usage,
)
from local_inference_test_bench.models import parse_manifest  # noqa: E402
from local_inference_test_bench import reporting as reporting_module  # noqa: E402
from local_inference_test_bench.reporting import (  # noqa: E402
    ReportError,
    validate_report,
    write_report,
)
from local_inference_test_bench.runner import BenchmarkRunner, RunnerError  # noqa: E402
from local_inference_test_bench.scoring import (  # noqa: E402
    BOUNDARY_EXPECTED,
    DEFENSIVE_EXPECTED,
    STRUCTURED_EXPECTED,
)


def manifest(*, parameter_scale: dict | None = None):
    model = {
        "id": "stub-public-id",
        "display_name": "Stub Model",
        "source": "publisher/stub-model",
        "digest": "sha256:public-digest-placeholder",
        "precision": "runtime-declared",
        "declared_context_tokens": 4096,
        "runtime_model": "runtime-selector-under-test",
        "settings": {
            "temperature": 0,
            "top_p": 1,
            "max_output_tokens": 128,
            "seed": 0,
        },
    }
    if parameter_scale is not None:
        model["parameter_scale"] = parameter_scale
    return parse_manifest(
        {
            "schema_version": "1.0",
            "suite_version": "1.0",
            "models": [model],
        }
    )


def passing_completions(
    runtime_model: str = "runtime-selector-under-test",
) -> list[Completion]:
    usage = Usage(prompt_tokens=20, completion_tokens=10, total_tokens=30)
    return [
        Completion(
            json.dumps(STRUCTURED_EXPECTED),
            "stop",
            usage,
            runtime_model=runtime_model,
        ),
        Completion(
            "def clamp_scores(values):\n"
            "    return [min(100, max(0, value)) for value in values]",
            "stop",
            usage,
            runtime_model=runtime_model,
        ),
        Completion(
            json.dumps(DEFENSIVE_EXPECTED),
            "stop",
            usage,
            runtime_model=runtime_model,
        ),
        Completion(
            "",
            "tool_calls",
            usage,
            tool_calls=(
                ToolCall("lookup_synthetic_record", json.dumps({"record_id": "SYN-104"})),
            ),
            runtime_model=runtime_model,
        ),
        Completion(
            json.dumps(BOUNDARY_EXPECTED),
            "stop",
            usage,
            runtime_model=runtime_model,
        ),
    ]


class StubClient:
    def __init__(self, completions, *, advertised=("runtime-selector-under-test",)) -> None:
        self.completions = list(completions)
        self.advertised = advertised
        self.requests = []

    def list_models(self):
        return self.advertised

    def chat_completions(self, **request):
        self.requests.append(request)
        response = self.completions.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class StepClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        current = self.value
        self.value += 0.01
        return current


class RunnerTests(unittest.TestCase):
    def test_preflight_client_error_retains_only_structured_diagnostic(self) -> None:
        private_marker = "private-transport-detail"

        class FailedPreflightClient(StubClient):
            def list_models(self):
                raise ClientError("timeout", private_marker)

        runner = BenchmarkRunner(
            FailedPreflightClient([]),
            manifest(),
            profile="smoke",
        )

        with self.assertRaises(RunnerError) as raised:
            runner.preflight()

        self.assertEqual(raised.exception.diagnostic_category, "timeout")
        self.assertEqual(raised.exception.diagnostic_phase, "preflight")
        self.assertNotIn(private_marker, str(raised.exception))
        self.assertNotIn(
            private_marker,
            "".join(traceback.format_exception(raised.exception)),
        )

    def test_preflight_unknown_client_category_is_normalized_and_ineligible(self) -> None:
        private_category = "private-category-from-adapter"

        class FailedPreflightClient(StubClient):
            def list_models(self):
                raise ClientError(private_category, "private transport detail")

        runner = BenchmarkRunner(
            FailedPreflightClient([]),
            manifest(),
            profile="smoke",
        )

        with self.assertRaises(RunnerError) as raised:
            runner.preflight()

        self.assertEqual(raised.exception.diagnostic_category, "other")
        self.assertEqual(raised.exception.diagnostic_phase, "preflight")
        self.assertNotIn(private_category, str(raised.exception))

    def test_runtime_identifier_collection_never_resolves_fqdn(self) -> None:
        reporting_module._runtime_identifiers.cache_clear()
        self.addCleanup(reporting_module._runtime_identifiers.cache_clear)
        with (
            mock.patch.object(
                reporting_module.socket,
                "gethostname",
                return_value="host-label.example",
            ),
            mock.patch.object(
                reporting_module.socket,
                "getfqdn",
                side_effect=AssertionError("resolver-backed lookup must not run"),
            ),
        ):
            identifiers = set(reporting_module._runtime_identifiers())

        self.assertTrue({"host-label", "host-label.example"}.issubset(identifiers))

    def test_baseline_imports_and_executes_without_site_or_optional_packages(self) -> None:
        script = textwrap.dedent(
            """
            import json
            import sys

            sys.path.insert(0, sys.argv[1])
            from local_inference_test_bench.client import Completion, Usage
            from local_inference_test_bench.models import parse_manifest
            from local_inference_test_bench.reporting import validate_report
            from local_inference_test_bench.runner import BenchmarkRunner

            configured = parse_manifest({
                "schema_version": "1.0",
                "suite_version": "1.0",
                "models": [{
                    "id": "isolated-model",
                    "display_name": "Isolated Model",
                    "source": "publisher/isolated-model",
                    "revision": "public-revision",
                    "precision": "runtime-declared",
                    "declared_context_tokens": 4096,
                    "runtime_model": "isolated-selector",
                    "settings": {
                        "temperature": 0,
                        "top_p": 1,
                        "max_output_tokens": 128,
                        "seed": 0
                    }
                }]
            })
            usage = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
            responses = [
                Completion(
                    json.dumps({
                        "suite": "synthetic",
                        "items": [
                            {"id": "alpha", "accepted": True},
                            {"id": "beta", "accepted": False}
                        ],
                        "count": 2
                    }),
                    "stop",
                    usage,
                    runtime_model="isolated-selector"
                ),
                Completion(
                    "def clamp_scores(values):\\n"
                    "    return [min(100, max(0, value)) for value in values]",
                    "stop",
                    usage,
                    runtime_model="isolated-selector"
                ),
                Completion(
                    json.dumps({
                        "classification": "credential_access_suspected",
                        "severity": "medium",
                        "containment": "review_and_isolate_synthetic_account"
                    }),
                    "stop",
                    usage,
                    runtime_model="isolated-selector"
                )
            ]

            class IsolatedClient:
                def list_models(self):
                    return ("isolated-selector",)

                def chat_completions(self, **request):
                    return responses.pop(0)

            report = BenchmarkRunner(IsolatedClient(), configured, profile="smoke").run()
            validate_report(report)
            assert report["validity"] == "valid"
            assert report["models"][0]["summary"]["semantic_pass_count"] == 3
            """
        )
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory() as temporary:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    "-c",
                    script,
                    str(Path(__file__).resolve().parents[1] / "src"),
                ],
                cwd=temporary,
                env=environment,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_same_display_name_preserves_distinct_revision_and_digest(self) -> None:
        data = {
            "schema_version": "1.0",
            "suite_version": "1.0",
            "models": [
                {
                    "id": "shared-name-revision",
                    "display_name": "Shared Display Name",
                    "source": "publisher/example-model",
                    "revision": "revision-one",
                    "precision": "runtime-declared",
                    "declared_context_tokens": 4096,
                    "runtime_model": "runtime-selector-one",
                    "settings": {
                        "temperature": 0,
                        "top_p": 1,
                        "max_output_tokens": 128,
                        "seed": 0,
                    },
                },
                {
                    "id": "shared-name-digest",
                    "display_name": "Shared Display Name",
                    "source": "publisher/example-model",
                    "digest": "sha256:public-digest-two",
                    "precision": "runtime-declared",
                    "declared_context_tokens": 4096,
                    "runtime_model": "runtime-selector-two",
                    "settings": {
                        "temperature": 0,
                        "top_p": 1,
                        "max_output_tokens": 128,
                        "seed": 0,
                    },
                },
            ],
        }
        completions = passing_completions("runtime-selector-one")[:3]
        completions.extend(passing_completions("runtime-selector-two")[:3])
        client = StubClient(
            completions,
            advertised=("runtime-selector-one", "runtime-selector-two"),
        )

        report = BenchmarkRunner(client, parse_manifest(data), profile="smoke").run()

        self.assertEqual(report["validity"], "valid")
        self.assertEqual(
            [model["provenance"]["display_name"] for model in report["models"]],
            ["Shared Display Name", "Shared Display Name"],
        )
        self.assertEqual(report["models"][0]["provenance"]["revision"], "revision-one")
        self.assertEqual(
            report["models"][1]["provenance"]["digest"],
            "sha256:public-digest-two",
        )

    def test_parameter_scale_flows_to_run_provenance_and_is_revalidated(self) -> None:
        report = BenchmarkRunner(
            StubClient(passing_completions()[:3]),
            manifest(
                parameter_scale={
                    "total_billions": 30.0,
                    "active_billions": 3.0,
                }
            ),
            profile="smoke",
        ).run()

        validate_report(report)
        self.assertEqual(
            report["models"][0]["provenance"]["parameter_scale"],
            {"total_billions": 30.0, "active_billions": 3.0},
        )

        invalid_scales = (
            {"total_billions": 30.0, "active_billions": 31.0},
            {"total_billions": None, "active_billions": 3.0},
            {"total_billions": 30.0001, "active_billions": 3.0},
            {"total_billions": 30.0, "active_billions": 3.0, "extra": None},
            {"total_billions": 10**10_000, "active_billions": None},
        )
        for index, scale in enumerate(invalid_scales):
            invalid = copy.deepcopy(report)
            invalid["models"][0]["provenance"]["parameter_scale"] = scale
            with self.subTest(index=index), self.assertRaises(ReportError):
                validate_report(invalid)

    def test_runtime_identity_mismatch_is_invalid_without_raw_identity(self) -> None:
        completions = passing_completions()[:3]
        completions[1] = Completion(
            completions[1].content,
            completions[1].finish_reason,
            completions[1].usage,
            runtime_model="unexpected-runtime-identity",
        )

        report = BenchmarkRunner(StubClient(completions), manifest(), profile="smoke").run()
        serialized = json.dumps(report)

        self.assertEqual(report["validity"], "invalid")
        self.assertFalse(report["models"][0]["runtime_identity_match"])
        self.assertNotIn("unexpected-runtime-identity", serialized)

    def test_standard_profile_is_sequential_and_report_is_aggregate_only(self) -> None:
        client = StubClient(passing_completions())
        runner = BenchmarkRunner(
            client,
            manifest(),
            profile="standard",
            clock=StepClock(),
            now=lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        )

        report = runner.run()
        serialized = json.dumps(report, sort_keys=True)

        validate_report(report)
        self.assertEqual(report["validity"], "valid")
        self.assertFalse(report["deployment_authorization"])
        model_report = report["models"][0]
        self.assertTrue(model_report["runtime_identity_match"])
        self.assertEqual(model_report["summary"]["case_count"], 5)
        self.assertEqual(model_report["summary"]["semantic_pass_count"], 5)
        self.assertEqual(model_report["summary"]["exact_format_pass_count"], 5)
        self.assertEqual(
            model_report["summary"]["completion_tokens_per_second_weighted"], 1000.0
        )
        self.assertEqual(model_report["cases"][0]["completion_tokens_per_second"], 1000.0)
        self.assertEqual(model_report["cases"][4]["route"], "safe_refusal")
        self.assertEqual(len(client.requests), 5)
        self.assertIsNone(client.requests[0]["tools"])
        self.assertEqual(client.requests[3]["tools"][0]["function"]["name"], "lookup_synthetic_record")

        # Raw prompts, responses, generated code, tool arguments, and runtime selectors stay transient.
        self.assertNotIn("clamp_scores", serialized)
        self.assertNotIn("synthetic-output", serialized)
        self.assertNotIn("record_id", serialized)
        self.assertNotIn("runtime_model", serialized)
        self.assertNotIn("runtime-selector-under-test", serialized)
        self.assertNotIn("response_sha256", serialized)
        self.assertNotIn("runtime_identity_sha256", serialized)

    def test_preallocated_run_identity_is_preserved_for_sampler_binding(self) -> None:
        identity = (
            "-".join(("11111111", "2222", "4333", "8444", "555555555555")),
            "2026-08-06T12:00:00Z",
        )
        report = BenchmarkRunner(
            StubClient(passing_completions()[:3]),
            manifest(),
            profile="smoke",
            clock=StepClock(),
        ).run(run_identity=identity)

        validate_report(report)
        self.assertEqual((report["run_id"], report["created_at"]), identity)

    def test_malformed_preallocated_identity_fails_before_preflight(self) -> None:
        runner = BenchmarkRunner(
            StubClient(passing_completions()[:3]),
            manifest(),
            profile="smoke",
        )
        invalid_identities = (
            ("not-a-uuid", "2026-08-06T12:00:00Z"),
            (
                "-".join(("11111111", "2222", "3333", "8444", "555555555555")),
                "2026-08-06T12:00:00Z",
            ),
            (
                "-".join(("11111111", "2222", "4333", "8444", "555555555555")),
                "2026-08-06T08:00:00-04:00",
            ),
            (
                "-".join(("AAAAAAAA", "BBBB", "4CCC", "8DDD", "EEEEEEEEEEEE")),
                "2026-08-06T12:00:00Z",
            ),
            (
                "-".join(("11111111", "2222", "4333", "8444", "555555555555")),
                "2026-08-06T12:00:00.500000Z",
            ),
        )
        with mock.patch.object(runner, "preflight") as preflight:
            for identity in invalid_identities:
                with self.subTest(identity=identity), self.assertRaisesRegex(
                    RunnerError, "preallocated run identity"
                ):
                    runner.run(run_identity=identity)

        preflight.assert_not_called()

    def test_not_applicable_route_and_termination_are_reserved_for_that_outcome(self) -> None:
        report = BenchmarkRunner(
            StubClient(passing_completions()),
            manifest(),
            profile="standard",
            clock=StepClock(),
        ).run()

        for field in ("route", "termination"):
            invalid = copy.deepcopy(report)
            invalid["models"][0]["cases"][0][field] = "not_applicable"
            with self.subTest(field=field), self.assertRaisesRegex(
                ReportError,
                "must agree",
            ):
                validate_report(invalid)

    def test_reasoning_only_is_categorical_and_text_is_never_retained(self) -> None:
        completions = passing_completions()[:3]
        completions[0] = Completion(
            "",
            "stop",
            Usage(prompt_tokens=20, completion_tokens=8, total_tokens=28),
            runtime_model="runtime-selector-under-test",
            reasoning_present=True,
        )
        report = BenchmarkRunner(
            StubClient(completions), manifest(), profile="smoke", clock=StepClock()
        ).run()
        serialized = json.dumps(report)

        first = report["models"][0]["cases"][0]
        self.assertEqual(first["termination"], "reasoning_only")
        self.assertTrue(first["reasoning_present"])
        self.assertNotIn("reasoning_content", serialized)

    def test_nested_report_contract_is_closed(self) -> None:
        report = BenchmarkRunner(
            StubClient(passing_completions()[:3]), manifest(), profile="smoke", clock=StepClock()
        ).run()
        with_unknown = copy.deepcopy(report)
        with_unknown["models"][0]["cases"][0]["unexpected"] = True
        with_raw_content = copy.deepcopy(report)
        with_raw_content["models"][0]["cases"][0]["content"] = "must-not-persist"
        wrong_category = copy.deepcopy(report)
        wrong_category["models"][0]["cases"][0]["route"] = "arbitrary"

        for invalid in (with_unknown, with_raw_content, wrong_category):
            with self.subTest(keys=invalid["models"][0]["cases"][0].keys()):
                with self.assertRaises(ReportError):
                    validate_report(invalid)

    def test_report_limits_and_output_budget_match_manifest_contract(self) -> None:
        report = BenchmarkRunner(
            StubClient(passing_completions()[:3]), manifest(), profile="smoke", clock=StepClock()
        ).run()
        too_long_source = copy.deepcopy(report)
        too_long_source["models"][0]["provenance"]["source"] = "s" * 501
        too_long_revision = copy.deepcopy(report)
        too_long_revision["models"][0]["provenance"]["digest"] = "d" * 201
        invalid_context = copy.deepcopy(report)
        invalid_context["models"][0]["provenance"]["declared_context_tokens"] = 0
        budget_exceeds_context = copy.deepcopy(report)
        budget_exceeds_context["models"][0]["provenance"]["declared_context_tokens"] = 64

        for invalid in (
            too_long_source,
            too_long_revision,
            invalid_context,
            budget_exceeds_context,
        ):
            with self.assertRaises(ReportError):
                validate_report(invalid)

    def test_case_throughput_must_be_arithmetically_consistent(self) -> None:
        report = BenchmarkRunner(
            StubClient(passing_completions()[:3]), manifest(), profile="smoke", clock=StepClock()
        ).run()
        report["models"][0]["cases"][0]["completion_tokens_per_second"] += 1

        with self.assertRaisesRegex(ReportError, "throughput"):
            validate_report(report)

    def test_provenance_rejects_private_identifier_classes(self) -> None:
        report = BenchmarkRunner(
            StubClient(passing_completions()[:3]), manifest(), profile="smoke", clock=StepClock()
        ).run()

        def ipv4(first: int, second: int, third: int, fourth: int) -> str:
            return str(
                ipaddress.IPv4Address(
                    (first << 24) | (second << 16) | (third << 8) | fourth
                )
            )

        private_identifiers = (
            ipv4(0, 0, 0, 0),
            ipv4(127, 0, 0, 1),
            ipv4(10, 2, 3, 4),
            ipv4(100, 64, 8, 9),
            ipv4(169, 254, 8, 9),
            str(ipaddress.IPv6Address((0xFD << 120) | 5)),
            str(ipaddress.IPv6Address((0xFE80 << 112) | 5)),
            str(ipaddress.IPv6Address(0)),
            str(ipaddress.IPv6Address(1)),
            ":".join(("aa", "bb", "cc", "dd", "ee", "ff")),
            "inference-node" + ".internal",
            "local" + "host",
            "/" + "Users/example/private-model",
            "/" + "root/private-model",
            "poly" + "range",
            "api_" + "key=not-a-real-value",
        )
        for index, identifier in enumerate(private_identifiers):
            invalid = copy.deepcopy(report)
            invalid["models"][0]["provenance"]["source"] = identifier
            with self.subTest(index=index):
                with self.assertRaises(ReportError):
                    validate_report(invalid)

    def test_runtime_and_denylist_literals_reject_punctuation_boundaries(self) -> None:
        report = BenchmarkRunner(
            StubClient(passing_completions()[:3]), manifest(), profile="smoke", clock=StepClock()
        ).run()
        sensitive = "private" + "-node"

        for value in (sensitive + ".", "x." + sensitive, sensitive + "_suffix"):
            invalid = copy.deepcopy(report)
            invalid["models"][0]["provenance"]["source"] = value
            with (
                self.subTest(value=value),
                mock.patch.object(
                    reporting_module,
                    "_runtime_identifiers",
                    return_value=(sensitive,),
                ),
                mock.patch.object(
                    reporting_module,
                    "_local_denylist_terms",
                    return_value=(sensitive,),
                ),
                self.assertRaises(ReportError),
            ):
                validate_report(invalid)

    def test_public_manifest_hash_not_raw_manifest_hash_is_reported(self) -> None:
        configured = manifest()
        report = BenchmarkRunner(
            StubClient(passing_completions()[:3]), configured, profile="smoke"
        ).run()

        self.assertEqual(report["public_manifest_sha256"], configured.public_sha256)
        self.assertNotIn("manifest_sha256", report)

    def test_missing_runtime_metadata_produces_limited_not_promotion_ready(self) -> None:
        without_runtime_identity = [
            Completion(item.content, item.finish_reason, item.usage, item.tool_calls)
            for item in passing_completions()[:3]
        ]
        report = BenchmarkRunner(
            StubClient(without_runtime_identity, advertised=()), manifest(), profile="smoke"
        ).run()

        self.assertEqual(report["validity"], "limited")
        self.assertFalse(report["models"][0]["runtime_identity_match"])
        self.assertFalse(report["deployment_authorization"])

    def test_transport_disturbance_is_categorical_and_invalid(self) -> None:
        completions = passing_completions()[:3]
        completions[1] = ClientError("timeout", "must-not-be-persisted")
        report = BenchmarkRunner(StubClient(completions), manifest(), profile="smoke").run()
        serialized = json.dumps(report)

        self.assertEqual(report["validity"], "invalid")
        self.assertEqual(report["models"][0]["cases"][1]["termination"], "timeout")
        self.assertEqual(report["models"][0]["cases"][1]["outcome"], "not_scored")
        self.assertNotIn("must-not-be-persisted", serialized)

    def test_report_write_is_append_only_and_owner_only(self) -> None:
        report = BenchmarkRunner(
            StubClient(passing_completions()[:3]),
            manifest(),
            profile="smoke",
            now=lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        ).run()
        with tempfile.TemporaryDirectory() as temporary:
            path = write_report(report, Path(temporary) / "artifacts")
            persisted = json.loads(path.read_text(encoding="utf-8"))
            mode = path.stat().st_mode & 0o777

        self.assertEqual(persisted, report)
        if os.name != "nt":
            self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
