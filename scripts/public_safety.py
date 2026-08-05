#!/usr/bin/env python3
"""Fail closed when tracked repository content crosses the public boundary.

The scanner intentionally reports only a rule identifier, repository-relative
file name, and line number. It never emits the matching text.
"""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import os
from pathlib import Path, PurePosixPath
import re
import socket
import stat
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Iterator, Sequence


DENYLIST_PATH = PurePosixPath(".local/privacy-denylist.txt")
EXPERIMENTS_PREFIX = PurePosixPath("docs/experiments")
MAX_TRACKED_BYTES = 5 * 1024 * 1024

# These names are intentionally assembled so that this scanner does not exempt
# its own source from the rule it enforces.
EXPERIMENTAL_NAMES = ("op" + "ik", "poly" + "range")

GENERIC_ACCOUNT_NAMES = frozenset(
    {
        "admin",
        "administrator",
        "nobody",
        "root",
        "runner",
        "ubuntu",
        "user",
    }
)

RISKY_SUFFIXES = frozenset(
    {
        ".7z",
        ".bin",
        ".bmp",
        ".cap",
        ".cer",
        ".crt",
        ".csr",
        ".db",
        ".der",
        ".doc",
        ".docx",
        ".gguf",
        ".gif",
        ".gz",
        ".har",
        ".jpeg",
        ".jpg",
        ".jks",
        ".key",
        ".keystore",
        ".kubeconfig",
        ".log",
        ".mobileprovision",
        ".onnx",
        ".ovpn",
        ".p12",
        ".p7b",
        ".p7c",
        ".pcap",
        ".pcapng",
        ".pdf",
        ".pem",
        ".pfx",
        ".png",
        ".ppt",
        ".pptx",
        ".rar",
        ".safetensors",
        ".sqlite",
        ".sqlite3",
        ".tar",
        ".tfstate",
        ".tfvars",
        ".tgz",
        ".tif",
        ".tiff",
        ".webp",
        ".xls",
        ".xlsx",
        ".zip",
    }
)

RISKY_BASENAMES = frozenset(
    {
        ".dockercfg",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "authorized_keys",
        "credentials",
        "id_dsa",
        "id_dsa.pub",
        "id_ecdsa",
        "id_ecdsa.pub",
        "id_ed25519",
        "id_ed25519.pub",
        "id_rsa",
        "id_rsa.pub",
        "known_hosts",
    }
)

_IPV4_CANDIDATE = re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])")
_IPV6_CANDIDATE = re.compile(
    r"(?i)(?<![0-9a-f:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}"
    r"(?:%[a-z0-9_.-]+)?(?![0-9a-f:])"
)
_MAC_COLON_OR_HYPHEN = re.compile(
    r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])"
)
_MAC_DOTTED = re.compile(
    r"(?i)(?<![0-9a-f])(?:[0-9a-f]{4}\.){2}[0-9a-f]{4}(?![0-9a-f])"
)
_POSIX_USER_PATH = re.compile(
    r"(?<![a-zA-Z0-9_.-])/(?:Users|home)/[a-zA-Z0-9._-]+(?=/|\b)"
)
_ROOT_USER_PATH = re.compile(r"(?<![a-zA-Z0-9_.-])/" + "root" + r"(?=/|\b)")
_WINDOWS_USER_PATH = re.compile(
    r"(?i)(?<![a-z0-9])(?:[a-z]:[\\/])Users[\\/][a-z0-9._-]+(?=[\\/]|\b)"
)
_PRIVATE_HOST = re.compile(
    r"(?i)(?<![a-z0-9_-])"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:lan|local|internal|home|corp|private|localdomain|home\.arpa)\.?"
    r"(?![a-z0-9_.-])"
)
_PRIVATE_KEY_HEADER = re.compile(
    r"-{5}BEGIN(?: [A-Z0-9]+)*(?: PRIVATE KEY| PRIVATE KEY BLOCK)-{5}", re.IGNORECASE
)
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?ix)"
    r"(?:^|[\s,{;/\\])"
    r"[\"']?"
    r"(?P<name>"
    r"(?:[a-z0-9]+[_-])*(?:"
    r"api[_-]?key|access[_-]?token|auth[_-]?token|bearer[_-]?token|"
    r"client[_-]?secret|connection[_-]?string|credential|password|passwd|"
    r"private[_-]?key|secret|token"
    r"))"
    r"[\"']?\s*(?::|=)\s*"
    r"(?P<value>"
    r"\"(?:\\.|[^\"\\])*\"|"
    r"'(?:\\.|[^'\\])*'|"
    r"[^\s,;#}]+"
    r")"
)


@dataclass(frozen=True, order=True)
class Finding:
    rule: str
    path: str
    line: int


@dataclass(frozen=True)
class IndexEntry:
    path: str
    mode: str
    object_id: str


@dataclass(frozen=True)
class ScanContext:
    runtime_literals: tuple[tuple[str, str], ...]
    denylist_terms: tuple[str, ...]


class RepositoryError(RuntimeError):
    """Raised for a Git operation failure without retaining command output."""


def _git(root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", os.fspath(root), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        raise RepositoryError
    return completed.stdout


def repository_root(candidate: Path) -> Path:
    try:
        output = _git(candidate, "rev-parse", "--show-toplevel")
        return Path(output.decode("utf-8", errors="strict").strip())
    except (OSError, UnicodeError, RepositoryError) as error:
        raise RepositoryError from error


def _index_entries(root: Path) -> list[IndexEntry]:
    records = _git(root, "ls-files", "--stage", "-z").split(b"\0")
    entries: list[IndexEntry] = []
    for record in records:
        if not record:
            continue
        metadata, separator, encoded_path = record.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3 or fields[2] != b"0":
            continue
        path = encoded_path.decode("utf-8", errors="surrogateescape")
        entries.append(
            IndexEntry(
                path=path,
                mode=fields[0].decode("ascii", errors="replace"),
                object_id=fields[1].decode("ascii", errors="replace"),
            )
        )
    return entries


def _tree_entries(root: Path, commit: str) -> list[IndexEntry]:
    records = _git(root, "ls-tree", "-r", "-z", commit).split(b"\0")
    entries: list[IndexEntry] = []
    for record in records:
        if not record:
            continue
        metadata, separator, encoded_path = record.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            continue
        path = encoded_path.decode("utf-8", errors="surrogateescape")
        entries.append(
            IndexEntry(
                path=path,
                mode=fields[0].decode("ascii", errors="replace"),
                object_id=fields[2].decode("ascii", errors="replace"),
            )
        )
    return entries


def _runtime_literals() -> tuple[tuple[str, str], ...]:
    candidates: list[tuple[str, str]] = []

    try:
        home = os.fspath(Path.home())
    except (OSError, RuntimeError):
        home = ""
    if home and home not in {"/", "."}:
        candidates.append(("current-home", home))

    try:
        username = getpass.getuser().strip()
    except (ImportError, KeyError, OSError):
        username = ""
    if username and username.casefold() not in GENERIC_ACCOUNT_NAMES:
        candidates.append(("current-username", username))

    hostnames: set[str] = set()
    for getter in (socket.gethostname, socket.getfqdn):
        try:
            value = getter().strip().rstrip(".")
        except OSError:
            value = ""
        if value:
            hostnames.add(value)
            hostnames.add(value.split(".", 1)[0])
    for hostname in sorted(hostnames):
        if hostname.casefold() not in {"localhost", "localhost.localdomain"}:
            candidates.append(("current-hostname", hostname))

    unique: dict[tuple[str, str], None] = {}
    for rule, value in candidates:
        if len(value) >= 3:
            unique[(rule, value)] = None
    return tuple(unique)


def _load_denylist(root: Path, strict: bool) -> tuple[tuple[str, ...], list[Finding]]:
    denylist = root.joinpath(*DENYLIST_PATH.parts)
    if not denylist.exists():
        if strict:
            return (), [Finding("denylist-required", DENYLIST_PATH.as_posix(), 1)]
        return (), []
    if not denylist.is_file() or denylist.is_symlink():
        return (), [Finding("denylist-invalid", DENYLIST_PATH.as_posix(), 1)]
    try:
        contents = denylist.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return (), [Finding("denylist-invalid", DENYLIST_PATH.as_posix(), 1)]

    terms: list[str] = []
    for line in contents.splitlines():
        term = line.strip()
        if term and not term.startswith("#"):
            terms.append(term)
    unique_terms = tuple(dict.fromkeys(terms))
    if strict and not unique_terms:
        return (), [Finding("denylist-empty", DENYLIST_PATH.as_posix(), 1)]
    findings: list[Finding] = []
    if strict:
        ignored = subprocess.run(
            [
                "git",
                "-C",
                os.fspath(root),
                "check-ignore",
                "--quiet",
                "--",
                DENYLIST_PATH.as_posix(),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if ignored.returncode != 0:
            findings.append(Finding("denylist-not-ignored", DENYLIST_PATH.as_posix(), 1))
        if os.name != "nt":
            try:
                permissions = stat.S_IMODE(denylist.stat().st_mode)
            except OSError:
                findings.append(Finding("denylist-invalid", DENYLIST_PATH.as_posix(), 1))
            else:
                if permissions & 0o077:
                    findings.append(Finding("denylist-permissions", DENYLIST_PATH.as_posix(), 1))
    return unique_terms, findings


def _is_rejected_ipv4(address: ipaddress.IPv4Address) -> tuple[bool, str]:
    value = int(address)
    ranges = (
        (10 << 24, (11 << 24) - 1, "private-ipv4"),
        ((172 << 24) | (16 << 16), (172 << 24) | (31 << 16) | 0xFFFF, "private-ipv4"),
        ((192 << 24) | (168 << 16), (192 << 24) | (168 << 16) | 0xFFFF, "private-ipv4"),
        ((100 << 24) | (64 << 16), (100 << 24) | (127 << 16) | 0xFFFF, "cgnat-ipv4"),
        ((169 << 24) | (254 << 16), (169 << 24) | (254 << 16) | 0xFFFF, "link-local-ipv4"),
    )
    for start, end, rule in ranges:
        if start <= value <= end:
            return True, rule
    return False, ""


def _is_rejected_ipv6(address: ipaddress.IPv6Address) -> bool:
    value = int(address)
    is_unique_local = value >> 121 == 0x7E
    is_link_local = value >> 118 == 0x3FA
    return is_unique_local or is_link_local


def _literal_present(line: str, value: str) -> bool:
    escaped = re.escape(value)
    if value[0].isalnum() and value[-1].isalnum():
        pattern = rf"(?<![a-zA-Z0-9_.-]){escaped}(?![a-zA-Z0-9_.-])"
    else:
        pattern = escaped
    return re.search(pattern, line, flags=re.IGNORECASE) is not None


def _credential_value_is_safe(name: str, raw_value: str) -> bool:
    value = raw_value.strip()
    was_quoted = len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}
    if was_quoted:
        value = value[1:-1].strip()
    folded = value.casefold()
    if not value or folded in {
        "changeme",
        "dummy",
        "example",
        "false",
        "none",
        "null",
        "placeholder",
        "redacted",
        "test",
        "true",
    }:
        return True
    if re.fullmatch(
        r"(?:changeme|dummy|example|placeholder|redacted|test)(?:\\[nrt]|[\"']).*",
        folded,
    ):
        return True
    if value.startswith(("$", "<", "{", "[")):
        return True
    if was_quoted and folded.startswith(
        ("changeme", "dummy", "example", "placeholder", "redacted", "test")
    ):
        return True
    if folded.startswith(
        (
            "env.",
            "getenv(",
            "os.environ",
            "os.getenv",
            "process.env",
            "secret(",
        )
    ):
        return True
    if folded in {
        "bytes",
        "credential",
        "credential_value",
        "key_value",
        "secret_value",
        "str",
        "token_value",
    }:
        return True
    if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.]*\(", value):
        return True
    normalized_name = re.sub(r"[^a-z0-9]", "", name.casefold())
    normalized_value = re.sub(r"[^a-z0-9]", "", folded)
    return normalized_value == normalized_name


def _has_private_hostname(line: str) -> bool:
    for match in _PRIVATE_HOST.finditer(line):
        candidate = match.group(0).rstrip(".").casefold()
        if candidate == "localhost.localdomain":
            continue
        if match.start() > 0 and line[match.start() - 1] == "\\":
            continue
        # A dotted method invocation can look like a two-label private host.
        if match.end() < len(line) and line[match.end()] == "(":
            continue
        return True
    return False


def _is_experiment_path(path: str) -> bool:
    parts = PurePosixPath(path).parts
    prefix = EXPERIMENTS_PREFIX.parts
    return len(parts) >= len(prefix) and parts[: len(prefix)] == prefix


def _scan_line(line: str, path: str, line_number: int, context: ScanContext) -> Iterator[Finding]:
    for candidate in _IPV4_CANDIDATE.finditer(line):
        try:
            address = ipaddress.IPv4Address(candidate.group(0))
        except ipaddress.AddressValueError:
            continue
        rejected, rule = _is_rejected_ipv4(address)
        if rejected:
            yield Finding(rule, path, line_number)

    for candidate in _IPV6_CANDIDATE.finditer(line):
        raw_address = candidate.group(0).split("%", 1)[0]
        try:
            address = ipaddress.IPv6Address(raw_address)
        except ipaddress.AddressValueError:
            continue
        if _is_rejected_ipv6(address):
            yield Finding("private-ipv6", path, line_number)

    if _MAC_COLON_OR_HYPHEN.search(line) or _MAC_DOTTED.search(line):
        yield Finding("mac-address", path, line_number)

    if _POSIX_USER_PATH.search(line) or _ROOT_USER_PATH.search(line) or _WINDOWS_USER_PATH.search(line):
        yield Finding("absolute-user-path", path, line_number)

    if _has_private_hostname(line):
        yield Finding("private-hostname", path, line_number)

    if _PRIVATE_KEY_HEADER.search(line):
        yield Finding("private-key", path, line_number)

    for assignment in _CREDENTIAL_ASSIGNMENT.finditer(line):
        if not _credential_value_is_safe(assignment.group("name"), assignment.group("value")):
            yield Finding("credential-assignment", path, line_number)

    for rule, literal in context.runtime_literals:
        if _literal_present(line, literal):
            yield Finding(rule, path, line_number)

    folded = line.casefold()
    for term in context.denylist_terms:
        if term.casefold() in folded:
            yield Finding("custom-denylist", path, line_number)

    if not _is_experiment_path(path):
        for name in EXPERIMENTAL_NAMES:
            if name in folded:
                yield Finding("experimental-name-scope", path, line_number)


def _risky_path_rule(path: str) -> str | None:
    pure_path = PurePosixPath(path)
    folded = path.casefold()
    basename = pure_path.name.casefold()

    if folded == DENYLIST_PATH.as_posix():
        return "tracked-local-file"
    is_local_only = folded == ".local" or folded.startswith(".local/")
    if is_local_only and folded != ".local/privacy-denylist.example":
        return "local-configuration"
    if folded in {"config/models.json"} or folded.endswith((".local.json", ".private.json")):
        return "local-configuration"
    if (
        (
            folded == "artifacts"
            or (folded.startswith("artifacts/") and folded != "artifacts/.gitkeep")
        )
        or folded == "reports"
        or folded.startswith("reports/")
        or folded == "results"
        or folded.startswith("results/")
        or folded == "runs"
        or folded.startswith("runs/")
    ):
        return "generated-artifact"
    if basename == ".env" or basename.startswith(".env."):
        return "risky-file-type"
    if basename in RISKY_BASENAMES or pure_path.suffix.casefold() in RISKY_SUFFIXES:
        return "risky-file-type"
    if folded in {".aws/credentials", ".docker/config.json", ".kube/config"}:
        return "risky-file-type"
    return None


def _decode_text(data: bytes, path: str) -> tuple[str | None, list[Finding]]:
    if any(byte < 0x20 and byte not in {0x09, 0x0A, 0x0D} for byte in data) or b"\x7f" in data:
        return None, [Finding("binary-file", path, 1)]
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None, [Finding("binary-file", path, 1)]
    if any(
        unicodedata.category(character) == "Cc" and character not in {"\t", "\n", "\r"}
        for character in text
    ):
        return None, [Finding("binary-file", path, 1)]
    return text, []


def _blob_is_oversized(root: Path, object_id: str) -> bool:
    try:
        raw_size = _git(root, "cat-file", "-s", object_id)
        size = int(raw_size.decode("ascii", errors="strict").strip())
    except (UnicodeError, ValueError) as error:
        raise RepositoryError from error
    return size > MAX_TRACKED_BYTES


def _scan_content(data: bytes, path: str, context: ScanContext) -> list[Finding]:
    text, findings = _decode_text(data, path)
    if text is None:
        return findings
    for line_number, line in enumerate(text.splitlines(), start=1):
        findings.extend(_scan_line(line, path, line_number, context))
    return findings


def _scan_entry_path(path: str, context: ScanContext) -> list[Finding]:
    findings: list[Finding] = []
    risky_rule = _risky_path_rule(path)
    if risky_rule:
        findings.append(Finding(risky_rule, path, 1))
    findings.extend(_scan_line(path, path, 1, context))
    return findings


def _scan_staged(root: Path, entries: Sequence[IndexEntry], context: ScanContext) -> list[Finding]:
    findings: list[Finding] = []
    for entry in entries:
        findings.extend(_scan_entry_path(entry.path, context))
        risky_path = _risky_path_rule(entry.path) is not None
        if entry.mode == "120000":
            findings.append(Finding("symlink", entry.path, 1))
            continue
        if entry.mode not in {"100644", "100755"}:
            findings.append(Finding("unsupported-file-mode", entry.path, 1))
            continue
        try:
            if _blob_is_oversized(root, entry.object_id):
                findings.append(Finding("oversized-file", entry.path, 1))
                continue
            if risky_path:
                continue
            data = _git(root, "cat-file", "blob", entry.object_id)
        except (OSError, RepositoryError):
            findings.append(Finding("repository-read-error", entry.path, 1))
            continue
        findings.extend(_scan_content(data, entry.path, context))
    return findings


def _path_contains_symlink(root: Path, path: str) -> bool:
    candidate = root
    for part in PurePosixPath(path).parts:
        candidate = candidate / part
        if candidate.is_symlink():
            return True
    return False


def _scan_full_tree(root: Path, entries: Sequence[IndexEntry], context: ScanContext) -> list[Finding]:
    findings: list[Finding] = []
    for entry in entries:
        findings.extend(_scan_entry_path(entry.path, context))
        risky_path = _risky_path_rule(entry.path) is not None
        file_path = root.joinpath(*PurePosixPath(entry.path).parts)
        if entry.mode == "120000" or _path_contains_symlink(root, entry.path):
            findings.append(Finding("symlink", entry.path, 1))
            continue
        if entry.mode not in {"100644", "100755"}:
            findings.append(Finding("unsupported-file-mode", entry.path, 1))
            continue
        if not file_path.exists():
            continue
        try:
            if file_path.stat().st_size > MAX_TRACKED_BYTES:
                findings.append(Finding("oversized-file", entry.path, 1))
                continue
            if risky_path:
                continue
            data = file_path.read_bytes()
        except OSError:
            findings.append(Finding("repository-read-error", entry.path, 1))
            continue
        findings.extend(_scan_content(data, entry.path, context))
    return findings


def _scan_history(
    root: Path,
    context: ScanContext,
    revision_roots: Sequence[str] = (),
) -> list[Finding]:
    root_messages: list[bytes] = []
    try:
        if revision_roots:
            peeled_roots: list[str] = []
            for revision in revision_roots:
                if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", revision):
                    raise RepositoryError
                object_type = _git(root, "cat-file", "-t", revision).decode(
                    "ascii", errors="strict"
                ).strip()
                if object_type == "tag":
                    tag_data = _git(root, "cat-file", "tag", revision)
                    _, separator, tag_message = tag_data.partition(b"\n\n")
                    if separator:
                        root_messages.append(tag_message)
                peeled = _git(root, "rev-parse", "--verify", f"{revision}^{{commit}}")
                peeled_roots.append(peeled.decode("ascii", errors="strict").strip())
            commit_output = _git(root, "rev-list", *peeled_roots)
        else:
            try:
                _git(root, "rev-parse", "--verify", "HEAD")
                commit_output = _git(root, "rev-list", "--all", "HEAD")
            except RepositoryError:
                commit_output = _git(root, "rev-list", "--all")
        commits = commit_output.decode("ascii", errors="strict").splitlines()
    except UnicodeError as error:
        raise RepositoryError from error

    findings: list[Finding] = []
    seen_blobs: set[tuple[str, str, str]] = set()
    seen_messages: set[bytes] = set()
    for message in root_messages:
        if message not in seen_messages:
            seen_messages.add(message)
            findings.extend(_scan_content(message, ".git/TAG_MESSAGE", context))
    for commit in commits:
        commit_data = _git(root, "cat-file", "commit", commit)
        _, separator, message = commit_data.partition(b"\n\n")
        if separator and message not in seen_messages:
            seen_messages.add(message)
            findings.extend(_scan_content(message, ".git/COMMIT_MESSAGE", context))

        for entry in _tree_entries(root, commit):
            identity = (entry.mode, entry.object_id, entry.path)
            if identity in seen_blobs:
                continue
            seen_blobs.add(identity)
            findings.extend(_scan_entry_path(entry.path, context))
            risky_path = _risky_path_rule(entry.path) is not None
            if entry.mode == "120000":
                findings.append(Finding("symlink", entry.path, 1))
                continue
            if entry.mode not in {"100644", "100755"}:
                findings.append(Finding("unsupported-file-mode", entry.path, 1))
                continue
            try:
                if _blob_is_oversized(root, entry.object_id):
                    findings.append(Finding("oversized-file", entry.path, 1))
                    continue
                if risky_path:
                    continue
                data = _git(root, "cat-file", "blob", entry.object_id)
            except (OSError, RepositoryError):
                findings.append(Finding("repository-read-error", entry.path, 1))
                continue
            findings.extend(_scan_content(data, entry.path, context))
    return findings


def scan_repository(
    root: Path,
    mode: str,
    strict: bool = False,
    revision_roots: Sequence[str] = (),
) -> tuple[list[Finding], ScanContext]:
    denylist_terms, denylist_findings = _load_denylist(root, strict)
    context = ScanContext(runtime_literals=_runtime_literals(), denylist_terms=denylist_terms)
    if mode == "staged":
        entries = _index_entries(root)
        findings = _scan_staged(root, entries, context)
    elif mode == "full-tree":
        entries = _index_entries(root)
        findings = _scan_full_tree(root, entries, context)
    elif mode == "history":
        findings = _scan_history(root, context, revision_roots)
    else:
        raise ValueError("unsupported scan mode")
    findings.extend(denylist_findings)
    return sorted(set(findings)), context


def _replace_literal(text: str, literal: str) -> str:
    needle = literal.casefold()
    if not needle:
        return text

    folded_parts: list[str] = []
    original_indexes: list[int] = []
    for index, character in enumerate(text):
        folded = character.casefold()
        folded_parts.append(folded)
        original_indexes.extend([index] * len(folded))
    folded_text = "".join(folded_parts)

    ranges: list[tuple[int, int]] = []
    offset = 0
    while True:
        match_at = folded_text.find(needle, offset)
        if match_at < 0:
            break
        start = original_indexes[match_at]
        end = original_indexes[match_at + len(needle) - 1] + 1
        if ranges and start <= ranges[-1][1]:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))
        offset = match_at + len(needle)

    if not ranges:
        return text
    pieces: list[str] = []
    cursor = 0
    for start, end in ranges:
        pieces.extend((text[cursor:start], "[redacted]"))
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def _safe_output_path(path: str, context: ScanContext) -> str:
    safe = path
    for _, literal in context.runtime_literals:
        safe = _replace_literal(safe, literal)
    for term in context.denylist_terms:
        safe = _replace_literal(safe, term)
    for name in EXPERIMENTAL_NAMES:
        safe = _replace_literal(safe, name)

    safe = _MAC_COLON_OR_HYPHEN.sub("[redacted]", safe)
    safe = _MAC_DOTTED.sub("[redacted]", safe)
    safe = _PRIVATE_HOST.sub("[redacted]", safe)
    safe = _POSIX_USER_PATH.sub("[redacted-path]", safe)
    safe = _ROOT_USER_PATH.sub("[redacted-path]", safe)
    safe = _WINDOWS_USER_PATH.sub("[redacted-path]", safe)
    safe = _PRIVATE_KEY_HEADER.sub("[redacted]", safe)

    def redact_credential(match: re.Match[str]) -> str:
        relative_start = match.start("value") - match.start()
        return match.group(0)[:relative_start] + "[redacted]"

    safe = _CREDENTIAL_ASSIGNMENT.sub(redact_credential, safe)

    def redact_ipv4(match: re.Match[str]) -> str:
        try:
            rejected, _ = _is_rejected_ipv4(ipaddress.IPv4Address(match.group(0)))
        except ipaddress.AddressValueError:
            rejected = False
        return "[redacted]" if rejected else match.group(0)

    safe = _IPV4_CANDIDATE.sub(redact_ipv4, safe)

    def redact_ipv6(match: re.Match[str]) -> str:
        raw_address = match.group(0).split("%", 1)[0]
        try:
            rejected = _is_rejected_ipv6(ipaddress.IPv6Address(raw_address))
        except ipaddress.AddressValueError:
            rejected = False
        return "[redacted]" if rejected else match.group(0)

    safe = _IPV6_CANDIDATE.sub(redact_ipv6, safe)
    safe = "".join(character if character.isprintable() and character not in "\t\r\n" else "?" for character in safe)
    return safe or "[invalid-path]"


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan the Git publication boundary.")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--staged", action="store_const", const="staged", dest="mode")
    modes.add_argument("--full-tree", action="store_const", const="full-tree", dest="mode")
    modes.add_argument("--history", action="store_const", const="history", dest="mode")
    parser.add_argument("--strict", action="store_true", help="require the ignored local denylist")
    parser.add_argument("--commit", action="append", default=[], help=argparse.SUPPRESS)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _argument_parser().parse_args(argv)
    try:
        root = repository_root(arguments.repo)
        if arguments.commit and arguments.mode != "history":
            raise ValueError("commit roots require history mode")
        findings, context = scan_repository(
            root,
            arguments.mode,
            arguments.strict,
            arguments.commit,
        )
    except (OSError, RepositoryError, ValueError):
        print("repository-error\t.\t1")
        return 2

    for finding in findings:
        print(f"{finding.rule}\t{_safe_output_path(finding.path, context)}\t{finding.line}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
