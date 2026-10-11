"""Deterministic, non-LLM PDF structure analyzer.

Extracts only non-content structural descriptors from PDF files.
No text content is persisted, logged, or sent anywhere.
"""

from __future__ import annotations

import math
from pathlib import Path

try:
    import pymupdf as fitz  # PyMuPDF
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

from .struct_schemas import (
    DocumentType,
    LayoutType,
    PageSize,
    ScannedLikelihood,
    StructuralRecord,
    TextDensity,
    WordCountBucket,
)
from .semantic_features import extract_taxonomy_codes


def _classify_page_size(width_pt: float, height_pt: float) -> PageSize:
    """Classify page dimensions into standard sizes."""
    a4_w, a4_h = 595.28, 841.89
    letter_w, letter_h = 612.0, 792.0
    tol = 20.0

    if abs(width_pt - a4_w) < tol and abs(height_pt - a4_h) < tol:
        return PageSize.A4
    if abs(width_pt - letter_w) < tol and abs(height_pt - letter_h) < tol:
        return PageSize.letter
    return PageSize.other


def _classify_layout(text_blocks: list[dict]) -> LayoutType:
    """Estimate column layout from text-block geometry."""
    if len(text_blocks) < 3:
        return LayoutType.standard

    centers_x = [b.get("x_center", 0) for b in text_blocks]
    page_width = max(b.get("x_right", 0) for b in text_blocks) if text_blocks else 1
    if page_width == 0:
        return LayoutType.unknown

    normalized = [c / page_width for c in centers_x]

    left_count = sum(1 for c in normalized if c < 0.4)
    right_count = sum(1 for c in normalized if c > 0.6)
    center_count = sum(1 for c in normalized if 0.4 <= c <= 0.6)

    # Categorize based on where blocks cluster
    if left_count > 0 and right_count > 0 and center_count < max(left_count, right_count):
        return LayoutType.two_column
    # Check if many blocks are in tables (aligned rows/columns)
    if _has_table_like_blocks(text_blocks):
        return LayoutType.tables
    return LayoutType.standard


def _has_table_like_blocks(blocks: list[dict]) -> bool:
    """Heuristic: multiple blocks with similar y-ranges suggest tables."""
    if len(blocks) < 6:
        return False
    y_ranges = [(b.get("y_top", 0), b.get("y_bottom", 0)) for b in blocks]
    # Count blocks sharing similar y-range (within 5pt)
    for i, (y0, y1) in enumerate(y_ranges):
        same_row = 0
        for j, (y2, y3) in enumerate(y_ranges):
            if i != j and abs(y0 - y2) < 5 and abs(y1 - y3) < 5:
                same_row += 1
        if same_row >= 2:
            return True
    return False


def _estimate_text_density(words_per_page: float) -> TextDensity:
    if words_per_page < 100:
        return TextDensity.low
    if words_per_page < 400:
        return TextDensity.medium
    return TextDensity.high


def _bucket_word_count(total_words: int) -> WordCountBucket:
    if total_words == 0:
        return WordCountBucket.zero
    if total_words <= 200:
        return WordCountBucket.under_200
    if total_words <= 500:
        return WordCountBucket.bucket_200_500
    if total_words <= 800:
        return WordCountBucket.bucket_500_800
    if total_words <= 1100:
        return WordCountBucket.bucket_800_1100
    if total_words <= 1500:
        return WordCountBucket.bucket_1100_1500
    if total_words <= 2000:
        return WordCountBucket.bucket_1500_2000
    return WordCountBucket.over_2000


def _guess_document_type(filename: str, text_samples: list[str]) -> DocumentType:
    """Broad document-type classification from filename and content hints."""
    fname_lower = filename.lower()
    # German cover letters
    if any(k in fname_lower for k in [
        "bewerbung", "anschreiben", "cover", "motivation", "anschreib",
    ]):
        return DocumentType.cover_letter
    # German CVs
    if any(k in fname_lower for k in [
        "cv", "lebenslauf", "resume", "werdegang", "tabellarisch",
    ]):
        return DocumentType.cv
    # Certificates
    if any(k in fname_lower for k in [
        "zeugnis", "zertifikat", "certificate", "urkunde",
        "fortbildung", "bescheinigung", "nachweis",
    ]):
        return DocumentType.certificate
    # Reference letters
    if any(k in fname_lower for k in [
        "referenz", "empfehlung", "reference",
    ]):
        return DocumentType.reference_letter
    # Portfolio
    if any(k in fname_lower for k in [
        "portfolio", "projekt", "arbeitsprobe",
    ]):
        return DocumentType.portfolio
    # Research / publication
    if any(k in fname_lower for k in [
        "publikation", "research", "forschung", "publication",
    ]):
        return DocumentType.research_summary
    # Ausdruck is commonly a printed CV/overview sheet in this corpus.
    if "ausdruck" in fname_lower:
        return DocumentType.cv
    return DocumentType.unknown


def _collect_text_blocks(page) -> list[dict]:
    """Extract geometric descriptors from text blocks (not text content)."""
    blocks = []
    try:
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") == 0:  # text block
                bbox = block.get("bbox", (0, 0, 0, 0))
                blocks.append({
                    "x_center": (bbox[0] + bbox[2]) / 2,
                    "y_center": (bbox[1] + bbox[3]) / 2,
                    "x_left": bbox[0],
                    "x_right": bbox[2],
                    "y_top": bbox[1],
                    "y_bottom": bbox[3],
                    "width": bbox[2] - bbox[0],
                    "height": bbox[3] - bbox[1],
                })
    except Exception:
        pass
    return blocks


def _count_words_ephemeral(page) -> int:
    """Count words on a page without persisting text content."""
    try:
        text = page.get_text("text")
        return len(text.split())
    except Exception:
        return 0


def _detect_images(page) -> bool:
    """Check if page contains images."""
    try:
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") == 1:
                return True
    except Exception:
        pass
    return False


def _detect_photo(page) -> bool:
    """Conservative portrait heuristic based on image geometry only."""
    try:
        rect = page.rect
        page_area = max(rect.width * rect.height, 1.0)
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 1:
                continue
            x0, y0, x1, y1 = block.get("bbox", (0, 0, 0, 0))
            width, height = max(0.0, x1 - x0), max(0.0, y1 - y0)
            aspect = height / max(width, 1.0)
            area_ratio = width * height / page_area
            if (y0 < rect.height * 0.42 and 1.15 <= aspect <= 2.2
                    and 0.008 <= area_ratio <= 0.16):
                return True
    except Exception:
        pass
    return False


def _detect_tables_heuristic(text_blocks: list[dict]) -> bool:
    """Detect table-like structures from block geometry alone."""
    return _has_table_like_blocks(text_blocks)


def analyze_pdf(path: str | Path) -> StructuralRecord | None:
    """Analyze a single PDF and return a non-content structural record.

    Args:
        path: Path to the PDF file.

    Returns:
        StructuralRecord with only non-content descriptors, or None if the PDF
        cannot be opened.
    """
    if fitz is None:
        raise ImportError("PyMuPDF (fitz) is required for PDF analysis")

    path = Path(path)
    if not path.exists():
        return None

    try:
        doc = fitz.open(str(path))
    except Exception:
        return None

    try:
        page_count = len(doc)
        if page_count == 0:
            return None

        total_words = 0
        all_text_blocks: list[dict] = []
        has_images = False
        has_photo = False
        image_pages = 0
        text_sample_for_type: list[str] = []
        semantic_text: list[str] = []

        for page in doc:
            total_words += _count_words_ephemeral(page)
            blocks = _collect_text_blocks(page)
            all_text_blocks.extend(blocks)
            if _detect_images(page):
                has_images = True
                image_pages += 1
            has_photo = has_photo or _detect_photo(page)
            if len(text_sample_for_type) < 2:
                # Ephemeral, bounded sample used only for classification.
                text_sample_for_type.append(page.get_text("text")[:500])
            if len(semantic_text) < 20:
                semantic_text.append(page.get_text("text")[:2000])

        # Page size from first page
        first_page = doc[0]
        rect = first_page.rect
        page_size = _classify_page_size(rect.width, rect.height)

        layout = _classify_layout(all_text_blocks)
        has_tables = _detect_tables_heuristic(all_text_blocks)

        # Scanned likelihood: if no extractable text blocks but pages exist
        scanned_likelihood = ScannedLikelihood.low
        if total_words == 0 and page_count > 0:
            scanned_likelihood = ScannedLikelihood.high
        elif total_words < 50 and page_count > 0:
            scanned_likelihood = ScannedLikelihood.medium

        words_per_page = total_words / max(page_count, 1)
        text_density = _estimate_text_density(words_per_page)
        word_bucket = _bucket_word_count(total_words)

        doc_type = _guess_document_type(path.name, text_sample_for_type)

        # Language detection without persistence: if we have enough text,
        # do a quick ephemeral check, then discard
        language = "unknown"
        if total_words > 20:
            try:
                first_page_text = doc[0].get_text("text")
                if first_page_text and len(first_page_text) > 50:
                    # Heuristic only; no text is retained.
                    de_chars = sum(1 for c in first_page_text if c in "äöüßÄÖÜ")
                    en_chars = sum(1 for c in first_page_text.lower() if c in "theandofinwith")
                    if de_chars > 2:
                        language = "de"
                    elif en_chars > 2:
                        language = "en"
            except Exception:
                pass

        return StructuralRecord(
            document_type=doc_type,
            page_count=page_count,
            page_size=page_size,
            layout=layout,
            approximate_word_count_bucket=word_bucket,
            text_density=text_density,
            has_tables=has_tables,
            has_images=has_images,
            image_ratio=image_pages / page_count,
            semantic_codes=extract_taxonomy_codes("\n".join(semantic_text)),
            scanned_likelihood=scanned_likelihood,
            language=language,
        )
        object.__setattr__(record, "_has_photo", has_photo)
        return record
    finally:
        doc.close()
