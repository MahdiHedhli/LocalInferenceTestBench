"""Validated, non-secret configuration models for the reference runner."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping


MANIFEST_SCHEMA_VERSION = "1.0"
SUITE_VERSION = "1.0"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")
_TOP_LEVEL_KEYS = {"schema_version", "suite_version", "credential_env", "models"}
_MODEL_KEYS = {
    "id",
    "display_name",
    "source",
    "revision",
    "digest",
    "precision",
    "parameter_scale",
    "declared_context_tokens",
    "runtime_model",
    "settings",
}
_REQUIRED_SETTINGS_KEYS = {"temperature", "top_p", "max_output_tokens", "seed"}
_SETTINGS_KEYS = _REQUIRED_SETTINGS_KEYS | {"reasoning_effort"}
_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}


class ManifestError(ValueError):
    """Raised when a model manifest violates the public configuration contract."""


def _plain_string(value: Any, field: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a non-empty string")
    result = value.strip()
    if len(result) > maximum or any(ord(character) < 32 for character in result):
        raise ManifestError(f"{field} contains unsupported characters or is too long")
    return result


def _reject_unknown(mapping: Mapping[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise ManifestError(f"{field} contains unsupported fields: {', '.join(unknown)}")


def _parameter_billions(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ManifestError(
            f"{field} must be null or a finite number greater than 0 and at most 1000000"
        )
    try:
        number = float(value)
    except OverflowError as error:
        raise ManifestError(
            f"{field} must be null or a finite number greater than 0 and at most 1000000"
        ) from error
    if not math.isfinite(number) or not 0 < number <= 1_000_000:
        raise ManifestError(
            f"{field} must be null or a finite number greater than 0 and at most 1000000"
        )
    try:
        decimal = Decimal(str(value))
        if decimal != decimal.quantize(Decimal("0.001")):
            raise ManifestError(f"{field} supports at most three fractional digits")
    except InvalidOperation as error:
        raise ManifestError(f"{field} has unsupported numeric precision") from error
    return number


@dataclass(frozen=True, slots=True)
class ParameterScale:
    """Optional public model-size metadata, including sparse active scale."""

    total_billions: float | None
    active_billions: float | None

    @classmethod
    def from_mapping(cls, value: Any, *, field: str) -> "ParameterScale":
        if not isinstance(value, Mapping) or set(value) != {
            "total_billions",
            "active_billions",
        }:
            raise ManifestError(f"{field} has an unsupported object contract")
        total = _parameter_billions(value["total_billions"], f"{field}.total_billions")
        active = _parameter_billions(
            value["active_billions"],
            f"{field}.active_billions",
        )
        if total is None and active is not None:
            raise ManifestError(f"{field}.active_billions requires total_billions")
        if total is not None and active is not None and active > total:
            raise ManifestError(f"{field}.active_billions cannot exceed total_billions")
        return cls(total_billions=total, active_billions=active)

    def as_report_data(self) -> dict[str, float | None]:
        return {
            "total_billions": self.total_billions,
            "active_billions": self.active_billions,
        }


@dataclass(frozen=True, slots=True)
class GenerationSettings:
    """Portable generation settings shared by all baseline cases for a model."""

    temperature: float = 0.0
    top_p: float = 1.0
    max_output_tokens: int = 512
    seed: int | None = 0
    reasoning_effort: str | None = None

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        declared_context_tokens: int,
    ) -> "GenerationSettings":
        if not isinstance(value, Mapping):
            raise ManifestError("settings must be an object")
        _reject_unknown(value, _SETTINGS_KEYS, "settings")
        missing = sorted(_REQUIRED_SETTINGS_KEYS - set(value))
        if missing:
            raise ManifestError(f"settings is missing required fields: {', '.join(missing)}")

        temperature = value["temperature"]
        top_p = value["top_p"]
        maximum = value["max_output_tokens"]
        seed = value["seed"]
        reasoning_effort = value.get("reasoning_effort")

        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            raise ManifestError("settings.temperature must be numeric")
        if not 0.0 <= float(temperature) <= 2.0:
            raise ManifestError("settings.temperature must be between 0 and 2")
        if isinstance(top_p, bool) or not isinstance(top_p, (int, float)):
            raise ManifestError("settings.top_p must be numeric")
        if not 0.0 < float(top_p) <= 1.0:
            raise ManifestError("settings.top_p must be greater than 0 and at most 1")
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
            raise ManifestError("settings.max_output_tokens must be a positive integer")
        if maximum > declared_context_tokens:
            raise ManifestError(
                "settings.max_output_tokens cannot exceed declared_context_tokens"
            )
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
            raise ManifestError("settings.seed must be an integer or null")
        if seed is not None and seed < -(2**63):
            raise ManifestError("settings.seed is below the supported minimum")
        if "reasoning_effort" in value and (
            not isinstance(reasoning_effort, str)
            or reasoning_effort not in _REASONING_EFFORTS
        ):
            raise ManifestError("settings.reasoning_effort is unsupported")

        return cls(
            temperature=float(temperature),
            top_p=float(top_p),
            max_output_tokens=maximum,
            seed=seed,
            reasoning_effort=reasoning_effort,
        )

    def as_api_parameters(self) -> dict[str, int | float | str]:
        """Return only non-secret OpenAI-compatible request parameters."""

        parameters: dict[str, int | float | str] = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_output_tokens,
        }
        if self.seed is not None:
            parameters["seed"] = self.seed
        if self.reasoning_effort is not None:
            parameters["reasoning_effort"] = self.reasoning_effort
        return parameters

    def as_report_data(self) -> dict[str, int | float | str | None]:
        result: dict[str, int | float | str | None] = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_output_tokens": self.max_output_tokens,
            "seed": self.seed,
        }
        if self.reasoning_effort is not None:
            result["reasoning_effort"] = self.reasoning_effort
        return result


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """Public provenance and local selector for one model under test."""

    id: str
    display_name: str
    source: str
    revision_or_digest: str
    provenance_kind: str
    precision: str
    declared_context_tokens: int
    runtime_model: str
    settings: GenerationSettings
    parameter_scale: ParameterScale | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], *, index: int) -> "ModelSpec":
        if not isinstance(value, Mapping):
            raise ManifestError(f"models[{index}] must be an object")
        _reject_unknown(value, _MODEL_KEYS, f"models[{index}]")

        model_id = _plain_string(value.get("id"), f"models[{index}].id", maximum=128)
        if not _IDENTIFIER.fullmatch(model_id):
            raise ManifestError(f"models[{index}].id must be a portable identifier")
        display_name = _plain_string(
            value.get("display_name"), f"models[{index}].display_name", maximum=500
        )
        source = _plain_string(value.get("source"), f"models[{index}].source")
        precision = _plain_string(
            value.get("precision"), f"models[{index}].precision", maximum=500
        )
        parameter_scale = (
            ParameterScale.from_mapping(
                value["parameter_scale"],
                field=f"models[{index}].parameter_scale",
            )
            if "parameter_scale" in value
            else None
        )

        revision = value.get("revision")
        digest = value.get("digest")
        if (revision is None) == (digest is None):
            raise ManifestError(
                f"models[{index}] must provide exactly one of revision or digest"
            )
        if revision is not None:
            provenance_kind = "revision"
            revision_or_digest = _plain_string(
                revision, f"models[{index}].revision", maximum=200
            )
        else:
            provenance_kind = "digest"
            revision_or_digest = _plain_string(
                digest, f"models[{index}].digest", maximum=200
            )

        declared_context = value.get("declared_context_tokens")
        if (
            isinstance(declared_context, bool)
            or not isinstance(declared_context, int)
            or declared_context < 1
        ):
            raise ManifestError(
                f"models[{index}].declared_context_tokens must be a positive integer"
            )

        runtime_model = _plain_string(
            value.get("runtime_model"), f"models[{index}].runtime_model", maximum=500
        )
        if (
            "://" in runtime_model
            or runtime_model.startswith(("/", "\\"))
            or re.match(r"^[A-Za-z]:[\\/]", runtime_model)
        ):
            raise ManifestError(
                f"models[{index}].runtime_model must be a selector, not an endpoint or absolute path"
            )

        settings = GenerationSettings.from_mapping(
            value.get("settings"),
            declared_context_tokens=declared_context,
        )
        return cls(
            id=model_id,
            display_name=display_name,
            source=source,
            revision_or_digest=revision_or_digest,
            provenance_kind=provenance_kind,
            precision=precision,
            declared_context_tokens=declared_context,
            runtime_model=runtime_model,
            settings=settings,
            parameter_scale=parameter_scale,
        )

    def provenance(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "display_name": self.display_name,
            "source": self.source,
            self.provenance_kind: self.revision_or_digest,
            "precision": self.precision,
            "declared_context_tokens": self.declared_context_tokens,
        }
        if self.parameter_scale is not None:
            result["parameter_scale"] = self.parameter_scale.as_report_data()
        return result


@dataclass(frozen=True, slots=True)
class Manifest:
    """Validated model manifest. It intentionally contains no endpoint or secret value."""

    schema_version: str
    suite_version: str
    credential_env: str | None
    models: tuple[ModelSpec, ...]
    public_sha256: str

    def select(self, model_ids: tuple[str, ...] | None = None) -> tuple[ModelSpec, ...]:
        if not model_ids:
            return self.models
        requested = set(model_ids)
        selected = tuple(model for model in self.models if model.id in requested)
        missing = sorted(requested - {model.id for model in selected})
        if missing:
            raise ManifestError(f"unknown model id(s): {', '.join(missing)}")
        return selected


def parse_manifest(data: Mapping[str, Any]) -> Manifest:
    """Validate a decoded manifest without retaining its original content."""

    if not isinstance(data, Mapping):
        raise ManifestError("manifest root must be an object")
    _reject_unknown(data, _TOP_LEVEL_KEYS, "manifest")
    schema_version = data.get("schema_version")
    if schema_version != MANIFEST_SCHEMA_VERSION:
        raise ManifestError(f"schema_version must be {MANIFEST_SCHEMA_VERSION}")
    suite_version = data.get("suite_version")
    if suite_version != SUITE_VERSION:
        raise ManifestError(f"suite_version must be {SUITE_VERSION}")

    credential_env = data.get("credential_env")
    if credential_env is not None:
        if not isinstance(credential_env, str) or not _ENV_NAME.fullmatch(credential_env):
            raise ManifestError("credential_env must be an uppercase environment variable name")

    raw_models = data.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise ManifestError("models must be a non-empty array")
    models = tuple(
        ModelSpec.from_mapping(raw_model, index=index)
        for index, raw_model in enumerate(raw_models)
    )
    ids = [model.id for model in models]
    if len(ids) != len(set(ids)):
        raise ManifestError("model ids must be unique")
    identities = [
        (model.source, model.provenance_kind, model.revision_or_digest) for model in models
    ]
    if len(identities) != len(set(identities)):
        raise ManifestError("model source/revision or source/digest identities must be unique")
    public_projection = {
        "schema_version": schema_version,
        "suite_version": suite_version,
        "models": [
            {
                "id": model.id,
                **model.provenance(),
                "settings": model.settings.as_report_data(),
            }
            for model in models
        ],
    }
    canonical_projection = json.dumps(
        public_projection,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return Manifest(
        schema_version=schema_version,
        suite_version=suite_version,
        credential_env=credential_env,
        models=models,
        public_sha256=hashlib.sha256(canonical_projection).hexdigest(),
    )


def load_manifest(path: str | Path) -> Manifest:
    """Read and validate a UTF-8 JSON manifest."""

    manifest_path = Path(path)
    try:
        payload = manifest_path.read_bytes()
    except OSError as error:
        raise ManifestError("manifest could not be read") from error
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestError("manifest must contain valid UTF-8 JSON") from error
    return parse_manifest(decoded)
