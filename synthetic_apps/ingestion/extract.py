from __future__ import annotations

import hashlib
from pathlib import Path
import re
import shutil
import subprocess

from ..schemas import DossierFeature, DocumentFeature, FeatureValue, PageFeature


def _run(command: list[str], path: Path) -> str | None:
    if shutil.which(command[0]) is None:
        return None
    try:
        return subprocess.check_output(command + [str(path)], stderr=subprocess.DEVNULL, text=True)
    except (OSError, subprocess.CalledProcessError):
        return None


def _pdfinfo(path: Path) -> dict[str, str]:
    raw = _run(["pdfinfo"], path) or ""
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^([^:]+):\s*(.*)$", raw, re.MULTILINE)}


def _pages(path: Path) -> list[PageFeature]:
    info = _pdfinfo(path)
    try:
        count = int(info.get("Pages", "0"))
    except ValueError:
        count = 0
    size = info.get("Page size", "")
    match = re.search(r"([\d.]+)\s+x\s+([\d.]+)", size)
    width, height = (float(match.group(1)), float(match.group(2))) if match else (None, None)
    text = _run(["pdftotext"], path)
    chars_per_page = len(text.strip()) // count if text and count else None
    image_listing = _run(["pdfimages", "-list"], path)
    images = len([line for line in (image_listing or "").splitlines()[2:] if line.strip()])
    return [PageFeature(
        page_number=i,
        width_pt=width,
        height_pt=height,
        extracted_characters=FeatureValue(chars_per_page, "observed" if chars_per_page is not None else "failed", 1.0 if chars_per_page is not None else None, "pdftotext", "measured" if chars_per_page is not None else "extraction_failed"),
        image_count=FeatureValue(images, "observed", 1.0, "pdfimages", "measured"),
        text_layer=FeatureValue(bool(chars_per_page), "observed", 0.8, "pdftotext", "text_present_or_absent"),
    ) for i in range(1, count + 1)]


def _category(path: Path) -> str:
    name = path.stem.lower()
    if "cv" in name or "resume" in name: return "cv"
    if "cover" in name or "anschreiben" in name: return "cover_letter"
    if "reference" in name or "zeugnis" in name: return "reference"
    if "certificate" in name or "zertifikat" in name: return "certificate"
    return "unknown"


def extract_dossier(dossier_path: Path, input_root: Path, private_id: str, ocr_dir: Path | None = None) -> DossierFeature:
    docs = []
    for pdf in sorted(dossier_path.rglob("*.pdf")):
        rel = pdf.relative_to(input_root).as_posix()
        pages = _pages(pdf)
        info = _pdfinfo(pdf)
        ocr = None
        if ocr_dir:
            candidate = ocr_dir / Path(rel).with_suffix(".txt")
            if candidate.exists(): ocr = candidate
        docs.append(DocumentFeature(
            relative_path=rel,
            category=FeatureValue(_category(pdf), "inferred", 0.9, "filename_rule", "document_category_rule"),
            page_count=FeatureValue(len(pages), "observed" if pages else "failed", 1.0 if pages else None, "pdfinfo", "measured" if pages else "pdf_metadata_unavailable"),
            pages=pages,
            source_mode=FeatureValue("image_or_hybrid" if any(p.image_count.value for p in pages) else "native_or_unknown", "inferred", 0.6, "pdfimages_and_text", "coarse_source_mode"),
            ocr_match=FeatureValue(bool(ocr), "observed", 1.0, "relative_path_stem", "matched" if ocr else "missing"),
        ))
    return DossierFeature(private_id=private_id, relative_path=str(dossier_path.relative_to(input_root)), documents=docs)


def stable_private_id(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:20]
