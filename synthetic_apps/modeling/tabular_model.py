"""Small license-independent tabular population model.

This module deliberately does not depend on SDV or another third-party
synthetic-data package.  It learns only coarsened structural fields from the
private analysis JSONs; it never reads PDF text.  The model is a compact
conditional-frequency model:

    page bucket -> layout/photo/scan bucket

The conditional sampling keeps correlations between structural properties while
remaining deterministic, inspectable and easy to audit.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import random
from typing import Any


@dataclass
class StructuralTableModel:
    schema_version: str = "structural-table-0.1"
    n_applicants: int = 0
    page_bucket_counts: dict[str, int] = field(default_factory=dict)
    conditional_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    feature_values: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StructuralTableModel":
        return cls(
            schema_version=data.get("schema_version", "structural-table-0.1"),
            n_applicants=int(data.get("n_applicants", 0)),
            page_bucket_counts=dict(data.get("page_bucket_counts", {})),
            conditional_counts={
                str(k): dict(v) for k, v in data.get("conditional_counts", {}).items()
            },
            feature_values={str(k): list(v) for k, v in data.get("feature_values", {}).items()},
        )

    def sample(self, count: int, seed: int = 42) -> list[dict[str, Any]]:
        if not self.page_bucket_counts:
            raise ValueError("model has no fitted rows")
        rng = random.Random(seed)
        buckets = list(self.page_bucket_counts)
        results: list[dict[str, Any]] = []
        for index in range(count):
            page_bucket = rng.choices(buckets, weights=[self.page_bucket_counts[b] for b in buckets], k=1)[0]
            row: dict[str, Any] = {"page_bucket": page_bucket}
            for feature, counts_by_bucket in self.conditional_counts.items():
                counts = counts_by_bucket.get(page_bucket) or {}
                if not counts:
                    values = self.feature_values.get(feature, ["unknown"])
                    row[feature] = rng.choice(values)
                else:
                    values = list(counts)
                    row[feature] = rng.choices(values, weights=[counts[v] for v in values], k=1)[0]
            row["synthetic_id"] = f"SG{index + 1:04d}"
            results.append(row)
        return results


def _bucket(value: Any) -> str:
    try:
        pages = max(1, int(value))
    except (TypeError, ValueError):
        pages = 1
    if pages <= 2:
        return "1-2"
    if pages <= 5:
        return "3-5"
    if pages <= 10:
        return "6-10"
    return "11+"


def _rows_from_profiles(profiles_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(profiles_dir.glob("*.json")):
        records = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            continue
        application = next(
            (r for r in records if r.get("document_type") in {"cover_letter", "application_package"}),
            None,
        )
        if application is None:
            application = max(records, key=lambda r: int(r.get("page_count", 1) or 1), default={})
        pages = int(application.get("page_count", 1) or 1)
        image_pages = sum(1 for r in records if r.get("has_images"))
        rows.append({
            "page_bucket": _bucket(pages),
            "layout": str(application.get("layout", "unknown")),
            "photo": "yes" if any(r.get("has_photo") for r in records) else "no",
            "image_density": "high" if image_pages / max(1, len(records)) >= 0.5 else "low",
            "document_count": _bucket(len(records)),
        })
    return rows


def fit_structural_table_model(profiles_dir: str | Path) -> StructuralTableModel:
    """Fit from coarsened structural analysis records, never source text."""
    profiles_dir = Path(profiles_dir)
    rows = _rows_from_profiles(profiles_dir)
    if not rows:
        raise ValueError("no structural profile rows found")
    page_counts = Counter(row["page_bucket"] for row in rows)
    conditional: dict[str, dict[str, dict[str, int]]] = {}
    feature_values: dict[str, list[str]] = {}
    for feature in ("layout", "photo", "image_density", "document_count"):
        values = sorted({row[feature] for row in rows})
        feature_values[feature] = values
        by_bucket: dict[str, Counter[str]] = defaultdict(Counter)
        for row in rows:
            by_bucket[row["page_bucket"]][row[feature]] += 1
        conditional[feature] = {bucket: dict(counts) for bucket, counts in by_bucket.items()}
    return StructuralTableModel(
        n_applicants=len(rows),
        page_bucket_counts=dict(page_counts),
        conditional_counts=conditional,
        feature_values=feature_values,
    )


def save_structural_table_model(model: StructuralTableModel, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def load_structural_table_model(path: str | Path) -> StructuralTableModel:
    return StructuralTableModel.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
