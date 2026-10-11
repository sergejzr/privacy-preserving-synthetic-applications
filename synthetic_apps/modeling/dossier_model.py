"""Learned dossier composition, subdocument sequences, and semantic distributions.

Fitted from two sources:
1. Structural profiles (analyze → PDF-level page count, layout, scan ratio)
2. Cleand MD files (Bewerbung.cleaned.md → subdocument types, sequences, page estimates)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
import json
import os
import re
from pathlib import Path
import random
from typing import Any


@dataclass
class SubdocumentDistribution:
    """Sequence patterns of subdocuments within Bewerbung.pdf."""
    sequence_patterns: list[list[str]] = field(default_factory=list)
    sequence_weights: list[float] = field(default_factory=list)
    # Per type: page count buckets
    subdoc_page_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    # Per type: presence probability
    subdoc_presence: dict[str, float] = field(default_factory=dict)


@dataclass
class DossierModel:
    schema_version: str
    n_dossiers: int
    document_count_distribution: dict[str, int]
    document_presence: dict[str, float]
    page_count_by_type: dict[str, dict[str, int]]
    semantic_code_presence: dict[str, dict[str, float]]
    calibrated: dict[str, bool]
    # Neu: Subdokument-Struktur
    subdocuments: SubdocumentDistribution = field(default_factory=SubdocumentDistribution)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["subdocuments"] = asdict(self.subdocuments)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DossierModel":
        sub = data.pop("subdocuments", {}) or {}
        model = cls(**data)
        model.subdocuments = SubdocumentDistribution(**sub)
        return model

    def sample(self, count: int, seed: int = 42) -> list[dict[str, Any]]:
        rng = random.Random(seed)
        count_values = list(self.document_count_distribution)
        count_weights = [self.document_count_distribution[key] for key in count_values]
        results = []
        for i in range(count):
            n_docs = int(rng.choices(count_values, weights=count_weights, k=1)[0])
            present = [dtype for dtype, probability in self.document_presence.items() if rng.random() < probability]
            if len(present) < n_docs:
                missing = [d for d in self.document_presence if d not in present]
                present.extend(missing[: n_docs - len(present)])
            present = present[:n_docs]
            documents = []
            for dtype in present:
                page_counts = self.page_count_by_type.get(dtype, {"1": 1})
                pages = int(rng.choices(list(page_counts), weights=list(page_counts.values()), k=1)[0])
                documents.append({"type": dtype, "page_target": pages})
            # Sample subdocument sequence for Bewerbung.pdf
            subdocs_seq = self._sample_subdoc_sequence(rng)
            semantic_profile = {}
            for family, codes in self.semantic_code_presence.items():
                semantic_profile[family] = sorted(code for code, probability in codes.items() if rng.random() < probability)
            results.append({
                "synthetic_id": f"SG{i+1:04d}",
                "documents": documents,
                "subdocuments": subdocs_seq,
                "semantic_profile": semantic_profile,
            })
        return results

    def _sample_subdoc_sequence(self, rng: random.Random) -> list[dict[str, Any]]:
        """Sample a subdocument sequence for Bewerbung.pdf."""
        if not self.subdocuments.sequence_patterns or not self.subdocuments.sequence_weights:
            return [{"type": "cover_letter", "page_target": 1}]
        seq = rng.choices(self.subdocuments.sequence_patterns, weights=self.subdocuments.sequence_weights, k=1)[0]
        result = []
        for sd_type in seq:
            page_buckets = self.subdocuments.subdoc_page_counts.get(sd_type, {"1": 1})
            pages = int(rng.choices(list(page_buckets), weights=list(page_buckets.values()), k=1)[0])
            result.append({"type": sd_type, "page_target": pages})

        # A real application package starts with an Anschreiben. The source
        # classifier can label sparse/continuation sections as ``unknown``;
        # that must not make the generated package begin with a CV annex.
        # Preserve the learned page count and sequence length by promoting an
        # existing cover letter or replacing the first ambiguous subdocument.
        cover_index = next(
            (i for i, item in enumerate(result)
             if item["type"] in {"cover_letter", "application_package"}),
            None,
        )
        if cover_index is not None and cover_index > 0:
            result.insert(0, result.pop(cover_index))
        elif cover_index is None and result:
            result[0]["type"] = "cover_letter"
        elif not result:
            result = [{"type": "cover_letter", "page_target": 1}]
        return result


def _classify_subdoc(first_line: str, section_heading: str | None = None) -> str:
    """Classify a subdocument by its first heading."""
    h = (section_heading or first_line).strip().lower()

    if 'bewerbung als' in h or 'bewerbung für' in h or 'anschreiben' in h or 'motivation' in h:
        return 'cover_letter'
    if 'lebenslauf' in h or 'curriculum' in h or 'cv' in h or 'werdegang' in h:
        return 'cv'
    if 'profil' in h or 'kernkompetenz' in h or 'fähigkeit' in h or 'qualifikation' in h:
        return 'cv'
    if 'berufserfahrung' in h or 'beruflicher werdegang' in h or 'tätigkeit' in h:
        return 'cv'
    if 'ausbildung' in h or 'akademische' in h or 'studium' in h or 'schulbildung' in h:
        return 'cv_section'
    if 'publikation' in h or 'schriften' in h:
        return 'publication'
    if 'sprach' in h or 'edv' in h:
        return 'cv_section'

    # Certificates (specific German terms)
    cert_kw = ['zeugnis', 'zertifikat', 'urkunde', 'bescheinigung', 'abschluss',
               'promotion', 'master', 'bachelor', 'diplom', 'magister', 'doktor',
               'fortbildung', 'teilnahme', 'nachweis', 'prüfung']
    if any(k in h for k in cert_kw):
        return 'certificate'

    # Reference letters
    ref_kw = ['referenz', 'empfehlung', 'referee']
    if any(k in h for k in ref_kw):
        return 'reference_letter'

    # Personal data (Ausdruck-like)
    if 'persönliche daten' in h or 'kontakt' in h or 'adress' in h or 'anschrift' in h:
        return 'personal'

    if 'weitere' in h or 'sonstige' in h or 'anlagen' in h or 'übersicht' in h:
        return 'other'

    return 'unknown'


def _parse_cleaned_md(text: str) -> list[dict[str, Any]]:
    """Parse Bewerbung.cleaned.md into subdocument parts with type and page estimate."""
    parts = re.split(r'\n---\s*\n(?=#)', text)
    result = []
    for part in parts:
        lines = part.strip().split('\n')
        first_line = lines[0] if lines else ''
        # Extract heading
        heading_match = re.match(r'^#\s+(.*)', first_line)
        heading = heading_match.group(1) if heading_match else first_line
        sd_type = _classify_subdoc(first_line, heading)
        n_lines = len(part.strip().split('\n'))
        est_pages = max(1, round(n_lines / 40))
        result.append({"type": sd_type, "page_estimate": est_pages, "lines": n_lines, "heading": heading[:60]})
    return result


def fit_dossier_model(
    profiles_dir: Path,
    cleaned_md_dir: str | Path | None = None,
    *,
    min_support: int = 3,
) -> DossierModel:
    """Fit a DossierModel from structural profiles and optional cleaned.md files.

    Args:
        profiles_dir: Directory with per-applicant structural JSON files.
        cleaned_md_dir: Optional directory with per-applicant subdirs containing
                       Bewerbung.cleaned.md for subdocument sequence learning.
        min_support: Minimum number of dossiers for a type to be considered calibrated.

    Returns:
        Fitted DossierModel.
    """
    profiles_dir = Path(profiles_dir)
    files = sorted(profiles_dir.glob("*.json"))
    if not files:
        raise ValueError("no structural profile files found")

    all_types: Counter[str] = Counter()
    dossier_counts: Counter[str] = Counter()
    pages: dict[str, Counter[str]] = defaultdict(Counter)
    semantics: dict[str, Counter[str]] = defaultdict(Counter)

    for path in files:
        records = json.loads(path.read_text(encoding="utf-8"))
        types = [record.get("document_type", "unknown") for record in records]
        dossier_counts[str(len(types))] += 1
        for dtype in set(types):
            all_types[dtype] += 1
        dossier_semantics: dict[str, set[str]] = defaultdict(set)
        for record in records:
            dtype = record.get("document_type", "unknown")
            pages[dtype][str(record.get("page_count", 1))] += 1
            for family, codes in record.get("semantic_codes", {}).items():
                for code in codes:
                    dossier_semantics[family].add(code)
        for family, codes in dossier_semantics.items():
            for code in codes:
                semantics[family][code] += 1

    n = len(files)
    calibrated: dict[str, bool] = {"document_presence": True, "page_count_by_type": True, "semantic_codes": True}
    presence = {dtype: count / n for dtype, count in all_types.items()}
    for dtype, count in all_types.items():
        if count < min_support:
            calibrated[f"document_presence:{dtype}"] = False
    semantic_presence = {family: {code: count / n for code, count in values.items()} for family, values in semantics.items()}

    # ___________________ Subdocument learning from cleaned.md ___________________
    subdoc_dist = SubdocumentDistribution()
    if cleaned_md_dir:
        md_dir = Path(cleaned_md_dir)
        all_sequences: list[list[str]] = []
        subdoc_type_counts: Counter[str] = Counter()
        subdoc_lines: dict[str, list[int]] = defaultdict(list)

        for applicant_dir in sorted(md_dir.iterdir()):
            if not applicant_dir.is_dir():
                continue
            md_file = applicant_dir / "Bewerbung.cleaned.md"
            if not md_file.exists():
                continue
            text = md_file.read_text(encoding="utf-8")
            parts = _parse_cleaned_md(text)
            if not parts:
                continue
            seq = [p["type"] for p in parts]
            all_sequences.append(seq)
            for p in parts:
                subdoc_type_counts[p["type"]] += 1
                subdoc_lines[p["type"]].append(p["lines"])

        if all_sequences:
            # Build weighted sequence patterns
            seq_counter = Counter(tuple(s) for s in all_sequences)
            total_seq = sum(seq_counter.values())
            subdoc_dist.sequence_patterns = [list(s) for s in seq_counter.keys()]
            subdoc_dist.sequence_weights = [c / total_seq for c in seq_counter.values()]

            # Build page count buckets per subdocument type
            for sd_type, lines_list in subdoc_lines.items():
                page_buckets: Counter[str] = Counter()
                for n_lines in lines_list:
                    bucket = str(max(1, round(n_lines / 40)))
                    page_buckets[bucket] += 1
                if page_buckets:
                    subdoc_dist.subdoc_page_counts[sd_type] = dict(page_buckets)

            # Build presence probabilities
            total_apps = len(all_sequences)
            for sd_type, count in subdoc_type_counts.items():
                subdoc_dist.subdoc_presence[sd_type] = count / total_apps

    return DossierModel(
        "dossier-0.2", n, dict(dossier_counts), presence,
        {dtype: dict(values) for dtype, values in pages.items()},
        semantic_presence, calibrated,
        subdocuments=subdoc_dist,
    )


def save_dossier_model(model: DossierModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def load_dossier_model(path: str | Path) -> DossierModel:
    path = Path(path)
    return DossierModel.from_dict(json.loads(path.read_text(encoding="utf-8")))
