from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILDER = PROJECT_ROOT / "scripts" / "build_leaderboard.py"
OLD_DATA_LIMIT = 2 * 1024 * 1024
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from local_inference_test_bench.submissions import (  # noqa: E402
    build_leaderboard_bundle,
    build_leaderboard,
    render_leaderboard_bytes,
    render_leaderboard_shard_bytes,
    render_submission_bytes,
)
from local_inference_test_bench import submissions as submissions_module  # noqa: E402
from test_submissions import (  # noqa: E402
    prepare_submission,
    public_environment,
    runtime_configuration,
    valid_report,
)


def _run_builder(*arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUILDER), *(str(argument) for argument in arguments)],
        cwd=PROJECT_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _json_files(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*.json"))
    }


class LeaderboardShardTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="litb-shard-tests-")
        cls.root = Path(cls.temporary.name)
        cls.submissions = cls.root / "submissions"
        cls.submissions.mkdir()

        environment = public_environment(
            cpu_model="Synthetic Processor " + ("P" * 180),
        )
        environment["hardware"]["accelerators"] = [
            {
                "kind": "discrete_gpu",
                "model": f"Synthetic Accelerator {index} " + ("A" * 175),
                "count": index + 1,
                "memory_gb": 16.0,
            }
            for index in range(8)
        ]
        environment["runtime_configuration"] = runtime_configuration()

        cls.input_bytes = 0
        cls.submission_count = 0
        cls.submission_ids: set[str] = set()
        # The old failure was aggregate-volume dependent. Keep adding valid,
        # same-schema records until the fixture is materially past that limit
        # and its projected leaderboard requires more than one bounded shard.
        target_bytes = OLD_DATA_LIMIT + (OLD_DATA_LIMIT // 2)
        while cls.input_bytes <= target_bytes:
            suffix = f"{cls.submission_count:06d}"
            report = valid_report(
                display_name=f"Synthetic Model {suffix} " + ("M" * 130),
                source=f"publisher/synthetic-{suffix}-" + ("S" * 205),
                latency_ms=10.0 + (cls.submission_count % 9),
            )
            submission = prepare_submission(report, environment)
            rendered = render_submission_bytes(submission)
            destination = cls.submissions / f"{submission['submission_id']}.json"
            destination.write_bytes(rendered)
            cls.input_bytes += len(rendered)
            cls.submission_count += 1
            cls.submission_ids.add(submission["submission_id"])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def _assert_index(self, path: Path) -> dict[str, object]:
        raw = path.read_bytes()
        self.assertLessEqual(len(raw), OLD_DATA_LIMIT)
        payload = json.loads(raw)
        self.assertEqual(
            set(payload),
            {"index_version", "schema_version", "entry_count", "shard_count"},
        )
        self.assertEqual(payload["index_version"], "1.0")
        self.assertEqual(payload["schema_version"], "1.1")
        self.assertEqual(payload["entry_count"], self.submission_count)
        self.assertIsInstance(payload["shard_count"], int)
        self.assertGreater(payload["shard_count"], 1)
        self.assertNotRegex(raw.decode("ascii"), r'(?i)"(?:url|path|href)"')
        return payload

    def test_corpus_really_crosses_the_retired_aggregate_cap(self) -> None:
        self.assertGreater(self.input_bytes, OLD_DATA_LIMIT)
        self.assertGreater(self.submission_count, 1)

    def test_bounded_default_output_remains_the_legacy_monolith(self) -> None:
        submissions = self.root / "small-submissions"
        submissions.mkdir()
        source = next(iter(sorted(self.submissions.glob("*.json"))))
        (submissions / source.name).write_bytes(source.read_bytes())
        output = self.root / "small-leaderboard.json"

        completed = _run_builder(
            "--submissions-dir",
            submissions,
            "--output",
            output,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        logical = build_leaderboard(submissions)
        self.assertEqual(output.read_bytes(), render_leaderboard_bytes(logical))
        self.assertEqual(
            set(json.loads(output.read_bytes())),
            {"schema_version", "entry_count", "entries"},
        )

    def test_large_build_switches_to_a_bounded_deterministic_index(self) -> None:
        first = self.root / "first-index.json"
        second = self.root / "second-index.json"

        for output in (first, second):
            completed = _run_builder(
                "--submissions-dir",
                self.submissions,
                "--output",
                output,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

        self._assert_index(first)
        self.assertEqual(first.read_bytes(), second.read_bytes())

        first.write_bytes(first.read_bytes().rstrip() + b"\n\n")
        stale = _run_builder(
            "--submissions-dir",
            self.submissions,
            "--output",
            first,
            "--check",
        )
        self.assertEqual(stale.returncode, 1)
        self.assertIn("generated data is stale", stale.stderr)

    def test_shard_packing_renders_each_entry_only_a_constant_number_of_times(self) -> None:
        logical = build_leaderboard(self.submissions)
        renderer = submissions_module.render_leaderboard_shard_bytes

        with mock.patch.object(
            submissions_module,
            "render_leaderboard_shard_bytes",
            wraps=renderer,
        ) as measured:
            index, shards = build_leaderboard_bundle(logical)

        self.assertGreater(index["shard_count"], 1)
        self.assertEqual(index["shard_count"], len(shards))
        self.assertLessEqual(
            measured.call_count,
            (self.submission_count * 3) + (len(shards) * 2),
        )

    def test_bundle_is_byte_stable_complete_and_individually_bounded(self) -> None:
        first = self.root / "bundle-first"
        second = self.root / "bundle-second"
        committed = PROJECT_ROOT / "site" / "data" / "leaderboard.json"
        committed_before = committed.read_bytes()

        for output in (first, second):
            completed = _run_builder(
                "--submissions-dir",
                self.submissions,
                "--bundle-output-dir",
                output,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

        self.assertEqual(committed.read_bytes(), committed_before)

        first_files = _json_files(first)
        second_files = _json_files(second)
        self.assertEqual(first_files, second_files)
        index = self._assert_index(first / "leaderboard.json")
        expected_names = {
            "leaderboard.json",
            *{
                f"leaderboard-{ordinal:06d}.json"
                for ordinal in range(1, int(index["shard_count"]) + 1)
            },
        }
        self.assertEqual(set(first_files), expected_names)

        entry_total = 0
        published_ids: set[str] = set()
        decoded_shards: list[dict[str, object]] = []
        for ordinal in range(1, int(index["shard_count"]) + 1):
            shard_id = f"{ordinal:06d}"
            name = f"leaderboard-{shard_id}.json"
            raw = first_files[name]
            self.assertGreater(len(raw), 0)
            self.assertLessEqual(len(raw), OLD_DATA_LIMIT)
            payload = json.loads(raw)
            decoded_shards.append(payload)
            self.assertEqual(
                set(payload),
                {
                    "index_version",
                    "schema_version",
                    "shard_id",
                    "entry_count",
                    "entries",
                },
            )
            self.assertEqual(payload["index_version"], "1.0")
            self.assertEqual(payload["schema_version"], "1.1")
            self.assertEqual(payload["shard_id"], shard_id)
            self.assertEqual(payload["entry_count"], len(payload["entries"]))
            self.assertGreater(payload["entry_count"], 0)
            entry_total += payload["entry_count"]
            shard_ids = [entry["submission_id"] for entry in payload["entries"]]
            self.assertEqual(len(shard_ids), len(set(shard_ids)))
            self.assertTrue(published_ids.isdisjoint(shard_ids))
            published_ids.update(shard_ids)

        self.assertEqual(entry_total, index["entry_count"])
        self.assertEqual(published_ids, self.submission_ids)
        for current, following in pairwise(decoded_shards):
            candidate = {
                **current,
                "entry_count": int(current["entry_count"]) + 1,
                "entries": [*current["entries"], following["entries"][0]],
            }
            self.assertGreater(
                len(render_leaderboard_shard_bytes(candidate)),
                OLD_DATA_LIMIT,
            )

    def test_bundle_fails_closed_on_corrupt_input(self) -> None:
        corrupt = self.root / "corrupt-submissions"
        corrupt.mkdir()
        source = next(iter(sorted(self.submissions.glob("*.json"))))
        payload = json.loads(source.read_text(encoding="utf-8"))
        payload["model"]["display_name"] = "Synthetic Changed Model"
        (corrupt / source.name).write_text(json.dumps(payload), encoding="utf-8")
        output = self.root / "corrupt-bundle"

        completed = _run_builder(
            "--submissions-dir",
            corrupt,
            "--bundle-output-dir",
            output,
        )

        self.assertEqual(completed.returncode, 1)
        self.assertFalse(output.exists() and any(output.rglob("*.json")))

    def test_bundle_refuses_a_nonempty_destination(self) -> None:
        output = self.root / "stale-bundle"
        output.mkdir()
        stale = output / "leaderboard-999999.json"
        stale.write_bytes(b"{}\n")

        completed = _run_builder(
            "--submissions-dir",
            self.submissions,
            "--bundle-output-dir",
            output,
        )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("must be empty", completed.stderr)
        self.assertEqual(stale.read_bytes(), b"{}\n")


if __name__ == "__main__":
    unittest.main()
