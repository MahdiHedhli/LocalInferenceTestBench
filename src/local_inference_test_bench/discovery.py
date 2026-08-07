"""Local model inventory discovery and deterministic pre-benchmark selection.

Discovery uses authoritative runtime inventory (LM Studio ``lms ls --json`` when
available). Selection scores use only metadata; they never consult benchmark
scores from the current or historical campaigns for ranking quality.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
import shutil
import subprocess
from typing import Any, Mapping, Sequence


SELECTION_POLICY_VERSION = "1.0"
DISCOVERY_SCHEMA_VERSION = "1.0"


class DiscoveryError(RuntimeError):
    """Raised when local model inventory cannot be collected safely."""


@dataclass(frozen=True)
class DiscoveredModel:
    """One runtime-local inventory record (public-safe fields only)."""

    runtime: str
    runtime_local_id: str
    source: str | None
    display_name: str
    architecture: str | None
    parameter_scale_total_billions: float | None
    parameter_scale_active_billions: float | None
    dense_or_moe: str | None
    precision: str | None
    format: str | None
    size_bytes: int | None
    backend: str | None
    declared_context_tokens: int | None
    modalities: tuple[str, ...]
    tool_use: bool | None
    embedding: bool
    generative: bool
    locally_present: bool
    load_estimate_ok: bool | None
    exclusion_reason: str | None
    eligibility: str
    family: str | None
    normalized_identity: str
    device_scope: str
    raw_params_string: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def as_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["modalities"] = list(self.modalities)
        data["notes"] = list(self.notes)
        return data


@dataclass(frozen=True)
class ScoredCandidate:
    """One eligible model with a frozen metadata-only utility score."""

    model: DiscoveredModel
    utility_score: float
    components: Mapping[str, float]
    selection_reason: str

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "runtime_local_id": self.model.runtime_local_id,
            "display_name": self.model.display_name,
            "source": self.model.source,
            "family": self.model.family,
            "architecture": self.model.architecture,
            "parameter_scale_total_billions": self.model.parameter_scale_total_billions,
            "parameter_scale_active_billions": self.model.parameter_scale_active_billions,
            "precision": self.model.precision,
            "backend": self.model.backend,
            "format": self.model.format,
            "utility_score": self.utility_score,
            "components": dict(self.components),
            "selection_reason": self.selection_reason,
            "normalized_identity": self.model.normalized_identity,
        }


def parse_parameter_scale(
    params_string: str | None,
) -> tuple[float | None, float | None, str | None]:
    """Parse LM Studio params strings into total/active billions and dense/moe."""

    if not params_string or not str(params_string).strip():
        return None, None, None
    text = str(params_string).strip()
    moe = re.match(
        r"(?ix)^(?P<total>\d+(?:\.\d+)?)\s*[Bb]?\s*[-x×]\s*(?P<active>\d+(?:\.\d+)?)\s*[Bb]?$",
        text,
    )
    if moe:
        total = float(moe.group("total"))
        active = float(moe.group("active"))
        return total, active, "moe"
    a_form = re.match(
        r"(?ix)^(?P<total>\d+(?:\.\d+)?)\s*[Bb]-A(?P<active>\d+(?:\.\d+)?)[Bb]$",
        text,
    )
    if a_form:
        return float(a_form.group("total")), float(a_form.group("active")), "moe"
    dense = re.match(r"(?ix)^(?P<total>\d+(?:\.\d+)?)\s*[Bb]$", text)
    if dense:
        return float(dense.group("total")), None, "dense"
    return None, None, None


def _backend_for_format(fmt: str | None) -> str | None:
    if not fmt:
        return None
    lowered = fmt.lower()
    if lowered in {"gguf"}:
        return "llama.cpp / Metal"
    if lowered in {"safetensors", "mlx"}:
        return "MLX"
    return fmt


def _family_from_record(model_key: str, architecture: str | None, display: str) -> str:
    key = model_key.lower()
    arch = (architecture or "").lower()
    if "gemma" in key or "gemma" in arch:
        return "gemma"
    if "qwen" in key or "qwen" in arch or "bonsai" in key:
        if "bonsai" in key:
            return "bonsai-qwen"
        return "qwen"
    if "bitnet" in key or "bitnet" in arch:
        return "bitnet"
    if "nemotron" in key or "nemotron" in arch:
        return "nemotron"
    if "deepseek" in key or "deepseek" in arch:
        return "deepseek"
    if "nomic" in key or "bert" in arch:
        return "embedding-bert"
    return (architecture or display or model_key).split("/")[-1].lower()


def _precision_label(quant: Any, fmt: str | None) -> str | None:
    if isinstance(quant, Mapping):
        name = quant.get("name")
        if isinstance(name, str) and name.strip():
            if fmt and fmt.lower() == "gguf":
                return f"GGUF {name.strip()}"
            if fmt and fmt.lower() in {"safetensors", "mlx"}:
                return f"MLX {name.strip()}"
            return name.strip()
    if isinstance(quant, str) and quant.strip():
        return quant.strip()
    if fmt and fmt.lower() == "gguf":
        return "GGUF"
    if fmt:
        return fmt
    return None


def _normalized_identity(
    *,
    family: str,
    total: float | None,
    active: float | None,
    precision: str | None,
    backend: str | None,
    format_name: str | None,
) -> str:
    scale = "unknown"
    if total is not None:
        if active is not None:
            scale = f"{total:g}B-A{active:g}B"
        else:
            scale = f"{total:g}B"
    return "|".join(
        [
            family or "unknown",
            scale,
            (precision or "unknown").lower().replace(" ", ""),
            (backend or "unknown").lower().replace(" ", ""),
            (format_name or "unknown").lower(),
        ]
    )


def _classify_lms_entry(entry: Mapping[str, Any]) -> DiscoveredModel:
    model_key = str(entry.get("modelKey") or entry.get("path") or "unknown")
    model_type = str(entry.get("type") or "").lower()
    fmt = entry.get("format")
    format_name = str(fmt) if isinstance(fmt, str) else None
    display = str(entry.get("displayName") or model_key)
    architecture = entry.get("architecture")
    arch = str(architecture) if isinstance(architecture, str) else None
    publisher = entry.get("publisher")
    source = None
    path = entry.get("path")
    if isinstance(path, str) and path and ":" not in path.split("/", 1)[0]:
        # Local path-like key without remote device prefix.
        source = path if "/" in path else (
            f"{publisher}/{model_key}" if isinstance(publisher, str) else model_key
        )
    elif isinstance(publisher, str) and publisher:
        source = f"{publisher}/{model_key.split('/')[-1]}"
    params_string = entry.get("paramsString")
    raw_params = str(params_string) if isinstance(params_string, str) else None
    total, active, dense_or_moe = parse_parameter_scale(raw_params)
    quant = entry.get("quantization")
    precision = _precision_label(quant, format_name)
    # BitNet i2_s often has null/empty quantization metadata in inventory.
    if "bitnet" in model_key.lower() and (
        precision is None or precision.upper() in {"GGUF", "SAFETENSORS"}
    ):
        precision = "GGUF i2_s"
    size = entry.get("sizeBytes")
    size_bytes = int(size) if isinstance(size, int) else None
    max_ctx = entry.get("maxContextLength")
    declared_context = int(max_ctx) if isinstance(max_ctx, int) else None
    vision = bool(entry.get("vision")) if "vision" in entry else False
    tool = entry.get("trainedForToolUse")
    tool_use = bool(tool) if isinstance(tool, bool) else None
    device = entry.get("deviceIdentifier")
    locally_present = device is None
    device_scope = "local" if locally_present else "remote_device"
    embedding = model_type == "embedding"
    generative = model_type in {"llm", "vlm"} and not embedding
    modalities: list[str] = []
    if embedding:
        modalities.append("embedding")
    else:
        modalities.append("text")
        if vision:
            modalities.append("vision")
    family = _family_from_record(model_key, arch, display)
    backend = _backend_for_format(format_name)
    if format_name and format_name.lower() == "safetensors":
        backend = "MLX"
    identity = _normalized_identity(
        family=family,
        total=total,
        active=active,
        precision=precision,
        backend=backend,
        format_name=format_name,
    )

    exclusion: str | None = None
    notes: list[str] = []
    if not locally_present:
        exclusion = "remote_device_not_local_install"
    elif embedding:
        exclusion = "embedding_only"
    elif model_type not in {"llm", "vlm", "embedding"}:
        exclusion = "unsupported_model_type"
    elif not generative:
        exclusion = "non_generative"
    elif declared_context is not None and declared_context < 2048:
        exclusion = "context_below_suite_floor"
        notes.append("declared context under 2048 tokens")

    # Incomplete multi-shard downloads are not always visible in lms JSON; callers
    # may attach notes. Keep inventory honest about incomplete local artifacts.
    if isinstance(entry.get("_incomplete"), bool) and entry["_incomplete"]:
        exclusion = "corrupt_or_incomplete_download"
        notes.append("incomplete multi-shard download")

    eligibility = "eligible" if exclusion is None else "excluded"
    return DiscoveredModel(
        runtime="LM Studio",
        runtime_local_id=model_key,
        source=source,
        display_name=display,
        architecture=arch,
        parameter_scale_total_billions=total,
        parameter_scale_active_billions=active,
        dense_or_moe=dense_or_moe,
        precision=precision,
        format=format_name,
        size_bytes=size_bytes,
        backend=backend,
        declared_context_tokens=declared_context,
        modalities=tuple(modalities),
        tool_use=tool_use,
        embedding=embedding,
        generative=generative,
        locally_present=locally_present,
        load_estimate_ok=None,
        exclusion_reason=exclusion,
        eligibility=eligibility,
        family=family,
        normalized_identity=identity,
        device_scope=device_scope,
        raw_params_string=raw_params,
        notes=tuple(notes),
    )


def discover_lm_studio_models(
    *,
    lms_path: str | None = None,
    timeout_seconds: float = 60.0,
) -> list[DiscoveredModel]:
    """Enumerate models known to the local LM Studio CLI."""

    binary = lms_path or shutil.which("lms")
    if not binary:
        raise DiscoveryError("LM Studio CLI (lms) is not available on PATH")
    try:
        completed = subprocess.run(
            [binary, "ls", "--json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DiscoveryError("failed to query LM Studio model inventory") from error
    if completed.returncode != 0:
        raise DiscoveryError("LM Studio model inventory command failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise DiscoveryError("LM Studio inventory was not valid JSON") from error
    if not isinstance(payload, list):
        raise DiscoveryError("LM Studio inventory JSON must be a list")
    models: list[DiscoveredModel] = []
    for entry in payload:
        if not isinstance(entry, Mapping):
            continue
        models.append(_classify_lms_entry(entry))
    return models


def discover_local_models() -> list[DiscoveredModel]:
    """Discover models from LITB-supported local runtimes currently present."""

    if not shutil.which("lms"):
        raise DiscoveryError(
            "no supported local runtime inventory CLI found (expected LM Studio lms)"
        )
    return discover_lm_studio_models()


def group_equivalents(models: Sequence[DiscoveredModel]) -> dict[str, list[DiscoveredModel]]:
    """Group inventory rows by normalized identity."""

    groups: dict[str, list[DiscoveredModel]] = {}
    for model in models:
        groups.setdefault(model.normalized_identity, []).append(model)
    return groups


def _scale_component(total: float | None, active: float | None) -> float:
    effective = active if active is not None else total
    if effective is None:
        return 1.0
    if effective < 3:
        return 1.0
    if effective < 10:
        return 2.0
    if effective <= 40:
        return 3.0
    # Very large models remain valuable but not automatically preferred when
    # host fit is uncertain; keep the top band at 3.
    return 3.0


def score_candidate(
    model: DiscoveredModel,
    *,
    represented_sources: set[str] | None = None,
    cohort_families: Sequence[str] = (),
    cohort_backends: Sequence[str] = (),
) -> ScoredCandidate:
    """Score one eligible model with the frozen metadata-only utility formula."""

    represented_sources = represented_sources or set()
    capability = 1.0  # text/chat generative
    if model.tool_use:
        capability += 1.0
    # Reasoning is only rewarded when encoded in metadata/name signals that are
    # objective inventory fields, not popularity research.
    name_blob = f"{model.display_name} {model.runtime_local_id} {model.source or ''}".lower()
    if "reason" in name_blob or "r1" in name_blob:
        capability += 1.0
    if "code" in name_blob or "coder" in name_blob:
        capability = min(3.0, capability + 0.5)
    capability = min(3.0, capability)

    scale = _scale_component(
        model.parameter_scale_total_billions,
        model.parameter_scale_active_billions,
    )

    arch_div = 0.0
    if model.dense_or_moe == "moe":
        arch_div += 1.0
    if model.family and model.family not in cohort_families:
        arch_div += 1.0
    arch_div = min(2.0, arch_div)

    runtime_div = 0.0
    backend = model.backend or ""
    if "MLX" in backend:
        runtime_div += 1.0
    if "llama.cpp" in backend:
        runtime_div += 1.0
    if backend and backend not in cohort_backends:
        runtime_div = min(2.0, runtime_div + 0.5)
    runtime_div = min(2.0, runtime_div)

    quant = 1.0
    precision = (model.precision or "").lower()
    if any(token in precision for token in ("q4", "4bit", "4-bit", "q5", "q6", "q8")):
        quant = 2.0
    elif "2bit" in precision or "iq2" in precision or "i2" in precision or "1.58" in precision:
        quant = 1.5
    elif precision:
        quant = 1.0
    else:
        quant = 0.5

    # Recency without network research: only structural inventory signals.
    recency = 1.0
    if any(token in name_blob for token in ("3.6", "3.5", "gemma-4", "gemma4", "v4", "bonsai")):
        recency = 2.0

    source_key = (model.source or model.runtime_local_id).lower()
    # cross_host_value and novelty_value are complementary labels that both
    # contribute 2 points: a represented source gets cross-host value, an
    # unrepresented source gets novelty. They intentionally do not stack.
    cross_host = 2.0 if source_key in represented_sources else 0.0
    novelty = 0.0 if source_key in represented_sources else 2.0

    components = {
        "capability_breadth": capability,
        "model_scale": scale,
        "architectural_diversity": arch_div,
        "runtime_diversity": runtime_div,
        "quantization_relevance": quant,
        "recency_relevance": recency,
        "cross_host_value": cross_host,
        "novelty_value": novelty,
    }
    utility = sum(components.values())
    reasons: list[str] = []
    if model.tool_use:
        reasons.append("tool-capable")
    if model.dense_or_moe == "moe":
        reasons.append("moe")
    else:
        reasons.append("dense")
    if backend:
        reasons.append(backend)
    if model.parameter_scale_total_billions is not None:
        reasons.append(f"{model.parameter_scale_total_billions:g}B-class")
    if cross_host:
        reasons.append("cross-host-replication")
    else:
        reasons.append("novel-to-leaderboard")
    return ScoredCandidate(
        model=model,
        utility_score=utility,
        components=components,
        selection_reason=", ".join(reasons),
    )


def select_campaign_cohort(
    models: Sequence[DiscoveredModel],
    *,
    limit: int = 5,
    represented_sources: set[str] | None = None,
) -> tuple[list[ScoredCandidate], list[ScoredCandidate]]:
    """Select up to ``limit`` models with a diversity-aware greedy ranking.

    Returns ``(selected, fallback_order)`` where fallback is the remaining ranked
    eligible candidates after selection. Ranking never uses benchmark scores.
    """

    if limit < 1:
        raise ValueError("limit must be at least 1")
    eligible = [m for m in models if m.eligibility == "eligible"]
    # Deduplicate exact normalized identities, prefer larger size_bytes then id.
    best_by_identity: dict[str, DiscoveredModel] = {}
    for model in eligible:
        existing = best_by_identity.get(model.normalized_identity)
        if existing is None:
            best_by_identity[model.normalized_identity] = model
            continue
        existing_size = existing.size_bytes or 0
        new_size = model.size_bytes or 0
        if new_size > existing_size or (
            new_size == existing_size
            and model.runtime_local_id < existing.runtime_local_id
        ):
            best_by_identity[model.normalized_identity] = model

    remaining = list(best_by_identity.values())
    selected: list[ScoredCandidate] = []

    def sort_key(scored: ScoredCandidate) -> tuple:
        total = scored.model.parameter_scale_total_billions or 0.0
        source = (scored.model.source or scored.model.runtime_local_id).lower()
        return (-scored.utility_score, -total, source)

    while remaining and len(selected) < limit:
        cohort_families = tuple(
            c.model.family for c in selected if c.model.family
        )
        cohort_backends = tuple(
            c.model.backend for c in selected if c.model.backend
        )
        scored_round = [
            score_candidate(
                model,
                represented_sources=represented_sources,
                cohort_families=cohort_families,
                cohort_backends=cohort_backends,
            )
            for model in remaining
        ]
        scored_round.sort(key=sort_key)
        pick = scored_round[0]
        selected.append(pick)
        remaining = [
            model
            for model in remaining
            if model.normalized_identity != pick.model.normalized_identity
        ]

    # Fallback order: rescore remaining against the frozen selected cohort.
    cohort_families = tuple(c.model.family for c in selected if c.model.family)
    cohort_backends = tuple(c.model.backend for c in selected if c.model.backend)
    fallback = sorted(
        [
            score_candidate(
                model,
                represented_sources=represented_sources,
                cohort_families=cohort_families,
                cohort_backends=cohort_backends,
            )
            for model in remaining
        ],
        key=sort_key,
    )
    return selected, fallback


def inventory_report(
    models: Sequence[DiscoveredModel],
    *,
    selected: Sequence[ScoredCandidate] | None = None,
    fallback: Sequence[ScoredCandidate] | None = None,
) -> dict[str, Any]:
    """Build a public-safe inventory and selection report object."""

    groups = group_equivalents(models)
    duplicate_groups = {
        key: [m.runtime_local_id for m in members]
        for key, members in groups.items()
        if len(members) > 1
    }
    eligible = [m for m in models if m.eligibility == "eligible"]
    excluded = [m for m in models if m.eligibility != "eligible"]
    return {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "selection_policy_version": SELECTION_POLICY_VERSION,
        "discovered_count": len(models),
        "eligible_count": len(eligible),
        "excluded_count": len(excluded),
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_groups": duplicate_groups,
        "models": [m.as_public_dict() for m in models],
        "selected": [s.as_public_dict() for s in (selected or ())],
        "fallback": [s.as_public_dict() for s in (fallback or ())],
        "selection_policy": {
            "version": SELECTION_POLICY_VERSION,
            "eligibility_gate": [
                "locally_present",
                "generative_text_capable",
                "not_embedding_only",
                "not_remote_device_only",
                "not_corrupt_or_incomplete",
                "declared_context_at_least_2048_when_known",
            ],
            "utility_components": {
                "capability_breadth": "0-3",
                "model_scale": "0-3",
                "architectural_diversity": "0-2",
                "runtime_diversity": "0-2",
                "quantization_relevance": "0-2",
                "recency_relevance": "0-2",
                "cross_host_value": "0-2",
                "novelty_value": "0-2",
            },
            "tie_break": [
                "higher_utility_score",
                "larger_parameter_scale_total",
                "source_identifier_lexicographic",
            ],
            "notes": [
                "Scores use metadata only; benchmark results never feed selection.",
                "Historical leaderboard sources may only contribute cross_host/novelty flags.",
                "cross_host_value and novelty_value are complementary 0-or-2 signals that do not stack.",
            ],
        },
    }
