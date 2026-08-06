"""Private process supervisor for one local measurement sampler invocation.

This module intentionally imports only the Python standard library so it can be
executed in isolated mode.  It is an internal containment boundary, not a public
command-line interface.
"""

from __future__ import annotations

import ctypes
import math
import os
import select
import signal
import subprocess
import sys
import time
from typing import Sequence


_PR_SET_CHILD_SUBREAPER = 36
_SUPERVISOR_FAILURE = 125
_SUPERVISOR_TERMINATED = 124
_MAX_CLEANUP_TIMEOUT_SECONDS = 30.0
_termination_requested = False


class _SupervisorError(Exception):
    """Raised when the private containment boundary cannot be established."""


def _request_termination(_signum: int, _frame: object) -> None:
    # A flag avoids asynchronous exceptions during Popen assignment or cleanup.
    global _termination_requested
    _termination_requested = True


def _enable_linux_subreaper() -> None:
    """Adopt orphaned adapter descendants on Linux or fail before spawning."""

    if not sys.platform.startswith("linux"):
        return
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        result = libc.prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0)
    except (AttributeError, OSError) as error:
        raise _SupervisorError("Linux child subreaper is unavailable") from error
    if result != 0:
        error_number = ctypes.get_errno()
        raise _SupervisorError("Linux child subreaper could not be enabled") from OSError(
            error_number,
            os.strerror(error_number),
        )


def _prepare_signal_state() -> None:
    """Restore waitable children and make supervisor termination deliverable."""

    if not hasattr(signal, "SIGCHLD"):
        raise _SupervisorError("POSIX child signals are unavailable")
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, _request_termination)
    if hasattr(signal, "pthread_sigmask"):
        signal.pthread_sigmask(
            signal.SIG_UNBLOCK,
            {signal.SIGCHLD, signal.SIGTERM},
        )


def _remaining(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _waitid_observer_available() -> bool:
    return all(
        getattr(os, name, None) is not None
        for name in ("P_PID", "WEXITED", "WNOWAIT", "WNOHANG", "waitid")
    ) and callable(getattr(os, "waitid", None))


def _darwin_kqueue_observer_available() -> bool:
    return sys.platform == "darwin" and all(
        getattr(select, name, None) is not None
        for name in (
            "kqueue",
            "kevent",
            "KQ_FILTER_PROC",
            "KQ_EV_ADD",
            "KQ_EV_ENABLE",
            "KQ_EV_ONESHOT",
            "KQ_EV_ERROR",
            "KQ_NOTE_EXIT",
        )
    )


def _require_nonreaping_observer() -> None:
    if _waitid_observer_available() or _darwin_kqueue_observer_available():
        return
    raise _SupervisorError("wait-without-reaping is unavailable")


def _observe_exit_with_waitid(pid: int) -> bool:
    while not _termination_requested:
        status = os.waitid(  # type: ignore[attr-defined]
            os.P_PID,
            pid,
            os.WEXITED | os.WNOWAIT | os.WNOHANG,
        )
        if status is not None and status.si_pid == pid:
            return True
        time.sleep(0.01)
    return False


def _observe_exit_with_darwin_kqueue(pid: int) -> bool:
    """Observe NOTE_EXIT without consuming the child's wait status."""

    queue = None
    try:
        try:
            queue = select.kqueue()  # type: ignore[attr-defined]
            registration = select.kevent(  # type: ignore[attr-defined]
                pid,
                filter=select.KQ_FILTER_PROC,  # type: ignore[attr-defined]
                flags=(
                    select.KQ_EV_ADD  # type: ignore[attr-defined]
                    | select.KQ_EV_ENABLE  # type: ignore[attr-defined]
                    | select.KQ_EV_ONESHOT  # type: ignore[attr-defined]
                ),
                fflags=select.KQ_NOTE_EXIT,  # type: ignore[attr-defined]
            )
        except (AttributeError, OSError, ValueError) as error:
            raise _SupervisorError(
                "Darwin process observer could not be created"
            ) from error
        try:
            queue.control([registration], 0, 0)
        except ProcessLookupError:
            # This helper is the child's sole waiter, SIGCHLD is SIG_DFL, and
            # neither poll nor wait has run. Darwin returns ESRCH when that
            # still-unreaped direct child exited before EVFILT_PROC registration.
            # Its zombie pins the PID/PGID until kill-before-wait cleanup.
            return True
        except (OSError, ValueError) as error:
            raise _SupervisorError(
                "Darwin process observer could not be created"
            ) from error

        while not _termination_requested:
            try:
                events = queue.control(None, 1, 0.05)
            except InterruptedError:
                continue
            if not events:
                continue
            event = events[0]
            if event.flags & select.KQ_EV_ERROR:  # type: ignore[attr-defined]
                raise _SupervisorError("Darwin process observer failed")
            if event.ident == pid and event.fflags & select.KQ_NOTE_EXIT:  # type: ignore[attr-defined]
                return True
        return False
    except OSError as error:
        raise _SupervisorError("Darwin process observer failed") from error
    finally:
        if queue is not None:
            try:
                queue.close()
            except OSError:
                pass


def _observe_exit_without_reaping(pid: int) -> bool:
    if _waitid_observer_available():
        return _observe_exit_with_waitid(pid)
    if _darwin_kqueue_observer_available():
        return _observe_exit_with_darwin_kqueue(pid)
    raise _SupervisorError("wait-without-reaping is unavailable")


def _cleanup_adapter_group(
    process: subprocess.Popen[bytes],
    *,
    cleanup_timeout: float,
    leader_exited: bool = False,
) -> tuple[int | None, bool]:
    """Kill before reaping, then boundedly reap same-group descendants."""

    # A non-None returncode means some other path already reaped the leader.  Its
    # numeric PID may have been reused, so signaling that process group is banned.
    if process.returncode is not None:
        return process.returncode, False

    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    deadline = time.monotonic() + cleanup_timeout
    cleanup_succeeded = True
    process_group = process.pid

    try:
        os.killpg(process_group, signal.SIGKILL)
    except ProcessLookupError:
        # A completed leader with no remaining live group members is expected.
        pass
    except PermissionError:
        # Darwin reports EPERM, rather than ESRCH, for a group containing only
        # an unreaped zombie leader.  It is safe only after the platform's
        # non-reaping observer saw that leader exit; a live leader fails closed.
        if not (sys.platform == "darwin" and leader_exited):
            cleanup_succeeded = False
            try:
                process.kill()
            except OSError:
                pass
    except OSError:
        cleanup_succeeded = False
        try:
            process.kill()
        except OSError:
            pass

    try:
        returncode: int | None = process.wait(timeout=_remaining(deadline))
    except (OSError, subprocess.TimeoutExpired):
        # Do not signal the group again: its leader may be reaped concurrently by
        # an abnormal platform wait implementation.  A direct-PID kill is still
        # safe while Popen has no returncode.
        cleanup_succeeded = False
        returncode = None
        if process.returncode is None:
            try:
                process.kill()
            except OSError:
                pass

    if returncode is None:
        return None, False

    while True:
        try:
            descendant_pid, _status = os.waitpid(-process_group, os.WNOHANG)
        except ChildProcessError:
            break
        except InterruptedError:
            continue
        except OSError:
            cleanup_succeeded = False
            break
        if descendant_pid > 0:
            continue
        if _remaining(deadline) <= 0:
            cleanup_succeeded = False
            break
        time.sleep(min(0.01, _remaining(deadline)))

    return returncode, cleanup_succeeded


def _parse_arguments(argv: Sequence[str]) -> tuple[str, float]:
    if len(argv) != 3:
        raise _SupervisorError("invalid private supervisor invocation")
    executable = argv[1]
    try:
        cleanup_timeout = float(argv[2])
    except ValueError as error:
        raise _SupervisorError("invalid private supervisor invocation") from error
    if (
        not executable
        or not math.isfinite(cleanup_timeout)
        or cleanup_timeout <= 0
        or cleanup_timeout > _MAX_CLEANUP_TIMEOUT_SECONDS
    ):
        raise _SupervisorError("invalid private supervisor invocation")
    return executable, cleanup_timeout


def _main(argv: Sequence[str]) -> int:
    """Run one sampler without ever writing supervisor diagnostics to stdout."""

    global _termination_requested
    _termination_requested = False
    process: subprocess.Popen[bytes] | None = None
    observed_exit = False
    termination_requested = False
    failed = False
    cleanup_timeout = 1.0
    try:
        executable, cleanup_timeout = _parse_arguments(argv)
        _require_nonreaping_observer()
        _prepare_signal_state()
        _enable_linux_subreaper()
        process = subprocess.Popen(
            [executable],
            stdin=None,
            stdout=None,
            stderr=subprocess.DEVNULL,
            env=dict(os.environ),
            close_fds=True,
            restore_signals=True,
            start_new_session=True,
            shell=False,
        )
        if not _termination_requested:
            observed_exit = _observe_exit_without_reaping(process.pid)
        termination_requested = _termination_requested
    except BaseException:
        failed = True

    returncode: int | None = None
    cleanup_succeeded = process is None
    if process is not None:
        returncode, cleanup_succeeded = _cleanup_adapter_group(
            process,
            cleanup_timeout=cleanup_timeout,
            leader_exited=observed_exit,
        )

    if (
        failed
        or termination_requested
        or not observed_exit
        or not cleanup_succeeded
        or returncode != 0
    ):
        return _SUPERVISOR_TERMINATED if termination_requested else _SUPERVISOR_FAILURE
    return 0


if __name__ == "__main__":
    try:
        exit_code = _main(sys.argv)
    except BaseException:
        exit_code = _SUPERVISOR_FAILURE
    raise SystemExit(exit_code)
