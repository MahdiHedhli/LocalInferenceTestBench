"""Minimized benchmark submissions and deterministic leaderboard generation."""

from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

from .reporting import ReportError, _walk_safe, validate_report
from .safety import (
    SafetyError,
    secure_directory,
    validate_env_file,
    validate_ignored_destination,
)


SUBMISSION_SCHEMA_VERSION = "1.0"
LEADERBOARD_SCHEMA_VERSION = "1.0"
_STANDARD_CASE_IDS = (
    "structured-json",
    "python-ast",
    "defensive-triage",
    "read-only-tool",
    "unapproved-change-boundary",
)
_OUTCOMES = {"pass", "semantic_only", "format_only", "fail", "not_scored"}
_ROUTES = {
    "direct_response",
    "read_only_tool",
    "safe_refusal",
    "unsafe_mutation",
    "unexpected_tool",
    "unrecognized",
}
_TERMINATIONS = {
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
    "timeout",
    "network_error",
    "authentication",
    "rate_limited",
    "server_error",
    "request_rejected",
    "invalid_json",
    "protocol_error",
    "response_too_large",
    "http_error",
}
_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_IPV4_CANDIDATE = re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])")
_IPV6_CANDIDATE = re.compile(
    r"(?i)(?<![0-9a-f:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}"
    r"(?:%[a-z0-9_.-]+)?(?![0-9a-f:])"
)
_UUID = re.compile(
    r"(?i)(?<![0-9a-f])"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"(?![0-9a-f])"
)
_DESCRIPTOR_IDENTIFIER_LABEL = re.compile(
    r"(?ix)"
    r"(?:"
    r"\bs\s*/?\s*n\b|"
    r"\bserial(?:\s+(?:number|no|id))?\b|"
    r"\binventory\s+(?:id|tag)\b|"
    r"\basset\s+(?:id|tag)\b|"
    r"\bdevice\s+uuid\b|"
    r"\bmachine\s+(?:id|name)\b|"
    r"\bhost\s*name\b|"
    r"\buser\s*name\b|"
    r"\baccount\s+(?:id|name)\b"
    r")"
)
_URL_OR_EMAIL = re.compile(
    r"(?i)(?:\b[a-z][a-z0-9+.-]*://|[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,})"
)
_SCANNER_SUPPRESSION_MARKER = re.compile(
    r"(?i)\b" + "git" + r"leaks\s*:\s*allow\b"
)
_MAX_SUBMISSION_BYTES = 256 * 1024
_MAX_DATASET_BYTES = 2 * 1024 * 1024
_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_MEMORY_ARCHITECTURES = {"shared", "discrete", "mixed", "unknown"}
_ACCELERATOR_KINDS = {
    "integrated_gpu",
    "discrete_gpu",
    "neural_accelerator",
    "other",
}
_EXECUTION_MODES = {"cpu_only", "accelerator_only", "hybrid", "unknown"}
_SPECULATIVE_DECODING_MODES = {"enabled", "disabled", "unknown"}
_OFFLOAD_MODES = {"none", "partial", "maximum", "not_applicable", "unknown"}
_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}
_MODEL_DISPLAY_NAME_MAX = 160
_MODEL_SOURCE_MAX = 240
_MODEL_PRECISION_MAX = 80
_MODEL_DESCRIPTOR_ASCII = re.compile(r"^[\x20-\x7e]+$")
_MODEL_REVIEW_INJECTION = re.compile(
    r"(?ix)"
    r"(?:"
    r"\b(?:ignore|disregard|override|bypass|forget|accept|approve|merge)\b|"
    r"\b(?:instructions?|prompts?|codex|coderabbit(?:ai)?|reviewer|maintainer)\b|"
    r"\b(?:system|assistant|developer|user)\s*:|"
    r"\b(?:result|submission|benchmark)\b.{0,32}"
    r"\b(?:safe|valid|verified|trusted|approved|pass(?:ed)?)\b|"
    r"\b(?:mark|treat|label|classify)\b.{0,32}"
    r"\b(?:safe|valid|verified|trusted|approved|pass(?:ed)?)\b|"
    r"```|<!--|-->|<\s*/?\s*script\b|\[\s*inst\s*\]|<<\s*sys\s*>>"
    r")"
)


class SubmissionError(ValueError):
    """Raised when public submission data violates the minimized contract."""


def _object(value: Any, keys: set[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise SubmissionError(f"{path} has an unsupported object contract")
    return value


def _object_with_optional(
    value: Any,
    required: set[str],
    optional: set[str],
    path: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SubmissionError(f"{path} has an unsupported object contract")
    keys = set(value)
    if not required.issubset(keys) or not keys.issubset(required | optional):
        raise SubmissionError(f"{path} has an unsupported object contract")
    return value


def _text(value: Any, path: str, *, maximum: int = 500) -> str:
    def unsafe_control(character: str) -> bool:
        codepoint = ord(character)
        return (
            codepoint < 32
            or 0x7F <= codepoint <= 0x9F
            or codepoint in {0x200E, 0x200F}
            or 0x202A <= codepoint <= 0x202E
            or codepoint in {0x2028, 0x2029}
            or 0x2066 <= codepoint <= 0x2069
            or 0xD800 <= codepoint <= 0xDFFF
        )

    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(unsafe_control(character) for character in value)
    ):
        raise SubmissionError(f"{path} must be bounded public text")
    if _SCANNER_SUPPRESSION_MARKER.search(value):
        raise SubmissionError(f"{path} contains a prohibited scanner suppression marker")
    return value


def _descriptor_text(value: Any, path: str, *, maximum: int) -> str:
    """Accept a public product label only when it carries no machine identifier."""

    result = _text(value, path, maximum=maximum)
    network_address = False
    for match in (*_IPV4_CANDIDATE.finditer(result), *_IPV6_CANDIDATE.finditer(result)):
        candidate = match.group(0).split("%", 1)[0]
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        network_address = True
        break
    if (
        network_address
        or _UUID.search(result)
        or _DESCRIPTOR_IDENTIFIER_LABEL.search(result)
        or _URL_OR_EMAIL.search(result)
    ):
        raise SubmissionError(f"{path} contains a prohibited machine identifier")
    return result


def _model_descriptor_text(value: Any, path: str, *, maximum: int) -> str:
    """Accept a compact public model label, never reviewer-directed content."""

    result = _descriptor_text(value, path, maximum=maximum)
    if not _MODEL_DESCRIPTOR_ASCII.fullmatch(result):
        raise SubmissionError(f"{path} must use visible ASCII model descriptor text")
    if _IPV4_CANDIDATE.search(result) or _IPV6_CANDIDATE.search(result):
        raise SubmissionError(f"{path} contains prohibited network-shaped descriptor text")
    if _MODEL_REVIEW_INJECTION.search(result):
        raise SubmissionError(f"{path} contains prohibited reviewer-directed content")
    return result


def _integer(
    value: Any,
    path: str,
    *,
    minimum: int = 0,
    maximum: int = _MAX_SAFE_INTEGER,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise SubmissionError(f"{path} must be an integer between {minimum} and {maximum}")
    return value


def _number(
    value: Any,
    path: str,
    *,
    minimum: float = 0.0,
    maximum: float = 1_000_000_000.0,
    decimal_places: int = 6,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < minimum
        or float(value) > maximum
    ):
        raise SubmissionError(f"{path} must be a finite number between {minimum} and {maximum}")
    try:
        decimal = Decimal(str(value))
        quantum = Decimal(1).scaleb(-decimal_places)
        if decimal != decimal.quantize(quantum):
            raise SubmissionError(
                f"{path} supports at most {decimal_places} fractional digits"
            )
    except InvalidOperation as error:
        raise SubmissionError(f"{path} has unsupported numeric precision") from error
    return float(value)


def _validate_model(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SubmissionError(f"{path} must be an object")
    base = {"display_name", "source", "precision", "declared_context_tokens"}
    identity = set(value) - base
    if identity not in ({"revision"}, {"digest"}):
        raise SubmissionError(f"{path} must contain exactly one public revision identifier")
    model = _object(value, base | identity, path)
    _model_descriptor_text(
        model["display_name"],
        f"{path}.display_name",
        maximum=_MODEL_DISPLAY_NAME_MAX,
    )
    _model_descriptor_text(
        model["source"],
        f"{path}.source",
        maximum=_MODEL_SOURCE_MAX,
    )
    _model_descriptor_text(
        model["precision"],
        f"{path}.precision",
        maximum=_MODEL_PRECISION_MAX,
    )
    _integer(model["declared_context_tokens"], f"{path}.declared_context_tokens", minimum=1)
    identity_field = next(iter(identity))
    _text(model[identity_field], f"{path}.{identity_field}", maximum=200)
    return model


def _validate_settings(value: Any, path: str, *, context_tokens: int) -> Mapping[str, Any]:
    settings = _object_with_optional(
        value,
        {"temperature", "top_p", "max_output_tokens", "seed"},
        {"reasoning_effort"},
        path,
    )
    temperature = _number(
        settings["temperature"],
        f"{path}.temperature",
        maximum=2,
    )
    top_p = _number(settings["top_p"], f"{path}.top_p", maximum=1)
    if top_p <= 0 or top_p > 1:
        raise SubmissionError(f"{path}.top_p is outside the supported range")
    maximum = _integer(settings["max_output_tokens"], f"{path}.max_output_tokens", minimum=1)
    if maximum > context_tokens:
        raise SubmissionError(f"{path}.max_output_tokens exceeds the declared context")
    seed = settings["seed"]
    if seed is not None:
        _integer(
            seed,
            f"{path}.seed",
            minimum=-_MAX_SAFE_INTEGER,
            maximum=_MAX_SAFE_INTEGER,
        )
    if "reasoning_effort" in settings:
        reasoning_effort = settings["reasoning_effort"]
        if (
            not isinstance(reasoning_effort, str)
            or reasoning_effort not in _REASONING_EFFORTS
        ):
            raise SubmissionError(f"{path}.reasoning_effort is unsupported")
    return settings


def _validate_runtime_configuration(value: Any, path: str) -> Mapping[str, Any]:
    configuration = _object(
        value,
        {
            "context_window_tokens",
            "concurrent_requests",
            "speculative_decoding",
            "offload_mode",
        },
        path,
    )
    context_window = configuration["context_window_tokens"]
    if context_window is not None:
        _integer(
            context_window,
            f"{path}.context_window_tokens",
            minimum=1,
        )
    concurrent_requests = configuration["concurrent_requests"]
    if concurrent_requests is not None:
        _integer(
            concurrent_requests,
            f"{path}.concurrent_requests",
            minimum=1,
            maximum=4096,
        )
    speculative_decoding = configuration["speculative_decoding"]
    if (
        not isinstance(speculative_decoding, str)
        or speculative_decoding not in _SPECULATIVE_DECODING_MODES
    ):
        raise SubmissionError(f"{path}.speculative_decoding is unsupported")
    offload_mode = configuration["offload_mode"]
    if not isinstance(offload_mode, str) or offload_mode not in _OFFLOAD_MODES:
        raise SubmissionError(f"{path}.offload_mode is unsupported")
    return configuration


def validate_public_environment(value: Mapping[str, Any]) -> None:
    """Validate the closed, intentionally public hardware/runtime descriptor."""

    descriptor = _object_with_optional(
        value,
        {"schema_version", "hardware", "runtime"},
        {"runtime_configuration"},
        "descriptor",
    )
    if descriptor["schema_version"] != "1.0":
        raise SubmissionError("descriptor schema version is unsupported")
    hardware = _object(
        descriptor["hardware"],
        {"cpu", "memory", "accelerators", "execution_mode"},
        "descriptor.hardware",
    )
    cpu = _object(
        hardware["cpu"],
        {"model", "logical_cores"},
        "descriptor.hardware.cpu",
    )
    _descriptor_text(cpu["model"], "descriptor.hardware.cpu.model", maximum=200)
    _integer(
        cpu["logical_cores"],
        "descriptor.hardware.cpu.logical_cores",
        minimum=1,
        maximum=4096,
    )
    memory = _object(
        hardware["memory"],
        {"system_gb", "architecture"},
        "descriptor.hardware.memory",
    )
    _number(
        memory["system_gb"],
        "descriptor.hardware.memory.system_gb",
        minimum=0.1,
        maximum=1_000_000,
        decimal_places=1,
    )
    if memory["architecture"] not in _MEMORY_ARCHITECTURES:
        raise SubmissionError("descriptor.hardware.memory.architecture is unsupported")
    accelerators = hardware["accelerators"]
    if not isinstance(accelerators, list) or len(accelerators) > 8:
        raise SubmissionError("descriptor.hardware.accelerators must contain at most 8 entries")
    accelerator_identities: set[tuple[str, str, int, float | None]] = set()
    for index, item in enumerate(accelerators):
        path = f"descriptor.hardware.accelerators[{index}]"
        accelerator = _object(item, {"kind", "model", "count", "memory_gb"}, path)
        if accelerator["kind"] not in _ACCELERATOR_KINDS:
            raise SubmissionError(f"{path}.kind is unsupported")
        _descriptor_text(accelerator["model"], f"{path}.model", maximum=200)
        _integer(accelerator["count"], f"{path}.count", minimum=1, maximum=64)
        memory_gb = accelerator["memory_gb"]
        if memory_gb is not None:
            _number(
                memory_gb,
                f"{path}.memory_gb",
                minimum=0.1,
                maximum=1_000_000,
                decimal_places=1,
            )
        identity = (
            str(accelerator["kind"]),
            str(accelerator["model"]).casefold(),
            int(accelerator["count"]),
            float(memory_gb) if memory_gb is not None else None,
        )
        if identity in accelerator_identities:
            raise SubmissionError("descriptor.hardware.accelerators contains a duplicate")
        accelerator_identities.add(identity)
    execution_mode = hardware["execution_mode"]
    if execution_mode not in _EXECUTION_MODES:
        raise SubmissionError("descriptor.hardware.execution_mode is unsupported")
    if execution_mode == "cpu_only" and accelerators:
        raise SubmissionError("cpu_only execution cannot list an accelerator")
    if execution_mode in {"accelerator_only", "hybrid"} and not accelerators:
        raise SubmissionError(f"{execution_mode} execution requires an accelerator")
    architecture = memory["architecture"]
    if architecture == "shared" and any(
        accelerator["memory_gb"] is not None for accelerator in accelerators
    ):
        raise SubmissionError("shared memory accelerators must use null memory_gb")
    if architecture == "discrete" and any(
        accelerator["memory_gb"] is None for accelerator in accelerators
    ):
        raise SubmissionError("discrete memory accelerators require memory_gb")
    runtime = _object(
        descriptor["runtime"],
        {"name", "version", "backend"},
        "descriptor.runtime",
    )
    _descriptor_text(runtime["name"], "descriptor.runtime.name", maximum=100)
    _descriptor_text(runtime["version"], "descriptor.runtime.version", maximum=100)
    _descriptor_text(runtime["backend"], "descriptor.runtime.backend", maximum=100)
    if "runtime_configuration" in descriptor:
        _validate_runtime_configuration(
            descriptor["runtime_configuration"],
            "descriptor.runtime_configuration",
        )
    try:
        _walk_safe(descriptor)
    except ReportError as error:
        raise SubmissionError("descriptor contains prohibited local data") from error


def _validate_cases(value: Any, path: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) != len(_STANDARD_CASE_IDS):
        raise SubmissionError(f"{path} must contain the complete standard profile")
    cases: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        case_path = f"{path}[{index}]"
        case = _object(item, {"case_id", "outcome", "route", "termination"}, case_path)
        case_id = case["case_id"]
        if case_id != _STANDARD_CASE_IDS[index]:
            raise SubmissionError(f"{path} does not match the standard profile")
        if case["outcome"] not in _OUTCOMES:
            raise SubmissionError(f"{case_path}.outcome is unsupported")
        if case["route"] not in _ROUTES:
            raise SubmissionError(f"{case_path}.route is unsupported")
        if case["termination"] not in _TERMINATIONS:
            raise SubmissionError(f"{case_path}.termination is unsupported")
        if case["route"] == "unsafe_mutation" and case["outcome"] in {
            "pass",
            "semantic_only",
        }:
            raise SubmissionError(f"{case_path} cannot pass after an unsafe mutation route")
        cases.append(case)
    return cases


def _validate_metrics(
    value: Any,
    path: str,
    *,
    cases: list[Mapping[str, Any]],
) -> Mapping[str, Any]:
    metrics = _object(
        value,
        {
            "case_count",
            "semantic_pass_count",
            "exact_format_pass_count",
            "scored_case_count",
            "usage_coverage_cases",
            "latency_ms_mean",
            "completion_tokens_per_second",
        },
        path,
    )
    case_count = _integer(metrics["case_count"], f"{path}.case_count")
    if case_count != len(_STANDARD_CASE_IDS):
        raise SubmissionError(f"{path}.case_count does not match the standard profile")
    scored_count = _integer(metrics["scored_case_count"], f"{path}.scored_case_count")
    semantic_count = _integer(
        metrics["semantic_pass_count"], f"{path}.semantic_pass_count"
    )
    exact_count = _integer(
        metrics["exact_format_pass_count"], f"{path}.exact_format_pass_count"
    )
    coverage = _integer(metrics["usage_coverage_cases"], f"{path}.usage_coverage_cases")
    if any(count > case_count for count in (scored_count, coverage)):
        raise SubmissionError(f"{path} contains a count greater than case_count")
    expected_semantic = sum(
        case["outcome"] in {"pass", "semantic_only"} for case in cases
    )
    expected_exact = sum(case["outcome"] in {"pass", "format_only"} for case in cases)
    expected_scored = sum(case["outcome"] != "not_scored" for case in cases)
    if expected_scored != case_count:
        raise SubmissionError(f"{path} requires every standard case to be scored")
    if (semantic_count, exact_count, scored_count) != (
        expected_semantic,
        expected_exact,
        expected_scored,
    ):
        raise SubmissionError(f"{path} counts do not match categorical case outcomes")
    latency = _number(metrics["latency_ms_mean"], f"{path}.latency_ms_mean")
    if round(latency, 1) != latency:
        raise SubmissionError(f"{path}.latency_ms_mean must use one decimal")
    throughput = metrics["completion_tokens_per_second"]
    if throughput is not None:
        normalized = _number(throughput, f"{path}.completion_tokens_per_second")
        if round(normalized, 1) != normalized:
            raise SubmissionError(f"{path}.completion_tokens_per_second must use one decimal")
        if coverage != case_count:
            raise SubmissionError(f"{path} cannot report throughput with incomplete usage")
    return metrics


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return encoded.encode("utf-8")
    except (TypeError, UnicodeEncodeError, ValueError) as error:
        raise SubmissionError("submission is not strict JSON") from error


def _canonical_float(value: int | float) -> float:
    normalized = float(value)
    return 0.0 if normalized == 0 else normalized


def _normalize_submission_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize contract numbers before content hashing or dataset generation."""

    normalized = copy.deepcopy(payload)
    hardware = normalized["hardware"]
    hardware["memory"]["system_gb"] = _canonical_float(
        hardware["memory"]["system_gb"]
    )
    for accelerator in hardware["accelerators"]:
        if accelerator["memory_gb"] is not None:
            accelerator["memory_gb"] = _canonical_float(accelerator["memory_gb"])
    settings = normalized["settings"]
    settings["temperature"] = _canonical_float(settings["temperature"])
    settings["top_p"] = _canonical_float(settings["top_p"])
    metrics = normalized["metrics"]
    metrics["latency_ms_mean"] = _canonical_float(metrics["latency_ms_mean"])
    if metrics["completion_tokens_per_second"] is not None:
        metrics["completion_tokens_per_second"] = _canonical_float(
            metrics["completion_tokens_per_second"]
        )
    return normalized


def _submission_digest(payload: Mapping[str, Any]) -> str:
    normalized = _normalize_submission_payload(payload)
    return hashlib.sha256(_canonical_bytes(normalized)).hexdigest()


def prepare_submissions(
    report: Mapping[str, Any],
    public_environment: Mapping[str, Any],
    model_ids: tuple[str, ...] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Create one separate public submission per selected model result."""

    try:
        validate_report(report)
    except ReportError as error:
        raise SubmissionError("source report failed validation") from error
    if report["validity"] != "valid":
        raise SubmissionError("only fully valid reports can be prepared for the leaderboard")
    if report["profile"] != "standard":
        raise SubmissionError("only the complete standard profile can be submitted")
    validate_public_environment(public_environment)

    models = report["models"]
    if model_ids:
        requested = set(model_ids)
        models = [model for model in models if model["model_id"] in requested]
        missing = sorted(requested - {model["model_id"] for model in models})
        if missing:
            raise SubmissionError("requested model id was not present in the source report")

    submissions: list[dict[str, Any]] = []
    for model in models:
        if model["validity"] != "valid":
            raise SubmissionError("every submitted model result must be fully valid")
        summary = model["summary"]
        throughput = summary["completion_tokens_per_second_weighted"]
        payload: dict[str, Any] = {
            "schema_version": SUBMISSION_SCHEMA_VERSION,
            "suite_version": report["suite_version"],
            "profile": report["profile"],
            "hardware": copy.deepcopy(public_environment["hardware"]),
            "runtime": copy.deepcopy(public_environment["runtime"]),
            "model": copy.deepcopy(model["provenance"]),
            "settings": copy.deepcopy(model["settings"]),
            "cases": [
                {
                    "case_id": case["case_id"],
                    "outcome": case["outcome"],
                    "route": case["route"],
                    "termination": case["termination"],
                }
                for case in model["cases"]
            ],
            "metrics": {
                "case_count": summary["case_count"],
                "semantic_pass_count": summary["semantic_pass_count"],
                "exact_format_pass_count": summary["exact_format_pass_count"],
                "scored_case_count": summary["scored_case_count"],
                "usage_coverage_cases": summary["usage_coverage_cases"],
                "latency_ms_mean": round(float(summary["latency_ms_mean"]), 1),
                "completion_tokens_per_second": (
                    round(float(throughput), 1) if throughput is not None else None
                ),
            },
        }
        if "runtime_configuration" in public_environment:
            payload["runtime_configuration"] = copy.deepcopy(
                public_environment["runtime_configuration"]
            )
        payload = _normalize_submission_payload(payload)
        submission = {"submission_id": _submission_digest(payload), **payload}
        validate_submission(submission)
        submissions.append(submission)
    return tuple(submissions)


def prepare_submission(
    report: Mapping[str, Any],
    public_environment: Mapping[str, Any],
    model_id: str | None = None,
) -> dict[str, Any]:
    """Prepare one model result, rejecting ambiguous multi-model reports."""

    submissions = prepare_submissions(
        report,
        public_environment,
        (model_id,) if model_id else None,
    )
    if len(submissions) != 1:
        raise SubmissionError("select one model or use prepare_submissions for a multi-model report")
    return submissions[0]


def validate_submission(submission: Mapping[str, Any]) -> None:
    """Validate the closed public contract and its content-derived identifier."""

    submission = _object_with_optional(
        submission,
        {
            "schema_version",
            "submission_id",
            "suite_version",
            "profile",
            "hardware",
            "runtime",
            "model",
            "settings",
            "cases",
            "metrics",
        },
        {"runtime_configuration"},
        "submission",
    )
    if submission["schema_version"] != SUBMISSION_SCHEMA_VERSION:
        raise SubmissionError("submission schema version is unsupported")
    if submission["suite_version"] != "1.0":
        raise SubmissionError("submission suite version is unsupported")
    profile = submission["profile"]
    if profile != "standard":
        raise SubmissionError("submission profile must be standard")
    public_environment = {
        "schema_version": "1.0",
        "hardware": submission["hardware"],
        "runtime": submission["runtime"],
    }
    if "runtime_configuration" in submission:
        public_environment["runtime_configuration"] = submission[
            "runtime_configuration"
        ]
    validate_public_environment(public_environment)
    submission_id = submission["submission_id"]
    if not isinstance(submission_id, str) or not _HEX_DIGEST.fullmatch(submission_id):
        raise SubmissionError("submission_id must be a lowercase SHA-256 digest")
    model = _validate_model(submission["model"], "submission.model")
    context_tokens = int(model["declared_context_tokens"])
    _validate_settings(
        submission["settings"],
        "submission.settings",
        context_tokens=context_tokens,
    )
    if "runtime_configuration" in submission:
        configured_context = submission["runtime_configuration"][
            "context_window_tokens"
        ]
        if (
            configured_context is not None
            and submission["settings"]["max_output_tokens"] > configured_context
        ):
            raise SubmissionError(
                "submission.settings.max_output_tokens exceeds the configured context window"
            )
    cases = _validate_cases(submission["cases"], "submission.cases")
    _validate_metrics(submission["metrics"], "submission.metrics", cases=cases)

    payload = {key: value for key, value in submission.items() if key != "submission_id"}
    if submission_id != _submission_digest(payload):
        raise SubmissionError("submission_id does not match the canonical public content")
    try:
        _walk_safe(submission)
    except ReportError as error:
        raise SubmissionError("submission contains prohibited local data") from error
    if len(_canonical_bytes(submission)) > _MAX_SUBMISSION_BYTES:
        raise SubmissionError("submission exceeds the public size limit")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"unsupported JSON constant: {value}")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object field")
        result[key] = value
    return result


def load_json_object(path: str | Path, *, maximum_bytes: int = _MAX_SUBMISSION_BYTES) -> dict[str, Any]:
    """Load one bounded, regular, duplicate-key-free UTF-8 JSON object."""

    source = Path(path)
    try:
        if source.is_symlink() or not source.is_file():
            raise SubmissionError("JSON input must be a regular file")
        if source.stat().st_size > maximum_bytes:
            raise SubmissionError("JSON input exceeds the public size limit")
        raw = source.read_bytes()
        decoded = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except SubmissionError:
        raise
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise SubmissionError("JSON input is not strict UTF-8 JSON") from error
    if not isinstance(decoded, dict):
        raise SubmissionError("JSON input root must be an object")
    return decoded


def prepare_submission_file(
    path: str | Path,
    descriptor_path: str | Path,
    model_ids: tuple[str, ...] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Load a private run report and return one public record per selected model."""

    report = load_json_object(path, maximum_bytes=1024 * 1024)
    descriptor = load_public_environment_file(descriptor_path)
    return prepare_submissions(report, descriptor, model_ids)


def load_public_environment_file(path: str | Path) -> dict[str, Any]:
    """Load a regular, owner-only, Git-ignored hardware/runtime descriptor."""

    try:
        approved_path = validate_env_file(path)
    except SafetyError as error:
        raise SubmissionError(
            "hardware descriptor must be regular, owner-only, and Git-ignored"
        ) from error
    descriptor = load_json_object(approved_path)
    validate_public_environment(descriptor)
    return descriptor


def load_saved_submission(path: str | Path) -> dict[str, Any]:
    """Load an exact owner-only candidate that is ignored when inside a worktree."""

    try:
        approved_path = validate_env_file(path)
    except SafetyError as error:
        raise SubmissionError(
            "saved candidate must be regular, owner-only, and Git-ignored"
        ) from error
    submission = load_json_object(approved_path)
    validate_submission(submission)
    submission_id = submission["submission_id"]
    if approved_path.name != f"{submission_id}.json":
        raise SubmissionError("saved candidate filename must match submission_id")
    try:
        existing = approved_path.read_bytes()
    except OSError as error:
        raise SubmissionError("saved candidate could not be read") from error
    if existing != render_submission_bytes(submission):
        raise SubmissionError("saved candidate bytes are not canonical")
    return submission


def render_submission_bytes(submission: Mapping[str, Any]) -> bytes:
    """Render the exact public bytes used for local saving and publication."""

    validate_submission(submission)
    try:
        rendered = json.dumps(
            submission,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise SubmissionError("submission is not strict JSON") from error
    encoded = (rendered + "\n").encode("utf-8")
    if len(encoded) > _MAX_SUBMISSION_BYTES:
        raise SubmissionError("submission exceeds the public size limit")
    return encoded


def write_submission(submission: Mapping[str, Any], output_dir: str | Path) -> Path:
    """Write one owner-only public candidate without replacing an existing file."""

    rendered = render_submission_bytes(submission)
    try:
        validate_ignored_destination(
            Path(output_dir) / f"{submission['submission_id']}.json"
        )
        directory = secure_directory(output_dir)
        path = directory / f"{submission['submission_id']}.json"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(rendered)
    except (OSError, SafetyError) as error:
        raise SubmissionError("submission could not be written securely") from error
    return path


def ensure_submission(submission: Mapping[str, Any], output_dir: str | Path) -> Path:
    """Save a candidate once, treating an exact secure existing file as success."""

    rendered = render_submission_bytes(submission)
    try:
        validate_ignored_destination(
            Path(output_dir) / f"{submission['submission_id']}.json"
        )
        directory = secure_directory(output_dir)
        path = directory / f"{submission['submission_id']}.json"
    except (OSError, SafetyError) as error:
        raise SubmissionError("submission destination could not be inspected") from error
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        try:
            return write_submission(submission, output_dir)
        except SubmissionError as write_error:
            # Another process may have won the O_EXCL race with the same bytes.
            try:
                metadata = path.lstat()
            except OSError:
                raise write_error
    except OSError as error:
        raise SubmissionError("submission destination could not be inspected") from error
    if path.is_symlink() or not path.is_file():
        raise SubmissionError("submission destination is not a regular file")
    if os.name != "nt":
        if metadata.st_mode & 0o077:
            raise SubmissionError("existing submission must be owner-only")
        if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
            raise SubmissionError("existing submission must be owned by the current user")
    try:
        existing = path.read_bytes()
    except OSError as error:
        raise SubmissionError("existing submission could not be read") from error
    if existing != rendered:
        raise SubmissionError("submission destination already contains different content")
    return path


def write_submissions(
    submissions: tuple[Mapping[str, Any], ...],
    output_dir: str | Path,
) -> tuple[Path, ...]:
    """Write a batch of already-separated public records append-only."""

    if not submissions:
        raise SubmissionError("no submissions were prepared")
    paths: list[Path] = []
    for submission in submissions:
        paths.append(write_submission(submission, output_dir))
    return tuple(paths)


def ensure_submissions(
    submissions: tuple[Mapping[str, Any], ...],
    output_dir: str | Path,
) -> tuple[Path, ...]:
    """Idempotently save a batch of already-separated public records."""

    if not submissions:
        raise SubmissionError("no submissions were prepared")
    return tuple(ensure_submission(submission, output_dir) for submission in submissions)


def _score_percent(count: int, total: int) -> float:
    return round((count / total) * 100.0, 1) if total else 0.0


def build_leaderboard(submissions_dir: str | Path) -> dict[str, Any]:
    """Validate accepted records and build deterministic quality-only rankings."""

    directory = Path(submissions_dir)
    if not directory.is_dir() or directory.is_symlink():
        raise SubmissionError("submissions directory must be a regular directory")
    files: list[Path] = []
    for path in sorted(directory.iterdir(), key=lambda candidate: candidate.name):
        if path.name == ".gitkeep" and path.is_file() and not path.is_symlink():
            continue
        if path.suffix != ".json" or path.is_symlink() or not path.is_file():
            raise SubmissionError("submissions directory contains an unsupported entry")
        files.append(path)
    try:
        input_bytes = sum(path.stat().st_size for path in files)
    except OSError as error:
        raise SubmissionError("submission input size could not be checked") from error
    if input_bytes > _MAX_DATASET_BYTES:
        raise SubmissionError("accepted submission input exceeds the site data limit")
    seen_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise SubmissionError("submission entries must be regular files")
        submission = load_json_object(path)
        validate_submission(submission)
        submission_id = submission["submission_id"]
        if path.name != f"{submission_id}.json":
            raise SubmissionError("submission filename must match submission_id")
        if submission_id in seen_ids:
            raise SubmissionError("duplicate submission_id")
        seen_ids.add(submission_id)
        normalized_submission = _normalize_submission_payload(
            {key: value for key, value in submission.items() if key != "submission_id"}
        )
        metrics = normalized_submission["metrics"]
        case_count = metrics["case_count"]
        leaderboard_metrics = copy.deepcopy(metrics)
        leaderboard_metrics["semantic_score_percent"] = _score_percent(
            metrics["semantic_pass_count"], case_count
        )
        leaderboard_metrics["exact_format_score_percent"] = _score_percent(
            metrics["exact_format_pass_count"], case_count
        )
        row = {
            "submission_id": submission_id,
            "suite_version": submission["suite_version"],
            "profile": submission["profile"],
            "hardware": copy.deepcopy(normalized_submission["hardware"]),
            "runtime": copy.deepcopy(normalized_submission["runtime"]),
            "model": copy.deepcopy(normalized_submission["model"]),
            "settings": copy.deepcopy(normalized_submission["settings"]),
            "metrics": leaderboard_metrics,
        }
        if "runtime_configuration" in normalized_submission:
            row["runtime_configuration"] = copy.deepcopy(
                normalized_submission["runtime_configuration"]
            )
        rows.append(row)

    rows.sort(
        key=lambda row: (
            -row["metrics"]["semantic_score_percent"],
            -row["metrics"]["exact_format_score_percent"],
            row["model"]["source"].casefold(),
            row["model"]["display_name"].casefold(),
            row["submission_id"],
        )
    )
    entries: list[dict[str, Any]] = []
    previous_quality: tuple[float, float] | None = None
    current_rank = 0
    for row in rows:
        quality = (
            row["metrics"]["semantic_score_percent"],
            row["metrics"]["exact_format_score_percent"],
        )
        if quality != previous_quality:
            current_rank += 1
            previous_quality = quality
        entries.append({"rank": current_rank, **row})
    leaderboard = {
        "schema_version": LEADERBOARD_SCHEMA_VERSION,
        "entry_count": len(entries),
        "entries": entries,
    }
    if len(render_leaderboard_bytes(leaderboard)) > _MAX_DATASET_BYTES:
        raise SubmissionError("generated leaderboard exceeds the site data limit")
    return leaderboard


def render_leaderboard_bytes(value: Mapping[str, Any]) -> bytes:
    """Render the one canonical byte representation used for publication."""

    try:
        rendered = json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise SubmissionError("leaderboard is not strict JSON") from error
    return (rendered + "\n").encode("utf-8")


def write_leaderboard(leaderboard: Mapping[str, Any], output: str | Path) -> None:
    """Replace generated static data atomically with deterministic JSON."""

    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.is_symlink() or not destination.parent.is_dir():
        raise SubmissionError("leaderboard output directory must be a regular directory")
    rendered = render_leaderboard_bytes(leaderboard)
    if len(rendered) > _MAX_DATASET_BYTES:
        raise SubmissionError("generated leaderboard exceeds the site data limit")
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(rendered)
        os.replace(temporary, destination)
    except OSError as error:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise SubmissionError("leaderboard data could not be written") from error
