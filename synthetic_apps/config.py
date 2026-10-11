from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from urllib.parse import urlparse


@dataclass
class RunConfig:
    track: str = "safe"
    input_dir: Path | None = None
    ocr_dir: Path | None = None
    output_dir: Path = Path("synthetic_dataset")
    count: int = 5
    seed: int = 42
    stage: str = "all"
    resume: bool = False
    force: bool = False
    offline: bool = True
    report: bool = True
    private_cache_dir: Path | None = None
    local_model_endpoint: str | None = None

    def validate(self, *, require_input: bool = True) -> None:
        if self.track not in {"safe", "private"}:
            raise ValueError("--track must be safe or private")
        if require_input and self.stage in {"all", "structured"} and self.input_dir is None:
            raise ValueError("--input is required for stage all/structured")
        if self.count < 1:
            raise ValueError("--count must be a positive integer")
        if self.stage not in {"all", "structured", "pdf"}:
            raise ValueError("--stage must be all, structured, or pdf")
        if self.input_dir and not self.input_dir.is_dir() and self.stage != "pdf":
            raise ValueError(f"input directory does not exist: {self.input_dir}")
        if self.ocr_dir and not self.ocr_dir.is_dir():
            raise ValueError(f"OCR directory does not exist: {self.ocr_dir}")
        if self.track == "private" and self.private_cache_dir is None:
            raise ValueError("private track requires --private-cache-dir outside the output tree")
        if self.private_cache_dir and self.output_dir.resolve() in self.private_cache_dir.resolve().parents:
            raise ValueError("private cache must not be inside the output tree")
        if self.local_model_endpoint:
            parsed = urlparse(self.local_model_endpoint)
            if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("local model endpoint must use loopback (127.0.0.1/localhost/::1)")


def load_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml
    except ImportError as exc:
        raise ValueError("YAML config requires PyYAML; use JSON or install PyYAML") from exc
    return yaml.safe_load(text) or {}


def config_from_file(path: Path, **overrides) -> RunConfig:
    raw = load_config(path)
    run = raw.get("run", raw)
    inputs = raw.get("inputs", {})
    values = {
        "track": run.get("track", "safe"),
        "input_dir": inputs.get("input_dir"),
        "ocr_dir": inputs.get("ocr_dir"),
        "count": run.get("count", 5),
        "seed": run.get("seed", 42),
        "stage": run.get("stage", "all"),
        "resume": run.get("resume", False),
        "offline": run.get("offline", True),
        "private_cache_dir": raw.get("private_cache_dir"),
        "local_model_endpoint": raw.get("local_models", {}).get("endpoint"),
    }
    values.update({k: v for k, v in overrides.items() if v is not None})
    for key in ("input_dir", "ocr_dir", "output_dir"):
        if values.get(key) is not None:
            values[key] = Path(values[key])
    return RunConfig(**values)
