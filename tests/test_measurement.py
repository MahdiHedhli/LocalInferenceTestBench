from __future__ import annotations

import io
import json
import os
from pathlib import Path
import signal
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
from local_inference_test_bench import _measurement_supervisor as supervisor  # noqa: E402
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
        self._configured_returncode = returncode
        self.returncode: int | None = None
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            self.returncode = -9 if self.killed else self._configured_returncode
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def terminate(self) -> None:
        self.kill()


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


def _process_identity(pid: int) -> str | None:
    """Return a reuse-resistant test identity without retaining host details."""

    if sys.platform.startswith("linux"):
        try:
            stat_line = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        except OSError:
            return None
        closing = stat_line.rfind(")")
        fields = stat_line[closing + 2 :].split()
        return fields[19] if closing >= 0 and len(fields) > 19 else None
    completed = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="],
        check=False,
        capture_output=True,
        text=True,
    )
    identity = completed.stdout.strip()
    return identity or None


def _test_process_has_marker(pid: int, marker: str) -> bool:
    if sys.platform.startswith("linux"):
        try:
            command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
        except OSError:
            return False
        return marker.encode("utf-8") in command
    completed = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0 and marker in completed.stdout


def _cleanup_test_process(pid: int | None, marker: str) -> None:
    """Never signal a PID unless its current command retains our unique marker."""

    if pid is None or not _test_process_has_marker(pid, marker):
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _wait_for_original_process_to_disappear(pid: int, identity: str | None) -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        current = _process_identity(pid)
        if current is None or current != identity:
            return
        time.sleep(0.02)
    raise AssertionError("measurement sampler descendant remained resident or zombie")


@POSIX_SAMPLER_ONLY
class MeasurementSupervisorTests(unittest.TestCase):
    def test_darwin_kqueue_fallback_observes_exit_without_waiting(self) -> None:
        process_id = 424242
        event = mock.Mock(ident=process_id, flags=0, fflags=0x80000000)
        registration = mock.Mock()
        queue = mock.Mock()
        queue.control.side_effect = (None, [event])
        darwin_select = mock.Mock()
        darwin_select.kqueue.return_value = queue
        darwin_select.kevent.return_value = registration
        darwin_select.KQ_FILTER_PROC = -5
        darwin_select.KQ_EV_ADD = 0x1
        darwin_select.KQ_EV_ENABLE = 0x4
        darwin_select.KQ_EV_ONESHOT = 0x10
        darwin_select.KQ_EV_ERROR = 0x4000
        darwin_select.KQ_NOTE_EXIT = 0x80000000
        supervisor._termination_requested = False

        with (
            mock.patch.object(supervisor.sys, "platform", "darwin"),
            mock.patch.object(supervisor.os, "waitid", None, create=True),
            mock.patch.object(supervisor, "select", darwin_select),
        ):
            observed = supervisor._observe_exit_without_reaping(process_id)

        self.assertTrue(observed)
        darwin_select.kevent.assert_called_once_with(
            process_id,
            filter=darwin_select.KQ_FILTER_PROC,
            flags=(
                darwin_select.KQ_EV_ADD
                | darwin_select.KQ_EV_ENABLE
                | darwin_select.KQ_EV_ONESHOT
            ),
            fflags=darwin_select.KQ_NOTE_EXIT,
        )
        self.assertEqual(
            queue.control.call_args_list,
            [mock.call([registration], 0, 0), mock.call(None, 1, 0.05)],
        )
        queue.close.assert_called_once_with()

    @unittest.skipUnless(sys.platform == "darwin", "Darwin kqueue integration")
    def test_real_darwin_kqueue_fallback_leaves_leader_unreaped(self) -> None:
        process = subprocess.Popen(
            ["/usr/bin/true"],
            start_new_session=True,
        )
        supervisor._termination_requested = False
        try:
            with mock.patch.object(supervisor.os, "waitid", None, create=True):
                observed = supervisor._observe_exit_without_reaping(process.pid)

            self.assertTrue(observed)
            self.assertIsNone(process.returncode)
            with mock.patch.object(supervisor.signal, "signal"):
                returncode, cleaned = supervisor._cleanup_adapter_group(
                    process,
                    cleanup_timeout=0.5,
                    leader_exited=True,
                )
            self.assertEqual(returncode, 0)
            self.assertTrue(cleaned)
        finally:
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
                process.wait(timeout=1.0)

    def test_cleanup_signals_group_before_direct_wait_and_never_after(self) -> None:
        events: list[str] = []

        class Process:
            pid = 424242
            returncode: int | None = None

            def wait(self, timeout: float | None = None) -> int:
                events.append("direct-wait")
                self.returncode = 0
                return 0

            def kill(self) -> None:
                events.append("direct-kill")

        process = Process()

        def kill_group(pid: int, sent_signal: int) -> None:
            self.assertEqual((pid, sent_signal), (process.pid, signal.SIGKILL))
            events.append("group-kill")

        def reap_group(pid: int, options: int) -> tuple[int, int]:
            self.assertEqual((pid, options), (-process.pid, os.WNOHANG))
            events.append("descendant-wait")
            raise ChildProcessError

        with (
            mock.patch.object(supervisor.signal, "signal"),
            mock.patch.object(supervisor.os, "killpg", side_effect=kill_group),
            mock.patch.object(supervisor.os, "waitpid", side_effect=reap_group),
        ):
            returncode, cleaned = supervisor._cleanup_adapter_group(
                process,  # type: ignore[arg-type]
                cleanup_timeout=0.2,
            )

        self.assertEqual(returncode, 0)
        self.assertTrue(cleaned)
        self.assertEqual(events, ["group-kill", "direct-wait", "descendant-wait"])

    def test_cleanup_never_signals_an_already_reaped_group_leader(self) -> None:
        process = mock.Mock(pid=424242, returncode=0)
        with mock.patch.object(supervisor.os, "killpg") as kill_group:
            returncode, cleaned = supervisor._cleanup_adapter_group(
                process,
                cleanup_timeout=0.2,
            )

        self.assertEqual(returncode, 0)
        self.assertFalse(cleaned)
        kill_group.assert_not_called()
        process.wait.assert_not_called()

    def test_linux_subreaper_failure_is_fail_closed_before_spawn(self) -> None:
        with (
            mock.patch.object(supervisor, "_prepare_signal_state"),
            mock.patch.object(
                supervisor,
                "_enable_linux_subreaper",
                side_effect=supervisor._SupervisorError("unavailable"),
            ),
            mock.patch.object(supervisor.subprocess, "Popen") as spawn,
        ):
            exit_code = supervisor._main(
                ["_measurement_supervisor.py", "/private/snapshot", "0.2"]
            )

        self.assertEqual(exit_code, supervisor._SUPERVISOR_FAILURE)
        spawn.assert_not_called()

    def test_linux_prctl_error_is_categorical(self) -> None:
        fake_libc = mock.Mock()
        fake_libc.prctl.return_value = -1
        with (
            mock.patch.object(supervisor.sys, "platform", "linux"),
            mock.patch.object(supervisor.ctypes, "CDLL", return_value=fake_libc),
            mock.patch.object(supervisor.ctypes, "get_errno", return_value=1),
            self.assertRaises(supervisor._SupervisorError),
        ):
            supervisor._enable_linux_subreaper()

        fake_libc.prctl.assert_called_once_with(
            supervisor._PR_SET_CHILD_SUBREAPER,
            1,
            0,
            0,
            0,
        )

    def test_term_during_spawn_assignment_still_cleans_the_bound_process(self) -> None:
        process = mock.Mock(pid=424242, returncode=None)

        def spawn(*_args: object, **_kwargs: object) -> mock.Mock:
            supervisor._request_termination(signal.SIGTERM, None)
            return process

        with (
            mock.patch.object(supervisor, "_prepare_signal_state"),
            mock.patch.object(supervisor, "_enable_linux_subreaper"),
            mock.patch.object(supervisor.subprocess, "Popen", side_effect=spawn),
            mock.patch.object(
                supervisor,
                "_cleanup_adapter_group",
                return_value=(-9, True),
            ) as cleanup,
        ):
            exit_code = supervisor._main(
                ["_measurement_supervisor.py", "/private/snapshot", "0.2"]
            )

        self.assertEqual(exit_code, supervisor._SUPERVISOR_TERMINATED)
        cleanup.assert_called_once_with(
            process,
            cleanup_timeout=0.2,
            leader_exited=False,
        )

    def test_term_at_exit_observation_still_runs_cleanup(self) -> None:
        process = mock.Mock(pid=424242, returncode=None)

        def observe(*_args: object) -> bool:
            supervisor._request_termination(signal.SIGTERM, None)
            return True

        with (
            mock.patch.object(supervisor, "_prepare_signal_state"),
            mock.patch.object(supervisor, "_enable_linux_subreaper"),
            mock.patch.object(supervisor.subprocess, "Popen", return_value=process),
            mock.patch.object(
                supervisor,
                "_observe_exit_without_reaping",
                side_effect=observe,
            ),
            mock.patch.object(
                supervisor,
                "_cleanup_adapter_group",
                return_value=(0, True),
            ) as cleanup,
        ):
            exit_code = supervisor._main(
                ["_measurement_supervisor.py", "/private/snapshot", "0.2"]
            )

        self.assertEqual(exit_code, supervisor._SUPERVISOR_TERMINATED)
        cleanup.assert_called_once_with(
            process,
            cleanup_timeout=0.2,
            leader_exited=True,
        )


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
        self.assertTrue(runner.call_args.kwargs["start_new_session"])
        command = runner.call_args.args[0]
        self.assertEqual(command[:3], [sys.executable, "-I", "-S"])
        self.assertTrue(command[3].endswith("_measurement_supervisor.py"))
        self.assertNotIn(os.fspath(executable), command[:4])

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
                self.assertEqual(argv[:3], [sys.executable, "-I", "-S"])
                snapshot = Path(argv[4])
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

    @POSIX_SAMPLER_ONLY
    def test_snapshot_cleanup_does_not_mask_the_primary_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._executable(Path(temporary))
            sampler = LocalMeasurementSampler(executable)
            real_snapshot_directory = tempfile.TemporaryDirectory()

            class CleanupFailure:
                name = real_snapshot_directory.name

                @staticmethod
                def cleanup() -> None:
                    real_snapshot_directory.cleanup()
                    raise OSError("cleanup failed")

            with (
                mock.patch(
                    "local_inference_test_bench.measurement.tempfile.TemporaryDirectory",
                    return_value=CleanupFailure(),
                ),
                mock.patch.object(
                    subprocess,
                    "Popen",
                    side_effect=OSError("spawn failed"),
                ),
                self.assertRaisesRegex(MeasurementError, "could not run safely") as raised,
            ):
                sampler.sample(
                    phase="pre",
                    source_run_id=RUN_ID,
                    model_ids=MODEL_IDS,
                )

        self.assertNotIn("removed safely", str(raised.exception))

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
            marker = f"litb-timeout-descendant-{os.getpid()}-{time.monotonic_ns()}"
            descendant_pid: int | None = None
            executable.write_text(
                "\n".join(
                    (
                        f"#!{sys.executable}",
                        "import json, subprocess, sys, time",
                        "from pathlib import Path",
                        "request = json.load(sys.stdin)",
                        "child = subprocess.Popen([sys.executable, '-c', "
                        f"'import time; time.sleep(60)', {marker!r}])",
                        f"Path({os.fspath(pid_file)!r}).write_text(str(child.pid), encoding='utf-8')",
                        "json.dump({**request, 'sample': {"
                        "'outcome': 'within_thresholds', 'categories': []}}, sys.stdout)",
                        "sys.stdout.flush()",
                        "time.sleep(60)",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)

            try:
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
                identity = _process_identity(descendant_pid)
                _wait_for_original_process_to_disappear(descendant_pid, identity)
            finally:
                _cleanup_test_process(descendant_pid, marker)

    @POSIX_SAMPLER_ONLY
    def test_successful_adapter_reaps_a_background_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "tree-sampler"
            pid_file = root / "descendant.pid"
            marker = f"litb-success-descendant-{os.getpid()}-{time.monotonic_ns()}"
            descendant_pid: int | None = None
            executable.write_text(
                "\n".join(
                    (
                        f"#!{sys.executable}",
                        "import json, subprocess, sys",
                        "from pathlib import Path",
                        "request = json.load(sys.stdin)",
                        "child = subprocess.Popen([sys.executable, '-c', "
                        f"'import time; time.sleep(60)', {marker!r}], "
                        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                        "stderr=subprocess.DEVNULL)",
                        f"Path({os.fspath(pid_file)!r}).write_text(str(child.pid), encoding='utf-8')",
                        "json.dump({**request, 'sample': {"
                        "'outcome': 'within_thresholds', 'categories': []}}, sys.stdout)",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)

            try:
                sample = LocalMeasurementSampler(executable).sample(
                    phase="pre",
                    source_run_id=RUN_ID,
                    model_ids=MODEL_IDS,
                )
                self.assertEqual(
                    sample,
                    {"outcome": "within_thresholds", "categories": []},
                )
                descendant_pid = int(pid_file.read_text(encoding="utf-8"))
                identity = _process_identity(descendant_pid)
                _wait_for_original_process_to_disappear(descendant_pid, identity)
            finally:
                _cleanup_test_process(descendant_pid, marker)

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
