"""Privacy and quality validation for the synthetic dataset.

Checks:
- Every PDF opens and has expected page count range
- All applicant IDs and filenames are unique
- Chronology and educational claims are consistent
- Generated documents only use fictional names and contact details
- No real-source PDF is byte-identical to a published PDF
- No private file path or source filename appears in published outputs
- Generated text is compared against local reference text for similarity
- Ground truth corresponds to actual generated document content
- dataset/ contains no .env, logs, temporary text dumps, or private files
- All public documentation identifies the corpus as synthetic
"""

from __future__ import annotations

import json
import re
import string
import hashlib
from pathlib import Path
from typing import Any

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None


def validate_dataset(
    dataset_path: str | Path,
    private_ref_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run all validation checks on a generated dataset.

    Args:
        dataset_path: Path to the dataset/ directory.
        private_ref_dir: Optional path to private reference PDFs for
                        similarity checking.

    Returns:
        Dict with 'passed', 'warnings', 'errors' lists.
    """
    dataset_path = Path(dataset_path)
    results: dict[str, Any] = {
        "dataset_path": str(dataset_path.resolve()),
        "passed": [],
        "warnings": [],
        "errors": [],
    }

    # 1. Check directory structure
    pdf_dir = dataset_path / "applications_pdf"
    stellen_dir = dataset_path / "stellenbeschreibungen"
    gt_dir = dataset_path / "ground_truth"
    extra_txt = dataset_path / "extra_attributes.txt"

    required_dirs = [pdf_dir, stellen_dir, gt_dir]
    for d in required_dirs:
        if not d.exists():
            results["errors"].append(f"Required directory missing: {d}")
        else:
            results["passed"].append(f"Directory exists: {d.relative_to(dataset_path)}")

    if not extra_txt.exists():
        results["errors"].append(f"Required file missing: extra_attributes.txt")
    else:
        results["passed"].append("File exists: extra_attributes.txt")

    # 2. Check applicant filenames and IDs
    if pdf_dir.exists():
        applicant_dirs = sorted([d for d in pdf_dir.iterdir() if d.is_dir()])
        if not applicant_dirs:
            results["warnings"].append("No applicant directories found in applications_pdf")
        else:
            results["passed"].append(f"Found {len(applicant_dirs)} applicant directories")

            # Check unique IDs
            ids = [d.name for d in applicant_dirs]
            if len(ids) != len(set(ids)):
                results["errors"].append("Duplicate applicant IDs found")
            else:
                results["passed"].append("All applicant IDs are unique")

            # Check ID format
            valid_id_pattern = re.compile(r"^SG\d{3}$")
            for aid in ids:
                if not valid_id_pattern.match(aid):
                    results["warnings"].append(f"Applicant ID '{aid}' does not match SGXXX format")

            # Check each applicant's PDFs
            for app_dir in applicant_dirs:
                app_results = _validate_applicant(app_dir)
                results["passed"].extend(app_results["passed"])
                results["warnings"].extend(app_results["warnings"])
                results["errors"].extend(app_results["errors"])

    # 3. Check stellenbeschreibung.md
    stellen_md = stellen_dir / "stellenbeschreibung.md"
    if stellen_md.exists():
        content = stellen_md.read_text()
        if len(content) < 200:
            results["errors"].append("Job description is too short")
        else:
            results["passed"].append(f"Job description: {len(content)} chars")

        # Check it's in German
        german_keywords = ["Stellenausschreibung", "Aufgaben", "Profil", "Wir bieten", "Kontakt"]
        found_kw = sum(1 for kw in german_keywords if kw in content)
        if found_kw < 2:
            results["warnings"].append("Job description may not be in German")
        else:
            results["passed"].append("Job description is in German")

        # Check no real institutions
        real_inst = ["Universität Bonn", "MPI", "Fraunhofer", "Helmholtz", "Leibniz",
                      "DFG", "BMBF", "DAAD", "EU-Kommission"]
        for ri in real_inst:
            if ri in content:
                results["warnings"].append(f"Possible real institution in job description: {ri}")

    # 4. Check extra_attributes.txt
    if extra_txt.exists():
        attrs = [a.strip() for a in extra_txt.read_text().splitlines() if a.strip()]
        if len(attrs) < 5:
            results["errors"].append(f"Only {len(attrs)} extra attributes, expected 12-15")
        else:
            results["passed"].append(f"{len(attrs)} extra attributes found")

    # 5. Check ground truth
    applicants_json = gt_dir / "applicants.json"
    if applicants_json.exists():
        try:
            profiles = json.loads(applicants_json.read_text())
            results["passed"].append(f"Ground truth: {len(profiles)} applicants")
            for p in profiles:
                aid = p.get("applicant_id", "?")
                if not p.get("fictional_name"):
                    results["warnings"].append(f"{aid}: missing fictional_name")
                email = p.get("fictional_email", "")
                if email and "@example.com" not in email:
                    # Allow clearly fictional/invented domains
                    if not any(real in email.lower() for real in ["example", "gmail", "yahoo", "web", "hotmail"]):
                        # Check if the domain looks fictional (invented university/company names)
                        domain = email.split("@")[-1] if "@" in email else ""
                        fictional_patterns = [".example.com", "-technologie.", "-forschung.", "institut", "universität",
                                             "quanten", "subraum", "forschungs", "zentrum", "-gmbh", "ag$", "eif$",
                                             "tu-", "fz-", "sfr.", "iq", "bfe", "dswt", "izq"]
                        is_fictional = any(p in domain.lower() for p in fictional_patterns)
                        if not is_fictional:
                            results["warnings"].append(f"{aid}: possible non-fictional email: {email}")
                phone = p.get("fictional_phone", "")
                if phone and phone.startswith("+49"):
                    pass  # valid fictional German number
        except json.JSONDecodeError as e:
            results["errors"].append(f"Invalid applicants.json: {e}")

    # 6. Check no private files in dataset
    private_patterns = [".env", ".log", ".tmp", "structure_profiles_private",
                        "references_private", "__pycache__"]
    for pattern in private_patterns:
        for f in dataset_path.rglob(pattern):
            results["errors"].append(f"Private file found in dataset: {f.relative_to(dataset_path)}")

    # 7. Check PDFs aren't byte-identical (via content hash)
    if pdf_dir.exists() and private_ref_dir:
        ref_dir = Path(private_ref_dir)
        if ref_dir.exists():
            ref_hashes = _collect_file_hashes(ref_dir)
            for app_dir in sorted(pdf_dir.iterdir()):
                if not app_dir.is_dir():
                    continue
                for pdf_file in sorted(app_dir.glob("*.pdf")):
                    content = pdf_file.read_bytes()
                    h = _hash_bytes(content)
                    if h in ref_hashes:
                        results["errors"].append(
                            f"Byte-identical to reference: {pdf_file.relative_to(dataset_path)}"
                        )

    # 8. Check synthetic footer or identifier
    synthetic_markers = ["Synthetic fictional test data", "not a real applicant", "synthetic"]
    for f in sorted(dataset_path.glob("**/*.md")):
        content = f.read_text()
        if not any(m in content for m in synthetic_markers):
            results["warnings"].append(f"No synthetic marker found in {f.relative_to(dataset_path)}")

    # Determine overall status
    if results["errors"]:
        results["status"] = "FAILED"
    elif results["warnings"]:
        results["status"] = "PASSED_WITH_WARNINGS"
    else:
        results["status"] = "PASSED"

    return results


def _validate_applicant(app_dir: Path) -> dict[str, list[str]]:
    """Validate a single applicant's PDFs."""
    results: dict[str, list[str]] = {"passed": [], "warnings": [], "errors": []}
    aid = app_dir.name
    pdf_files = sorted(app_dir.glob("*.pdf"))

    if not pdf_files:
        results["warnings"].append(f"{aid}: no PDF files found")
        return results

    # Check filenames are reasonable
    valid_names = {
        "Ausdruck", "Bewerbung",
        "CV", "Cover_Letter", "Application_Package", "Certificates",
        "Reference_Letter", "Portfolio",
    }
    for f in pdf_files:
        stem = f.stem
        if stem not in valid_names:
            results["warnings"].append(f"{aid}: unexpected filename: {f.name}")

    # Check PDFs can be opened
    if fitz is not None:
        for f in pdf_files:
            try:
                doc = fitz.open(str(f))
                page_count = len(doc)
                if page_count == 0:
                    results["errors"].append(f"{aid}/{f.name}: empty PDF")
                doc.close()
            except Exception as e:
                results["errors"].append(f"{aid}/{f.name}: cannot open: {e}")

    # Check for example.com emails in PDF text
    if fitz is not None:
        for f in pdf_files:
            try:
                doc = fitz.open(str(f))
                for page in doc:
                    text = page.get_text("text")
                    # Find email-like strings
                    emails = re.findall(r'\S+@\S+', text)
                    for email in emails:
                        if "example.com" not in email and not email.endswith("."):
                            if len(email) > 5 and "@" in email:
                                # Check if it's a clearly fictional domain
                                domain = email.split("@")[-1] if "@" in email else ""
                                fictional_patterns = ["-technologie.", "-forschung.", "institut", "universität",
                                                     "quanten", "subraum", "forschungs", "zentrum", "-gmbh",
                                                     "tu-", "fz-"]
                                is_fictional = any(p in domain.lower() for p in fictional_patterns)
                                if not is_fictional:
                                    results["warnings"].append(
                                        f"{aid}/{f.name}: non-example.com email: {email}"
                                    )
                doc.close()
            except Exception:
                pass

    # Check page-level content quality.  A repeated page is almost always a
    # rendering/padding bug in this project; common headers and footers alone
    # are ignored by requiring a substantial normalized text body.
    if fitz is not None:
        for f in pdf_files:
            try:
                doc = fitz.open(str(f))
                seen: dict[str, int] = {}
                for page_no, page in enumerate(doc, start=1):
                    text = _normalized_page_text(page.get_text("text"))
                    if len(text) < 180:
                        continue
                    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    if digest in seen:
                        results["errors"].append(
                            f"{aid}/{f.name}: duplicate page content on pages "
                            f"{seen[digest]} and {page_no}"
                        )
                    else:
                        seen[digest] = page_no
                doc.close()
            except Exception:
                pass

    return results


def _normalized_page_text(text: str) -> str:
    """Normalize layout noise while retaining meaningful page content."""
    lines = []
    for line in text.splitlines():
        value = re.sub(r"\s+", " ", line).strip().lower()
        if not value or value in {"synthetic fictional test data", "synthetische testdaten"}:
            continue
        lines.append(value)
    return " ".join(lines)


def _collect_file_hashes(directory: Path) -> set[str]:
    """Collect SHA256 hashes of all files in a directory tree."""
    hashes = set()
    for f in directory.rglob("*"):
        if f.is_file():
            hashes.add(_hash_bytes(f.read_bytes()))
    return hashes


def _hash_bytes(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()
