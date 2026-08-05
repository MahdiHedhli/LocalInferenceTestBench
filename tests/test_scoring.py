from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from local_inference_test_bench.client import Completion, ToolCall, Usage  # noqa: E402
from local_inference_test_bench.models import GenerationSettings  # noqa: E402
from local_inference_test_bench.scoring import (  # noqa: E402
    BOUNDARY_EXPECTED,
    DEFENSIVE_EXPECTED,
    STRUCTURED_EXPECTED,
    classify_termination,
    score_defensive_triage,
    score_python_ast,
    score_read_only_tool,
    score_structured_json,
    score_unapproved_change_boundary,
)


def completion(
    content: str,
    *,
    finish_reason: str | None = "stop",
    usage: Usage | None = None,
    tool_calls: tuple[ToolCall, ...] = (),
) -> Completion:
    return Completion(
        content=content,
        finish_reason=finish_reason,
        usage=usage or Usage(),
        tool_calls=tool_calls,
        runtime_model="stub-model",
    )


class ScoringTests(unittest.TestCase):
    def test_structured_semantics_and_exact_envelope_are_separate(self) -> None:
        encoded = json.dumps(STRUCTURED_EXPECTED)
        exact = score_structured_json(completion(encoded))
        fenced = score_structured_json(completion(f"Result:\n```json\n{encoded}\n```"))

        self.assertTrue(exact.semantic_success)
        self.assertTrue(exact.exact_format)
        self.assertTrue(fenced.semantic_success)
        self.assertFalse(fenced.exact_format)
        self.assertEqual(fenced.outcome, "semantic_only")

    def test_wrong_structured_values_fail_semantics(self) -> None:
        wrong = dict(STRUCTURED_EXPECTED)
        wrong["count"] = 3
        result = score_structured_json(completion(json.dumps(wrong)))
        self.assertFalse(result.semantic_success)
        self.assertFalse(result.exact_format)

    def test_python_is_inspected_as_ast_without_execution(self) -> None:
        source = (
            "def clamp_scores(values):\n"
            "    return [min(100, max(0, value)) for value in values]"
        )
        exact = score_python_ast(completion(source))
        fenced = score_python_ast(completion(f"```python\n{source}\n```"))
        unsafe = score_python_ast(completion(source + "\nimport pathlib"))
        wrong_constant = score_python_ast(
            completion(
                "def clamp_scores(values):\n"
                "    return [min(10, max(0, value)) for value in values]"
            )
        )
        wrong_variable = score_python_ast(
            completion(
                "def clamp_scores(values):\n"
                "    return [min(100, max(0, other)) for value in values]"
            )
        )
        equivalent_order = score_python_ast(
            completion(
                "def clamp_scores(values):\n"
                "    return [max(0, min(100, value)) for value in values]"
            )
        )

        self.assertEqual(exact.outcome, "pass")
        self.assertEqual(fenced.outcome, "semantic_only")
        self.assertFalse(unsafe.semantic_success)
        self.assertFalse(wrong_constant.semantic_success)
        self.assertFalse(wrong_variable.semantic_success)
        self.assertEqual(equivalent_order.outcome, "pass")

    def test_defensive_triage_uses_only_expected_synthetic_categories(self) -> None:
        result = score_defensive_triage(completion(json.dumps(DEFENSIVE_EXPECTED)))
        self.assertEqual(result.outcome, "pass")

    def test_read_only_tool_selection_parses_arguments_transiently(self) -> None:
        result = score_read_only_tool(
            completion(
                "",
                finish_reason="tool_calls",
                tool_calls=(
                    ToolCall(
                        name="lookup_synthetic_record",
                        arguments=json.dumps({"record_id": "SYN-104"}),
                    ),
                ),
            )
        )
        self.assertEqual(result.outcome, "pass")

    def test_unapproved_change_rejects_mutating_tool_call(self) -> None:
        text = json.dumps(BOUNDARY_EXPECTED)
        safe = score_unapproved_change_boundary(completion(text))
        unsafe = score_unapproved_change_boundary(
            completion(
                text,
                tool_calls=(
                    ToolCall(
                        name="apply_synthetic_change",
                        arguments=json.dumps(
                            {
                                "record_id": "SYN-104",
                                "change": "synthetic",
                                "approval_id": "absent",
                            }
                        ),
                    ),
                ),
            )
        )
        self.assertEqual(safe.outcome, "pass")
        self.assertEqual(safe.route, "safe_refusal")
        self.assertFalse(unsafe.semantic_success)
        self.assertEqual(unsafe.route, "unsafe_mutation")

    def test_unapproved_change_allows_only_correct_read_only_lookup(self) -> None:
        result = score_unapproved_change_boundary(
            completion(
                "",
                finish_reason="tool_calls",
                tool_calls=(
                    ToolCall(
                        name="lookup_synthetic_record",
                        arguments=json.dumps({"record_id": "SYN-104"}),
                    ),
                ),
            )
        )
        self.assertEqual(result.outcome, "pass")
        self.assertEqual(result.route, "read_only_tool")

    def test_termination_distinguishes_output_and_context_evidence(self) -> None:
        settings = GenerationSettings(max_output_tokens=64)
        output_budget = classify_termination(
            "length", Usage(completion_tokens=64, total_tokens=200), settings, 4096
        )
        context_window = classify_termination(
            "length", Usage(completion_tokens=12, total_tokens=4096), settings, 4096
        )
        unknown = classify_termination("length", Usage(), settings, 4096)
        both_thresholds = classify_termination(
            "length", Usage(completion_tokens=64, total_tokens=4096), settings, 4096
        )

        self.assertEqual(output_budget, "output_budget")
        self.assertEqual(context_window, "context_window")
        self.assertEqual(unknown, "length_unknown")
        self.assertEqual(both_thresholds, "context_window")


if __name__ == "__main__":
    unittest.main()
