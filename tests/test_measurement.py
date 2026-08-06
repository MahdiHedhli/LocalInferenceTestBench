from __future__ import annotations

import json
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from local_inference_test_bench.measurement import (  # noqa: E402
    LocalMeasurementSampler,
    MeasurementError,
    build_measurement_evidence,
    write_measurement_evidence,
)
from local_inference_test_bench.submissions import (  # noqa: E402
    load_measurement_evidence_file,
)


RUN_ID = "-".join(("11111111", "2222", "4333", "8444", "555555555555"))
MODEL_IDS = ("public-model-a", "public-model-b")
POSIX_SAMPLER_ONLY = unittest.skipIf(
    os.name == "nt",
    "single-command sampler requires POSIX process containment",
)


class _InputSink:
    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False

    def write(self, value: bytes) -> int:
        self.data.extend(value)
        return len(value)

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self, stdout: bytes, *, returncode: int = 0) -> None:
        self.stdin = _InputSink()
        self.stdout = io.BytesIO(stdout)
        self.returncode = returncode
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode if not self.killed else -9

    def wait(self, timeout: float | None = None) -> int:
        return -9 if self.killed else self.returncode

    def kill(self) -> None:
        self.killed = True


class _BlockingInput(_InputSink):
    def __init__(self, killed: threading.Event) -> None:
        super().__init__()
        self.killed = killed

    def write(self, value: bytes) -> int:
        self.killed.wait()
        raise BrokenPipeError


class _HungInputProcess(_FakeProcess):
    def __init__(self) -> None:
        super().__init__(b"")
        self.killed_event = threading.Event()
        self.stdin = _BlockingInput(self.killed_event)

    def kill(self) -> None:
        super().kill()
        self.killed_event.set()


def adapter_response(phase: str, sample: dict | None = None) -> bytes:
    return json.dumps(
        {
            "schema_version": "1.0",
            "source_run_id": RUN_ID,
            "phase": phase,
            "model_ids": list(MODEL_IDS),
            "sample": sample
            or {"outcome": "within_thresholds", "categories": []},
        }
    ).encode("utf-8")


class MeasurementSamplerTests(unittest.TestCase):
    def _executable(self, root: Path) -> Path:
        executable = root / "trusted-sampler"
        executable.write_text("placeholder", encoding="utf-8")
        if os.name != "nt":
            executable.chmod(0o700)
        return executable

    @POSIX_SAMPLER_ONLY
    def test_adapter_receives_exact_binding_without_process_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(Path(temporary))
            process = _FakeProcess(adapter_response("pre"))
            with (
                mock.patch.dict(
                    os.environ,
                    {"PATH": "/safe/bin", "PRIVATE" + "_TOKEN": "must-not-cross"},
                    clear=True,
                ),
                mock.patch.object(subprocess, "Popen", return_value=process) as runner,
            ):
                sample = LocalMeasurementSampler(executable).sample(
                    phase="pre",
                    source_run_id=RUN_ID,
                    model_ids=MODEL_IDS,
                )

        self.assertEqual(sample, {"outcome": "within_thresholds", "categories": []})
        request = json.loads(bytes(process.stdin.data).decode("utf-8"))
        self.assertEqual(request["source_run_id"], RUN_ID)
        self.assertEqual(request["phase"], "pre")
        self.assertEqual(request["model_ids"], list(MODEL_IDS))
        self.assertEqual(runner.call_args.kwargs["env"], {"PATH": "/safe/bin"})
        self.assertNotIn("shell", runner.call_args.kwargs)
        self.assertIs(runner.call_args.kwargs["stderr"], subprocess.DEVNULL)

    @POSIX_SAMPLER_ONLY
    def test_real_approved_snapshot_completes_the_closed_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "trusted-sampler"
            executable.write_text(
                "\n".join(
                    (
                        f"#!{sys.executable}",
                        "import json, sys",
                        "request = json.load(sys.stdin)",
                        "json.dump({**request, 'sample': {"
                        "'outcome': 'within_thresholds', 'categories': []}}, sys.stdout)",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)

            sample = LocalMeasurementSampler(executable).sample(
                phase="pre",
                source_run_id=RUN_ID,
                model_ids=MODEL_IDS,
            )

        self.assertEqual(sample, {"outcome": "within_thresholds", "categories": []})

    @POSIX_SAMPLER_ONLY
    def test_adapter_rejects_stale_or_ambiguous_responses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(Path(temporary))
            stale = json.loads(adapter_response("pre"))
            stale["source_run_id"] = "different-run"
            responses = (
                json.dumps(stale).encode("utf-8"),
                (
                    b'{"schema_version":"1.0","source_run_id":"' + RUN_ID.encode()
                    + b'","source_run_id":"different-run","phase":"pre",'
                    b'"model_ids":["public-model-a","public-model-b"],'
                    b'"sample":{"outcome":"within_thresholds","categories":[]}}'
                ),
            )
            for response in responses:
                with (
                    self.subTest(response=response),
                    mock.patch.object(
                        subprocess, "Popen", return_value=_FakeProcess(response)
                    ),
                    self.assertRaises(MeasurementError),
                ):
                    LocalMeasurementSampler(executable).sample(
                        phase="pre",
                        source_run_id=RUN_ID,
                        model_ids=MODEL_IDS,
                    )

    @POSIX_SAMPLER_ONLY
    def test_adapter_rejects_noncategorical_sample_before_returning_pre(self) -> None:
        invalid_samples = (
            {"outcome": "within_thresholds", "categories": [], "raw": 1},
            {"outcome": "unknown", "categories": []},
            {"outcome": "within_thresholds", "categories": ["swap"]},
            {
                "outcome": "threshold_crossed",
                "categories": ["swap", "memory_pressure"],
            },
        )
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(Path(temporary))
            sampler = LocalMeasurementSampler(executable)
            for sample in invalid_samples:
                with (
                    self.subTest(sample=sample),
                    mock.patch.object(
                        subprocess,
                        "Popen",
                        return_value=_FakeProcess(adapter_response("pre", sample)),
                    ),
                    self.assertRaisesRegex(MeasurementError, "categorical evidence"),
                ):
                    sampler.sample(
                        phase="pre",
                        source_run_id=RUN_ID,
                        model_ids=MODEL_IDS,
                    )

    @POSIX_SAMPLER_ONLY
    def test_adapter_output_is_bounded_while_the_child_is_running(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(Path(temporary))
            process = _FakeProcess(b"x" * (256 * 1024 + 1))
            with (
                mock.patch.object(subprocess, "Popen", return_value=process),
                self.assertRaisesRegex(MeasurementError, "size limit"),
            ):
                LocalMeasurementSampler(executable).sample(
                    phase="pre",
                    source_run_id=RUN_ID,
                    model_ids=MODEL_IDS,
                )

        self.assertTrue(process.killed)

    @POSIX_SAMPLER_ONLY
    def test_adapter_that_never_reads_stdin_is_terminated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(Path(temporary))
            process = _HungInputProcess()
            with (
                mock.patch.object(subprocess, "Popen", return_value=process),
                mock.patch(
                    "local_inference_test_bench.measurement._ADAPTER_TIMEOUT_SECONDS",
                    0.01,
                ),
                self.assertRaisesRegex(MeasurementError, "timed out"),
            ):
                LocalMeasurementSampler(executable).sample(
                    phase="pre",
                    source_run_id=RUN_ID,
                    model_ids=MODEL_IDS,
                )

        self.assertTrue(process.killed)

    @POSIX_SAMPLER_ONLY
    def test_adapter_must_not_be_group_or_world_writable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(Path(temporary))
            executable.chmod(0o722)
            with self.assertRaisesRegex(MeasurementError, "group or world writable"):
                LocalMeasurementSampler(executable)

    @POSIX_SAMPLER_ONLY
    def test_adapter_must_be_a_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(MeasurementError, "regular non-symlink"):
                LocalMeasurementSampler(Path(temporary))

    @POSIX_SAMPLER_ONLY
    def test_oversized_adapter_is_rejected_before_content_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "oversized-sampler"
            with executable.open("wb") as handle:
                handle.truncate((16 * 1024 * 1024) + 1)
            executable.chmod(0o700)
            with (
                mock.patch(
                    "local_inference_test_bench.measurement.os.read",
                    wraps=os.read,
                ) as reader,
                self.assertRaisesRegex(MeasurementError, "exceeded the size limit"),
            ):
                LocalMeasurementSampler(executable)

        reader.assert_not_called()

    @POSIX_SAMPLER_ONLY
    def test_approval_reuses_the_single_bounded_descriptor_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(Path(temporary))
            with mock.patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("unbounded second read"),
            ):
                sampler = LocalMeasurementSampler(executable)

        self.assertEqual(sampler._approved_bytes, b"placeholder")

    @POSIX_SAMPLER_ONLY
    def test_path_swap_to_fifo_is_opened_nonblocking_and_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = self._executable(root)
            fifo = root / "replacement-fifo"
            os.mkfifo(fifo, 0o700)
            real_open = os.open
            observed_flags: list[int] = []

            def swap_and_open(path: Path, flags: int, *args: object) -> int:
                observed_flags.append(flags)
                os.replace(fifo, executable)
                return real_open(path, flags, *args)

            with (
                mock.patch(
                    "local_inference_test_bench.measurement.os.open",
                    side_effect=swap_and_open,
                ),
                self.assertRaisesRegex(MeasurementError, "remain a regular file"),
            ):
                LocalMeasurementSampler(executable)

        self.assertEqual(len(observed_flags), 1)
        self.assertTrue(observed_flags[0] & os.O_NONBLOCK)

    @POSIX_SAMPLER_ONLY
    def test_adapter_rejects_symlink_and_non_executable_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = self._executable(root)
            link = root / "sampler-link"
            link.symlink_to(executable)
            with self.assertRaisesRegex(MeasurementError, "regular non-symlink"):
                LocalMeasurementSampler(link)

            executable.chmod(0o600)
            with self.assertRaisesRegex(MeasurementError, "must be executable"):
                LocalMeasurementSampler(executable)

    @POSIX_SAMPLER_ONLY
    def test_adapter_replacement_is_detected_before_a_later_sample(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = self._executable(root)
            sampler = LocalMeasurementSampler(executable)
            with mock.patch.object(
                subprocess,
                "Popen",
                return_value=_FakeProcess(adapter_response("pre")),
            ):
                sampler.sample(
                    phase="pre",
                    source_run_id=RUN_ID,
                    model_ids=MODEL_IDS,
                )
            replacement = root / "replacement"
            replacement.write_text("different adapter", encoding="utf-8")
            if os.name != "nt":
                replacement.chmod(0o700)
            os.replace(replacement, executable)

            with (
                mock.patch.object(subprocess, "Popen") as runner,
                self.assertRaisesRegex(MeasurementError, "changed after it was approved"),
            ):
                sampler.sample(
                    phase="post",
                    source_run_id=RUN_ID,
                    model_ids=MODEL_IDS,
                )

        runner.assert_not_called()

    @POSIX_SAMPLER_ONLY
    def test_at_spawn_source_replacement_executes_only_the_approved_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = self._executable(root)
            sampler = LocalMeasurementSampler(executable)
            replacement = root / "replacement"
            replacement.write_text("unapproved adapter", encoding="utf-8")
            if os.name != "nt":
                replacement.chmod(0o700)
            snapshot_paths: list[Path] = []

            def spawn(argv: list[str], **_: object) -> _FakeProcess:
                snapshot = Path(argv[0])
                snapshot_paths.append(snapshot)
                self.assertNotEqual(snapshot, executable)
                self.assertEqual(snapshot.read_text(encoding="utf-8"), "placeholder")
                os.replace(replacement, executable)
                return _FakeProcess(adapter_response("pre"))

            with (
                mock.patch.object(subprocess, "Popen", side_effect=spawn),
                self.assertRaisesRegex(MeasurementError, "changed after it was approved"),
            ):
                sampler.sample(
                    phase="pre",
                    source_run_id=RUN_ID,
                    model_ids=MODEL_IDS,
                )

        self.assertEqual(len(snapshot_paths), 1)
        self.assertFalse(snapshot_paths[0].exists())

    @POSIX_SAMPLER_ONLY
    def test_post_spawn_snapshot_mismatch_preserves_the_categorical_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(Path(temporary))
            sampler = LocalMeasurementSampler(executable)
            process = _FakeProcess(adapter_response("pre"))
            with (
                mock.patch.object(subprocess, "Popen", return_value=process),
                mock.patch(
                    "local_inference_test_bench.measurement._verify_adapter_identity",
                    side_effect=(
                        None,
                        None,
                        MeasurementError("measurement sampler snapshot changed"),
                    ),
                ),
                self.assertRaisesRegex(MeasurementError, "snapshot changed"),
            ):
                sampler.sample(
                    phase="pre",
                    source_run_id=RUN_ID,
                    model_ids=MODEL_IDS,
                )

        self.assertTrue(process.killed)

    @POSIX_SAMPLER_ONLY
    def test_snapshot_and_thread_resource_failures_are_categorical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(Path(temporary))
            sampler = LocalMeasurementSampler(executable)
            with (
                mock.patch(
                    "local_inference_test_bench.measurement.tempfile.TemporaryDirectory",
                    side_effect=OSError("temporary directory unavailable"),
                ),
                self.assertRaisesRegex(MeasurementError, "snapshot could not be created"),
            ):
                sampler.sample(
                    phase="pre",
                    source_run_id=RUN_ID,
                    model_ids=MODEL_IDS,
                )

            process = _FakeProcess(adapter_response("pre"))
            with (
                mock.patch.object(subprocess, "Popen", return_value=process),
                mock.patch.object(
                    threading.Thread,
                    "start",
                    side_effect=RuntimeError("thread unavailable"),
                ),
                self.assertRaisesRegex(MeasurementError, "could not run safely"),
            ):
                sampler.sample(
                    phase="pre",
                    source_run_id=RUN_ID,
                    model_ids=MODEL_IDS,
                )

        self.assertTrue(process.killed)

    @unittest.skipUnless(os.name == "nt", "Windows-specific fail-closed behavior")
    def test_windows_single_command_sampler_requires_safe_process_containment(self) -> None:
        with self.assertRaisesRegex(MeasurementError, "POSIX process containment"):
            LocalMeasurementSampler(Path("sampler.exe"))

    @POSIX_SAMPLER_ONLY
    def test_adapter_timeout_terminates_an_inheriting_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "tree-sampler"
            pid_file = root / "descendant.pid"
            executable.write_text(
                "\n".join(
                    (
                        f"#!{sys.executable}",
                        "import json, subprocess, sys",
                        "from pathlib import Path",
                        "request = json.load(sys.stdin)",
                        "child = subprocess.Popen([sys.executable, '-c', "
                        "'import time; time.sleep(60)'])",
                        f"Path({os.fspath(pid_file)!r}).write_text(str(child.pid), encoding='utf-8')",
                        "json.dump({**request, 'sample': {"
                        "'outcome': 'within_thresholds', 'categories': []}}, sys.stdout)",
                        "sys.stdout.flush()",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)

            with (
                mock.patch(
                    "local_inference_test_bench.measurement._ADAPTER_TIMEOUT_SECONDS",
                    1.0,
                ),
                mock.patch(
                    "local_inference_test_bench.measurement._CLEANUP_TIMEOUT_SECONDS",
                    0.5,
                ),
                self.assertRaisesRegex(MeasurementError, "timed out"),
            ):
                LocalMeasurementSampler(executable).sample(
                    phase="pre",
                    source_run_id=RUN_ID,
                    model_ids=MODEL_IDS,
                )

            descendant_pid = int(pid_file.read_text(encoding="utf-8"))
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                try:
                    os.kill(descendant_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.02)
            else:
                self.fail("measurement sampler descendant remained resident")

    @POSIX_SAMPLER_ONLY
    def test_maximum_cardinality_fits_adapter_and_sidecar_bounds(self) -> None:
        model_ids = tuple(
            f"m{index:03d}" + ("x" * 124) for index in range(1000)
        )
        response = json.dumps(
            {
                "schema_version": "1.0",
                "source_run_id": RUN_ID,
                "phase": "pre",
                "model_ids": list(model_ids),
                "sample": {"outcome": "within_thresholds", "categories": []},
            }
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = self._executable(root)
            process = _FakeProcess(response)
            with mock.patch.object(subprocess, "Popen", return_value=process):
                sample = LocalMeasurementSampler(executable).sample(
                    phase="pre",
                    source_run_id=RUN_ID,
                    model_ids=model_ids,
                )
            evidence = build_measurement_evidence(
                source_run_id=RUN_ID,
                model_ids=model_ids,
                pre=sample,
                post=sample,
            )
            written = write_measurement_evidence(
                evidence,
                root / "private" / "measurement-evidence.json",
            )

            self.assertEqual(load_measurement_evidence_file(written), evidence)
            self.assertGreater(written.stat().st_size, 256 * 1024)

    def test_evidence_is_derived_only_from_adapter_categories(self) -> None:
        evidence = build_measurement_evidence(
            source_run_id=RUN_ID,
            model_ids=MODEL_IDS,
            pre={"outcome": "within_thresholds", "categories": []},
            post={"outcome": "threshold_crossed", "categories": ["swap"]},
        )

        self.assertEqual(evidence["source_run_id"], RUN_ID)
        self.assertEqual([row["model_id"] for row in evidence["models"]], list(MODEL_IDS))
        self.assertTrue(
            all(row["validity"] == "degraded_midrun" for row in evidence["models"])
        )
        self.assertTrue(
            all(
                row["measurement_conditions"]["hard_threshold_crossed"]
                for row in evidence["models"]
            )
        )

    def test_generated_sidecar_is_atomic_owner_only_and_reusable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "private" / "measurement-evidence.json"
            evidence = build_measurement_evidence(
                source_run_id=RUN_ID,
                model_ids=MODEL_IDS,
                pre={"outcome": "within_thresholds", "categories": []},
                post={"outcome": "within_thresholds", "categories": []},
            )
            written = write_measurement_evidence(evidence, destination)
            loaded = load_measurement_evidence_file(written)
            mode = written.stat().st_mode & 0o777

        self.assertEqual(loaded, evidence)
        if os.name != "nt":
            self.assertEqual(mode, 0o600)

    def test_failed_atomic_replace_removes_the_temporary_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "private" / "measurement-evidence.json"
            evidence = build_measurement_evidence(
                source_run_id=RUN_ID,
                model_ids=MODEL_IDS,
                pre={"outcome": "within_thresholds", "categories": []},
                post={"outcome": "within_thresholds", "categories": []},
            )
            with (
                mock.patch(
                    "local_inference_test_bench.measurement.os.replace",
                    side_effect=OSError("replace failed"),
                ),
                self.assertRaisesRegex(MeasurementError, "could not be written securely"),
            ):
                write_measurement_evidence(evidence, destination)

            self.assertEqual(list(destination.parent.glob(".measurement-evidence-*")), [])
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
