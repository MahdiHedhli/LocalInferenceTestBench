"""Minimized benchmark submissions and deterministic leaderboard generation."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

from .models import ParameterScaleValidationError, validate_parameter_scale_values
from .reporting import ReportError, _walk_safe, validate_report
from .safety import (
    SafetyError,
    secure_directory,
    validate_env_file,
    validate_ignored_destination,
)
from .suites import (
    CAPABILITIES,
    MODALITIES,
    SuiteCase,
    resolve_public_suite,
)


SUBMISSION_SCHEMA_VERSION = "1.1"
LEADERBOARD_SCHEMA_VERSION = "1.1"
LEADERBOARD_INDEX_VERSION = "1.0"
LEGACY_SUBMISSION_SCHEMA_VERSION = "1.0"
LEGACY_LEADERBOARD_SCHEMA_VERSION = "1.0"
_OUTCOMES = {
    "pass",
    "semantic_only",
    "format_only",
    "fail",
    "not_scored",
    "not_applicable",
}
_ROUTES = {
    "direct_response",
    "read_only_tool",
    "safe_refusal",
    "unsafe_mutation",
    "unexpected_tool",
    "unrecognized",
    "not_applicable",
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
    "not_applicable",
}
_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_FACET_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_IPV4_CANDIDATE = re.compile(r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])")
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
    r"(?i)(?:\bhttps?:|\b[a-z][a-z0-9+.-]*://|"
    r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,})"
)
_LOCAL_HOST_MARKER = re.compile(
    r"(?i)(?<![a-z0-9])" + ("local" + "host") + r"(?![a-z0-9])"
)
_SCANNER_SUPPRESSION_MARKER = re.compile(
    r"(?i)\b" + "git" + r"leaks\s*:\s*allow\b"
)
_MAX_SUBMISSION_BYTES = 256 * 1024
MAX_MEASUREMENT_EVIDENCE_BYTES = 2 * 1024 * 1024
# This is a per-file publication limit. The accepted corpus itself is unbounded;
# the static transport paginates it into independently bounded shard files.
_MAX_DATA_FILE_BYTES = 2 * 1024 * 1024
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
_PUBLIC_VALIDITIES = {"clean", "nonquiescent", "degraded_midrun"}
_LEADERBOARD_VALIDITIES = _PUBLIC_VALIDITIES | {"legacy_unreported"}
_MEASUREMENT_OUTCOMES = {
    "within_thresholds",
    "threshold_crossed",
}
_MEASUREMENT_CATEGORY_ORDER = (
    "memory_pressure",
    "thermal",
    "sustained_load",
    "swap",
    "resident_models",
)
_MEASUREMENT_CATEGORIES = frozenset(_MEASUREMENT_CATEGORY_ORDER)
_DETERMINISM_VERDICTS = {"stable", "warning", "blocking_instability"}
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
_CONFIG_KEY_VERSION = "1.0"
_CONFIG_SELECTION_VERSION = "1.0"
_PLAUSIBILITY_POLICY_VERSION = "1.0"
_WILSON_Z_95 = 1.959963984540054
_VALIDITY_SELECTION_ORDER = (
    "clean",
    "nonquiescent",
    "degraded_midrun",
    "legacy_unreported",
)
_PLAUSIBILITY_SIGNAL_ORDER = (
    "latency_below_envelope",
    "throughput_above_envelope",
)
_MODEL_SIZE_BUCKETS = (
    "under_4b",
    "4b_to_under_14b",
    "14b_to_under_35b",
    "35b_to_under_70b",
    "70b_and_above",
)
_PLAUSIBILITY_ENVELOPES = {
    "cpu_only": {
        "under_4b": (0.1, 2_500.0),
        "4b_to_under_14b": (0.1, 1_500.0),
        "14b_to_under_35b": (0.2, 800.0),
        "35b_to_under_70b": (0.5, 400.0),
        "70b_and_above": (1.0, 200.0),
    },
    "shared_accelerator": {
        "under_4b": (0.1, 10_000.0),
        "4b_to_under_14b": (0.1, 6_000.0),
        "14b_to_under_35b": (0.1, 4_000.0),
        "35b_to_under_70b": (0.1, 2_500.0),
        "70b_and_above": (0.2, 1_500.0),
    },
    "discrete_accelerator": {
        "under_4b": (0.1, 20_000.0),
        "4b_to_under_14b": (0.1, 12_000.0),
        "14b_to_under_35b": (0.1, 8_000.0),
        "35b_to_under_70b": (0.1, 5_000.0),
        "70b_and_above": (0.2, 3_000.0),
    },
    "mixed_accelerator": {
        "under_4b": (0.1, 20_000.0),
        "4b_to_under_14b": (0.1, 12_000.0),
        "14b_to_under_35b": (0.1, 8_000.0),
        "35b_to_under_70b": (0.1, 5_000.0),
        "70b_and_above": (0.2, 3_000.0),
    },
}


@dataclass(frozen=True, slots=True)
class FacetSelector:
    """A versioned selection seam for one leaderboard view."""

    facet_id: str
    capabilities: frozenset[str] | None
    modalities: frozenset[str]
    dimension_filters: tuple[tuple[str, Any], ...] = ()


DEFAULT_FACET = FacetSelector(
    facet_id="all-cases-text",
    capabilities=None,
    modalities=frozenset({"text"}),
)

# These names define the public configuration cell. Stage 4 uses this exact
# versioned structure for collapse and corroboration rather than an inline tuple.
CONFIG_KEY_DIMENSIONS = {
    "version": _CONFIG_KEY_VERSION,
    "fields": (
        "hardware",
        "model_identity",
        "precision",
        "runtime",
        "runtime_configuration",
        "settings",
    ),
}

# This policy is intentionally not consumed yet. It fixes the graduation rule
# before enough data exists to justify a dedicated faceted view.
FACET_GRADUATION_POLICY = {
    "version": "1.0",
    "minimum_entries": 25,
    "minimum_model_families": 5,
}


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
    """Accept a reviewer-neutral public label with no machine identifier."""

    result = _text(value, path, maximum=maximum)
    if not _MODEL_DESCRIPTOR_ASCII.fullmatch(result):
        raise SubmissionError(f"{path} must use visible ASCII descriptor text")
    if _MODEL_REVIEW_INJECTION.search(result):
        raise SubmissionError(f"{path} contains prohibited reviewer-directed content")
    if (
        _IPV4_CANDIDATE.search(result)
        or _IPV6_CANDIDATE.search(result)
        or _UUID.search(result)
        or _DESCRIPTOR_IDENTIFIER_LABEL.search(result)
        or _URL_OR_EMAIL.search(result)
        or _LOCAL_HOST_MARKER.search(result)
    ):
        raise SubmissionError(f"{path} contains a prohibited machine identifier")
    return result


def _model_descriptor_text(value: Any, path: str, *, maximum: int) -> str:
    """Accept a compact public model label, never reviewer-directed content."""

    return _descriptor_text(value, path, maximum=maximum)


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
    decimal_places: int | None = 6,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < minimum
        or float(value) > maximum
    ):
        raise SubmissionError(f"{path} must be a finite number between {minimum} and {maximum}")
    if decimal_places is not None:
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


def _validate_parameter_scale(value: Any, path: str) -> Mapping[str, Any]:
    try:
        validate_parameter_scale_values(value)
    except ParameterScaleValidationError as error:
        if error.code == "object_contract":
            message = f"{path} has an unsupported object contract"
        else:
            error_path = f"{path}.{error.field}"
            if error.code == "zero":
                message = f"{error_path} must be positive when known"
            elif error.code == "invalid_number":
                message = (
                    f"{error_path} must be a finite number between 0.0 and 1000000.0"
                )
            elif error.code == "fractional_digits":
                message = f"{error_path} supports at most 3 fractional digits"
            elif error.code == "numeric_precision":
                message = f"{error_path} has unsupported numeric precision"
            elif error.code == "active_requires_total":
                message = f"{path}.active_billions requires total_billions"
            elif error.code == "active_exceeds_total":
                message = f"{path}.active_billions cannot exceed total_billions"
            else:
                raise AssertionError(
                    f"unsupported parameter-scale error code: {error.code}"
                ) from error
        raise SubmissionError(message) from error
    return value


def _validate_model(
    value: Any,
    path: str,
    *,
    require_parameter_scale: bool = False,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SubmissionError(f"{path} must be an object")
    base = {"display_name", "source", "precision", "declared_context_tokens"}
    if require_parameter_scale:
        base.add("parameter_scale")
    optional_scale = {"parameter_scale"} if not require_parameter_scale else set()
    identity = set(value) - base - optional_scale
    if identity not in ({"revision"}, {"digest"}):
        raise SubmissionError(f"{path} must contain exactly one public revision identifier")
    model = _object_with_optional(value, base | identity, optional_scale, path)
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
    if "parameter_scale" in model:
        _validate_parameter_scale(model["parameter_scale"], f"{path}.parameter_scale")
    identity_field = next(iter(identity))
    _model_descriptor_text(
        model[identity_field],
        f"{path}.{identity_field}",
        maximum=200,
    )
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


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise SubmissionError(f"{path} must be boolean")
    return value


def _validate_measurement_sample(value: Any, path: str) -> Mapping[str, Any]:
    sample = _object(value, {"outcome", "categories"}, path)
    outcome = sample["outcome"]
    if not isinstance(outcome, str) or outcome not in _MEASUREMENT_OUTCOMES:
        raise SubmissionError(f"{path}.outcome is unsupported")
    categories = sample["categories"]
    if not isinstance(categories, list) or len(categories) > len(_MEASUREMENT_CATEGORIES):
        raise SubmissionError(f"{path}.categories is unsupported")
    if any(
        not isinstance(category, str) or category not in _MEASUREMENT_CATEGORIES
        for category in categories
    ):
        raise SubmissionError(f"{path}.categories is unsupported")
    expected_order = [
        category for category in _MEASUREMENT_CATEGORY_ORDER if category in categories
    ]
    if categories != expected_order:
        raise SubmissionError(f"{path}.categories must be unique and canonical")
    if (outcome == "threshold_crossed") != bool(categories):
        raise SubmissionError(f"{path}.outcome does not match its threshold categories")
    return sample


def validate_measurement_sample(value: Any) -> dict[str, Any]:
    """Validate and copy one closed categorical sampler result."""

    sample = _validate_measurement_sample(value, "measurement_sample")
    return {
        "outcome": sample["outcome"],
        "categories": list(sample["categories"]),
    }


def _derived_public_validity(
    pre: Mapping[str, Any],
    post: Mapping[str, Any],
) -> str:
    pre_categories = set(pre["categories"])
    post_categories = set(post["categories"])
    if post_categories - pre_categories:
        return "degraded_midrun"
    if pre_categories:
        return "nonquiescent"
    return "clean"


def _validate_measurement_conditions(value: Any, path: str) -> Mapping[str, Any]:
    conditions = _object(value, {"pre", "post", "hard_threshold_crossed"}, path)
    pre = _validate_measurement_sample(conditions["pre"], f"{path}.pre")
    post = _validate_measurement_sample(conditions["post"], f"{path}.post")
    crossed = _boolean(
        conditions["hard_threshold_crossed"],
        f"{path}.hard_threshold_crossed",
    )
    expected_crossed = bool(pre["categories"] or post["categories"])
    if crossed != expected_crossed:
        raise SubmissionError(f"{path}.hard_threshold_crossed is inconsistent")
    return conditions


def _validate_determinism(value: Any, path: str) -> Mapping[str, Any]:
    determinism = _object(
        value,
        {
            "n_runs",
            "semantic_pass_rate",
            "envelope_class_stable",
            "finish_reason_stable",
            "fingerprint_stable",
            "verdict",
        },
        path,
    )
    n_runs = _integer(
        determinism["n_runs"],
        f"{path}.n_runs",
        minimum=3,
        maximum=5,
    )
    semantic_pass_rate = _number(
        determinism["semantic_pass_rate"],
        f"{path}.semantic_pass_rate",
        maximum=1,
        decimal_places=None,
    )
    passed_runs = round(semantic_pass_rate * n_runs)
    expected_rate = passed_runs / n_runs
    if (
        not 0 <= passed_runs <= n_runs
        or abs(semantic_pass_rate - expected_rate) > 0.000000500001
    ):
        raise SubmissionError(f"{path}.semantic_pass_rate is inconsistent with n_runs")
    envelope_stable = _boolean(
        determinism["envelope_class_stable"],
        f"{path}.envelope_class_stable",
    )
    finish_stable = _boolean(
        determinism["finish_reason_stable"],
        f"{path}.finish_reason_stable",
    )
    fingerprint_stable = _boolean(
        determinism["fingerprint_stable"],
        f"{path}.fingerprint_stable",
    )
    verdict = determinism["verdict"]
    if not isinstance(verdict, str) or verdict not in _DETERMINISM_VERDICTS:
        raise SubmissionError(f"{path}.verdict is unsupported")
    semantic_stable = passed_runs in {0, n_runs}
    expected_verdict = (
        "blocking_instability"
        if not semantic_stable or not envelope_stable or not finish_stable
        else "warning" if not fingerprint_stable else "stable"
    )
    if verdict != expected_verdict:
        raise SubmissionError(f"{path}.verdict is inconsistent")
    return determinism


def _validate_measurement_result(value: Any, path: str) -> Mapping[str, Any]:
    result = _object_with_optional(
        value,
        {"model_id", "validity", "measurement_conditions"},
        {"determinism"},
        path,
    )
    _text(result["model_id"], f"{path}.model_id", maximum=128)
    validity = result["validity"]
    if not isinstance(validity, str) or validity not in _PUBLIC_VALIDITIES:
        raise SubmissionError(f"{path}.validity is unsupported")
    conditions = _validate_measurement_conditions(
        result["measurement_conditions"],
        f"{path}.measurement_conditions",
    )
    expected_validity = _derived_public_validity(conditions["pre"], conditions["post"])
    if validity != expected_validity:
        raise SubmissionError(f"{path}.validity is inconsistent with its measurements")
    if "determinism" in result:
        _validate_determinism(result["determinism"], f"{path}.determinism")
    return result


def validate_measurement_evidence(value: Mapping[str, Any]) -> None:
    """Validate one ignored, categorical, per-model measurement evidence file."""

    evidence = _object(
        value,
        {"schema_version", "source_run_id", "models"},
        "measurement_evidence",
    )
    if evidence["schema_version"] != "1.0":
        raise SubmissionError("measurement evidence schema version is unsupported")
    _text(evidence["source_run_id"], "measurement_evidence.source_run_id", maximum=128)
    models = evidence["models"]
    if not isinstance(models, list) or not 1 <= len(models) <= 1000:
        raise SubmissionError(
            "measurement_evidence.models must contain between 1 and 1000 entries"
        )
    validated = [
        _validate_measurement_result(model, f"measurement_evidence.models[{index}]")
        for index, model in enumerate(models)
    ]
    model_ids = [str(model["model_id"]) for model in validated]
    if len(model_ids) != len(set(model_ids)):
        raise SubmissionError("measurement evidence model ids must be unique")
    try:
        _walk_safe(evidence)
    except ReportError as error:
        raise SubmissionError("measurement evidence contains prohibited local data") from error


def _validate_measurement_period(value: Any, path: str) -> str:
    period = _text(value, path, maximum=7)
    if not re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", period):
        raise SubmissionError(f"{path} must use YYYY-MM")
    current_period = datetime.now(timezone.utc).strftime("%Y-%m")
    if period > current_period:
        raise SubmissionError(f"{path} cannot be in the future")
    return period


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
            str(accelerator["model"]).lower(),
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


def _validate_cases(
    value: Any,
    path: str,
    *,
    suite: tuple[SuiteCase, ...],
    legacy: bool,
) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) != len(suite):
        raise SubmissionError(f"{path} must contain the complete resolved suite")
    cases: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        case_path = f"{path}[{index}]"
        keys = {"case_id", "outcome", "route", "termination"}
        if not legacy:
            keys |= {"capability", "modality"}
        case = _object(item, keys, case_path)
        expected = suite[index]
        case_id = case["case_id"]
        if case_id != expected.case_id:
            raise SubmissionError(f"{path} does not match the resolved suite")
        if not legacy and (
            case["capability"] != expected.capability
            or case["modality"] != expected.modality
            or case["capability"] not in CAPABILITIES
            or case["modality"] not in MODALITIES
        ):
            raise SubmissionError(f"{case_path} taxonomy does not match the resolved suite")
        allowed_outcomes = _OUTCOMES - ({"not_applicable"} if legacy else set())
        if case["outcome"] not in allowed_outcomes:
            raise SubmissionError(f"{case_path}.outcome is unsupported")
        if case["route"] not in _ROUTES:
            raise SubmissionError(f"{case_path}.route is unsupported")
        if case["termination"] not in _TERMINATIONS:
            raise SubmissionError(f"{case_path}.termination is unsupported")
        not_applicable = case["outcome"] == "not_applicable"
        if (
            not_applicable != (case["route"] == "not_applicable")
            or not_applicable != (case["termination"] == "not_applicable")
        ):
            raise SubmissionError(
                f"{case_path} not_applicable outcome, route, and termination must agree"
            )
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
    suite_length: int,
    legacy: bool,
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
    if case_count != suite_length:
        raise SubmissionError(f"{path}.case_count does not match the resolved suite")
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
    expected_scored = sum(
        case["outcome"] not in {"not_scored", "not_applicable"} for case in cases
    )
    if not legacy and expected_scored == 0:
        raise SubmissionError(f"{path} requires at least one scored public case")
    not_applicable = sum(case["outcome"] == "not_applicable" for case in cases)
    if legacy:
        eligible_case_count = expected_scored
    else:
        eligible_case_count = expected_scored + not_applicable
    if eligible_case_count != case_count:
        raise SubmissionError(f"{path} contains an attempted case that was not scored")
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
        if coverage != expected_scored:
            raise SubmissionError(f"{path} cannot report throughput with incomplete usage")
    if coverage > expected_scored:
        raise SubmissionError(f"{path}.usage_coverage_cases exceeds scored cases")
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
    parameter_scale = normalized["model"].get("parameter_scale")
    if parameter_scale is not None:
        for field in ("total_billions", "active_billions"):
            if parameter_scale[field] is not None:
                parameter_scale[field] = _canonical_float(parameter_scale[field])
    metrics = normalized["metrics"]
    metrics["latency_ms_mean"] = _canonical_float(metrics["latency_ms_mean"])
    if metrics["completion_tokens_per_second"] is not None:
        metrics["completion_tokens_per_second"] = _canonical_float(
            metrics["completion_tokens_per_second"]
        )
    if "determinism" in normalized:
        normalized["determinism"]["semantic_pass_rate"] = _canonical_float(
            normalized["determinism"]["semantic_pass_rate"]
        )
    return normalized


def _submission_digest(payload: Mapping[str, Any]) -> str:
    normalized = _normalize_submission_payload(payload)
    return hashlib.sha256(_canonical_bytes(normalized)).hexdigest()


def prepare_submissions(
    report: Mapping[str, Any],
    public_environment: Mapping[str, Any],
    model_ids: tuple[str, ...] | None = None,
    *,
    measurement_evidence: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Create one separate public submission per selected model result."""

    try:
        validate_report(report)
    except ReportError as error:
        raise SubmissionError("source report failed validation") from error
    if report["validity"] != "valid":
        raise SubmissionError("only fully valid reports can be prepared for the leaderboard")
    try:
        suite = resolve_public_suite(report["profile"], report["suite_version"])
    except ValueError as error:
        raise SubmissionError("only a registered complete public suite can be submitted") from error
    validate_public_environment(public_environment)
    validate_measurement_evidence(measurement_evidence)
    if measurement_evidence["source_run_id"] != report["run_id"]:
        raise SubmissionError("measurement evidence does not match the source run")

    report_model_ids = {model["model_id"] for model in report["models"]}
    evidence_by_model = {
        result["model_id"]: result for result in measurement_evidence["models"]
    }
    if not set(evidence_by_model).issubset(report_model_ids):
        raise SubmissionError("measurement evidence contains a model outside the source report")

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
        evidence = evidence_by_model.get(model["model_id"])
        if evidence is None:
            raise SubmissionError("every submitted model requires measurement evidence")
        throughput = summary["completion_tokens_per_second_weighted"]
        payload: dict[str, Any] = {
            "schema_version": SUBMISSION_SCHEMA_VERSION,
            "suite_version": report["suite_version"],
            "profile": report["profile"],
            "measurement_period": str(report["created_at"])[:7],
            "validity": evidence["validity"],
            "measurement_conditions": copy.deepcopy(
                evidence["measurement_conditions"]
            ),
            "hardware": copy.deepcopy(public_environment["hardware"]),
            "runtime": copy.deepcopy(public_environment["runtime"]),
            "model": {
                **copy.deepcopy(model["provenance"]),
                "parameter_scale": copy.deepcopy(
                    model["provenance"].get(
                        "parameter_scale",
                        {"total_billions": None, "active_billions": None},
                    )
                ),
            },
            "settings": copy.deepcopy(model["settings"]),
            "cases": [
                {
                    "case_id": case["case_id"],
                    "capability": suite_case.capability,
                    "modality": suite_case.modality,
                    "outcome": case["outcome"],
                    "route": case["route"],
                    "termination": case["termination"],
                }
                for case, suite_case in zip(model["cases"], suite, strict=True)
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
        if "determinism" in evidence:
            payload["determinism"] = copy.deepcopy(evidence["determinism"])
        payload = _normalize_submission_payload(payload)
        submission = {"submission_id": _submission_digest(payload), **payload}
        validate_submission(submission)
        submissions.append(submission)
    return tuple(submissions)


def prepare_submission(
    report: Mapping[str, Any],
    public_environment: Mapping[str, Any],
    model_id: str | None = None,
    *,
    measurement_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Prepare one model result, rejecting ambiguous multi-model reports."""

    submissions = prepare_submissions(
        report,
        public_environment,
        (model_id,) if model_id else None,
        measurement_evidence=measurement_evidence,
    )
    if len(submissions) != 1:
        raise SubmissionError(
            "select one model or use prepare_submissions for a multi-model report"
        )
    return submissions[0]


def _validate_submission(
    submission: Mapping[str, Any],
    *,
    allow_legacy: bool,
) -> None:
    """Validate one current candidate or retained legacy accepted record."""

    schema_version = submission.get("schema_version") if isinstance(submission, Mapping) else None
    legacy = schema_version == LEGACY_SUBMISSION_SCHEMA_VERSION
    if legacy and not allow_legacy:
        raise SubmissionError("legacy submissions must be regenerated as schema 1.1")
    if schema_version not in {
        SUBMISSION_SCHEMA_VERSION,
        *({LEGACY_SUBMISSION_SCHEMA_VERSION} if allow_legacy else set()),
    }:
        raise SubmissionError("submission schema version is unsupported")
    required = {
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
    }
    optional = {"runtime_configuration"}
    if not legacy:
        required |= {"measurement_period", "validity", "measurement_conditions"}
        optional.add("determinism")
    submission = _object_with_optional(submission, required, optional, "submission")
    profile = _text(submission["profile"], "submission.profile", maximum=128)
    suite_version = _text(
        submission["suite_version"],
        "submission.suite_version",
        maximum=128,
    )
    try:
        suite = resolve_public_suite(profile, suite_version)
    except ValueError as error:
        raise SubmissionError("submission suite is unsupported") from error
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
    if legacy and "parameter_scale" in submission["model"]:
        raise SubmissionError("legacy submission.model has an unsupported object contract")
    model = _validate_model(
        submission["model"],
        "submission.model",
        require_parameter_scale=not legacy,
    )
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
    if not legacy:
        validity = submission["validity"]
        if not isinstance(validity, str) or validity not in _PUBLIC_VALIDITIES:
            raise SubmissionError("submission.validity is unsupported")
        _validate_measurement_period(
            submission["measurement_period"],
            "submission.measurement_period",
        )
        conditions = _validate_measurement_conditions(
            submission["measurement_conditions"],
            "submission.measurement_conditions",
        )
        if validity != _derived_public_validity(conditions["pre"], conditions["post"]):
            raise SubmissionError("submission.validity is inconsistent with its measurements")
        if "determinism" in submission:
            _validate_determinism(submission["determinism"], "submission.determinism")
    cases = _validate_cases(
        submission["cases"],
        "submission.cases",
        suite=suite,
        legacy=legacy,
    )
    _validate_metrics(
        submission["metrics"],
        "submission.metrics",
        cases=cases,
        suite_length=len(suite),
        legacy=legacy,
    )

    payload = {key: value for key, value in submission.items() if key != "submission_id"}
    if submission_id != _submission_digest(payload):
        raise SubmissionError("submission_id does not match the canonical public content")
    try:
        _walk_safe(submission)
    except ReportError as error:
        raise SubmissionError("submission contains prohibited local data") from error
    if len(_canonical_bytes(submission)) > _MAX_SUBMISSION_BYTES:
        raise SubmissionError("submission exceeds the public size limit")


def validate_submission(submission: Mapping[str, Any]) -> None:
    """Validate one current-schema public candidate and its content identifier."""

    _validate_submission(submission, allow_legacy=False)


def validate_accepted_submission(submission: Mapping[str, Any]) -> None:
    """Validate a retained accepted record under the explicit 1.0/1.1 policy."""

    _validate_submission(submission, allow_legacy=True)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"unsupported JSON constant: {value}")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object field")
        result[key] = value
    return result


def load_json_object(
    path: str | Path,
    *,
    maximum_bytes: int = _MAX_SUBMISSION_BYTES,
) -> dict[str, Any]:
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
    *,
    measurement_evidence_path: str | Path,
) -> tuple[dict[str, Any], ...]:
    """Load a private run report and return one public record per selected model."""

    report = load_json_object(path, maximum_bytes=1024 * 1024)
    descriptor = load_public_environment_file(descriptor_path)
    evidence = load_measurement_evidence_file(measurement_evidence_path)
    return prepare_submissions(
        report,
        descriptor,
        model_ids,
        measurement_evidence=evidence,
    )


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


def load_measurement_evidence_file(path: str | Path) -> dict[str, Any]:
    """Load ignored, owner-only, categorical per-run measurement evidence."""

    try:
        approved_path = validate_env_file(path)
    except SafetyError as error:
        raise SubmissionError(
            "measurement evidence must be regular, owner-only, and Git-ignored"
        ) from error
    evidence = load_json_object(
        approved_path,
        maximum_bytes=MAX_MEASUREMENT_EVIDENCE_BYTES,
    )
    validate_measurement_evidence(evidence)
    return evidence


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
    if not total:
        return 0.0
    # Round exact integer ratios to the nearest tenth, with ties away from zero.
    # This is intentionally language-neutral rather than Python's half-even round.
    tenths = (2 * count * 1000 + total) // (2 * total)
    return tenths / 10.0


def _validate_facet_selector(facet: FacetSelector) -> None:
    if (
        not isinstance(facet, FacetSelector)
        or not facet.facet_id
        or not facet.modalities
        or not facet.modalities.issubset(MODALITIES)
        or (
            facet.capabilities is not None
            and (
                not facet.capabilities
                or not facet.capabilities.issubset(CAPABILITIES)
            )
        )
    ):
        raise SubmissionError("leaderboard facet selector is unsupported")
    dimension_names = set(CONFIG_KEY_DIMENSIONS["fields"])
    selected_dimensions = [name for name, _value in facet.dimension_filters]
    if (
        len(selected_dimensions) != len(set(selected_dimensions))
        or any(name not in dimension_names for name in selected_dimensions)
    ):
        raise SubmissionError("leaderboard facet dimension filter is unsupported")


def _model_identity(model: Mapping[str, Any]) -> dict[str, Any]:
    identity_field = "revision" if "revision" in model else "digest"
    return {
        "display_name": model["display_name"],
        "source": model["source"],
        identity_field: model[identity_field],
        "declared_context_tokens": model["declared_context_tokens"],
        "parameter_scale": copy.deepcopy(
            model.get(
                "parameter_scale",
                {"total_billions": None, "active_billions": None},
            )
        ),
    }


def _facet_dimensions(submission: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "hardware": submission["hardware"],
        "model_identity": _model_identity(submission["model"]),
        "precision": submission["model"]["precision"],
        "runtime": submission["runtime"],
        "runtime_configuration": submission.get("runtime_configuration"),
        "settings": submission["settings"],
    }


def _facet_cases(
    submission: Mapping[str, Any],
    suite: tuple[SuiteCase, ...],
    facet: FacetSelector,
) -> list[Mapping[str, Any]]:
    selected: list[Mapping[str, Any]] = []
    for case, definition in zip(submission["cases"], suite, strict=True):
        if definition.modality not in facet.modalities:
            continue
        if facet.capabilities is not None and definition.capability not in facet.capabilities:
            continue
        selected.append(case)
    return selected


def wilson_interval_95(passes: int, total: int) -> dict[str, int]:
    """Return conservative outward-rounded whole-percent Wilson bounds."""

    if (
        isinstance(passes, bool)
        or isinstance(total, bool)
        or not isinstance(passes, int)
        or not isinstance(total, int)
        or total < 1
        or passes < 0
        or passes > total
    ):
        raise SubmissionError("Wilson interval counts are inconsistent")
    proportion = passes / total
    squared = _WILSON_Z_95 * _WILSON_Z_95
    denominator = 1.0 + squared / total
    center = (proportion + squared / (2.0 * total)) / denominator
    margin = (
        _WILSON_Z_95
        * math.sqrt(
            (proportion * (1.0 - proportion) + squared / (4.0 * total))
            / total
        )
        / denominator
    )
    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)
    return {
        "lower_percent": max(0, min(100, math.floor(lower * 100.0))),
        "upper_percent": max(0, min(100, math.ceil(upper * 100.0))),
    }


def _config_key(dimensions: Mapping[str, Any]) -> tuple[bytes, str]:
    payload = {
        "version": CONFIG_KEY_DIMENSIONS["version"],
        "dimensions": dimensions,
    }
    canonical = _canonical_bytes(payload)
    return canonical, hashlib.sha256(canonical).hexdigest()


def _representative_key(row: Mapping[str, Any]) -> tuple[int, int, str]:
    validity = str(row["validity"])
    try:
        priority = _VALIDITY_SELECTION_ORDER.index(validity)
    except ValueError as error:
        raise SubmissionError("leaderboard row validity is unsupported") from error
    period = row["measurement_period"]
    period_number = (
        int(str(period)[:4]) * 12 + int(str(period)[5:7]) if period is not None else -1
    )
    return priority, -period_number, str(row["submission_id"])


def _corroboration(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    by_validity: dict[str, Any] = {}
    total = 0
    for validity in _VALIDITY_SELECTION_ORDER:
        matching = [row for row in rows if row["validity"] == validity]
        periods = sorted(
            str(row["measurement_period"])
            for row in matching
            if row["measurement_period"] is not None
        )
        by_validity[validity] = {
            "count": len(matching),
            "earliest_period": periods[0] if periods else None,
            "latest_period": periods[-1] if periods else None,
        }
        total += len(matching)
    if total != len(rows):
        raise SubmissionError("leaderboard corroboration contains an unsupported validity")
    return {
        "accepted_record_count": total,
        "by_validity": by_validity,
    }


def _distribution(values: list[float]) -> dict[str, int | float | None]:
    if not values:
        return {
            "sample_count": 0,
            "median": None,
            "minimum": None,
            "maximum": None,
        }
    ordered = sorted(Decimal(str(value)) for value in values)
    middle = len(ordered) // 2
    median = (
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / Decimal(2)
    )
    return {
        "sample_count": len(ordered),
        "median": _canonical_float(float(median)),
        "minimum": _canonical_float(float(ordered[0])),
        "maximum": _canonical_float(float(ordered[-1])),
    }


def _performance_distribution(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    latencies = [
        float(row["metrics"]["latency_ms_mean"])
        for row in rows
        if row["metrics"]["latency_ms_mean"] is not None
    ]
    throughput = [
        float(row["metrics"]["completion_tokens_per_second"])
        for row in rows
        if row["metrics"]["completion_tokens_per_second"] is not None
    ]
    return {
        "latency_ms_mean": _distribution(latencies),
        "completion_tokens_per_second": _distribution(throughput),
    }


def _hardware_class(hardware: Mapping[str, Any]) -> str:
    execution_mode = hardware["execution_mode"]
    if execution_mode == "cpu_only":
        return "cpu_only"
    if execution_mode not in {"accelerator_only", "hybrid"}:
        return "unknown"
    architecture = hardware["memory"]["architecture"]
    return {
        "shared": "shared_accelerator",
        "discrete": "discrete_accelerator",
        "mixed": "mixed_accelerator",
    }.get(architecture, "unknown")


def _model_size_basis(model: Mapping[str, Any]) -> tuple[str, str]:
    scale = model.get("parameter_scale")
    if not isinstance(scale, Mapping):
        return "unknown", "unknown"
    active = scale.get("active_billions")
    total = scale.get("total_billions")
    if active is not None:
        value = float(active)
        basis = "active_billions"
    elif total is not None:
        value = float(total)
        basis = "total_billions"
    else:
        return "unknown", "unknown"
    if value < 4:
        bucket = "under_4b"
    elif value < 14:
        bucket = "4b_to_under_14b"
    elif value < 35:
        bucket = "14b_to_under_35b"
    elif value < 70:
        bucket = "35b_to_under_70b"
    else:
        bucket = "70b_and_above"
    return bucket, basis


def _plausibility(
    rows: list[Mapping[str, Any]],
    representative: Mapping[str, Any],
) -> dict[str, Any]:
    hardware_class = _hardware_class(representative["hardware"])
    size_bucket, size_basis = _model_size_basis(representative["model"])
    envelope = _PLAUSIBILITY_ENVELOPES.get(hardware_class, {}).get(size_bucket)
    evaluated = 0
    outside = 0
    found_signals: set[str] = set()
    if envelope is not None:
        minimum_latency, maximum_throughput = envelope
        for row in rows:
            metrics = row["metrics"]
            latency = metrics["latency_ms_mean"]
            throughput = metrics["completion_tokens_per_second"]
            if latency is None and throughput is None:
                continue
            evaluated += 1
            row_signals: set[str] = set()
            if latency is not None and float(latency) < minimum_latency:
                row_signals.add("latency_below_envelope")
            if throughput is not None and float(throughput) > maximum_throughput:
                row_signals.add("throughput_above_envelope")
            if row_signals:
                outside += 1
                found_signals.update(row_signals)
    status = (
        "not_evaluated"
        if evaluated == 0
        else "caution" if outside else "within_envelope"
    )
    return {
        "policy_version": _PLAUSIBILITY_POLICY_VERSION,
        "status": status,
        "basis": {
            "hardware_class": hardware_class,
            "model_size_bucket": size_bucket,
            "model_size_basis": size_basis,
        },
        "evaluated_record_count": evaluated,
        "outside_envelope_record_count": outside,
        "signals": [
            signal for signal in _PLAUSIBILITY_SIGNAL_ORDER if signal in found_signals
        ],
    }


def _interval_components(
    rows: list[dict[str, Any]],
    metric: str,
) -> list[list[dict[str, Any]]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            row["score_intervals"][metric]["lower_percent"],
            row["score_intervals"][metric]["upper_percent"],
            row["submission_id"],
        ),
    )
    components: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_upper = -1
    for row in ordered:
        interval = row["score_intervals"][metric]
        if current and interval["lower_percent"] > current_upper:
            components.append(current)
            current = []
            current_upper = -1
        current.append(row)
        current_upper = max(current_upper, interval["upper_percent"])
    if current:
        components.append(current)
    components.reverse()
    return components


def _assign_rank_bands(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bands: list[list[dict[str, Any]]] = []
    for semantic_component in _interval_components(rows, "semantic"):
        bands.extend(_interval_components(semantic_component, "exact_format"))
    entries: list[dict[str, Any]] = []
    for band_number, band in enumerate(bands, start=1):
        for row in sorted(band, key=lambda candidate: candidate["submission_id"]):
            entries.append({**row, "rank": band_number})
    return entries


def _legacy_leaderboard_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        row.pop("_submission_schema_version")
        entries.append({"rank": current_rank, **row})
    return entries


def _versioned_config_cells(
    rows: list[dict[str, Any]],
    facet: FacetSelector,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, bytes], list[dict[str, Any]]] = {}
    digests: dict[tuple[str, str, str, bytes], str] = {}
    for row in rows:
        if "parameter_scale" not in row["model"]:
            row["model"]["parameter_scale"] = {
                "total_billions": None,
                "active_billions": None,
            }
        dimensions = _facet_dimensions(row)
        canonical, digest = _config_key(dimensions)
        scope = (facet.facet_id, row["profile"], row["suite_version"], canonical)
        grouped.setdefault(scope, []).append(row)
        digests[scope] = digest

    cells: list[dict[str, Any]] = []
    for scope, group in grouped.items():
        representative = min(group, key=_representative_key)
        cell = {
            key: copy.deepcopy(value)
            for key, value in representative.items()
            if key != "_submission_schema_version"
        }
        cell.update(
            {
                "facet_id": facet.facet_id,
                "submission_schema_version": representative[
                    "_submission_schema_version"
                ],
                "config_cell": {
                    "key_version": _CONFIG_KEY_VERSION,
                    "selection_version": _CONFIG_SELECTION_VERSION,
                    "digest": digests[scope],
                },
                "corroboration": _corroboration(group),
                "score_intervals": {
                    "method": "wilson_95",
                    "semantic": wilson_interval_95(
                        representative["metrics"]["semantic_pass_count"],
                        representative["metrics"]["scored_case_count"],
                    ),
                    "exact_format": wilson_interval_95(
                        representative["metrics"]["exact_format_pass_count"],
                        representative["metrics"]["scored_case_count"],
                    ),
                },
                "performance_distribution": _performance_distribution(group),
                "plausibility": _plausibility(group, representative),
            }
        )
        cells.append(cell)
    return _assign_rank_bands(cells)


def _validate_derived_metrics(
    value: Any,
    path: str,
    *,
    suite_length: int,
) -> Mapping[str, Any]:
    metrics = _object(
        value,
        {
            "case_count",
            "semantic_pass_count",
            "semantic_score_percent",
            "exact_format_pass_count",
            "exact_format_score_percent",
            "scored_case_count",
            "usage_coverage_cases",
            "latency_ms_mean",
            "completion_tokens_per_second",
        },
        path,
    )
    case_count = _integer(metrics["case_count"], f"{path}.case_count", minimum=1)
    if case_count > suite_length:
        raise SubmissionError(f"{path}.case_count exceeds the resolved suite")
    scored = _integer(
        metrics["scored_case_count"],
        f"{path}.scored_case_count",
        minimum=1,
        maximum=case_count,
    )
    semantic = _integer(
        metrics["semantic_pass_count"],
        f"{path}.semantic_pass_count",
        maximum=scored,
    )
    exact = _integer(
        metrics["exact_format_pass_count"],
        f"{path}.exact_format_pass_count",
        maximum=scored,
    )
    coverage = _integer(
        metrics["usage_coverage_cases"],
        f"{path}.usage_coverage_cases",
        maximum=scored,
    )
    if metrics["semantic_score_percent"] != _score_percent(semantic, scored):
        raise SubmissionError(f"{path}.semantic_score_percent is inconsistent")
    if metrics["exact_format_score_percent"] != _score_percent(exact, scored):
        raise SubmissionError(f"{path}.exact_format_score_percent is inconsistent")
    full_suite = case_count == suite_length
    latency = metrics["latency_ms_mean"]
    throughput = metrics["completion_tokens_per_second"]
    if not full_suite:
        if coverage != 0 or latency is not None or throughput is not None:
            raise SubmissionError(f"{path} relabels unavailable facet performance")
        return metrics
    normalized_latency = _number(latency, f"{path}.latency_ms_mean")
    if round(normalized_latency, 1) != normalized_latency:
        raise SubmissionError(f"{path}.latency_ms_mean must use one decimal")
    if throughput is not None:
        normalized_throughput = _number(
            throughput,
            f"{path}.completion_tokens_per_second",
        )
        if round(normalized_throughput, 1) != normalized_throughput:
            raise SubmissionError(
                f"{path}.completion_tokens_per_second must use one decimal"
            )
        if coverage != scored:
            raise SubmissionError(f"{path} reports throughput with incomplete usage")
    return metrics


def _validate_corroboration(
    value: Any,
    path: str,
    *,
    representative_validity: str,
    representative_period: str | None,
) -> Mapping[str, Any]:
    corroboration = _object(value, {"accepted_record_count", "by_validity"}, path)
    accepted = _integer(
        corroboration["accepted_record_count"],
        f"{path}.accepted_record_count",
        minimum=1,
    )
    by_validity = _object(
        corroboration["by_validity"],
        set(_VALIDITY_SELECTION_ORDER),
        f"{path}.by_validity",
    )
    total = 0
    for validity in _VALIDITY_SELECTION_ORDER:
        summary_path = f"{path}.by_validity.{validity}"
        summary = _object(
            by_validity[validity],
            {"count", "earliest_period", "latest_period"},
            summary_path,
        )
        count = _integer(summary["count"], f"{summary_path}.count")
        earliest = summary["earliest_period"]
        latest = summary["latest_period"]
        if count == 0 or validity == "legacy_unreported":
            if earliest is not None or latest is not None:
                raise SubmissionError(f"{summary_path} has unsupported periods")
        else:
            _validate_measurement_period(earliest, f"{summary_path}.earliest_period")
            _validate_measurement_period(latest, f"{summary_path}.latest_period")
            if earliest > latest:
                raise SubmissionError(f"{summary_path} period range is reversed")
        total += count
    if total != accepted:
        raise SubmissionError(f"{path}.accepted_record_count is inconsistent")
    representative = by_validity[representative_validity]
    if representative["count"] < 1:
        raise SubmissionError(f"{path} omits the representative validity")
    if representative_validity == "legacy_unreported":
        if representative_period is not None:
            raise SubmissionError(f"{path} gives a legacy representative a period")
    elif not (
        representative["earliest_period"]
        <= representative_period
        <= representative["latest_period"]
    ):
        raise SubmissionError(f"{path} does not cover the representative period")
    return corroboration


def _validate_distribution(
    value: Any,
    path: str,
    *,
    maximum_samples: int,
    representative_value: float | None,
) -> Mapping[str, Any]:
    distribution = _object(
        value,
        {"sample_count", "median", "minimum", "maximum"},
        path,
    )
    sample_count = _integer(
        distribution["sample_count"],
        f"{path}.sample_count",
        maximum=maximum_samples,
    )
    statistics = (
        distribution["minimum"],
        distribution["median"],
        distribution["maximum"],
    )
    if sample_count == 0:
        if any(item is not None for item in statistics) or representative_value is not None:
            raise SubmissionError(f"{path} zero-sample distribution is inconsistent")
        return distribution
    normalized = [
        _number(item, f"{path}.{field}", decimal_places=2)
        for item, field in zip(statistics, ("minimum", "median", "maximum"), strict=True)
    ]
    minimum, median, maximum = normalized
    if not minimum <= median <= maximum:
        raise SubmissionError(f"{path} statistics are not ordered")
    if sample_count == 1 and not minimum == median == maximum:
        raise SubmissionError(f"{path} single-sample distribution is inconsistent")
    if sample_count == 2:
        expected_median = (
            Decimal(str(minimum)) + Decimal(str(maximum))
        ) / Decimal(2)
        if Decimal(str(median)) != expected_median:
            raise SubmissionError(f"{path} two-sample median is inconsistent")
    if representative_value is not None and not minimum <= representative_value <= maximum:
        raise SubmissionError(f"{path} excludes the representative value")
    return distribution


def validate_leaderboard_entry(
    value: Mapping[str, Any],
    *,
    registry: Mapping[tuple[str, str], tuple[SuiteCase, ...]] | None = None,
) -> None:
    """Validate one projected schema 1.1 configuration cell."""

    required = {
        "rank",
        "facet_id",
        "config_cell",
        "corroboration",
        "score_intervals",
        "performance_distribution",
        "plausibility",
        "submission_schema_version",
        "submission_id",
        "suite_version",
        "profile",
        "validity",
        "measurement_period",
        "measurement_conditions",
        "hardware",
        "runtime",
        "model",
        "settings",
        "metrics",
    }
    entry = _object_with_optional(
        value,
        required,
        {"runtime_configuration", "determinism"},
        "leaderboard_entry",
    )
    _integer(entry["rank"], "leaderboard_entry.rank", minimum=1)
    if not isinstance(entry["facet_id"], str) or not _FACET_ID.fullmatch(
        entry["facet_id"]
    ):
        raise SubmissionError("leaderboard_entry.facet_id is unsupported")
    if not isinstance(entry["submission_id"], str) or not _HEX_DIGEST.fullmatch(
        entry["submission_id"]
    ):
        raise SubmissionError("leaderboard_entry.submission_id is unsupported")
    profile = _text(entry["profile"], "leaderboard_entry.profile", maximum=128)
    suite_version = _text(
        entry["suite_version"],
        "leaderboard_entry.suite_version",
        maximum=128,
    )
    active_registry = registry
    try:
        suite = (
            active_registry[(profile, suite_version)]
            if active_registry is not None
            else resolve_public_suite(profile, suite_version)
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SubmissionError("leaderboard_entry suite is unsupported") from error

    source_version = entry["submission_schema_version"]
    validity = entry["validity"]
    if source_version == LEGACY_SUBMISSION_SCHEMA_VERSION:
        if (
            validity != "legacy_unreported"
            or entry["measurement_period"] is not None
            or entry["measurement_conditions"] is not None
            or "determinism" in entry
        ):
            raise SubmissionError("leaderboard_entry legacy evidence is inconsistent")
    elif source_version == SUBMISSION_SCHEMA_VERSION:
        if validity not in _PUBLIC_VALIDITIES:
            raise SubmissionError("leaderboard_entry validity is unsupported")
        _validate_measurement_period(
            entry["measurement_period"],
            "leaderboard_entry.measurement_period",
        )
        conditions = _validate_measurement_conditions(
            entry["measurement_conditions"],
            "leaderboard_entry.measurement_conditions",
        )
        if validity != _derived_public_validity(conditions["pre"], conditions["post"]):
            raise SubmissionError("leaderboard_entry validity is inconsistent")
        if "determinism" in entry:
            _validate_determinism(entry["determinism"], "leaderboard_entry.determinism")
    else:
        raise SubmissionError("leaderboard_entry source schema is unsupported")

    environment = {
        "schema_version": "1.0",
        "hardware": entry["hardware"],
        "runtime": entry["runtime"],
    }
    if "runtime_configuration" in entry:
        environment["runtime_configuration"] = entry["runtime_configuration"]
    validate_public_environment(environment)
    model = _validate_model(
        entry["model"],
        "leaderboard_entry.model",
        require_parameter_scale=True,
    )
    _validate_settings(
        entry["settings"],
        "leaderboard_entry.settings",
        context_tokens=int(model["declared_context_tokens"]),
    )
    if "runtime_configuration" in entry:
        configured_context = entry["runtime_configuration"]["context_window_tokens"]
        if (
            configured_context is not None
            and entry["settings"]["max_output_tokens"] > configured_context
        ):
            raise SubmissionError(
                "leaderboard_entry.settings.max_output_tokens exceeds the configured "
                "context window"
            )
    metrics = _validate_derived_metrics(
        entry["metrics"],
        "leaderboard_entry.metrics",
        suite_length=len(suite),
    )

    config_cell = _object(
        entry["config_cell"],
        {"key_version", "selection_version", "digest"},
        "leaderboard_entry.config_cell",
    )
    if (
        config_cell["key_version"] != _CONFIG_KEY_VERSION
        or config_cell["selection_version"] != _CONFIG_SELECTION_VERSION
        or not isinstance(config_cell["digest"], str)
        or not _HEX_DIGEST.fullmatch(config_cell["digest"])
    ):
        raise SubmissionError("leaderboard_entry config cell is unsupported")
    _canonical, expected_digest = _config_key(_facet_dimensions(entry))
    if config_cell["digest"] != expected_digest:
        raise SubmissionError("leaderboard_entry config digest is inconsistent")

    corroboration = _validate_corroboration(
        entry["corroboration"],
        "leaderboard_entry.corroboration",
        representative_validity=validity,
        representative_period=entry["measurement_period"],
    )
    intervals = _object(
        entry["score_intervals"],
        {"method", "semantic", "exact_format"},
        "leaderboard_entry.score_intervals",
    )
    if intervals["method"] != "wilson_95":
        raise SubmissionError("leaderboard_entry score interval method is unsupported")
    for name, count_field in (
        ("semantic", "semantic_pass_count"),
        ("exact_format", "exact_format_pass_count"),
    ):
        interval = _object(
            intervals[name],
            {"lower_percent", "upper_percent"},
            f"leaderboard_entry.score_intervals.{name}",
        )
        expected = wilson_interval_95(
            metrics[count_field],
            metrics["scored_case_count"],
        )
        if dict(interval) != expected:
            raise SubmissionError("leaderboard_entry Wilson interval is inconsistent")

    performance = _object(
        entry["performance_distribution"],
        {"latency_ms_mean", "completion_tokens_per_second"},
        "leaderboard_entry.performance_distribution",
    )
    maximum_samples = corroboration["accepted_record_count"]
    latency = _validate_distribution(
        performance["latency_ms_mean"],
        "leaderboard_entry.performance_distribution.latency_ms_mean",
        maximum_samples=maximum_samples,
        representative_value=metrics["latency_ms_mean"],
    )
    if latency["sample_count"] != (
        0 if metrics["latency_ms_mean"] is None else maximum_samples
    ):
        raise SubmissionError("leaderboard_entry latency sample count is inconsistent")
    throughput = _validate_distribution(
        performance["completion_tokens_per_second"],
        "leaderboard_entry.performance_distribution.completion_tokens_per_second",
        maximum_samples=maximum_samples,
        representative_value=metrics["completion_tokens_per_second"],
    )

    plausibility = _object(
        entry["plausibility"],
        {
            "policy_version",
            "status",
            "basis",
            "evaluated_record_count",
            "outside_envelope_record_count",
            "signals",
        },
        "leaderboard_entry.plausibility",
    )
    expected_hardware = _hardware_class(entry["hardware"])
    expected_bucket, expected_basis = _model_size_basis(entry["model"])
    basis = _object(
        plausibility["basis"],
        {"hardware_class", "model_size_bucket", "model_size_basis"},
        "leaderboard_entry.plausibility.basis",
    )
    if dict(basis) != {
        "hardware_class": expected_hardware,
        "model_size_bucket": expected_bucket,
        "model_size_basis": expected_basis,
    }:
        raise SubmissionError("leaderboard_entry plausibility basis is inconsistent")
    envelope = _PLAUSIBILITY_ENVELOPES.get(expected_hardware, {}).get(expected_bucket)
    expected_signals: list[str] = []
    if envelope is not None:
        minimum_latency, maximum_throughput = envelope
        if latency["sample_count"] and latency["minimum"] < minimum_latency:
            expected_signals.append("latency_below_envelope")
        if throughput["sample_count"] and throughput["maximum"] > maximum_throughput:
            expected_signals.append("throughput_above_envelope")
    evaluated = _integer(
        plausibility["evaluated_record_count"],
        "leaderboard_entry.plausibility.evaluated_record_count",
        maximum=maximum_samples,
    )
    outside = _integer(
        plausibility["outside_envelope_record_count"],
        "leaderboard_entry.plausibility.outside_envelope_record_count",
        maximum=evaluated,
    )
    expected_evaluated = (
        0
        if envelope is None
        else max(latency["sample_count"], throughput["sample_count"])
    )
    expected_status = (
        "not_evaluated" if evaluated == 0 else "caution" if outside else "within_envelope"
    )
    if (
        evaluated != expected_evaluated
        or plausibility["status"] != expected_status
        or plausibility["policy_version"] != _PLAUSIBILITY_POLICY_VERSION
        or plausibility["signals"] != expected_signals
        or bool(outside) != bool(expected_signals)
    ):
        raise SubmissionError("leaderboard_entry plausibility is inconsistent")


def validate_versioned_leaderboard(value: Mapping[str, Any]) -> None:
    """Validate one complete logical schema 1.1 leaderboard and its rank bands."""

    leaderboard = _object(value, {"schema_version", "entry_count", "entries"}, "leaderboard")
    if leaderboard["schema_version"] != LEADERBOARD_SCHEMA_VERSION:
        raise SubmissionError("leaderboard schema version is unsupported")
    entries = leaderboard["entries"]
    if not isinstance(entries, list):
        raise SubmissionError("leaderboard.entries must be a list")
    if _integer(leaderboard["entry_count"], "leaderboard.entry_count") != len(entries):
        raise SubmissionError("leaderboard.entry_count is inconsistent")
    seen_ids: set[str] = set()
    seen_cells: set[tuple[str, str, str, str]] = set()
    for entry in entries:
        validate_leaderboard_entry(entry)
        if entry["submission_id"] in seen_ids:
            raise SubmissionError("leaderboard contains a duplicate representative")
        seen_ids.add(entry["submission_id"])
        scope = (
            entry["facet_id"],
            entry["profile"],
            entry["suite_version"],
            entry["config_cell"]["digest"],
        )
        if scope in seen_cells:
            raise SubmissionError("leaderboard contains a duplicate config cell")
        seen_cells.add(scope)
    unranked = [
        {key: copy.deepcopy(item) for key, item in entry.items() if key != "rank"}
        for entry in entries
    ]
    expected = _assign_rank_bands(unranked)
    if [
        (entry["submission_id"], entry["rank"]) for entry in entries
    ] != [
        (entry["submission_id"], entry["rank"]) for entry in expected
    ]:
        raise SubmissionError("leaderboard rank bands are inconsistent")


def build_leaderboard(
    submissions_dir: str | Path,
    *,
    facet: FacetSelector = DEFAULT_FACET,
) -> dict[str, Any]:
    """Validate accepted records and build one deterministic faceted ranking."""

    _validate_facet_selector(facet)

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
    seen_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    contains_current_submission = False
    contains_subset_projection = False
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise SubmissionError("submission entries must be regular files")
        submission = load_json_object(path)
        validate_accepted_submission(submission)
        submission_id = submission["submission_id"]
        if path.name != f"{submission_id}.json":
            raise SubmissionError("submission filename must match submission_id")
        if submission_id in seen_ids:
            raise SubmissionError("duplicate submission_id")
        seen_ids.add(submission_id)
        is_legacy = submission["schema_version"] == LEGACY_SUBMISSION_SCHEMA_VERSION
        normalized_submission = _normalize_submission_payload(
            {key: value for key, value in submission.items() if key != "submission_id"}
        )
        dimensions = _facet_dimensions(normalized_submission)
        if any(dimensions[name] != expected for name, expected in facet.dimension_filters):
            continue
        try:
            suite = resolve_public_suite(
                submission["profile"],
                submission["suite_version"],
            )
        except ValueError as error:
            raise SubmissionError("accepted submission suite is unsupported") from error
        selected_cases = _facet_cases(normalized_submission, suite, facet)
        scored_cases = [
            case
            for case in selected_cases
            if case["outcome"] not in {"not_scored", "not_applicable"}
        ]
        if not scored_cases:
            continue
        source_metrics = normalized_submission["metrics"]
        case_count = len(selected_cases)
        scored_case_count = len(scored_cases)
        semantic_pass_count = sum(
            case["outcome"] in {"pass", "semantic_only"} for case in scored_cases
        )
        exact_format_pass_count = sum(
            case["outcome"] in {"pass", "format_only"} for case in scored_cases
        )
        full_suite_performance = case_count == len(suite)
        contains_subset_projection = contains_subset_projection or not full_suite_performance
        metrics = {
            **copy.deepcopy(source_metrics),
            "case_count": case_count,
            "semantic_pass_count": semantic_pass_count,
            "exact_format_pass_count": exact_format_pass_count,
            "scored_case_count": scored_case_count,
            # Accepted submissions intentionally retain only full-suite aggregate
            # performance. A strict subset facet cannot reconstruct honest timing
            # or throughput from categorical case outcomes, so omit those values
            # instead of relabeling full-suite measurements as facet measurements.
            "usage_coverage_cases": (
                min(source_metrics["usage_coverage_cases"], scored_case_count)
                if full_suite_performance
                else 0
            ),
            "latency_ms_mean": (
                source_metrics["latency_ms_mean"] if full_suite_performance else None
            ),
            "completion_tokens_per_second": (
                source_metrics["completion_tokens_per_second"]
                if full_suite_performance
                else None
            ),
        }
        leaderboard_metrics = copy.deepcopy(metrics)
        leaderboard_metrics["semantic_score_percent"] = _score_percent(
            semantic_pass_count, scored_case_count
        )
        leaderboard_metrics["exact_format_score_percent"] = _score_percent(
            exact_format_pass_count, scored_case_count
        )
        row = {
            "_submission_schema_version": submission["schema_version"],
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
        if not is_legacy:
            row.update(
                {
                    "validity": normalized_submission["validity"],
                    "measurement_period": normalized_submission["measurement_period"],
                    "measurement_conditions": copy.deepcopy(
                        normalized_submission["measurement_conditions"]
                    ),
                }
            )
            if "determinism" in normalized_submission:
                row["determinism"] = copy.deepcopy(normalized_submission["determinism"])
        contains_current_submission = contains_current_submission or not is_legacy
        rows.append(row)

    versioned_projection = (
        contains_current_submission
        or contains_subset_projection
        or facet != DEFAULT_FACET
    )
    if versioned_projection:
        for row in rows:
            if row["_submission_schema_version"] == LEGACY_SUBMISSION_SCHEMA_VERSION:
                row.update(
                    {
                        "validity": "legacy_unreported",
                        "measurement_period": None,
                        "measurement_conditions": None,
                    }
                )
        entries = _versioned_config_cells(rows, facet)
    else:
        entries = _legacy_leaderboard_rows(rows)
    leaderboard = {
        "schema_version": (
            LEADERBOARD_SCHEMA_VERSION
            if versioned_projection
            else LEGACY_LEADERBOARD_SCHEMA_VERSION
        ),
        "entry_count": len(entries),
        "entries": entries,
    }
    if leaderboard["schema_version"] == LEADERBOARD_SCHEMA_VERSION:
        validate_versioned_leaderboard(leaderboard)
    return leaderboard


def _shard_id(index: int) -> str:
    return f"{index:06d}"


def _leaderboard_shard(
    leaderboard: Mapping[str, Any],
    index: int,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "index_version": LEADERBOARD_INDEX_VERSION,
        "schema_version": leaderboard["schema_version"],
        "shard_id": _shard_id(index),
        "entry_count": len(entries),
        "entries": entries,
    }


def render_leaderboard_shard_bytes(value: Mapping[str, Any]) -> bytes:
    """Render the compact canonical representation used for one transport shard."""

    try:
        rendered = json.dumps(
            value,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise SubmissionError("leaderboard shard is not strict JSON") from error
    return (rendered + "\n").encode("utf-8")


def _compact_entry_size(value: Mapping[str, Any]) -> int:
    return len(render_leaderboard_shard_bytes(value)) - 1


def _projected_shard_size(
    leaderboard: Mapping[str, Any],
    shard_number: int,
    entry_count: int,
    compact_entry_bytes: int,
) -> int:
    envelope = {
        "index_version": LEADERBOARD_INDEX_VERSION,
        "schema_version": leaderboard["schema_version"],
        "shard_id": _shard_id(shard_number),
        "entry_count": entry_count,
        "entries": [],
    }
    separators = max(0, entry_count - 1)
    return len(render_leaderboard_shard_bytes(envelope)) + compact_entry_bytes + separators


def build_leaderboard_bundle(
    leaderboard: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    """Partition one logical leaderboard into a bounded index and shard payloads."""

    if set(leaderboard) != {"schema_version", "entry_count", "entries"}:
        raise SubmissionError("leaderboard has an unsupported transport contract")
    schema_version = leaderboard["schema_version"]
    entry_count = leaderboard["entry_count"]
    entries = leaderboard["entries"]
    if (
        schema_version not in {
            LEGACY_LEADERBOARD_SCHEMA_VERSION,
            LEADERBOARD_SCHEMA_VERSION,
        }
        or isinstance(entry_count, bool)
        or not isinstance(entry_count, int)
        or entry_count < 0
        or not isinstance(entries, list)
        or len(entries) != entry_count
    ):
        raise SubmissionError("leaderboard has an unsupported transport contract")

    shards: list[dict[str, Any]] = []
    current_entries: list[dict[str, Any]] = []
    current_entry_bytes = 0
    for entry in entries:
        entry_bytes = _compact_entry_size(entry)
        shard_number = len(shards) + 1
        candidate_count = len(current_entries) + 1
        candidate_entry_bytes = current_entry_bytes + entry_bytes
        candidate_size = _projected_shard_size(
            leaderboard,
            shard_number,
            candidate_count,
            candidate_entry_bytes,
        )
        if candidate_size <= _MAX_DATA_FILE_BYTES:
            current_entries.append(entry)
            current_entry_bytes = candidate_entry_bytes
            continue
        if not current_entries:
            raise SubmissionError("one leaderboard entry exceeds the site data file limit")
        shards.append(_leaderboard_shard(leaderboard, shard_number, current_entries))
        current_entries = [entry]
        current_entry_bytes = entry_bytes
        if (
            _projected_shard_size(
                leaderboard,
                shard_number + 1,
                1,
                current_entry_bytes,
            )
            > _MAX_DATA_FILE_BYTES
        ):
            raise SubmissionError("one leaderboard entry exceeds the site data file limit")
    if current_entries:
        shards.append(
            _leaderboard_shard(leaderboard, len(shards) + 1, current_entries)
        )

    for shard in shards:
        if len(render_leaderboard_shard_bytes(shard)) > _MAX_DATA_FILE_BYTES:
            raise SubmissionError("generated leaderboard shard exceeds the site data file limit")

    index = {
        "index_version": LEADERBOARD_INDEX_VERSION,
        "schema_version": schema_version,
        "entry_count": entry_count,
        "shard_count": len(shards),
    }
    if len(render_leaderboard_bytes(index)) > _MAX_DATA_FILE_BYTES:
        raise SubmissionError("leaderboard index exceeds the site data file limit")
    return index, tuple(shards)


def build_persisted_leaderboard(leaderboard: Mapping[str, Any]) -> dict[str, Any]:
    """Use the legacy monolith while bounded, then switch to the compact index."""

    try:
        encoder = json.JSONEncoder(
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        rendered_size = 1
        for chunk in encoder.iterencode(leaderboard):
            rendered_size += len(chunk)
            if rendered_size > _MAX_DATA_FILE_BYTES:
                break
    except (TypeError, ValueError) as error:
        raise SubmissionError("leaderboard is not strict JSON") from error
    if rendered_size <= _MAX_DATA_FILE_BYTES:
        return copy.deepcopy(dict(leaderboard))
    index, _shards = build_leaderboard_bundle(leaderboard)
    return index


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


def _write_leaderboard_bytes(rendered: bytes, output: str | Path) -> None:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.is_symlink() or not destination.parent.is_dir():
        raise SubmissionError("leaderboard output directory must be a regular directory")
    if len(rendered) > _MAX_DATA_FILE_BYTES:
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


def write_leaderboard(leaderboard: Mapping[str, Any], output: str | Path) -> None:
    """Replace one bounded generated static-data file atomically."""

    _write_leaderboard_bytes(render_leaderboard_bytes(leaderboard), output)


def write_leaderboard_bundle(
    leaderboard: Mapping[str, Any],
    output_dir: str | Path,
) -> tuple[Path, tuple[Path, ...]]:
    """Write a bounded static index and deterministic ordinal shards."""

    destination = Path(output_dir)
    index, shards = build_leaderboard_bundle(leaderboard)
    index_bytes = render_leaderboard_bytes(index)
    if destination.exists():
        if destination.is_symlink() or not destination.is_dir():
            raise SubmissionError("leaderboard bundle directory must be a regular directory")
        try:
            if any(destination.iterdir()):
                raise SubmissionError("leaderboard bundle directory must be empty")
        except OSError as error:
            raise SubmissionError("leaderboard bundle directory could not be inspected") from error
    else:
        try:
            destination.mkdir(parents=True)
        except OSError as error:
            raise SubmissionError("leaderboard bundle directory could not be created") from error
    index_path = destination / "leaderboard.json"
    _write_leaderboard_bytes(index_bytes, index_path)
    shard_paths: list[Path] = []
    for shard in shards:
        path = destination / f"leaderboard-{shard['shard_id']}.json"
        _write_leaderboard_bytes(render_leaderboard_shard_bytes(shard), path)
        shard_paths.append(path)
    return index_path, tuple(shard_paths)
