#!/usr/bin/env python3
"""Create a clean allowlisted staging tree for a public repository."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


FILES = [
    ".gitignore", "README.md", "LICENSE", "NOTICE", "SECURITY.md", "CONTRIBUTING.md",
    "pyproject.toml", "config.example.yaml", "config.public.example.yaml",
]
DIRECTORIES = ["synthetic_apps", "templates", "tests", "scripts"]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: build_public_release.py OUTPUT_DIR", file=sys.stderr)
        return 2
    source = Path(__file__).resolve().parents[1]
    output = Path(sys.argv[1]).resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copy2(source / name, output / name)
    for name in DIRECTORIES:
        ignored = ["__pycache__", ".pytest_cache", "*.pyc"]
        if name == "tests":
            ignored.append("test_generation.py")
        shutil.copytree(source / name, output / name,
                        ignore=shutil.ignore_patterns(*ignored))
    print(f"public release staging tree: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
