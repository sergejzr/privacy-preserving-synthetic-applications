from __future__ import annotations

from pathlib import Path


def ensure_safe_output(output: Path, input_dir: Path | None) -> None:
    output = output.resolve()
    if input_dir is not None:
        source = input_dir.resolve()
        if output == source or source in output.parents:
            raise ValueError("output must not be inside the private input directory")
    output.mkdir(parents=True, exist_ok=True)


def prepare_output(output: Path) -> dict[str, Path]:
    paths = {
        "structured": output / "structured",
        "features": output / "private" / "features",
        "reports": output / "reports",
        "logs": output / "logs",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def prepare_private_cache(cache: Path) -> dict[str, Path]:
    paths = {"features": cache / "features", "models": cache / "models", "logs": cache / "logs"}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths
