"""Pydantic schemas for structural analysis and generation."""

from __future__ import annotations

import enum
from typing import Any
from pydantic import BaseModel, Field, PrivateAttr


class DocumentType(str, enum.Enum):
    cv = "cv"
    cover_letter = "cover_letter"
    certificate = "certificate"
    reference_letter = "reference_letter"
    portfolio = "portfolio"
    research_summary = "research_summary"
    unknown = "unknown"


class LayoutType(str, enum.Enum):
    standard = "standard"
    two_column = "two_column"
    tables = "tables"
    unknown = "unknown"


class ScannedLikelihood(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TextDensity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class WordCountBucket(str, enum.Enum):
    zero = "0"
    under_200 = "0-200"
    bucket_200_500 = "200-500"
    bucket_500_800 = "500-800"
    bucket_800_1100 = "800-1100"
    bucket_1100_1500 = "1100-1500"
    bucket_1500_2000 = "1500-2000"
    over_2000 = "2000+"


class PageSize(str, enum.Enum):
    A4 = "A4"
    letter = "letter"
    other = "other"


class StructuralRecord(BaseModel):
    """Non-content structural descriptor for a single PDF document."""

    document_type: DocumentType = DocumentType.unknown
    page_count: int = Field(ge=1)
    page_size: PageSize
    layout: LayoutType = LayoutType.unknown
    approximate_word_count_bucket: WordCountBucket
    text_density: TextDensity = TextDensity.medium
    has_tables: bool = False
    has_images: bool = False
    _has_photo: bool = PrivateAttr(default=False)

    @property
    def has_photo(self) -> bool:
        return self._has_photo
    image_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    semantic_codes: dict[str, list[str]] = Field(default_factory=dict)
    scanned_likelihood: ScannedLikelihood = ScannedLikelihood.low
    language: str = "unknown"

    model_config = {"frozen": True}


class CategoryDistribution(BaseModel):
    """Aggregate distribution counts for a categorical field."""
    counts: dict[str, int] = Field(default_factory=dict)


class NumericDistribution(BaseModel):
    """Aggregate distribution for a numeric field."""
    min: int = 0
    max: int = 0
    mean: float = 0.0
    buckets: dict[str, int] = Field(default_factory=dict)


class StructuralAggregation(BaseModel):
    """Aggregate statistics across a set of structural records."""
    total_documents: int = 0
    total_pages: int = 0
    document_types: CategoryDistribution = Field(default_factory=CategoryDistribution)
    page_sizes: CategoryDistribution = Field(default_factory=CategoryDistribution)
    layouts: CategoryDistribution = Field(default_factory=CategoryDistribution)
    word_count_buckets: CategoryDistribution = Field(default_factory=CategoryDistribution)
    text_densities: CategoryDistribution = Field(default_factory=CategoryDistribution)
    scanned_likelihoods: CategoryDistribution = Field(default_factory=CategoryDistribution)
    languages: CategoryDistribution = Field(default_factory=CategoryDistribution)
    page_count_distribution: NumericDistribution = Field(default_factory=NumericDistribution)
    tables_fraction: float = 0.0
    images_fraction: float = 0.0
