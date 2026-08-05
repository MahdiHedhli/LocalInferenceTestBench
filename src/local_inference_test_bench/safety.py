"""Endpoint and credential gates for local-only inference."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
from typing import Callable, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit


class SafetyError(ValueError):
    """Raised before a request when a local safety boundary is not satisfied."""


@dataclass(frozen=True, slots=True)
class SafeEndpoint:
    """A normalized endpoint whose host resolved only to private addresses."""

    base_url: str
    host: str
    addresses: tuple[str, ...]


Resolver = Callable[..., Sequence[tuple]]
_ENV_LINE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_ALLOWED_ENDPOINT_NETWORKS = (
    ipaddress.IPv4Network((127 << 24, 8)),
    ipaddress.IPv4Network((10 << 24, 8)),
    ipaddress.IPv4Network(((172 << 24) | (16 << 16), 12)),
    ipaddress.IPv4Network(((192 << 24) | (168 << 16), 16)),
    ipaddress.IPv4Network(((169 << 24) | (254 << 16), 16)),
    ipaddress.IPv6Network((1, 128)),
    ipaddress.IPv6Network((0xFC << 120, 7)),
    ipaddress.IPv6Network((0xFE80 << 112, 10)),
)


def _git_environment() -> dict[str, str]:
    """Return the process environment without repository-routing overrides."""

    return {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }


def _has_git_marker(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in (path, *path.parents))


def _is_private_address(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    return any(
        parsed.version == network.version and parsed in network
        for network in _ALLOWED_ENDPOINT_NETWORKS
    )


def validate_endpoint(endpoint: str, *, resolver: Resolver = socket.getaddrinfo) -> SafeEndpoint:
    """Resolve and accept only credential-free local/private HTTP(S) base URLs."""

    if not isinstance(endpoint, str) or not endpoint:
        raise SafetyError("endpoint must be a non-empty URL")
    if any(ord(character) < 32 for character in endpoint):
        raise SafetyError("endpoint contains unsupported characters")
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError as error:
        raise SafetyError("endpoint is not a valid URL") from error
    if parsed.scheme not in {"http", "https"}:
        raise SafetyError("endpoint scheme must be http or https")
    if parsed.username is not None or parsed.password is not None:
        raise SafetyError("endpoint must not contain credentials")
    if parsed.query or parsed.fragment:
        raise SafetyError("endpoint must not contain a query or fragment")
    if not parsed.hostname:
        raise SafetyError("endpoint must include a host")
    if parsed.path.rstrip("/") not in {"", "/v1"}:
        raise SafetyError("endpoint path must be empty or /v1")
    if port is not None and not 1 <= port <= 65535:
        raise SafetyError("endpoint port is outside the valid range")

    try:
        answers = resolver(
            parsed.hostname,
            port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except (OSError, socket.gaierror) as error:
        raise SafetyError("endpoint host could not be resolved") from error

    addresses = sorted(
        {
            answer[4][0].split("%", 1)[0]
            for answer in answers
            if len(answer) >= 5 and answer[4]
        }
    )
    if not addresses:
        raise SafetyError("endpoint host did not resolve to an address")
    if any(not _is_private_address(address) for address in addresses):
        raise SafetyError("endpoint host must resolve only to private or loopback addresses")

    host = parsed.hostname.lower()
    rendered_host = f"[{host}]" if ":" in host else host
    netloc = rendered_host if port is None else f"{rendered_host}:{port}"
    normalized_path = "/v1" if parsed.path.rstrip("/") == "/v1" else ""
    return SafeEndpoint(
        base_url=urlunsplit((parsed.scheme, netloc, normalized_path, "", "")),
        host=host,
        addresses=tuple(addresses),
    )


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise SafetyError("credential environment file could not be read") from error
    for number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_LINE.fullmatch(line)
        if not match:
            raise SafetyError(f"credential environment file has invalid syntax at line {number}")
        name, raw_value = match.groups()
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[name] = value
    return values


def _is_in_ignored_worktree(path: Path, *, require_worktree: bool = False) -> bool:
    """Return whether Git confirms that a file inside a worktree is ignored.

    Files outside a worktree cannot accidentally be added to this repository and are accepted unless
    ``require_worktree`` is set. Git is a publication safeguard here, not a Python runtime
    dependency.
    """

    try:
        root_result = subprocess.run(
            ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
            env=_git_environment(),
        )
    except (OSError, subprocess.SubprocessError):
        return not require_worktree and not _has_git_marker(path.parent)
    if root_result.returncode != 0:
        return not require_worktree and not _has_git_marker(path.parent)
    root = Path(root_result.stdout.strip()).resolve()
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except OSError:
        return False
    except ValueError:
        return not require_worktree
    try:
        ignored = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--quiet", "--", str(resolved)],
            check=False,
            capture_output=True,
            timeout=3,
            env=_git_environment(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return ignored.returncode == 0


def validate_ignored_destination(path: str | Path) -> Path:
    """Require a future output path to be Git-ignored when it is in a worktree.

    Unlike :func:`validate_env_file`, this check intentionally supports a path
    that does not exist yet. Destinations outside a worktree remain valid.
    """

    candidate = Path(path).expanduser().resolve(strict=False)
    probe = candidate.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.exists() and not probe.is_dir():
        probe = probe.parent
    try:
        root_result = subprocess.run(
            ["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
            env=_git_environment(),
        )
    except (OSError, subprocess.SubprocessError) as error:
        if _has_git_marker(probe):
            raise SafetyError("submission destination ignore status could not be verified") from error
        return candidate
    if root_result.returncode != 0:
        if _has_git_marker(probe):
            raise SafetyError("submission destination ignore status could not be verified")
        return candidate
    root = Path(root_result.stdout.strip()).resolve()
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return candidate
    relative_text = relative.as_posix()
    try:
        tracked = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "--error-unmatch",
                "--",
                relative_text,
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            env=_git_environment(),
        )
        ignored = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "check-ignore",
                "--quiet",
                "--no-index",
                "--",
                relative_text,
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            env=_git_environment(),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SafetyError("submission destination ignore status could not be verified") from error
    if tracked.returncode not in {0, 1} or ignored.returncode not in {0, 1}:
        raise SafetyError("submission destination ignore status could not be verified")
    if tracked.returncode == 0 or ignored.returncode == 1:
        raise SafetyError("submission destination must be Git-ignored")
    return candidate


def validate_env_file(
    path: str | Path, *, require_worktree: bool = False
) -> Path:
    """Require a regular, owner-only, ignored file, optionally inside a worktree."""

    env_path = Path(path)
    try:
        metadata = env_path.lstat()
    except OSError as error:
        raise SafetyError("credential environment file could not be inspected") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise SafetyError("credential environment file must be a regular, non-symlink file")
    if os.name != "nt":
        if metadata.st_mode & 0o077:
            raise SafetyError("credential environment file permissions must be owner-only")
        if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
            raise SafetyError("credential environment file must be owned by the current user")
    if not _is_in_ignored_worktree(env_path, require_worktree=require_worktree):
        raise SafetyError("credential environment file must be ignored by Git")
    return env_path


def load_credential(
    environment_name: str | None,
    *,
    env_file: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Load one credential from process environment or an owner-only ignored env file.

    The value is returned to the caller but is never logged or included in an exception.
    """

    if environment_name is None:
        if env_file is not None:
            raise SafetyError("env_file requires credential_env in the manifest")
        return None
    if not re.fullmatch(r"[A-Z_][A-Z0-9_]{0,127}", environment_name):
        raise SafetyError("credential environment variable name is invalid")
    process_environment = os.environ if environ is None else environ
    value = process_environment.get(environment_name)
    if value:
        return value
    if env_file is not None:
        values = _parse_env_file(validate_env_file(env_file))
        value = values.get(environment_name)
        if value:
            return value
    raise SafetyError("required credential is not available from an approved environment source")


def secure_directory(path: str | Path) -> Path:
    """Create a local artifacts directory and restrict access where supported."""

    directory = Path(path)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not directory.is_dir() or directory.is_symlink():
        raise SafetyError("artifacts path must be a real directory")
    if os.name != "nt":
        try:
            directory.chmod(0o700)
        except OSError as error:
            raise SafetyError("artifacts directory permissions could not be secured") from error
    return directory
