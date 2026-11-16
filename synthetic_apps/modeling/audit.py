"""Post-Render-Audit: misst Ist-Seitenzahlen gegen Plan.

Wird nach dem Rendering ausgeführt, meldet Abweichungen.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None


def audit_pdf_plan(applicants_json: str | Path, pdf_base_dir: str | Path) -> list[dict[str, Any]]:
    """Vergleicht generierte PDF-Seitenzahlen mit den geplanten.

    Args:
        applicants_json: Pfad zu ground_truth/applicants.json
        pdf_base_dir: Pfad zu applications_pdf/

    Returns:
        Liste von Audit-Einträgen (applicant_id, doc_name, plan, ist, abweichung)
    """
    pdf_base_dir = Path(pdf_base_dir)
    results: list[dict[str, Any]] = []

    profiles = json.loads(Path(applicants_json).read_text())
    for profile in profiles:
        aid = profile.get("applicant_id", "?")
        plan = profile.get("sampled_structural_plan", None)
        app_dir = pdf_base_dir / aid
        if not app_dir.exists():
            continue

        for pdf_file in sorted(app_dir.glob("*.pdf")):
            doc_name = pdf_file.stem
            if fitz:
                doc = fitz.open(str(pdf_file))
                actual_pages = len(doc)
                doc.close()
            else:
                actual_pages = 0

            planned = 0
            if plan:
                docs = plan.get("documents", [])
                for d in docs:
                    planned_type = d.get("doc_type", d.get("type", ""))
                    aliases = {
                        "ausdruck": {"ausdruck"},
                        "bewerbung": {"bewerbung", "application_package"},
                        "cv": {"cv"},
                        "application_package": {"application_package", "bewerbung"},
                        "cover_letter": {"cover_letter"},
                        "certificate": {"certificate", "certificates"},
                        "reference_letter": {"reference_letter"},
                    }.get(planned_type, {planned_type})
                    if doc_name.lower() in aliases or any(
                        alias in doc_name.lower() for alias in aliases
                    ):
                        planned = d.get("page_target", 0) or d.get("page_count", 0)
                        break

            deviation = actual_pages - planned
            results.append({
                "applicant_id": aid,
                "document": doc_name,
                "planned_pages": planned,
                "actual_pages": actual_pages,
                "deviation": deviation,
                "status": "ok" if deviation == 0 else "deviation",
            })

    return results


def print_audit_report(results: list[dict[str, Any]]) -> str:
    """Format audit results as a printable report."""
    total = len(results)
    deviations = [r for r in results if r["status"] == "deviation"]
    lines = [
        f"Audit: {total} Dokumente geprüft",
        f"  Plan erfüllt: {total - len(deviations)}",
        f"  Abweichungen: {len(deviations)}",
    ]
    if deviations:
        lines.append("  Details:")
        for d in deviations:
            lines.append(f"    {d['applicant_id']}/{d['document']}: "
                         f"Soll={d['planned_pages']} Ist={d['actual_pages']} "
                         f"Diff={d['deviation']:+d}")
    return "\n".join(lines)
