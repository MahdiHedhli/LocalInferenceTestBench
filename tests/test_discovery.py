"""Unit tests for local inventory discovery and metadata-only selection."""

from __future__ import annotations

import unittest

from local_inference_test_bench.discovery import (
    SELECTION_POLICY_VERSION,
    _classify_lms_entry,
    parse_parameter_scale,
    select_campaign_cohort,
)


class DiscoveryTests(unittest.TestCase):
    def test_parse_parameter_scale_dense_and_moe(self) -> None:
        self.assertEqual(parse_parameter_scale("12B"), (12.0, None, "dense"))
        self.assertEqual(parse_parameter_scale("30B-A3B"), (30.0, 3.0, "moe"))
        self.assertEqual(parse_parameter_scale("256x8.4B"), (256.0, 8.4, "moe"))
        self.assertEqual(parse_parameter_scale(None), (None, None, None))
        self.assertEqual(parse_parameter_scale("   "), (None, None, None))
        self.assertEqual(parse_parameter_scale("large"), (None, None, None))

    def test_excludes_embedding_and_remote(self) -> None:
        embedding = _classify_lms_entry(
            {
                "type": "embedding",
                "modelKey": "text-embedding-nomic-embed-text-v1.5",
                "displayName": "Nomic Embed",
                "format": "gguf",
                "architecture": "nomic-bert",
                "deviceIdentifier": None,
                "quantization": {"name": "Q4_K_M", "bits": 4},
                "sizeBytes": 1000,
                "maxContextLength": 2048,
            }
        )
        remote = _classify_lms_entry(
            {
                "type": "llm",
                "modelKey": "qwen/qwen3.5-2b",
                "displayName": "Qwen3.5 2B",
                "format": "gguf",
                "architecture": "qwen35",
                "paramsString": "2B",
                "deviceIdentifier": "remote-device",
                "quantization": {"name": "Q4_K_M", "bits": 4},
                "trainedForToolUse": True,
                "maxContextLength": 8192,
                "sizeBytes": 1000,
            }
        )
        self.assertEqual(embedding.eligibility, "excluded")
        self.assertEqual(embedding.exclusion_reason, "embedding_only")
        self.assertEqual(remote.eligibility, "excluded")
        self.assertEqual(remote.exclusion_reason, "remote_device_not_local_install")

    def test_selection_is_deterministic_and_metadata_only(self) -> None:
        local_models = [
            _classify_lms_entry(
                {
                    "type": "llm",
                    "modelKey": "google/gemma-4-12b-qat",
                    "displayName": "Gemma 4 12B QAT",
                    "format": "gguf",
                    "architecture": "gemma4",
                    "paramsString": "12B",
                    "deviceIdentifier": None,
                    "quantization": {"name": "Q4_0", "bits": 4},
                    "trainedForToolUse": True,
                    "maxContextLength": 262144,
                    "sizeBytes": 7000000000,
                    "path": "google/gemma-4-12b-qat",
                    "publisher": "google",
                }
            ),
            _classify_lms_entry(
                {
                    "type": "llm",
                    "modelKey": "prism-ml/bonsai-27b",
                    "displayName": "Bonsai 27B",
                    "format": "safetensors",
                    "architecture": "qwen3_5",
                    "paramsString": "27B",
                    "deviceIdentifier": None,
                    "quantization": {"name": "2bit", "bits": 2},
                    "trainedForToolUse": True,
                    "maxContextLength": 262144,
                    "sizeBytes": 8500000000,
                    "path": "prism-ml/bonsai-27b",
                    "publisher": "prism-ml",
                }
            ),
            _classify_lms_entry(
                {
                    "type": "llm",
                    "modelKey": "bitnet-b1.58-2b-4t",
                    "displayName": "BitNet 2B",
                    "format": "gguf",
                    "architecture": "bitnet-b1.58",
                    "paramsString": "2B",
                    "deviceIdentifier": None,
                    "trainedForToolUse": False,
                    "maxContextLength": 4096,
                    "sizeBytes": 1100000000,
                    "path": "microsoft/bitnet-b1.58-2B-4T-gguf",
                    "publisher": "microsoft",
                }
            ),
        ]
        first, _ = select_campaign_cohort(local_models, limit=5)
        second, _ = select_campaign_cohort(local_models, limit=5)
        self.assertEqual(
            [item.model.runtime_local_id for item in first],
            [item.model.runtime_local_id for item in second],
        )
        self.assertEqual(len(first), 3)
        self.assertEqual(SELECTION_POLICY_VERSION, "1.0")
        # Tool-capable mid/large models outrank the small no-tool model under the
        # frozen formula; exact order is locked for regression protection.
        self.assertEqual(
            [item.model.runtime_local_id for item in first],
            [
                "google/gemma-4-12b-qat",
                "prism-ml/bonsai-27b",
                "bitnet-b1.58-2b-4t",
            ],
        )


if __name__ == "__main__":
    unittest.main()
