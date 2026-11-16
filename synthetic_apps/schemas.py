from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal
import json

Status = Literal["observed", "inferred", "unknown", "not_applicable", "failed"]


@dataclass
class FeatureValue:
    value: Any = None
    status: Status = "unknown"
    confidence: float | None = None
    method: str = "not_available"
    reason: str = "not_observed"

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")


@dataclass
class PageFeature:
    page_number: int
    width_pt: float | None = None
    height_pt: float | None = None
    extracted_characters: FeatureValue = field(default_factory=FeatureValue)
    image_count: FeatureValue = field(default_factory=FeatureValue)
    text_layer: FeatureValue = field(default_factory=FeatureValue)


@dataclass
class DocumentFeature:
    relative_path: str
    category: FeatureValue = field(default_factory=FeatureValue)
    page_count: FeatureValue = field(default_factory=FeatureValue)
    pages: list[PageFeature] = field(default_factory=list)
    source_mode: FeatureValue = field(default_factory=FeatureValue)
    ocr_match: FeatureValue = field(default_factory=FeatureValue)


@dataclass
class DossierFeature:
    private_id: str
    relative_path: str
    documents: list[DocumentFeature] = field(default_factory=list)
    schema_version: str = "features-0.1"

    def public_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result.pop("private_id", None)
        return result

    def to_json(self) -> str:
        return json.dumps(self.public_dict(), ensure_ascii=False, indent=2)
