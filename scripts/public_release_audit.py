#!/usr/bin/env python3
"""Fail-closed checks for artifacts that must not enter a public repository."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PRIVATE_NAMES = {
    "references_private", "structure_profiles_private", "private_models",
    "model_cache", "applications_pdf", "ground_truth", "auth.json",
    "config.openwebui.test.yaml",
}
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*['\"][^'\"]{12,}"),
]
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}


def audit(root: Path) -> list[str]:
    findings: list[str] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in PRIVATE_NAMES or any(part in PRIVATE_NAMES for part in path.parts):
            findings.append(f"private path: {path.relative_to(root)}")
            continue
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"secret-like content: {path.relative_to(root)}")
                break
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args()
    findings = audit(args.root.resolve())
    if findings:
        print("PUBLIC RELEASE AUDIT: FAILED")
        print("\n".join(f"- {finding}" for finding in findings))
        return 1
    print("PUBLIC RELEASE AUDIT: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
