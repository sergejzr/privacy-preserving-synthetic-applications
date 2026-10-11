"""Private, interpretable population model for structural synthetic sampling.

The model stores smoothed conditional counts and bounded page-count ranges. It
never stores source text, paths, embeddings, or individual source records.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import random
from typing import Any

from .struct_schemas import StructuralRecord


@dataclass
class ConditionalStats:
    counts: dict[str, int]
    page_min: int
    page_max: int


@dataclass
class PopulationModel:
    schema_version: str
    n_documents: int
    global_counts: dict[str, dict[str, int]]
    by_document_type: dict[str, ConditionalStats]
    min_support: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coarsen(value: str, counts: Counter[str], min_support: int) -> str:
    return value if counts[value] >= min_support else "other"


def fit_population_model(records: list[StructuralRecord], min_support: int = 5) -> PopulationModel:
    if not records:
        raise ValueError("cannot fit a population model without records")
    if min_support < 1:
        raise ValueError("min_support must be positive")

    fields = ("document_type", "page_size", "layout", "approximate_word_count_bucket",
              "text_density", "scanned_likelihood", "language")
    raw_global = {field: Counter(str(getattr(record, field).value if hasattr(getattr(record, field), "value") else getattr(record, field)) for record in records) for field in fields}
    global_counts = {
        field: {(_coarsen(key, counts, min_support)): sum(v for k, v in counts.items() if _coarsen(k, counts, min_support) == _coarsen(key, counts, min_support)) for key in counts}
        for field, counts in raw_global.items()
    }

    grouped: dict[str, list[StructuralRecord]] = defaultdict(list)
    for record in records:
        dtype = record.document_type.value
        grouped[dtype if raw_global["document_type"][dtype] >= min_support else "other"].append(record)

    by_type: dict[str, ConditionalStats] = {}
    for dtype, group in grouped.items():
        counts: dict[str, int] = {}
        for field in fields[1:]:
            counter = Counter(str(getattr(r, field).value if hasattr(getattr(r, field), "value") else getattr(r, field)) for r in group)
            for key, value in counter.items():
                counts[f"{field}={_coarsen(key, counter, min_support)}"] = value
        by_type[dtype] = ConditionalStats(
            counts=counts,
            page_min=min(r.page_count for r in group),
            page_max=max(r.page_count for r in group),
        )
    return PopulationModel("population-0.1", len(records), global_counts, by_type, min_support)


def _draw(rng: random.Random, counts: dict[str, int], alpha: float = 1.0) -> str:
    keys = list(counts)
    weights = [counts[key] + alpha for key in keys]
    return rng.choices(keys, weights=weights, k=1)[0]


def sample_document_plans(model: PopulationModel, count: int, seed: int = 42) -> list[dict[str, Any]]:
    if count < 1:
        raise ValueError("count must be positive")
    rng = random.Random(seed)
    type_counts = model.global_counts["document_type"]
    plans = []
    for index in range(count):
        document_type = _draw(rng, type_counts)
        stats = model.by_document_type.get(document_type) or model.by_document_type.get("other")
        if stats is None:
            stats = next(iter(model.by_document_type.values()))
        conditionals: dict[str, str] = {}
        for field in ("page_size", "layout", "approximate_word_count_bucket", "text_density", "scanned_likelihood", "language"):
            values = {key.split("=", 1)[1]: value for key, value in stats.counts.items() if key.startswith(field + "=")}
            conditionals[field] = _draw(rng, values) if values else "unknown"
        plans.append({
            "synthetic_id": f"SG{index + 1:04d}",
            "document_type": document_type,
            "page_target": rng.randint(stats.page_min, stats.page_max),
            **conditionals,
            "sampling_seed": seed + index,
        })
    return plans


def load_records(profiles_dir: Path) -> list[StructuralRecord]:
    records: list[StructuralRecord] = []
    for path in sorted(profiles_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        records.extend(StructuralRecord(**item) for item in data)
    return records


def save_population_model(model: PopulationModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def load_population_model(path: Path) -> PopulationModel:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["by_document_type"] = {key: ConditionalStats(**value) for key, value in data["by_document_type"].items()}
    return PopulationModel(**data)
