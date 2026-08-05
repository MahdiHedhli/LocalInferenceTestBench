"""Aggregate-only report validation and secure, append-only persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import getpass
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
from typing import Any, Mapping
from urllib.parse import urlsplit
import uuid

from .safety import SafetyError, secure_directory


class ReportError(ValueError):
    """Raised when a report could violate the public data-minimization contract."""


_FORBIDDEN_KEYS = {
    "api_key",
    "authorization",
    "completion",
    "content",
    "endpoint",
    "environment",
    "headers",
    "hostname",
    "machine",
    "messages",
    "platform",
    "prompt",
    "raw",
    "reasoning",
    "response",
    "secret",
    "token_text",
    "tool_arguments",
    "tool_args",
}
_ROOT_HOME = "/" + "ro" + "ot"
_HOME_PATH = re.compile(
    r"(?i)(?:^|\s)(?:/(?:Users|home)/[^/\s]+|"
    + re.escape(_ROOT_HOME)
    + r"(?:/|\b)|[A-Za-z]:[\\/]Users[\\/][^\\/\s]+)"
)
_IPV4_CANDIDATE = re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])")
_IPV6_CANDIDATE = re.compile(
    r"(?i)(?<![0-9a-f:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}"
    r"(?:%[a-z0-9_.-]+)?(?![0-9a-f:])"
)
_MAC_COLON_OR_HYPHEN = re.compile(
    r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])"
)
_MAC_DOTTED = re.compile(
    r"(?i)(?<![0-9a-f])(?:[0-9a-f]{4}\.){2}[0-9a-f]{4}(?![0-9a-f])"
)
_PRIVATE_HOST = re.compile(
    r"(?i)(?<![a-z0-9_-])"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:lan|local|internal|home|corp|private|localdomain|home\.arpa)\.?"
    r"(?![a-z0-9_.-])"
)
_PRIVATE_KEY_HEADER = re.compile(
    r"-{5}BEGIN(?: [A-Z0-9]+)*(?: PRIVATE KEY| PRIVATE KEY BLOCK)-{5}",
    re.IGNORECASE,
)
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)(?:^|[\s,{;])[\"']?(?:[a-z0-9]+[_-])*(?:api[_-]?key|access[_-]?token|"
    r"auth[_-]?token|bearer[_-]?token|client[_-]?secret|connection[_-]?string|credential|"
    r"password|passwd|private[_-]?key|secret|token)[\"']?\s*(?::|=)\s*\S+"
)
_EXPERIMENT_ONLY_NAMES = ("op" + "ik", "poly" + "range")
_LOCAL_HOST_NAME = "local" + "host"
_GENERIC_ACCOUNT_NAMES = {
    "admin",
    "administrator",
    "nobody",
    "root",
    "runner",
    "ubuntu",
    "user",
}
_PUBLIC_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_VALIDITIES = {"valid", "limited", "invalid"}
_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}
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
_PROFILE_CASE_IDS = {
    "smoke": ("structured-json", "python-ast", "defensive-triage"),
    "standard": (
        "structured-json",
        "python-ast",
        "defensive-triage",
        "read-only-tool",
        "unapproved-change-boundary",
    ),
}


def _contains_private_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return parsed.hostname.lower() in {"localhost"} or parsed.hostname.lower().endswith(".local")
    return _is_rejected_ip(address)


def _is_rejected_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    value = int(address)
    if isinstance(address, ipaddress.IPv4Address):
        ranges = (
            (0, 0),
            (10 << 24, (11 << 24) - 1),
            ((172 << 24) | (16 << 16), (172 << 24) | (31 << 16) | 0xFFFF),
            ((192 << 24) | (168 << 16), (192 << 24) | (168 << 16) | 0xFFFF),
            ((100 << 24) | (64 << 16), (100 << 24) | (127 << 16) | 0xFFFF),
            ((169 << 24) | (254 << 16), (169 << 24) | (254 << 16) | 0xFFFF),
            (127 << 24, (128 << 24) - 1),
        )
        return any(start <= value <= end for start, end in ranges)
    return value in {0, 1} or value >> 121 == 0x7E or value >> 118 == 0x3FA


def _contains_rejected_address(value: str) -> bool:
    for candidate in _IPV4_CANDIDATE.finditer(value):
        try:
            if _is_rejected_ip(ipaddress.IPv4Address(candidate.group(0))):
                return True
        except ipaddress.AddressValueError:
            continue
    for candidate in _IPV6_CANDIDATE.finditer(value):
        try:
            address = ipaddress.IPv6Address(candidate.group(0).split("%", 1)[0])
        except ipaddress.AddressValueError:
            continue
        if _is_rejected_ip(address):
            return True
    return False


@lru_cache(maxsize=1)
def _runtime_identifiers() -> tuple[str, ...]:
    candidates: set[str] = set()
    try:
        home = os.fspath(Path.home())
    except (OSError, RuntimeError):
        home = ""
    if home and home not in {"/", "."}:
        candidates.add(home)
    try:
        username = getpass.getuser().strip()
    except (ImportError, KeyError, OSError):
        username = ""
    if username and username.casefold() not in _GENERIC_ACCOUNT_NAMES:
        candidates.add(username)
    # getfqdn() can block on resolver configuration. The kernel-provided
    # hostname is local and immediate; private DNS aliases belong in the
    # required local denylist.
    try:
        hostname = socket.gethostname().strip().rstrip(".")
    except OSError:
        hostname = ""
    if hostname and hostname.casefold() not in {"localhost", "localhost.localdomain"}:
        candidates.add(hostname)
        candidates.add(hostname.split(".", 1)[0])
    return tuple(candidate for candidate in candidates if len(candidate) >= 3)


@lru_cache(maxsize=1)
def _local_denylist_terms() -> tuple[str, ...]:
    denylist = Path(".local") / "privacy-denylist.txt"
    try:
        if denylist.is_symlink() or not denylist.is_file():
            return ()
        lines = denylist.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return ()
    return tuple(
        dict.fromkeys(
            line.strip()
            for line in lines
            if line.strip() and not line.strip().startswith("#")
        )
    )


def _contains_literal(value: str, candidate: str) -> bool:
    escaped = re.escape(candidate)
    if candidate[0].isalnum() and candidate[-1].isalnum():
        escaped = rf"(?<![A-Za-z0-9_.-]){escaped}(?![A-Za-z0-9_.-])"
    return re.search(escaped, value, flags=re.IGNORECASE) is not None


def _walk_safe(value: Any, path: str = "report") -> None:
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        if (
            _HOME_PATH.search(value)
            or _contains_rejected_address(value)
            or _contains_private_url(value)
            or _MAC_COLON_OR_HYPHEN.search(value)
            or _MAC_DOTTED.search(value)
            or _PRIVATE_HOST.search(value)
            or _PRIVATE_KEY_HEADER.search(value)
            or _CREDENTIAL_ASSIGNMENT.search(value)
            or any(_contains_literal(value, name) for name in _EXPERIMENT_ONLY_NAMES)
            or _contains_literal(value, _LOCAL_HOST_NAME)
            or any(_contains_literal(value, identifier) for identifier in _runtime_identifiers())
            or any(_contains_literal(value, term) for term in _local_denylist_terms())
        ):
            raise ReportError(f"{path} contains a prohibited local identifier")
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ReportError(f"{path} contains a non-string field name")
            if key.lower() in _FORBIDDEN_KEYS:
                raise ReportError(f"{path} contains prohibited field {key}")
            _walk_safe(nested, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _walk_safe(nested, f"{path}[{index}]")
        return
    raise ReportError(f"{path} contains a non-serializable value")


def _object(value: Any, keys: set[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ReportError(f"{path} has an unsupported object contract")
    return value


def _string(value: Any, path: str, *, maximum: int = 500) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise ReportError(f"{path} must be a bounded non-empty string")
    return value


def _public_id(value: Any, path: str) -> str:
    result = _string(value, path, maximum=128)
    if not _PUBLIC_ID.fullmatch(result):
        raise ReportError(f"{path} must be a public identifier")
    return result


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ReportError(f"{path} must be an integer of at least {minimum}")
    return value


def _nullable_integer(value: Any, path: str) -> int | None:
    if value is None:
        return None
    return _integer(value, path)


def _number(value: Any, path: str, *, minimum: float = 0.0) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < minimum
    ):
        raise ReportError(f"{path} must be a finite number of at least {minimum}")
    return float(value)


def _nullable_number(value: Any, path: str) -> float | None:
    if value is None:
        return None
    return _number(value, path)


def _enum(value: Any, allowed: set[str], path: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ReportError(f"{path} has an unsupported category")
    return value


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ReportError(f"{path} must be boolean")
    return value


def _validate_settings(value: Any, path: str) -> int:
    required = {"temperature", "top_p", "max_output_tokens", "seed"}
    if (
        not isinstance(value, Mapping)
        or not required.issubset(value)
        or not set(value).issubset(required | {"reasoning_effort"})
    ):
        raise ReportError(f"{path} has an unsupported object contract")
    settings = value
    temperature = _number(settings["temperature"], f"{path}.temperature")
    if temperature > 2:
        raise ReportError(f"{path}.temperature exceeds the supported maximum")
    top_p = _number(settings["top_p"], f"{path}.top_p")
    if top_p <= 0 or top_p > 1:
        raise ReportError(f"{path}.top_p is outside the supported range")
    maximum = _integer(
        settings["max_output_tokens"], f"{path}.max_output_tokens", minimum=1
    )
    if settings["seed"] is not None:
        _integer(settings["seed"], f"{path}.seed", minimum=-(2**63))
    if "reasoning_effort" in settings:
        _enum(
            settings["reasoning_effort"],
            _REASONING_EFFORTS,
            f"{path}.reasoning_effort",
        )
    return maximum


def _validate_provenance(value: Any, path: str) -> int:
    if not isinstance(value, Mapping):
        raise ReportError(f"{path} must be an object")
    base_keys = {
        "display_name",
        "source",
        "precision",
        "declared_context_tokens",
    }
    revision_keys = set(value) - base_keys
    if revision_keys not in ({"revision"}, {"digest"}):
        raise ReportError(f"{path} must contain exactly one public revision identifier")
    provenance = _object(value, base_keys | revision_keys, path)
    _string(provenance["display_name"], f"{path}.display_name")
    _string(provenance["source"], f"{path}.source")
    _string(provenance["precision"], f"{path}.precision")
    context_tokens = _integer(
        provenance["declared_context_tokens"],
        f"{path}.declared_context_tokens",
        minimum=1,
    )
    revision_field = next(iter(revision_keys))
    _string(provenance[revision_field], f"{path}.{revision_field}", maximum=200)
    return context_tokens


def _validate_usage(value: Any, path: str) -> Mapping[str, int | None]:
    usage = _object(
        value,
        {"prompt_tokens", "completion_tokens", "total_tokens"},
        path,
    )
    for field in usage:
        _nullable_integer(usage[field], f"{path}.{field}")
    return usage


def _validate_case(value: Any, path: str) -> Mapping[str, Any]:
    case = _object(
        value,
        {
            "case_id",
            "semantic_success",
            "exact_format",
            "outcome",
            "route",
            "reasoning_present",
            "latency_ms",
            "completion_tokens_per_second",
            "usage",
            "termination",
        },
        path,
    )
    _public_id(case["case_id"], f"{path}.case_id")
    semantic = _boolean(case["semantic_success"], f"{path}.semantic_success")
    exact = _boolean(case["exact_format"], f"{path}.exact_format")
    outcome = _enum(case["outcome"], _OUTCOMES, f"{path}.outcome")
    route = _enum(case["route"], _ROUTES, f"{path}.route")
    reasoning_present = _boolean(case["reasoning_present"], f"{path}.reasoning_present")
    latency = _number(case["latency_ms"], f"{path}.latency_ms")
    rate = _nullable_number(
        case["completion_tokens_per_second"],
        f"{path}.completion_tokens_per_second",
    )
    usage = _validate_usage(case["usage"], f"{path}.usage")
    termination = _enum(case["termination"], _TERMINATIONS, f"{path}.termination")

    expected_flags = {
        "pass": (True, True),
        "semantic_only": (True, False),
        "format_only": (False, True),
        "fail": (False, False),
        "not_scored": (False, False),
    }
    if (semantic, exact) != expected_flags[outcome]:
        raise ReportError(f"{path} outcome is inconsistent with its categorical checks")
    if route == "unsafe_mutation" and semantic:
        raise ReportError(f"{path} cannot pass after an unsafe mutation route")
    if termination == "reasoning_only" and not reasoning_present:
        raise ReportError(f"{path} reasoning-only termination requires reasoning presence")
    completion_tokens = usage["completion_tokens"]
    expected_rate = (
        round(completion_tokens / (latency / 1000.0), 3)
        if completion_tokens is not None and latency > 0
        else None
    )
    if rate is None or expected_rate is None:
        if rate is not expected_rate:
            raise ReportError(f"{path} throughput is arithmetically inconsistent")
    elif not _approximately_equal(rate, expected_rate):
        raise ReportError(f"{path} throughput is arithmetically inconsistent")
    return case


def _approximately_equal(first: float, second: float) -> bool:
    return abs(first - second) <= 0.001


def _validate_summary(value: Any, cases: list[Mapping[str, Any]], path: str) -> None:
    summary = _object(
        value,
        {
            "case_count",
            "semantic_pass_count",
            "exact_format_pass_count",
            "scored_case_count",
            "latency_ms_total",
            "latency_ms_mean",
            "completion_tokens_per_second_weighted",
            "usage_coverage_cases",
            "prompt_tokens_total",
            "completion_tokens_total",
            "tokens_total",
        },
        path,
    )
    integer_fields = {
        "case_count": len(cases),
        "semantic_pass_count": sum(case["semantic_success"] for case in cases),
        "exact_format_pass_count": sum(case["exact_format"] for case in cases),
        "scored_case_count": sum(case["outcome"] != "not_scored" for case in cases),
    }
    complete_usage = [
        all(case["usage"][field] is not None for field in case["usage"])
        for case in cases
    ]
    integer_fields["usage_coverage_cases"] = sum(complete_usage)
    for field, expected in integer_fields.items():
        if _integer(summary[field], f"{path}.{field}") != expected:
            raise ReportError(f"{path}.{field} is arithmetically inconsistent")

    latency_total = round(sum(float(case["latency_ms"]) for case in cases), 3)
    latency_mean = round(latency_total / len(cases), 3) if cases else 0.0
    if not _approximately_equal(
        _number(summary["latency_ms_total"], f"{path}.latency_ms_total"), latency_total
    ):
        raise ReportError(f"{path}.latency_ms_total is arithmetically inconsistent")
    if not _approximately_equal(
        _number(summary["latency_ms_mean"], f"{path}.latency_ms_mean"), latency_mean
    ):
        raise ReportError(f"{path}.latency_ms_mean is arithmetically inconsistent")

    total_fields = {
        "prompt_tokens_total": "prompt_tokens",
        "completion_tokens_total": "completion_tokens",
        "tokens_total": "total_tokens",
    }
    complete = bool(cases) and all(complete_usage)
    for summary_field, usage_field in total_fields.items():
        recorded = _nullable_integer(summary[summary_field], f"{path}.{summary_field}")
        expected = sum(case["usage"][usage_field] for case in cases) if complete else None
        if recorded != expected:
            raise ReportError(f"{path}.{summary_field} is arithmetically inconsistent")

    recorded_rate = _nullable_number(
        summary["completion_tokens_per_second_weighted"],
        f"{path}.completion_tokens_per_second_weighted",
    )
    completion_total = summary["completion_tokens_total"]
    expected_rate = (
        round(completion_total / (latency_total / 1000.0), 3)
        if completion_total is not None and latency_total > 0
        else None
    )
    if recorded_rate is None or expected_rate is None:
        if recorded_rate is not expected_rate:
            raise ReportError(f"{path}.completion_tokens_per_second_weighted is inconsistent")
    elif not _approximately_equal(recorded_rate, expected_rate):
        raise ReportError(f"{path}.completion_tokens_per_second_weighted is inconsistent")


def _validate_model(value: Any, path: str, expected_case_ids: tuple[str, ...]) -> str:
    model = _object(
        value,
        {
            "model_id",
            "provenance",
            "settings",
            "preflight",
            "runtime_identity_match",
            "validity",
            "summary",
            "cases",
        },
        path,
    )
    _public_id(model["model_id"], f"{path}.model_id")
    context_tokens = _validate_provenance(model["provenance"], f"{path}.provenance")
    maximum_output = _validate_settings(model["settings"], f"{path}.settings")
    if maximum_output > context_tokens:
        raise ReportError(f"{path} output budget exceeds declared context")
    preflight = _enum(
        model["preflight"], {"verified", "metadata_unavailable"}, f"{path}.preflight"
    )
    identity_match = _boolean(
        model["runtime_identity_match"], f"{path}.runtime_identity_match"
    )
    validity = _enum(model["validity"], _VALIDITIES, f"{path}.validity")
    raw_cases = model["cases"]
    if not isinstance(raw_cases, list):
        raise ReportError(f"{path}.cases must be an array")
    cases = [_validate_case(case, f"{path}.cases[{index}]") for index, case in enumerate(raw_cases)]
    if tuple(case["case_id"] for case in cases) != expected_case_ids:
        raise ReportError(f"{path}.cases does not match the selected profile")
    _validate_summary(model["summary"], cases, f"{path}.summary")
    if preflight == "metadata_unavailable" and identity_match:
        raise ReportError(f"{path} cannot claim an identity match without preflight metadata")
    if validity == "valid" and (preflight != "verified" or not identity_match):
        raise ReportError(f"{path} valid status requires verified matching runtime identity")
    return validity


def validate_report(report: Mapping[str, Any]) -> None:
    """Enforce the full closed run-record contract before persistence."""

    required = {
        "schema_version",
        "suite_version",
        "run_id",
        "created_at",
        "profile",
        "public_manifest_sha256",
        "validity",
        "deployment_authorization",
        "models",
    }
    report = _object(report, required, "report")
    if report["schema_version"] != "1.0" or report["suite_version"] != "1.0":
        raise ReportError("report version is unsupported")
    _public_id(report["run_id"], "report.run_id")
    created_at = _string(report["created_at"], "report.created_at", maximum=64)
    try:
        parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReportError("report.created_at must be an ISO 8601 date-time") from error
    if not created_at.endswith("Z") or parsed_created_at.utcoffset() != timezone.utc.utcoffset(None):
        raise ReportError("report.created_at must be UTC with a Z suffix")
    profile = _enum(report["profile"], set(_PROFILE_CASE_IDS), "report.profile")
    validity = _enum(report["validity"], _VALIDITIES, "report.validity")
    if report["deployment_authorization"] is not False:
        raise ReportError("benchmark reports must never authorize deployment")
    if not re.fullmatch(r"[0-9a-f]{64}", str(report["public_manifest_sha256"])):
        raise ReportError("public_manifest_sha256 is invalid")
    if not isinstance(report["models"], list) or not report["models"]:
        raise ReportError("report.models must be a non-empty array")
    model_validities = [
        _validate_model(model, f"report.models[{index}]", _PROFILE_CASE_IDS[profile])
        for index, model in enumerate(report["models"])
    ]
    model_ids = [model["model_id"] for model in report["models"]]
    if len(model_ids) != len(set(model_ids)):
        raise ReportError("report model ids must be unique")
    expected_validity = (
        "invalid"
        if "invalid" in model_validities
        else "limited" if "limited" in model_validities else "valid"
    )
    if validity != expected_validity:
        raise ReportError("report validity is inconsistent with model validity")
    _walk_safe(report)
    try:
        json.dumps(report, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ReportError("report is not strict JSON") from error


def new_run_identity(now: datetime | None = None) -> tuple[str, str]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    normalized = current.astimezone(timezone.utc)
    return str(uuid.uuid4()), normalized.isoformat(timespec="seconds").replace("+00:00", "Z")


def write_report(report: Mapping[str, Any], artifacts_dir: str | Path) -> Path:
    """Write a new owner-only JSON artifact without overwriting an earlier run."""

    validate_report(report)
    directory = secure_directory(artifacts_dir)
    created = str(report["created_at"]).replace(":", "").replace("-", "")
    created = re.sub(r"[^0-9TZ]", "", created)
    run_suffix = str(report["run_id"]).replace("-", "")[:12]
    filename = f"run-{created}-{run_suffix}.json"
    path = directory / filename
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
            handle.write("\n")
    except (OSError, SafetyError) as error:
        raise ReportError("report could not be persisted securely") from error
    if os.name != "nt":
        try:
            path.chmod(0o600)
        except OSError as error:
            raise ReportError("report permissions could not be secured") from error
    return path
