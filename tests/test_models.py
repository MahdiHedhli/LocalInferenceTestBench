from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from local_inference_test_bench.models import (  # noqa: E402
    ManifestError,
    load_manifest,
    parse_manifest,
)


def valid_manifest_data() -> dict:
    return {
        "schema_version": "1.0",
        "suite_version": "1.0",
        "credential_env": "INFERENCE_TEST_TOKEN",
        "models": [
            {
                "id": "model-a-rev-1",
                "display_name": "Example Model",
                "source": "publisher/example-model",
                "revision": "revision-1",
                "precision": "runtime-declared",
                "declared_context_tokens": 4096,
                "runtime_model": "loaded-model-a",
                "settings": {
                    "temperature": 0,
                    "top_p": 1,
                    "max_output_tokens": 256,
                    "seed": 7,
                },
            }
        ],
    }


class ManifestTests(unittest.TestCase):
    def test_rejects_invalid_collection_shapes_and_duplicate_ids(self) -> None:
        with self.assertRaisesRegex(ManifestError, "root"):
            parse_manifest([])

        data = valid_manifest_data()
        data["models"] = []
        with self.assertRaisesRegex(ManifestError, "non-empty array"):
            parse_manifest(data)

        data = valid_manifest_data()
        duplicate = copy.deepcopy(data["models"][0])
        duplicate["revision"] = "revision-2"
        data["models"].append(duplicate)
        with self.assertRaisesRegex(ManifestError, "ids must be unique"):
            parse_manifest(data)

    def test_rejects_unsupported_manifest_and_suite_versions(self) -> None:
        for field in ("schema_version", "suite_version"):
            data = valid_manifest_data()
            data[field] = "2.0"
            with self.subTest(field=field), self.assertRaisesRegex(ManifestError, field):
                parse_manifest(data)

    def test_rejects_missing_unknown_and_out_of_range_settings(self) -> None:
        mutations = (
            ("missing", lambda settings: settings.pop("seed")),
            ("unknown", lambda settings: settings.__setitem__("frequency_penalty", 0)),
            ("temperature", lambda settings: settings.__setitem__("temperature", 2.1)),
            ("top_p", lambda settings: settings.__setitem__("top_p", 0)),
            ("max_output_tokens", lambda settings: settings.__setitem__("max_output_tokens", 0)),
            ("seed", lambda settings: settings.__setitem__("seed", True)),
            (
                "reasoning_effort",
                lambda settings: settings.__setitem__("reasoning_effort", "extreme"),
            ),
        )
        for label, mutate in mutations:
            data = valid_manifest_data()
            mutate(data["models"][0]["settings"])
            with self.subTest(label=label), self.assertRaises(ManifestError):
                parse_manifest(data)

    def test_loads_valid_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "models.json"
            path.write_text(json.dumps(valid_manifest_data()), encoding="utf-8")
            manifest = load_manifest(path)

        self.assertEqual(manifest.models[0].id, "model-a-rev-1")
        self.assertEqual(manifest.models[0].settings.max_output_tokens, 256)
        self.assertRegex(manifest.public_sha256, r"^[0-9a-f]{64}$")

    def test_optional_reasoning_effort_is_public_and_bounded(self) -> None:
        data = valid_manifest_data()
        data["models"][0]["settings"]["reasoning_effort"] = "none"

        manifest = parse_manifest(data)

        settings = manifest.models[0].settings
        self.assertEqual(settings.reasoning_effort, "none")
        self.assertEqual(settings.as_api_parameters()["reasoning_effort"], "none")
        self.assertEqual(settings.as_report_data()["reasoning_effort"], "none")

    def test_public_fingerprint_excludes_credential_and_runtime_selector(self) -> None:
        first_data = valid_manifest_data()
        second_data = copy.deepcopy(first_data)
        second_data["credential_env"] = "A_DIFFERENT_ENVIRONMENT_NAME"
        second_data["models"][0]["runtime_model"] = "a-different-local-selector"

        first = parse_manifest(first_data)
        second = parse_manifest(second_data)

        self.assertEqual(first.public_sha256, second.public_sha256)
        second_data["models"][0]["source"] = "publisher/a-distinct-model"
        self.assertNotEqual(first.public_sha256, parse_manifest(second_data).public_sha256)

    def test_same_display_name_with_distinct_provenance_is_valid(self) -> None:
        data = valid_manifest_data()
        second = copy.deepcopy(data["models"][0])
        second["id"] = "model-a-rev-2"
        second["revision"] = "revision-2"
        data["models"].append(second)

        manifest = parse_manifest(data)

        self.assertEqual(len(manifest.models), 2)
        self.assertEqual(manifest.models[0].display_name, manifest.models[1].display_name)

    def test_requires_exactly_one_revision_or_digest(self) -> None:
        data = valid_manifest_data()
        data["models"][0]["digest"] = "sha256:placeholder"
        with self.assertRaisesRegex(ManifestError, "exactly one"):
            parse_manifest(data)

        del data["models"][0]["digest"]
        del data["models"][0]["revision"]
        with self.assertRaisesRegex(ManifestError, "exactly one"):
            parse_manifest(data)

    def test_rejects_unrecognized_or_secret_configuration_fields(self) -> None:
        data = valid_manifest_data()
        data["models"][0]["endpoint"] = "not-retained"
        with self.assertRaisesRegex(ManifestError, "unsupported fields"):
            parse_manifest(data)

        data = valid_manifest_data()
        data["api_key"] = "not-retained"
        with self.assertRaisesRegex(ManifestError, "unsupported fields"):
            parse_manifest(data)

    def test_validates_generation_budget_and_runtime_selector(self) -> None:
        data = valid_manifest_data()
        data["models"][0]["settings"]["max_output_tokens"] = 5000
        with self.assertRaisesRegex(ManifestError, "cannot exceed"):
            parse_manifest(data)

        data = valid_manifest_data()
        data["models"][0]["runtime_model"] = "/absolute/local/model"
        with self.assertRaisesRegex(ManifestError, "selector"):
            parse_manifest(data)

        data = valid_manifest_data()
        data["models"][0]["settings"]["seed"] = -(2**63) - 1
        with self.assertRaisesRegex(ManifestError, "seed"):
            parse_manifest(data)


if __name__ == "__main__":
    unittest.main()
