from __future__ import annotations

import argparse
import io
import os
import re
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


MAX_TEXT_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 20_000
MAX_ARCHIVE_DEPTH = 3

IGNORED_DIRECTORIES = {"__pycache__", ".pytest_cache", ".mypy_cache"}
ALLOWED_SENSITIVE_FILENAMES = {
    ".env.example",
    "credential_audit_report.md",
    "secret_scan.py",
    "secret_scan_policy.md",
    "test_secret_scan.py",
}
SENSITIVE_FILENAME_TOKEN = re.compile(
    r"(?:^|[._-])(credential|credentials|secret|secrets|token|tokens|cookie|cookies|session|sessions)(?:$|[._-])",
    re.IGNORECASE,
)
PRIVATE_KEY_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}
PRIVATE_KEY_NAMES = {"id_dsa", "id_ecdsa", "id_ed25519", "id_rsa"}
SENSITIVE_FILE_SUFFIXES = {"", ".cfg", ".conf", ".env", ".ini", ".json", ".txt", ".yaml", ".yml"}
CONFIG_FILE_SUFFIXES = SENSITIVE_FILE_SUFFIXES | {".toml"}
ARCHIVE_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".zip")


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    line: int | None
    message: str

    def render(self) -> str:
        location = self.path if self.line is None else f"{self.path}:{self.line}"
        return f"{location}: [{self.rule}] {self.message}"


@dataclass(frozen=True)
class ContentRule:
    rule: str
    pattern: re.Pattern[str]
    message: str
    captured_value_group: int | None = None


CONTENT_RULES = (
    ContentRule(
        "private-key",
        re.compile(
            r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"
        ),
        "private key material detected",
    ),
    ContentRule(
        "openai-style-token",
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
        "API token pattern detected",
    ),
    ContentRule(
        "github-token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        "GitHub token pattern detected",
    ),
    ContentRule(
        "aws-access-key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "AWS access key identifier detected",
    ),
    ContentRule(
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "JWT pattern detected",
    ),
)

SENSITIVE_ASSIGNMENT = re.compile(
    r"^\s*(?:export\s+)?[\"']?(?P<key>[A-Za-z0-9_-]*(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|passwd|github[_-]?(?:key|token)|cookie|session)[A-Za-z0-9_-]*)[\"']?\s*[:=]\s*[\"']?(?P<value>[A-Za-z0-9_./+=:@-]{8,})[\"']?\s*[,;]?\s*(?:#.*)?$",
    re.IGNORECASE,
)

PLACEHOLDER_MARKERS = (
    "${",
    "<",
    "changeme",
    "dummy",
    "example",
    "placeholder",
    "replace-me",
    "replace_me",
    "test-only",
    "your-",
    "your_",
)


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().strip("\"'").lower()
    if not normalized:
        return True
    if any(marker in normalized for marker in PLACEHOLDER_MARKERS):
        return True
    compact = re.sub(r"[^a-z0-9]", "", normalized)
    return bool(compact) and len(set(compact)) <= 2


def _archive_kind(name: str) -> str | None:
    lower = name.lower()
    if lower.endswith((".tar.gz", ".tgz", ".tar")):
        return "tar"
    if lower.endswith(".zip"):
        return "zip"
    return None


def _scan_name(path: str, *, root_git_allowed: bool = False) -> list[Finding]:
    normalized = path.replace("\\", "/")
    pure_path = PurePosixPath(normalized)
    findings: list[Finding] = []
    lowered_parts = [part.lower() for part in pure_path.parts]

    if ".git" in lowered_parts and not root_git_allowed:
        findings.append(
            Finding(path, "nested-git", None, "nested Git metadata is forbidden")
        )

    name = pure_path.name.lower()
    if name in ALLOWED_SENSITIVE_FILENAMES:
        return findings
    if name == ".env" or name.startswith(".env."):
        findings.append(
            Finding(path, "forbidden-filename", None, "environment file is forbidden")
        )
    elif name in PRIVATE_KEY_NAMES or PurePosixPath(name).suffix in PRIVATE_KEY_SUFFIXES:
        findings.append(
            Finding(path, "forbidden-filename", None, "private credential file is forbidden")
        )
    elif (
        SENSITIVE_FILENAME_TOKEN.search(name)
        and PurePosixPath(name).suffix in SENSITIVE_FILE_SUFFIXES
    ):
        findings.append(
            Finding(path, "forbidden-filename", None, "credential or session filename is forbidden")
        )
    return findings


def _scan_text(data: bytes, display_path: str) -> list[Finding]:
    if b"\x00" in data[:4096]:
        return []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return []

    findings: list[Finding] = []
    for rule in CONTENT_RULES:
        for match in rule.pattern.finditer(text):
            if rule.captured_value_group is not None:
                value = match.group(rule.captured_value_group)
                if _looks_like_placeholder(value):
                    continue
            line = text.count("\n", 0, match.start()) + 1
            findings.append(Finding(display_path, rule.rule, line, rule.message))

    config_suffix = PurePosixPath(display_path.split("!")[-1]).suffix.lower()
    for line_number, line_text in enumerate(text.splitlines(), start=1):
        match = SENSITIVE_ASSIGNMENT.match(line_text)
        if match is None:
            continue
        key = match.group("key")
        value = match.group("value")
        if key != key.upper() and config_suffix not in CONFIG_FILE_SUFFIXES:
            continue
        if _looks_like_placeholder(value):
            continue
        findings.append(
            Finding(
                display_path,
                "sensitive-assignment",
                line_number,
                "non-placeholder sensitive assignment detected",
            )
        )
    return findings


def _scan_archive_bytes(
    data: bytes,
    display_path: str,
    *,
    kind: str,
    depth: int,
) -> list[Finding]:
    if depth > MAX_ARCHIVE_DEPTH:
        return [
            Finding(
                display_path,
                "archive-depth",
                None,
                "nested archive depth exceeds the allowed scan limit",
            )
        ]
    if len(data) > MAX_ARCHIVE_BYTES:
        return [
            Finding(
                display_path,
                "archive-size",
                None,
                "archive exceeds the allowed scan size",
            )
        ]

    findings: list[Finding] = []
    member_count = 0
    expanded_bytes = 0
    nested_git_roots: set[str] = set()
    try:
        if kind == "tar":
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
                for member in archive:
                    member_count += 1
                    if member_count > MAX_ARCHIVE_MEMBERS:
                        raise ValueError("archive member count exceeds scan limit")
                    member_name = member.name.replace("\\", "/")
                    member_path = f"{display_path}!{member_name}"
                    pure_name = PurePosixPath(member_name)
                    if pure_name.is_absolute() or ".." in pure_name.parts:
                        findings.append(
                            Finding(member_path, "archive-path", None, "unsafe archive member path")
                        )
                    lowered_parts = [part.lower() for part in pure_name.parts]
                    if ".git" in lowered_parts:
                        git_index = lowered_parts.index(".git")
                        git_root = "/".join(pure_name.parts[: git_index + 1])
                        if git_root not in nested_git_roots:
                            nested_git_roots.add(git_root)
                            findings.append(
                                Finding(
                                    f"{display_path}!{git_root}",
                                    "nested-git",
                                    None,
                                    "nested Git metadata is forbidden",
                                )
                            )
                    findings.extend(_scan_name(member_path, root_git_allowed=True))
                    if not member.isfile():
                        continue
                    expanded_bytes += member.size
                    if member.size > MAX_TEXT_BYTES or expanded_bytes > MAX_ARCHIVE_BYTES:
                        findings.append(
                            Finding(
                                member_path,
                                "unscannable-member",
                                None,
                                "archive member exceeds the fail-closed scan limit",
                            )
                        )
                        continue
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        continue
                    member_data = extracted.read(MAX_TEXT_BYTES + 1)
                    findings.extend(_scan_member_data(member_data, member_path, depth))
        elif kind == "zip":
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for member in archive.infolist():
                    member_count += 1
                    if member_count > MAX_ARCHIVE_MEMBERS:
                        raise ValueError("archive member count exceeds scan limit")
                    member_name = member.filename.replace("\\", "/")
                    member_path = f"{display_path}!{member_name}"
                    pure_name = PurePosixPath(member_name)
                    if pure_name.is_absolute() or ".." in pure_name.parts:
                        findings.append(
                            Finding(member_path, "archive-path", None, "unsafe archive member path")
                        )
                    lowered_parts = [part.lower() for part in pure_name.parts]
                    if ".git" in lowered_parts:
                        git_index = lowered_parts.index(".git")
                        git_root = "/".join(pure_name.parts[: git_index + 1])
                        if git_root not in nested_git_roots:
                            nested_git_roots.add(git_root)
                            findings.append(
                                Finding(
                                    f"{display_path}!{git_root}",
                                    "nested-git",
                                    None,
                                    "nested Git metadata is forbidden",
                                )
                            )
                    findings.extend(_scan_name(member_path, root_git_allowed=True))
                    if member.is_dir():
                        continue
                    expanded_bytes += member.file_size
                    if member.file_size > MAX_TEXT_BYTES or expanded_bytes > MAX_ARCHIVE_BYTES:
                        findings.append(
                            Finding(
                                member_path,
                                "unscannable-member",
                                None,
                                "archive member exceeds the fail-closed scan limit",
                            )
                        )
                        continue
                    member_data = archive.read(member)
                    findings.extend(_scan_member_data(member_data, member_path, depth))
    except (OSError, tarfile.TarError, zipfile.BadZipFile, RuntimeError, ValueError) as exc:
        findings.append(
            Finding(
                display_path,
                "archive-error",
                None,
                f"archive could not be completely inspected: {type(exc).__name__}",
            )
        )
    return findings


def _scan_member_data(data: bytes, display_path: str, depth: int) -> list[Finding]:
    nested_kind = _archive_kind(display_path)
    if nested_kind is not None:
        return _scan_archive_bytes(
            data,
            display_path,
            kind=nested_kind,
            depth=depth + 1,
        )
    return _scan_text(data, display_path)


def _scan_file(path: Path, display_path: str) -> list[Finding]:
    findings = _scan_name(display_path)
    try:
        size = path.stat().st_size
        archive_kind = _archive_kind(path.name)
        if archive_kind is not None:
            if size > MAX_ARCHIVE_BYTES:
                findings.append(
                    Finding(display_path, "archive-size", None, "archive exceeds the allowed scan size")
                )
                return findings
            data = path.read_bytes()
            findings.extend(
                _scan_archive_bytes(data, display_path, kind=archive_kind, depth=0)
            )
        elif size <= MAX_TEXT_BYTES:
            findings.extend(_scan_text(path.read_bytes(), display_path))
    except OSError as exc:
        findings.append(
            Finding(
                display_path,
                "read-error",
                None,
                f"file could not be inspected: {type(exc).__name__}",
            )
        )
    return findings


def _scan_directory(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        relative_current = current_path.relative_to(root)

        for directory in list(directories):
            directory_path = current_path / directory
            if directory in IGNORED_DIRECTORIES:
                directories.remove(directory)
                continue
            if directory == ".git":
                directories.remove(directory)
                if relative_current != Path("."):
                    display = (relative_current / directory).as_posix()
                    findings.append(
                        Finding(display, "nested-git", None, "nested Git metadata is forbidden")
                    )
                continue
            if directory_path.is_symlink():
                directories.remove(directory)
                display = (relative_current / directory).as_posix()
                findings.append(
                    Finding(display, "symlink", None, "symlinked directories are not scanned")
                )

        for filename in filenames:
            path = current_path / filename
            display = (relative_current / filename).as_posix()
            if path.is_symlink():
                findings.append(
                    Finding(display, "symlink", None, "symlinked files are not scanned")
                )
                continue
            findings.extend(_scan_file(path, display))
    return findings


def scan_targets(targets: Iterable[str | Path]) -> list[Finding]:
    findings: list[Finding] = []
    for target_value in targets:
        target = Path(target_value).resolve()
        if not target.exists():
            findings.append(
                Finding(str(target_value), "missing-target", None, "scan target does not exist")
            )
        elif target.is_dir():
            findings.extend(_scan_directory(target))
        elif target.is_file():
            findings.extend(_scan_file(target, target.name))
        else:
            findings.append(
                Finding(str(target_value), "unsupported-target", None, "scan target is unsupported")
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed secret scanner for Creator Agent release inputs and archives."
    )
    parser.add_argument("targets", nargs="+", help="Directories or archives to inspect")
    args = parser.parse_args(argv)

    findings = scan_targets(args.targets)
    if findings:
        print(f"Secret scan FAIL: {len(findings)} finding(s).", file=sys.stderr)
        for finding in findings:
            print(finding.render(), file=sys.stderr)
        return 1
    print(f"Secret scan PASS: {len(args.targets)} target(s) inspected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
