"""OutputDocumentPlan — zentrale Spezifikation für Dokumenterzeugung.

Fasst StructuralModel (Seiten, Scans, Layout) und DossierModel
(Dokumenttypen, Semantik) zu einem ausführbaren Plan zusammen.

Output sind genau 2 PDFs pro Bewerber — wie im Original:
  - Ausdruck.pdf (Deckblatt, ~2 Seiten)
  - Bewerbung.pdf (merged — Cover Letter + CV + Zeugnisse + Referenzen + ...)
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from .dossier_model import DossierModel
from .structural_model import StructuralModel

_rng = random.Random(20261008)


class SubDocumentPlan:
    """Ein Sub-Dokument innerhalb von Bewerbung.pdf."""

    def __init__(
        self,
        subdoc_type: str,
        order: int,
        page_target: int = 1,
        template: str = "cover_letter",
        section_plan: list[str] | None = None,
    ):
        self.subdoc_type = subdoc_type
        self.order = order
        self.page_target = page_target
        self.template = template
        self.section_plan = section_plan or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "subdoc_type": self.subdoc_type,
            "order": self.order,
            "page_target": self.page_target,
            "template": self.template,
            "section_plan": self.section_plan,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SubDocumentPlan:
        return cls(**d)


class OutputDocumentPlan:
    """Spezifikation einer merged Ausgabedatei (Ausdruck.pdf oder Bewerbung.pdf)."""

    def __init__(
        self,
        doc_type: str,
        page_target: int,
        order: int,
        layout: str = "two_column",
        scan_indices: list[int] | None = None,
        scan_mode: str = "full_raster",
        subdocuments: list[SubDocumentPlan] | None = None,
    ):
        self.doc_type = doc_type
        self.page_target = page_target
        self.order = order
        self.layout = layout
        self.scan_indices = scan_indices or []
        self.scan_mode = scan_mode
        self.subdocuments = subdocuments or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_type": self.doc_type,
            "page_target": self.page_target,
            "order": self.order,
            "layout": self.layout,
            "scan_indices": self.scan_indices,
            "scan_mode": self.scan_mode,
            "subdocuments": [s.to_dict() for s in self.subdocuments],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OutputDocumentPlan:
        return cls(
            doc_type=d["doc_type"],
            page_target=d.get("page_target", 1),
            order=d.get("order", 0),
            layout=d.get("layout", "two_column"),
            scan_indices=d.get("scan_indices"),
            scan_mode=d.get("scan_mode", "full_raster"),
            subdocuments=[SubDocumentPlan.from_dict(s) for s in d.get("subdocuments", [])],
        )


class DossierOutputPlan:
    """Kompletter Output-Plan für einen Bewerber — merge von Structural + Dossier.

    Produziert genau 2 merged PDFs: Ausdruck.pdf + Bewerbung.pdf (wie im Original).
    """

    def __init__(
        self,
        synthetic_id: str,
        documents: list[OutputDocumentPlan],
        semantic_profile: dict[str, list[str]],
        total_page_target: int = 0,
        photo_present: bool = False,
    ):
        self.synthetic_id = synthetic_id
        self.documents = sorted(documents, key=lambda d: d.order)
        self.semantic_profile = semantic_profile
        self.total_page_target = total_page_target or sum(d.page_target for d in documents)
        self.photo_present = bool(photo_present)

    def to_dict(self) -> dict[str, Any]:
        return {
            "synthetic_id": self.synthetic_id,
            "total_page_target": self.total_page_target,
            "documents": [d.to_dict() for d in self.documents],
            "semantic_profile": self.semantic_profile,
            "photo_present": self.photo_present,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DossierOutputPlan:
        return cls(
            synthetic_id=d["synthetic_id"],
            documents=[OutputDocumentPlan.from_dict(dd) for dd in d["documents"]],
            semantic_profile=d.get("semantic_profile", {}),
            total_page_target=d.get("total_page_target", 0),
            photo_present=bool(d.get("photo_present", False)),
        )

    @classmethod
    def from_samples(
        cls,
        structural_plan: dict[str, Any],
        dossier_plan: dict[str, Any],
        idx: int,
    ) -> DossierOutputPlan:
        """Merge Structural + Dossier in genau 2 Output-Dokumente:
        Ausdruck.pdf und Bewerbung.pdf (mit Sub-Dokumenten).
        """
        synthetic_id = dossier_plan.get("synthetic_id", f"SG{idx+1:04d}")
        structural_bewerbung = structural_plan.get("bewerbung", {})
        structural_ausdruck = structural_plan.get("ausdruck", {})

        # Scanned-Pages aus Structural-Plan übernehmen
        doc_plans = structural_plan.get("documents", [])
        scan_map: dict[str, list[int]] = {}
        for dp in doc_plans:
            scan_map[dp.get("type", "")] = dp.get("scanned_pages", [])

        # Ausdruck.pdf — immer 2 Seiten, kein Scan
        ausdruck_scan = scan_map.get("ausdruck", [])
        ausdruck = OutputDocumentPlan(
            doc_type="ausdruck",
            page_target=structural_ausdruck.get("page_count", 2),
            order=0,
            layout=structural_ausdruck.get("layout", "two_column"),
            scan_indices=ausdruck_scan if len(ausdruck_scan) < 2 else [],
            scan_mode="clean",
            subdocuments=[],
        )

        # Bewerbung.pdf — merged mit Sub-Dokumenten
        # Sub-Dokumente kommen aus dossier_plan["subdocuments"] (gelernt aus cleaned.md)
        dossier_subdocs = dossier_plan.get("subdocuments", dossier_plan.get("documents", []))
        bewerbung_subdocs: list[SubDocumentPlan] = []
        for order, dd in enumerate(dossier_subdocs):
            dtype = dd.get("type", "unknown")
            template_map = {
                "cover_letter": "cover_letter",
                "cv": "cv_standard",
                "cv_section": "cv_standard",
                "certificate": "certificate",
                "reference_letter": "reference_letter",
                "publication": "cv_standard",
                "personal": "ausdruck",
                "other": "cv_standard",
                "unknown": "cv_standard",
            }
            template = template_map.get(dtype, "cv_standard")
            bewerbung_subdocs.append(SubDocumentPlan(
                subdoc_type=dtype,
                order=order,
                page_target=dd.get("page_target", 1),
                template=template,
            ))

        # Set two-column template if layout is two_column
        bewerbung_layout_val = structural_bewerbung.get("layout", "standard")
        for subdoc in bewerbung_subdocs:
            if subdoc.template == "cv_standard" and bewerbung_layout_val == "two_column":
                subdoc.template = "cv_two_column"

        bewerbung_pages = structural_bewerbung.get("page_count", 15)
        # The dossier model observes source classes independently while the
        # structural model observes the merged Bewerbung.pdf. Normalize the
        # subdocument targets to the authoritative package target.
        if bewerbung_subdocs:
            raw_targets = [max(1, int(s.page_target)) for s in bewerbung_subdocs]
            remaining = max(len(raw_targets), int(bewerbung_pages))
            normalized: list[int] = []
            for pos, raw in enumerate(raw_targets):
                minimum_for_rest = len(raw_targets) - pos - 1
                allocation = max(1, min(raw, remaining - minimum_for_rest))
                normalized.append(allocation)
                remaining -= allocation
            preferred = next(
                (i for i, s in enumerate(bewerbung_subdocs)
                 if s.subdoc_type in {"cover_letter", "application_package"}),
                len(bewerbung_subdocs) - 1,
            )
            normalized[preferred] += max(0, remaining)
            for subdoc, target in zip(bewerbung_subdocs, normalized):
                subdoc.page_target = target

        bewerbung_scan = scan_map.get("bewerbung", [])
        bewerbung = OutputDocumentPlan(
            doc_type="bewerbung",
            page_target=bewerbung_pages,
            order=1,
            layout=structural_bewerbung.get("layout", "standard"),
            scan_indices=bewerbung_scan,
            scan_mode="full_raster" if len(bewerbung_scan) > bewerbung_pages * 0.5 else "mixed",
            subdocuments=bewerbung_subdocs,
        )

        return cls(
            synthetic_id=synthetic_id,
            documents=[ausdruck, bewerbung],
            semantic_profile=dossier_plan.get("semantic_profile", {}),
            total_page_target=ausdruck.page_target + bewerbung.page_target,
            photo_present=bool(structural_bewerbung.get("photo_present", False)),
        )


# ---------------------------------------------------------------------------
# Helper: Pläne samplen und mergen
# ---------------------------------------------------------------------------

def sample_output_plans(
    structural_model: StructuralModel,
    dossier_model: DossierModel,
    count: int,
    seed: int = 42,
) -> list[DossierOutputPlan]:
    """Sample und merge Structural- + Dossier-Pläne zu Output-Plänen."""
    structural_plans = []
    for _ in range(count):
        structural_plans.append(structural_model.sample_applicant())

    for sp in structural_plans:
        sp["documents"] = sp.get("documents") or structural_model.document_plan(sp)

    dossier_plans = dossier_model.sample(count, seed=seed)

    merged = []
    for i, (sp, dp) in enumerate(zip(structural_plans, dossier_plans)):
        merged.append(DossierOutputPlan.from_samples(sp, dp, i))
    return merged


def save_output_plans(plans: list[DossierOutputPlan], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([p.to_dict() for p in plans], indent=2, ensure_ascii=False))


def load_output_plans(path: str | Path) -> list[DossierOutputPlan]:
    return [DossierOutputPlan.from_dict(d) for d in json.loads(Path(path).read_text())]
