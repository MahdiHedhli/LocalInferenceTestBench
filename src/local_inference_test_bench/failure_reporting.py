"""Build identifier-minimized, opt-in benchmark failure issue drafts."""

from __future__ import annotations

from dataclasses import dataclass
import json
import platform
import re
import sys
from typing import Any, Mapping
from urllib.parse import urlencode

from . import __version__
from .reporting import ReportError, _walk_safe
from .submissions import (
    SubmissionError,
    _descriptor_text,
    validate_public_environment,
)


ISSUE_BASE_URL = (
    "https://github.com/MahdiHedhli/LITB/issues/new"
)
FAILURE_DRAFT_SCHEMA_VERSION = "1.0"

ELIGIBLE_FAILURE_CATEGORIES = frozenset(
    {
        "timeout",
        "network_error",
        "server_error",
        "http_error",
        "request_rejected",
        "invalid_json",
        "protocol_error",
        "response_too_large",
        "internal_harness_error",
    }
)
REPORT_FAILURE_PRIORITY = (
    "response_too_large",
    "invalid_json",
    "protocol_error",
    "server_error",
    "request_rejected",
    "timeout",
    "network_error",
    "http_error",
)
FAILURE_PHASES = frozenset({"preflight", "case_execution", "runner_internal"})

_DRAFT_KEYS = {
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
_RUNTIME_KEYS = {"name", "version", "backend"}
_PROFILES = frozenset({"smoke", "standard"})
_SUITE_VERSIONS = frozenset({"1.0"})
_OS_FAMILIES = frozenset({"macos", "linux", "windows", "other"})
_PYTHON_SERIES = frozenset(
    {"python_3_11", "python_3_12", "python_3_13", "python_3_14", "other"}
)
_ARCHITECTURES = frozenset({"arm64", "x86_64", "other"})
_HARDWARE_CLASSES = frozenset(
    {
        "cpu_only",
        "shared_accelerator",
        "discrete_accelerator",
        "mixed_accelerator",
        "unknown",
    }
)
_SEMANTIC_VERSION = re.compile(
    r"[0-9]+[.][0-9]+[.][0-9]+(?:[-+][A-Za-z0-9.-]+)?"
)
_UNKNOWN_RUNTIME = {"name": "unknown", "version": "unknown", "backend": "unknown"}


@dataclass(frozen=True, slots=True)
class FailureSignal:
    """A closed compatibility signal that contains no failure detail."""

    phase: str
    failure_category: str

    def __post_init__(self) -> None:
        if not isinstance(self.phase, str) or self.phase not in FAILURE_PHASES:
            raise ValueError("failure signal phase is unsupported")
        if (
            not isinstance(self.failure_category, str)
            or self.failure_category not in ELIGIBLE_FAILURE_CATEGORIES
        ):
            raise ValueError("failure signal category is unsupported")
        internal = self.failure_category == "internal_harness_error"
        if internal != (self.phase == "runner_internal"):
            raise ValueError("failure signal phase and category are inconsistent")


def detect_report_failure(report: object) -> FailureSignal | None:
    """Select one eligible case termination without retaining case identity."""

    if not isinstance(report, Mapping):
        return None
    present: set[str] = set()
    models = report.get("models")
    if not isinstance(models, list):
        return None
    for model in models:
        if not isinstance(model, Mapping):
            continue
        cases = model.get("cases")
        if not isinstance(cases, list):
            continue
        for case in cases:
            if not isinstance(case, Mapping):
                continue
            termination = case.get("termination")
            if termination in REPORT_FAILURE_PRIORITY:
                present.add(str(termination))
    for category in REPORT_FAILURE_PRIORITY:
        if category in present:
            return FailureSignal(
                phase="case_execution",
                failure_category=category,
            )
    return None


def _platform_value(getter) -> str:  # noqa: ANN001
    try:
        value = getter()
    except Exception:
        return ""
    return value if isinstance(value, str) else ""


def _os_family() -> str:
    return {
        "darwin": "macos",
        "linux": "linux",
        "windows": "windows",
    }.get(_platform_value(platform.system).strip().casefold(), "other")


def _architecture() -> str:
    value = _platform_value(platform.machine).strip().casefold()
    if value in {"arm64", "aarch64"}:
        return "arm64"
    if value in {"x86_64", "amd64", "x64"}:
        return "x86_64"
    return "other"


def _python_series() -> str:
    major = getattr(sys.version_info, "major", None)
    minor = getattr(sys.version_info, "minor", None)
    candidate = f"python_{major}_{minor}"
    return candidate if candidate in _PYTHON_SERIES else "other"


def _project_environment(
    value: Mapping[str, Any] | None,
) -> tuple[str, dict[str, str]]:
    if value is None:
        return "unknown", dict(_UNKNOWN_RUNTIME)
    try:
        validate_public_environment(value)
        hardware = value["hardware"]
        runtime = value["runtime"]
        execution_mode = hardware["execution_mode"]
        if execution_mode == "cpu_only":
            hardware_class = "cpu_only"
        else:
            hardware_class = {
                "shared": "shared_accelerator",
                "discrete": "discrete_accelerator",
                "mixed": "mixed_accelerator",
            }.get(hardware["memory"]["architecture"], "unknown")
        projected_runtime = {
            "name": runtime["name"],
            "version": runtime["version"],
            "backend": runtime["backend"],
        }
    except Exception:
        return "unknown", dict(_UNKNOWN_RUNTIME)
    return hardware_class, projected_runtime


def build_failure_draft(
    signal: FailureSignal,
    *,
    profile: str,
    suite_version: str,
    public_environment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create the complete closed draft shown before browser consent."""

    if not isinstance(signal, FailureSignal):
        raise ValueError("failure signal is invalid")
    hardware_class, runtime = _project_environment(public_environment)
    draft: dict[str, Any] = {
        "schema_version": FAILURE_DRAFT_SCHEMA_VERSION,
        "report_type": "benchmark_execution_failure",
        "litb_version": __version__,
        "command": "run",
        "profile": profile,
        "suite_version": suite_version,
        "phase": signal.phase,
        "failure_category": signal.failure_category,
        "os_family": _os_family(),
        "python_series": _python_series(),
        "architecture": _architecture(),
        "hardware_class": hardware_class,
        "runtime": runtime,
    }
    validate_failure_draft(draft)
    return draft


def validate_failure_draft(value: Mapping[str, Any]) -> None:
    """Validate the exact identifier-minimized issue-draft contract."""

    if not isinstance(value, Mapping) or set(value) != _DRAFT_KEYS:
        raise ValueError("failure draft has an unsupported object contract")
    fixed = {
        "schema_version": FAILURE_DRAFT_SCHEMA_VERSION,
        "report_type": "benchmark_execution_failure",
        "command": "run",
    }
    for key, expected in fixed.items():
        if value[key] != expected:
            raise ValueError(f"failure draft {key} is unsupported")
    version = value["litb_version"]
    if (
        not isinstance(version, str)
        or len(version) > 32
        or _SEMANTIC_VERSION.fullmatch(version) is None
    ):
        raise ValueError("failure draft litb_version is unsupported")
    enums = {
        "profile": _PROFILES,
        "suite_version": _SUITE_VERSIONS,
        "phase": FAILURE_PHASES,
        "failure_category": ELIGIBLE_FAILURE_CATEGORIES,
        "os_family": _OS_FAMILIES,
        "python_series": _PYTHON_SERIES,
        "architecture": _ARCHITECTURES,
        "hardware_class": _HARDWARE_CLASSES,
    }
    for key, choices in enums.items():
        if not isinstance(value[key], str) or value[key] not in choices:
            raise ValueError(f"failure draft {key} is unsupported")
    FailureSignal(
        phase=value["phase"],
        failure_category=value["failure_category"],
    )
    runtime = value["runtime"]
    if not isinstance(runtime, Mapping) or set(runtime) != _RUNTIME_KEYS:
        raise ValueError("failure draft runtime has an unsupported object contract")
    for key in sorted(_RUNTIME_KEYS):
        try:
            _descriptor_text(
                runtime[key],
                f"failure draft runtime.{key}",
                maximum=100,
            )
        except SubmissionError as error:
            raise ValueError("failure draft runtime text is unsupported") from error
    try:
        _walk_safe(runtime, "failure_draft.runtime")
    except ReportError as error:
        raise ValueError("failure draft runtime text is unsupported") from error


def _canonical_draft(value: Mapping[str, Any]) -> str:
    validate_failure_draft(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def render_issue_body(draft: Mapping[str, Any]) -> str:
    """Render a bounded deterministic body containing only the validated draft."""

    canonical = _canonical_draft(draft)
    body = (
        "## Sanitized benchmark execution compatibility signal\n\n"
        "This is a self-reported execution failure, not a model score or attestation. "
        "No raw logs, prompts, responses, endpoints, credentials, or host identifiers "
        "are included.\n\n"
        "```json\n"
        f"{canonical}\n"
        "```\n"
    )
    if len(body.encode("utf-8")) > 4096:
        raise ValueError("failure issue body exceeds its size limit")
    return body


def build_issue_url(draft: Mapping[str, Any]) -> str:
    """Build the one fixed-origin GitHub issue-composer URL."""

    validate_failure_draft(draft)
    title = (
        "Benchmark execution failure: "
        f"{draft['phase']}/{draft['failure_category']}"
    )
    if not title.isascii() or len(title) > 120:
        raise ValueError("failure issue title exceeds its size limit")
    body = render_issue_body(draft)
    query = urlencode((("title", title), ("body", body)))
    url = f"{ISSUE_BASE_URL}?{query}"
    if len(url.encode("utf-8")) > 8192:
        raise ValueError("failure issue URL exceeds its size limit")
    return url
