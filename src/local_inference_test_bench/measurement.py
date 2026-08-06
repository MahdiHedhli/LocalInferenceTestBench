"""Bounded local adapter bridge for categorical measurement evidence."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import tempfile
import threading
import time
from typing import Any, Mapping, Sequence

from .safety import (
    SafetyError,
    secure_directory,
    validate_env_file,
    validate_ignored_destination,
)
from .submissions import (
    MAX_MEASUREMENT_EVIDENCE_BYTES,
    SubmissionError,
    validate_measurement_sample,
    validate_measurement_evidence,
)


_MAX_ADAPTER_OUTPUT_BYTES = 256 * 1024
_MAX_ADAPTER_REQUEST_BYTES = 256 * 1024
_MAX_ADAPTER_EXECUTABLE_BYTES = 16 * 1024 * 1024
_ADAPTER_TIMEOUT_SECONDS = 30.0
_CLEANUP_TIMEOUT_SECONDS = 2.0
_SAFE_ENVIRONMENT_KEYS = (
    "PATH",
    "HOME",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "SystemRoot",
    "WINDIR",
    "PATHEXT",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
)


class MeasurementError(SubmissionError):
    """Raised when trusted local measurement evidence cannot be obtained safely."""


@dataclass(frozen=True, slots=True)
class _AdapterIdentity:
    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _AdapterInspection:
    identity: _AdapterIdentity
    approved_bytes: bytes | None


def _reject_json_constant(_: str) -> None:
    raise ValueError("unsupported JSON constant")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object field")
        result[key] = value
    return result


def _file_signature(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def _inspect_adapter(
    path: Path,
    *,
    capture_bytes: bool = False,
) -> _AdapterInspection:
    descriptor: int | None = None
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise MeasurementError("measurement sampler must be a regular non-symlink file")
        if before.st_size > _MAX_ADAPTER_EXECUTABLE_BYTES:
            raise MeasurementError("measurement sampler executable exceeded the size limit")
        if os.name != "nt":
            if before.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise MeasurementError(
                    "measurement sampler must not be group or world writable"
                )
            if not os.access(path, os.X_OK):
                raise MeasurementError("measurement sampler must be executable")
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | (getattr(os, "O_NONBLOCK", 0) if os.name != "nt" else 0)
        )
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise MeasurementError("measurement sampler must remain a regular file")
        if os.name != "nt":
            if opened.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise MeasurementError(
                    "measurement sampler must not be group or world writable"
                )
            if not opened.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
                raise MeasurementError("measurement sampler must be executable")
        if opened.st_size > _MAX_ADAPTER_EXECUTABLE_BYTES:
            raise MeasurementError("measurement sampler executable exceeded the size limit")
        digest = hashlib.sha256()
        bytes_read = 0
        captured: list[bytes] | None = [] if capture_bytes else None
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            bytes_read += len(chunk)
            if bytes_read > _MAX_ADAPTER_EXECUTABLE_BYTES:
                raise MeasurementError(
                    "measurement sampler executable exceeded the size limit"
                )
            digest.update(chunk)
            if captured is not None:
                captured.append(chunk)
        after = path.lstat()
    except MeasurementError:
        raise
    except OSError as error:
        raise MeasurementError("measurement sampler could not be inspected") from error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
    if not (
        _file_signature(before) == _file_signature(opened) == _file_signature(after)
    ):
        raise MeasurementError("measurement sampler changed while it was inspected")
    return _AdapterInspection(
        identity=_AdapterIdentity(*_file_signature(after), digest.hexdigest()),
        approved_bytes=b"".join(captured) if captured is not None else None,
    )


def _adapter_path(path: str | Path) -> tuple[Path, _AdapterIdentity, bytes]:
    if os.name == "nt":
        raise MeasurementError(
            "single-command measurement sampling requires POSIX process containment; "
            "use prepare-submission with an exact-bound sidecar on Windows"
        )
    candidate = Path(path).expanduser()
    try:
        metadata = candidate.lstat()
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise MeasurementError("measurement sampler could not be inspected") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise MeasurementError("measurement sampler must be a regular non-symlink file")
    inspection = _inspect_adapter(resolved, capture_bytes=True)
    identity = inspection.identity
    if identity.size > _MAX_ADAPTER_EXECUTABLE_BYTES:
        raise MeasurementError("measurement sampler executable exceeded the size limit")
    approved_bytes = inspection.approved_bytes
    if (
        approved_bytes is None
        or len(approved_bytes) != identity.size
        or hashlib.sha256(approved_bytes).hexdigest() != identity.sha256
    ):
        raise MeasurementError("measurement sampler changed while it was approved")
    _verify_adapter_identity(resolved, identity)
    return resolved, identity, approved_bytes


def _verify_adapter_identity(path: Path, expected: _AdapterIdentity) -> None:
    if _inspect_adapter(path).identity != expected:
        raise MeasurementError("measurement sampler changed after it was approved")


@contextmanager
def _approved_adapter_snapshot(
    approved_bytes: bytes,
    expected_digest: str,
    suffix: str,
):
    """Materialize approved bytes in a private, non-writable execution directory."""

    temporary: tempfile.TemporaryDirectory[str] | None = None
    directory: Path | None = None
    snapshot: Path | None = None
    descriptor: int | None = None
    try:
        temporary = tempfile.TemporaryDirectory(prefix="litb-measurement-sampler-")
        directory = Path(temporary.name)
        snapshot = directory / f"sampler{suffix}"
        if os.name != "nt":
            directory.chmod(0o700)
        descriptor = os.open(
            snapshot,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o500,
        )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(approved_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            snapshot.chmod(0o500)
        snapshot_identity = _inspect_adapter(snapshot).identity
        if snapshot_identity.sha256 != expected_digest:
            raise MeasurementError("measurement sampler snapshot could not be verified")
        if os.name != "nt":
            directory.chmod(0o500)
        yield snapshot, snapshot_identity
    except MeasurementError:
        raise
    except OSError as error:
        raise MeasurementError(
            "measurement sampler snapshot could not be created safely"
        ) from error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if os.name != "nt":
            if directory is not None:
                try:
                    directory.chmod(0o700)
                except OSError:
                    pass
            if snapshot is not None:
                try:
                    snapshot.chmod(0o600)
                except OSError:
                    pass
        if temporary is not None:
            try:
                temporary.cleanup()
            except OSError as error:
                raise MeasurementError(
                    "measurement sampler snapshot could not be removed safely"
                ) from error


def _strict_adapter_response(raw: bytes) -> dict[str, Any]:
    if len(raw) > _MAX_ADAPTER_OUTPUT_BYTES:
        raise MeasurementError("measurement sampler output exceeded the size limit")
    try:
        decoded = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise MeasurementError("measurement sampler returned invalid JSON") from error
    if not isinstance(decoded, dict):
        raise MeasurementError("measurement sampler returned invalid JSON")
    return decoded


def _terminate_adapter_tree(process: subprocess.Popen[bytes]) -> None:
    """Best-effort bounded teardown of the isolated adapter process tree."""

    pid = getattr(process, "pid", None)
    if isinstance(pid, int) and pid > 0:
        try:
            os.killpg(pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    else:
        try:
            process.kill()
        except OSError:
            pass
    try:
        if process.poll() is None:
            process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=_CLEANUP_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _close_pipe_descriptor(pipe: Any) -> None:
    try:
        os.close(pipe.fileno())
    except (AttributeError, OSError, ValueError):
        pass


def _run_adapter_bounded(
    executable: Path,
    expected_identity: _AdapterIdentity,
    request: bytes,
) -> bytes:
    """Run an adapter while bounding capture, lifetime, and process-tree cleanup."""

    if os.name == "nt":
        raise MeasurementError(
            "single-command measurement sampling requires POSIX process containment"
        )
    if len(request) > _MAX_ADAPTER_REQUEST_BYTES:
        raise MeasurementError("measurement sampler request exceeded the size limit")
    environment = {
        key: os.environ[key] for key in _SAFE_ENVIRONMENT_KEYS if key in os.environ
    }
    _verify_adapter_identity(executable, expected_identity)
    try:
        process = subprocess.Popen(
            [os.fspath(executable)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
            start_new_session=True,
        )
    except (OSError, RuntimeError) as error:
        raise MeasurementError("measurement sampler could not run safely") from error

    captured: list[bytes] = []
    read_failed: list[bool] = []
    write_failed: list[bool] = []

    def write_stdin() -> None:
        try:
            if process.stdin is None:
                write_failed.append(True)
                return
            process.stdin.write(request)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            write_failed.append(True)

    def read_stdout() -> None:
        try:
            if process.stdout is None:
                read_failed.append(True)
                return
            captured.append(process.stdout.read(_MAX_ADAPTER_OUTPUT_BYTES + 1))
        except OSError:
            read_failed.append(True)

    deadline = time.monotonic() + _ADAPTER_TIMEOUT_SECONDS
    reader = threading.Thread(target=read_stdout, daemon=True)
    writer = threading.Thread(target=write_stdin, daemon=True)
    reader_started = False
    writer_started = False
    try:
        _verify_adapter_identity(executable, expected_identity)
        if process.stdin is None or process.stdout is None:
            raise MeasurementError("measurement sampler could not run safely")
        reader.start()
        reader_started = True
        writer.start()
        writer_started = True
        writer.join(max(0.0, deadline - time.monotonic()))
        reader.join(max(0.0, deadline - time.monotonic()))
        if writer.is_alive() or reader.is_alive():
            raise MeasurementError("measurement sampler timed out")
        raw = captured[0] if captured else b""
        if write_failed or read_failed:
            raise MeasurementError("measurement sampler input or output could not be transferred")
        if len(raw) > _MAX_ADAPTER_OUTPUT_BYTES:
            raise MeasurementError("measurement sampler output exceeded the size limit")
        try:
            returncode = process.wait(max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as error:
            raise MeasurementError("measurement sampler timed out") from error
        if returncode != 0:
            raise MeasurementError("measurement sampler did not complete successfully")
        return raw
    except (OSError, RuntimeError) as error:
        raise MeasurementError("measurement sampler could not run safely") from error
    finally:
        _terminate_adapter_tree(process)
        if writer_started and writer.is_alive():
            _close_pipe_descriptor(process.stdin)
        if reader_started and reader.is_alive():
            _close_pipe_descriptor(process.stdout)
        if writer_started:
            writer.join(_CLEANUP_TIMEOUT_SECONDS)
        if reader_started:
            reader.join(_CLEANUP_TIMEOUT_SECONDS)
        if (
            (not writer_started or not writer.is_alive())
            and process.stdin is not None
            and not process.stdin.closed
        ):
            try:
                process.stdin.close()
            except OSError:
                pass
        if (not reader_started or not reader.is_alive()) and process.stdout is not None:
            try:
                process.stdout.close()
            except OSError:
                pass


class LocalMeasurementSampler:
    """Invoke one explicitly selected adapter for synchronous pre/post samples."""

    def __init__(self, executable: str | Path) -> None:
        (
            self.executable,
            self._identity,
            self._approved_bytes,
        ) = _adapter_path(executable)

    def sample(
        self,
        *,
        phase: str,
        source_run_id: str,
        model_ids: Sequence[str],
    ) -> dict[str, Any]:
        if phase not in {"pre", "post"}:
            raise MeasurementError("measurement sampler phase is invalid")
        expected_models = list(model_ids)
        request = {
            "schema_version": "1.0",
            "source_run_id": source_run_id,
            "phase": phase,
            "model_ids": expected_models,
        }
        request_bytes = json.dumps(
            request,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        _verify_adapter_identity(self.executable, self._identity)
        with _approved_adapter_snapshot(
            self._approved_bytes,
            self._identity.sha256,
            self.executable.suffix,
        ) as (snapshot, snapshot_identity):
            response = _strict_adapter_response(
                _run_adapter_bounded(snapshot, snapshot_identity, request_bytes)
            )
        _verify_adapter_identity(self.executable, self._identity)
        if set(response) != {
            "schema_version",
            "source_run_id",
            "phase",
            "model_ids",
            "sample",
        }:
            raise MeasurementError("measurement sampler response shape is invalid")
        if (
            response["schema_version"] != "1.0"
            or response["source_run_id"] != source_run_id
            or response["phase"] != phase
            or response["model_ids"] != expected_models
            or not isinstance(response["sample"], dict)
        ):
            raise MeasurementError("measurement sampler response binding is invalid")
        try:
            return validate_measurement_sample(response["sample"])
        except SubmissionError as error:
            raise MeasurementError(
                "measurement sampler returned invalid categorical evidence"
            ) from error


def build_measurement_evidence(
    *,
    source_run_id: str,
    model_ids: Sequence[str],
    pre: Mapping[str, Any],
    post: Mapping[str, Any],
) -> dict[str, Any]:
    """Build exact-bound evidence from two adapter-produced categorical samples."""

    pre_sample = dict(pre)
    post_sample = dict(post)
    if set(pre_sample) != {"outcome", "categories"} or set(post_sample) != {
        "outcome",
        "categories",
    }:
        raise MeasurementError("measurement sampler returned invalid categorical evidence")
    pre_categories = pre_sample.get("categories")
    post_categories = post_sample.get("categories")
    if (
        not isinstance(pre_categories, list)
        or not all(isinstance(category, str) for category in pre_categories)
        or not isinstance(post_categories, list)
        or not all(isinstance(category, str) for category in post_categories)
    ):
        raise MeasurementError("measurement sampler returned invalid categorical evidence")
    pre_set = set(pre_categories)
    post_set = set(post_categories)
    validity = (
        "degraded_midrun"
        if post_set - pre_set
        else "nonquiescent" if pre_set else "clean"
    )
    conditions = {
        "pre": pre_sample,
        "post": post_sample,
        "hard_threshold_crossed": bool(pre_set or post_set),
    }
    evidence = {
        "schema_version": "1.0",
        "source_run_id": source_run_id,
        "models": [
            {
                "model_id": model_id,
                "validity": validity,
                "measurement_conditions": conditions,
            }
            for model_id in model_ids
        ],
    }
    try:
        validate_measurement_evidence(evidence)
    except SubmissionError as error:
        raise MeasurementError(
            "measurement sampler returned invalid categorical evidence"
        ) from error
    return evidence


def write_measurement_evidence(
    evidence: Mapping[str, Any], path: str | Path
) -> Path:
    """Atomically retain one owner-only ignored sidecar for the completed run."""

    try:
        validate_measurement_evidence(evidence)
        rendered = (
            json.dumps(
                evidence,
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (SubmissionError, TypeError, ValueError) as error:
        raise MeasurementError("measurement evidence could not be rendered safely") from error
    if len(rendered) > MAX_MEASUREMENT_EVIDENCE_BYTES:
        raise MeasurementError("measurement evidence exceeded the size limit")

    temporary_path: Path | None = None
    try:
        requested = Path(path).expanduser()
        if requested.is_symlink():
            raise SafetyError("measurement evidence destination must not be a symlink")
        destination = validate_ignored_destination(requested)
        directory = secure_directory(destination.parent)
        if destination.exists() or destination.is_symlink():
            validate_env_file(destination)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".measurement-evidence-",
            suffix=".json",
            dir=directory,
        )
        temporary_path = Path(temporary_name)
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
        if os.name != "nt":
            destination.chmod(0o600)
        return destination
    except (OSError, SafetyError) as error:
        raise MeasurementError("measurement evidence could not be written securely") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
