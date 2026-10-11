"""Structural generative model fitted from real applicant data.

Samples page counts, layout types, scan ratios, and document structure
distributions that match the real corpus.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_rng = random.Random(20261008)


@dataclass
class DiscreteDistribution:
    """A weighted discrete distribution."""
    values: list[Any]
    probabilities: list[float]  # must sum to 1.0

    def sample(self, rng: random.Random | None = None) -> Any:
        if not self.values:
            raise ValueError("Empty distribution")
        return (rng or _rng).choices(self.values, weights=self.probabilities, k=1)[0]


@dataclass
class StructuralModel:
    """Generative model for applicant document structure.

    Fitted from real data, samples coherent document configurations.
    """

    # Per-applicant: total pages in Bewerbung.pdf
    bewerbung_page_count: DiscreteDistribution | None = None
    # Per-applicant: image-heavy ratio (0-1)
    image_ratio: DiscreteDistribution | None = None
    photo_presence: DiscreteDistribution | None = None
    # Per-applicant: layout of Bewerbung.pdf
    bewerbung_layout: DiscreteDistribution | None = None
    # Ausdruck.pdf is always 2 pages, two_column, with images
    ausdruck_fixed: dict[str, Any] = field(default_factory=lambda: {
        "page_count": 2,
        "layout": "two_column",
        "has_images": True,
    })

    # Model metadata
    n_applicants: int = 0
    total_pages_real: int = 0
    image_ratio_total: float = 0.82
    model_version: str = "0.1.0"
    seed: int = 20261008

    def to_dict(self) -> dict[str, Any]:
        def _dist_to_dict(d: DiscreteDistribution | None) -> dict | None:
            if d is None:
                return None
            return {"values": d.values, "probabilities": d.probabilities}

        return {
            "model_version": self.model_version,
            "seed": self.seed,
            "n_applicants": self.n_applicants,
            "total_pages_real": self.total_pages_real,
            "image_ratio_total": self.image_ratio_total,
            "ausdruck_fixed": self.ausdruck_fixed,
            "bewerbung_page_count": _dist_to_dict(self.bewerbung_page_count),
            "image_ratio": _dist_to_dict(self.image_ratio),
            "photo_presence": _dist_to_dict(self.photo_presence),
            "bewerbung_layout": _dist_to_dict(self.bewerbung_layout),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StructuralModel:
        def _dict_to_dist(d: dict | None) -> DiscreteDistribution | None:
            if d is None:
                return None
            return DiscreteDistribution(values=d["values"], probabilities=d["probabilities"])

        ausdruck_fixed = {
            "page_count": 2,
            "layout": "two_column",
            "has_images": True,
            **(data.get("ausdruck_fixed") or {}),
        }
        return cls(
            model_version=data.get("model_version", "0.1.0"),
            seed=data.get("seed", 20261008),
            n_applicants=data.get("n_applicants", 0),
            total_pages_real=data.get("total_pages_real", 0),
            image_ratio_total=data.get("image_ratio_total", 0.82),
            ausdruck_fixed=ausdruck_fixed,
            bewerbung_page_count=_dict_to_dist(data.get("bewerbung_page_count")),
            image_ratio=_dict_to_dist(data.get("image_ratio")),
            photo_presence=_dict_to_dist(data.get("photo_presence")) or DiscreteDistribution(
                [False, True], [0.5, 0.5]
            ),
            bewerbung_layout=_dict_to_dist(data.get("bewerbung_layout")),
        )

    def sample_applicant(self, rng: random.Random | None = None) -> dict[str, Any]:
        """Sample a coherent applicant document configuration."""
        # Sample Bewerbung.pdf page count
        if self.bewerbung_page_count is None:
            raise ValueError("Model not fitted: missing bewerbung_page_count")
        bewerbung_pages = self.bewerbung_page_count.sample(rng)

        # Sample layout
        layout = self.bewerbung_layout.sample(rng) if self.bewerbung_layout else "two_column"

        # Sample image ratio
        if self.image_ratio is None:
            img_ratio = 0.8
        else:
            img_ratio = self.image_ratio.sample(rng)

        photo_present = (
            self.photo_presence.sample(rng)
            if self.photo_presence is not None
            else bool(self.ausdruck_fixed.get("has_images", True))
        )

        # Calculate image-only and text pages
        img_heavy_pages = max(0, round(bewerbung_pages * img_ratio))
        text_pages = bewerbung_pages - img_heavy_pages

        return {
            "ausdruck": {
                "page_count": self.ausdruck_fixed["page_count"],
                "layout": self.ausdruck_fixed["layout"],
                "has_images": self.ausdruck_fixed["has_images"],
                "scanned": False,  # Ausdruck is always clean text
            },
            "bewerbung": {
                "page_count": bewerbung_pages,
                "layout": layout,
                "has_images": True,
                "img_heavy_pages": img_heavy_pages,
                "text_pages": text_pages,
                "img_ratio": img_ratio,
                "photo_present": bool(photo_present),
            },
            "total_pages": self.ausdruck_fixed["page_count"] + bewerbung_pages,
        }

    def document_plan(self, applicant_config: dict[str, Any], rng: random.Random | None = None) -> list[dict[str, Any]]:
        """Generate a document plan from a sampled applicant configuration.

        Returns a list of document specs: type, page count, scan ratio, layout.
        """
        bewerbung = applicant_config["bewerbung"]

        # For multi-page documents, determine which pages get scanned
        bewerbung_pages = bewerbung["page_count"]
        img_heavy = bewerbung["img_heavy_pages"]

        # Randomly assign which pages are image-heavy (prefer later pages)
        # Keep the first page clean when there are later pages available.
        page_indices = list(range(1, bewerbung_pages)) if bewerbung_pages > 1 else [0]
        # Weight toward later pages for scanning (matching real: certs at end)
        if len(page_indices) > 1:
            weights = [i + 1 for i in page_indices]
            selected = (rng or _rng).choices(page_indices, weights=weights, k=img_heavy)
            # Ensure unique pages selected
            img_pages = set(selected)
            while len(img_pages) < img_heavy:
                img_pages.add((rng or _rng).randint(0, bewerbung_pages - 1))
            img_pages = list(img_pages)
        else:
            img_pages = [0] if img_heavy > 0 else []

        return [
            {
                "type": "ausdruck",
                "page_count": applicant_config["ausdruck"]["page_count"],
                "scan_ratio": 0.0,  # never scanned
                "layout": applicant_config["ausdruck"]["layout"],
            },
            {
                "type": "bewerbung",
                "page_count": bewerbung_pages,
                "scan_ratio": img_heavy / bewerbung_pages,
                "layout": bewerbung["layout"],
                "scanned_pages": sorted(img_pages),
            },
        ]


# ---------------------------------------------------------------------------
# Fit
# ---------------------------------------------------------------------------

def fit_model(structural_profiles_dir: str | Path, seed: int = 20261008) -> StructuralModel:
    """Fit a StructuralModel from structural profile JSONs.

    Args:
        structural_profiles_dir: Directory with per-applicant JSON files
                                 generated by `synthetic-apps analyze`.
        seed: Random seed for reproducibility.

    Returns:
        Fitted StructuralModel.
    """
    global _rng
    _rng = random.Random(seed)

    profiles_dir = Path(structural_profiles_dir)
    if not profiles_dir.exists():
        raise FileNotFoundError(f"Profiles directory not found: {profiles_dir}")

    # Collect all per-applicant records
    bewerbung_pages: list[int] = []
    image_ratios: list[float] = []
    layouts: list[str] = []

    for json_file in sorted(profiles_dir.glob("*.json")):
        records = json.loads(json_file.read_text())
        for rec in records:
            dt = rec.get("document_type", "")
            if dt == "cover_letter":  # Bewerbung.pdf classified as cover_letter
                pages = rec.get("page_count", 0)
                if pages > 0:
                    bewerbung_pages.append(pages)
                layout = rec.get("layout", "unknown")
                if layout not in ("unknown",):
                    layouts.append(layout)
                # Estimate image ratio from word bucket and images flag
                has_images = rec.get("has_images", False)
                word_bucket = rec.get("approximate_word_count_bucket", "0")

                # Heuristic: if has_images=True and word bucket small, it's image-heavy
                if has_images:
                    bucket_low = int(word_bucket.split("-")[0]) if "-" in word_bucket else 0
                    if bucket_low == 0:
                        # scanned-like: estimate from real distribution
                        # Use per-applicant scan ratio
                        pass

    # Fit directly from the private profile files. No side-channel stats file
    # in /tmp is required, and no source text is read here.
    if not bewerbung_pages:
        raise ValueError("No cover_letter/Bewerbung structural records found")

    page_counts = {}
    for value in bewerbung_pages:
        page_counts[value] = page_counts.get(value, 0) + 1
    pages_values = sorted(page_counts)
    pages_probs = [page_counts[value] / len(bewerbung_pages) for value in pages_values]

    ratio_counts: dict[float, int] = {}
    layout_counts: dict[str, int] = {}
    photo_counts: dict[bool, int] = {True: 0, False: 0}
    for json_file in sorted(profiles_dir.glob("*.json")):
        for rec in json.loads(json_file.read_text()):
            if rec.get("document_type") != "cover_letter":
                continue
            photo_counts[bool(rec.get("has_photo", False))] += 1
            ratio = rec.get("image_ratio")
            if ratio is None:
                ratio = 1.0 if rec.get("has_images") else 0.0
            ratio_bucket = round(float(ratio) * 10) / 10
            ratio_counts[ratio_bucket] = ratio_counts.get(ratio_bucket, 0) + 1
            layout = rec.get("layout", "unknown")
            if layout != "unknown":
                layout_counts[layout] = layout_counts.get(layout, 0) + 1

    ratio_values = sorted(ratio_counts) or [0.0]
    ratio_total = sum(ratio_counts.values()) or 1
    ratio_probs = [ratio_counts[value] / ratio_total for value in ratio_values]
    layout_values = sorted(layout_counts) or ["standard"]
    layout_total = sum(layout_counts.values()) or 1
    layout_probs = [layout_counts[value] / layout_total for value in layout_values]
    photo_total = sum(photo_counts.values()) or 1
    photo_presence = DiscreteDistribution(
        [False, True],
        [photo_counts[False] / photo_total, photo_counts[True] / photo_total],
    )

    n_applicants = len(list(profiles_dir.glob("*.json")))
    total_pages = sum(bewerbung_pages)
    image_ratio_total = sum(value * count for value, count in ratio_counts.items()) / ratio_total

    model = StructuralModel(
        bewerbung_page_count=DiscreteDistribution(pages_values, pages_probs),
        image_ratio=DiscreteDistribution(ratio_values, ratio_probs),
        bewerbung_layout=DiscreteDistribution(layout_values, layout_probs),
        photo_presence=photo_presence,
        n_applicants=n_applicants,
        total_pages_real=total_pages,
        image_ratio_total=image_ratio_total,
        seed=seed,
    )

    return model


def save_model(model: StructuralModel, path: str | Path) -> None:
    """Save a fitted model to JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model.to_dict(), indent=2, ensure_ascii=False))


def load_model(path: str | Path) -> StructuralModel:
    """Load a fitted model from JSON."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Model file not found: {path}")
    data = json.loads(path.read_text())
    return StructuralModel.from_dict(data)
