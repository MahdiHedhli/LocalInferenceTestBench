"""Versioned benchmark-suite metadata shared by reports and public submissions."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping


CAPABILITIES = frozenset(
    {
        "structured_output",
        "coding",
        "agent_tool_use",
        "cyber_triage",
        "safety_boundary",
    }
)
MODALITIES = frozenset({"text", "vision"})
_CASE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


@dataclass(frozen=True, slots=True)
class SuiteCase:
    """Public metadata for one ordered, rule-scored benchmark case."""

    case_id: str
    capability: str
    modality: str = "text"

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not _CASE_ID.fullmatch(self.case_id):
            raise ValueError("suite case id is unsupported")
        if self.capability not in CAPABILITIES:
            raise ValueError("suite case capability is unsupported")
        if self.modality not in MODALITIES:
            raise ValueError("suite case modality is unsupported")


STANDARD_1_0_CASES = (
    SuiteCase("structured-json", "structured_output"),
    SuiteCase("python-ast", "coding"),
    SuiteCase("defensive-triage", "cyber_triage"),
    SuiteCase("read-only-tool", "agent_tool_use"),
    SuiteCase("unapproved-change-boundary", "safety_boundary"),
)

# This is the public submission registry. Adding another suite definition here is
# sufficient for the Python validators and exporter to resolve its ordered cases.
PUBLIC_SUITE_REGISTRY: dict[tuple[str, str], tuple[SuiteCase, ...]] = {
    ("standard", "1.0"): STANDARD_1_0_CASES,
}

# Smoke is a local run profile, not a public leaderboard suite. Keeping it out of
# PUBLIC_SUITE_REGISTRY preserves the complete-standard-run submission boundary.
_LOCAL_REPORT_SUITES: Mapping[tuple[str, str], tuple[SuiteCase, ...]] = {
    ("smoke", "1.0"): STANDARD_1_0_CASES[:3],
}


def _validated_suite(suite: object) -> tuple[SuiteCase, ...]:
    if (
        not isinstance(suite, tuple)
        or not suite
        or any(not isinstance(case, SuiteCase) for case in suite)
    ):
        raise ValueError("benchmark suite definition is unsupported")
    case_ids = [case.case_id for case in suite]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("benchmark suite case ids must be unique")
    return suite


def resolve_public_suite(profile: str, suite_version: str) -> tuple[SuiteCase, ...]:
    """Resolve one public suite by registry membership."""

    try:
        suite = PUBLIC_SUITE_REGISTRY[(profile, suite_version)]
    except KeyError as error:
        raise ValueError("public benchmark suite is unsupported") from error
    return _validated_suite(suite)


def resolve_report_suite(profile: str, suite_version: str) -> tuple[SuiteCase, ...]:
    """Resolve a local report suite, including public suites and the smoke lane."""

    key = (profile, suite_version)
    if key in PUBLIC_SUITE_REGISTRY:
        return _validated_suite(PUBLIC_SUITE_REGISTRY[key])
    try:
        suite = _LOCAL_REPORT_SUITES[key]
    except KeyError as error:
        raise ValueError("benchmark report suite is unsupported") from error
    return _validated_suite(suite)
