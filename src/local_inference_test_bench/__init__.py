"""Hardware-agnostic, privacy-conscious local inference evaluation."""

from .models import (
    GenerationSettings,
    Manifest,
    ManifestError,
    ModelSpec,
    load_manifest,
)
from .runner import BenchmarkRunner, PROFILE_CASES

__all__ = [
    "BenchmarkRunner",
    "GenerationSettings",
    "Manifest",
    "ManifestError",
    "ModelSpec",
    "PROFILE_CASES",
    "load_manifest",
]

__version__ = "0.3.0"
