#!/usr/bin/env python3
"""Fail when public Git history contains machine-local or sensitive artifacts."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MAX_TRACKED_FILE_BYTES = 5 * 1024 * 1024

DISALLOWED_PARTS = {
    "__pycache__",
    ".idea",
    ".vscode",
    ".codex",
    ".superpowers",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    "test-results",
    "playwright-report",
}
DISALLOWED_NAMES = {
    ".DS_Store",
    ".env",
    "2.1.0",
    "credentials.json",
    "secrets.json",
}
DISALLOWED_SUFFIXES = {".pyc", ".pyo", ".pyd", ".pem", ".key", ".p12", ".swp", ".swo"}
SECRET_PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    "GitHub token": re.compile(rb"(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    "OpenAI-style token": re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "AWS access key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
}
REQUIRED_IGNORES = (
    ".env",
    ".idea/workspace.xml",
    ".DS_Store",
    ".superpowers/session.json",
    "frontend/node_modules/example.js",
    "frontend/dist/index.html",
    "frontend/test-results/result.json",
)


def tracked_paths() -> list[PurePosixPath]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    return [
        PurePosixPath(value.decode("utf-8"))
        for value in result.stdout.split(b"\0")
        if value
    ]


def path_violations(path: PurePosixPath, size: int) -> list[str]:
    issues: list[str] = []
    if path.name in DISALLOWED_NAMES:
        issues.append("disallowed filename")
    if DISALLOWED_PARTS.intersection(path.parts):
        issues.append("generated or machine-local directory")
    if path.suffix.lower() in DISALLOWED_SUFFIXES:
        issues.append("disallowed file type")
    if size > MAX_TRACKED_FILE_BYTES:
        issues.append(f"file exceeds {MAX_TRACKED_FILE_BYTES // (1024 * 1024)} MiB")
    return issues


def secret_violations(content: bytes) -> list[str]:
    return [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(content)]


def is_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", path],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    return result.returncode == 0


def audit() -> list[str]:
    issues: list[str] = []
    paths = tracked_paths()
    for relative_path in paths:
        local_path = REPOSITORY_ROOT / relative_path
        if local_path.is_symlink():
            issues.append(f"{relative_path}: tracked symbolic link is not allowed")
            continue
        size = local_path.lstat().st_size
        for reason in path_violations(relative_path, size):
            issues.append(f"{relative_path}: {reason}")

        if size <= MAX_TRACKED_FILE_BYTES:
            content = local_path.read_bytes()
            for secret_type in secret_violations(content):
                issues.append(f"{relative_path}: contains {secret_type} marker")

    for path in REQUIRED_IGNORES:
        if not is_ignored(path):
            issues.append(f"{path}: sensitive/generated path is not ignored")
    return issues


def main() -> int:
    issues = audit()
    if issues:
        print("Public repository audit failed:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    print(
        f"Public repository audit passed: {len(tracked_paths())} tracked files, "
        f"maximum allowed size {MAX_TRACKED_FILE_BYTES // (1024 * 1024)} MiB."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
