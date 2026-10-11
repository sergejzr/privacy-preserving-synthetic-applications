"""Ground truth generation for the synthetic dataset.

Generates two ground-truth layers:
1. Canonical truth (already in applicants.json)
2. Document-observable truth: maps which facts are actually supported
   by which generated documents.

This distinction matters for evaluation: the extraction pipeline should
not be penalized for failing to extract facts absent from the PDFs.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

_rng = random.Random(20261008)


def generate_document_evidence(
    applicants_path: str | Path,
    pdf_base_dir: str | Path,
    output_dir: str | Path,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate document-evidence ground truth.

    For each applicant, maps canonical facts to the specific document
    types where they appear, marking facts as:
    - 'present': fact is stated in the document
    - 'absent': fact is deliberately omitted
    - 'conflicted': contradictory evidence exists

    Args:
        applicants_path: Path to applicants.json.
        pdf_base_dir: Path to applications_pdf/ directory.
        output_dir: Output directory for ground truth files.
        manifest: Optional manifest dict.

    Returns:
        The document_evidence dict.
    """
    applicants_path = Path(applicants_path)
    pdf_base_dir = Path(pdf_base_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if manifest is None:
        manifest = {}
    manifest["phase"] = "E"
    manifest["ground_truth_version"] = "0.1.0"

    profiles = json.loads(applicants_path.read_text())
    all_evidence: dict[str, Any] = {}

    for profile in profiles:
        aid = profile.get("applicant_id", "?")
        name = profile.get("fictional_name", "?")
        facts_to_disclose = profile.get("facts_to_disclose", [])
        facts_to_omit = profile.get("facts_to_omit", [])
        contradictions = profile.get("intentional_contradictions", [])
        expected_attrs = profile.get("expected_evaluation_attributes", {})

        # Determine which document types exist
        app_pdf_dir = pdf_base_dir / aid
        existing_docs = []
        if app_pdf_dir.exists():
            existing_docs = [f.stem for f in sorted(app_pdf_dir.glob("*.pdf"))]

        # Build evidence map
        evidence: dict[str, Any] = {
            "applicant_id": aid,
            "fictional_name": name,
            "documents_available": existing_docs,
            "canonical_facts": [],
            "document_observable_facts": [],
            "conflicts": [],
        }

        # Map disclosed facts to documents
        for fact in facts_to_disclose:
            fact_id = _fact_id(aid, fact)
            doc_types = _assign_to_documents(fact, existing_docs)
            evidence["canonical_facts"].append({
                "fact_id": fact_id,
                "fact": fact,
                "truth": True,
            })
            evidence["document_observable_facts"].append({
                "fact_id": fact_id,
                "fact": fact,
                "present_in": doc_types,
                "status": "present",
            })

        # Map omitted facts
        for fact in facts_to_omit:
            fact_id = _fact_id(aid, fact)
            evidence["canonical_facts"].append({
                "fact_id": fact_id,
                "fact": fact,
                "truth": False,
            })
            evidence["document_observable_facts"].append({
                "fact_id": fact_id,
                "fact": fact,
                "present_in": [],
                "status": "absent",
            })

        # Map intentional contradictions
        for contradiction in contradictions:
            cid = _fact_id(aid, contradiction.get("fact_a", "")[:40])
            evidence["conflicts"].append({
                "conflict_id": cid,
                "fact_a": contradiction.get("fact_a", ""),
                "fact_b": contradiction.get("fact_b", ""),
                "description": contradiction.get("description", ""),
            })
            evidence["document_observable_facts"].append({
                "fact_id": f"{cid}_a",
                "fact": contradiction.get("fact_a", ""),
                "present_in": ["Cover_Letter" if "Anschreiben" in contradiction.get("fact_a", "") else "CV"],
                "status": "conflicted",
            })
            evidence["document_observable_facts"].append({
                "fact_id": f"{cid}_b",
                "fact": contradiction.get("fact_b", ""),
                "present_in": ["CV"],
                "status": "conflicted",
            })

        # Map expected evaluation attributes as facts
        for attr_key, attr_value in expected_attrs.items():
            fact_text = f"{attr_key}: {attr_value}"
            fact_id = _fact_id(aid, attr_key)
            evidence["canonical_facts"].append({
                "fact_id": fact_id,
                "fact": fact_text,
                "truth": attr_value,
            })
            # Expected attributes should be extractable from CV and Cover_Letter
            evidence["document_observable_facts"].append({
                "fact_id": fact_id,
                "fact": fact_text,
                "present_in": ["CV", "Cover_Letter"],
                "status": "present",
            })

        # Add employment history as document-observable facts
        for i, emp in enumerate(profile.get("employment_history", [])):
            fact_text = f"{emp.get('position', '?')} bei {emp.get('employer', '?')} ({emp.get('month_start', '?')} - {emp.get('month_end', '?')})"
            fact_id = _fact_id(aid, f"emp_{i}")
            evidence["canonical_facts"].append({
                "fact_id": fact_id,
                "fact": fact_text,
                "truth": True,
            })
            evidence["document_observable_facts"].append({
                "fact_id": fact_id,
                "fact": fact_text,
                "present_in": ["CV"],
                "status": "present",
            })

        # Add education as document-observable facts
        for i, edu in enumerate(profile.get("education", [])):
            fact_text = f"{edu.get('degree', '?')} an {edu.get('institution', '?')} ({edu.get('year_start', '?')}-{edu.get('year_end', '?')})"
            fact_id = _fact_id(aid, f"edu_{i}")
            evidence["canonical_facts"].append({
                "fact_id": fact_id,
                "fact": fact_text,
                "truth": True,
            })
            evidence["document_observable_facts"].append({
                "fact_id": fact_id,
                "fact": fact_text,
                "present_in": ["CV"],
                "status": "present",
            })

        all_evidence[aid] = evidence

    # Write document_evidence.json
    evidence_path = output_dir / "document_evidence.json"
    tmp = evidence_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(all_evidence, indent=2, ensure_ascii=False))
    tmp.rename(evidence_path)

    manifest["document_evidence_path"] = str(evidence_path)
    manifest["document_evidence_count"] = sum(
        len(e["document_observable_facts"]) for e in all_evidence.values()
    )

    return all_evidence


def _fact_id(applicant_id: str, text: str) -> str:
    """Generate a deterministic fact ID from text."""
    h = hashlib.sha256(text.encode()).hexdigest()[:12]
    return f"{applicant_id}_fact_{h}"


def _assign_to_documents(fact: str, available_docs: list[str]) -> list[str]:
    """Assign a fact to likely documents based on content heuristics."""
    docs = []
    fact_lower = fact.lower()
    for doc in available_docs:
        doc_lower = doc.lower()
        # Cover letters mention motivation, experience, qualifications
        if any(k in doc_lower for k in ["cover", "anschreiben", "motivation"]):
            if any(k in fact_lower for k in [
                "motivation", "interesse", "erfahrung", "qualifikation",
                "kompetenz", "leitung", "projekt", "forschung",
            ]):
                docs.append(doc)
        # CVs contain all career facts
        if any(k in doc_lower for k in ["cv", "lebenslauf", "resume"]):
            docs.append(doc)
        # Certificates confirm specific employment/education
        if any(k in doc_lower for k in ["certificate", "zeugnis", "zertifikat"]):
            if any(k in fact_lower for k in [
                "position", "employer", "arbeitgeber", "beschäftigt",
                "tätigkeit", "aufgabe", "zeugnis",
            ]):
                docs.append(doc)
        # Reference letters mention personal qualities
        if any(k in doc_lower for k in ["reference", "referenz", "empfehlung"]):
            if any(k in fact_lower for k in [
                "empfehlung", "zusammenarbeit", "persönlich",
                "charakter", "referenz", "team",
            ]):
                docs.append(doc)

    # Deduplicate
    return list(dict.fromkeys(docs))
