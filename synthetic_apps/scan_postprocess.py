"""Post-process clean PDFs into scanned-looking documents.

Applies scan artifacts to a configurable subset of pages.
- full_scan: Page rasterized to image, original text removed.
  Used for ~40-60% of pages (simulating scanned certificates).
- clean: Page left as-is with original text.
  Used for cover pages, CVs, etc.

No overlay/transparency tricks — pages are either raster-scanned or clean.
"""

from __future__ import annotations

import io
import random
from typing import Tuple

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

from PIL import Image, ImageDraw, ImageFilter

_rng = random.Random(20261008)


def seed_rng(seed: int):
    _rng.seed(seed)


def _rand(a: float, b: float) -> float:
    return _rng.uniform(a, b)


def _randint(a: int, b: int) -> int:
    return _rng.randint(a, b)


def _paper_color() -> Tuple[int, int, int]:
    return (
        max(220, min(255, 245 + _randint(-12, 5))),
        max(215, min(255, 240 + _randint(-12, 5))),
        max(200, min(255, 235 + _randint(-15, 5))),
    )


def _add_noise(pixels, w: int, h: int, intensity: float = 0.015):
    num_pixels = int(w * h * intensity)
    for _ in range(num_pixels):
        x = _randint(0, w - 1)
        y = _randint(0, h - 1)
        r, g, b = pixels[x, y]
        n = _randint(-6, 6)
        pixels[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))


def _add_dust_speckles(draw, w: int, h: int, count: int = 10):
    for _ in range(count):
        x = _randint(0, w - 1)
        y = _randint(0, h - 1)
        r = _randint(1, 3)
        gray = _randint(100, 200)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(gray, gray, gray))


def _add_border_shadow(im: Image.Image, width: int = 6) -> Image.Image:
    w, h = im.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for i in range(width):
        alpha = int(35 * (1 - i / width))
        draw.rectangle([0, i, w, i + 1], fill=(0, 0, 0, alpha))
        draw.rectangle([0, h - i - 1, w, h - i], fill=(0, 0, 0, alpha))
        draw.rectangle([i, 0, i + 1, h], fill=(0, 0, 0, alpha))
        draw.rectangle([w - i - 1, 0, w - i, h], fill=(0, 0, 0, alpha))
    return Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")


def _add_fold_line(draw, w: float, h: float):
    """Occasional fold/scan streak with varied orientation and position."""
    if _rng.random() >= 0.14:
        return
    if _rng.random() < 0.72:
        x = _rand(w * 0.08, w * 0.92)
        draw.line([(x, 0), (x + _rand(-3, 3), h)], fill=(170, 165, 150), width=1)
        draw.line([(x + 1, 0), (x + 1, h)], fill=(210, 200, 185), width=1)
    else:
        y = _rand(h * 0.08, h * 0.92)
        draw.line([(0, y), (w, y + _rand(-3, 3))], fill=(170, 165, 150), width=1)


def _add_rotation(im: Image.Image, max_angle: float = 1.0) -> Image.Image:
    angle = _rand(-max_angle, max_angle)
    if abs(angle) < 0.15:
        return im
    bg = _paper_color()
    return im.rotate(angle, expand=False, fillcolor=bg, resample=Image.BICUBIC)


def _add_stamp_and_marks(draw, w: float, h: float):
    if _rng.random() < 0.1:
        for hy in [h * 0.1, h * 0.5, h * 0.9]:
            draw.ellipse([w * 0.03 - 4, hy - 4, w * 0.03 + 4, hy + 4],
                         outline=(120, 120, 120), fill=(235, 230, 220))
    if _rng.random() < 0.12:
        hx = _rand(w * 0.1, w * 0.7)
        hy = _rand(h * 0.3, h * 0.7)
        hw = _rand(60, 150)
        hh = _rand(12, 18)
        draw.rectangle([hx, hy, hx + hw, hy + hh], fill=(255, 255, 0, 50))


def convert_pdf_to_scanned(
    pdf_bytes: bytes,
    scan_fraction: float = 0.5,
    scan_random_seed: int | None = None,
    dpi: int = 72,
    scan_page_indices: list[int] | None = None,
) -> bytes:
    """Convert clean PDF pages to scanned-looking pages.

    A configurable fraction of pages are rasterized into images with
    realistic scan artifacts and have their original text removed.
    The remaining pages are left clean with extractable text.

    Args:
        pdf_bytes: Input clean PDF bytes.
        scan_fraction: Fraction of pages to fully scan (0-1).
        scan_random_seed: Seed for reproducible page selection.
        dpi: Rasterization DPI (lower = faster, default 72).
        scan_page_indices: Explicit list of page indices to scan.
                           Overrides scan_fraction when provided.

    Returns:
        PDF bytes with mix of scanned and clean pages.
    """
    if fitz is None:
        return pdf_bytes

    if scan_random_seed is not None:
        local_rng = random.Random(scan_random_seed)
    else:
        local_rng = _rng

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return pdf_bytes

    num_pages = len(doc)
    if num_pages == 0:
        doc.close()
        return pdf_bytes

    # Determine which pages to scan
    if scan_page_indices is not None:
        # Use explicit indices from structural model
        scan_indices = set(idx for idx in scan_page_indices if idx < num_pages)
    elif num_pages >= 2:
        # Keep at least the first page clean (cover/header), scan from remaining
        scan_candidates = list(range(1, num_pages))
        target_scan = max(0, round((num_pages - 1) * scan_fraction))
        num_scan = min(target_scan, len(scan_candidates))
        local_rng.shuffle(scan_candidates)
        scan_indices = set(scan_candidates[:num_scan])
    else:
        # Single page: sometimes scanned
        scan_indices = {0} if local_rng.random() < scan_fraction else set()

    # Process in reverse order so page indices stay valid
    for idx in sorted(scan_indices, reverse=True):
        page = doc[idx]
        try:
            rect = page.rect
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            draw = ImageDraw.Draw(img, "RGBA")
            w, h = img.size
            _add_noise(img.load(), w, h, intensity=0.02)
            if _rng.random() < 0.48:
                _add_dust_speckles(draw, w, h, count=_randint(4, 16))
            _add_stamp_and_marks(draw, w, h)
            _add_fold_line(draw, w, h)
            img = _add_border_shadow(img)
            img = _add_rotation(img)
            img = img.filter(ImageFilter.GaussianBlur(radius=_rand(0.2, 0.6)))

            img_bytes = io.BytesIO()
            img.save(img_bytes, format="PNG")

            # Replace page: new blank page with just the scanned image
            doc.insert_page(idx + 1, width=rect.width, height=rect.height)
            new_page = doc[idx + 1]
            new_page.insert_image(
                fitz.Rect(0, 0, rect.width, rect.height),
                stream=img_bytes.getvalue(),
            )
            doc.delete_page(idx)
        except Exception:
            pass

    buf = io.BytesIO()
    doc.save(buf, garbage=4, deflate=True)
    doc.close()
    return buf.getvalue()
