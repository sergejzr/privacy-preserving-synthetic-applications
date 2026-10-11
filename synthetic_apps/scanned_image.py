"""Programmatic generation of realistic scanned-document images.

Fully deterministic, no external generation API needed.
Renders text on paper-like backgrounds with scan artifacts.
"""

from __future__ import annotations

import io
import math
import random
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Point = Tuple[float, float]

# ---------------------------------------------------------------------------
# Global RNG controlled by a seed for reproducibility
# ---------------------------------------------------------------------------

_rng = random.Random(20261008)


def seed_rng(seed: int):
    _rng.seed(seed)


def _rand(a: float, b: float) -> float:
    return _rng.uniform(a, b)


def _randint(a: int, b: int) -> int:
    return _rng.randint(a, b)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _paper_color() -> Tuple[int, int, int]:
    """Off-white with slight random variation."""
    base = 248
    return (
        max(220, min(255, base + _randint(-15, 5))),
        max(215, min(255, base + _randint(-15, 5))),
        max(200, min(255, base + _randint(-20, 5))),
    )


def _find_font(size: int = 11) -> ImageFont.FreeTypeFont:
    """Find a serif or sans-serif font available on the system."""
    import os
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    # Fallback: default PIL font (small, but works)
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Scan artifacts
# ---------------------------------------------------------------------------

def _add_noise(draw: ImageDraw, img: Image.Image, intensity: float = 0.02):
    """Add subtle Gaussian-like noise."""
    px = img.load()
    w, h = img.size
    num_pixels = int(w * h * intensity)
    for _ in range(num_pixels):
        x = _randint(0, w - 1)
        y = _randint(0, h - 1)
        r, g, b = px[x, y]
        noise = _randint(-8, 8)
        px[x, y] = (
            max(0, min(255, r + noise)),
            max(0, min(255, g + noise)),
            max(0, min(255, b + noise)),
        )


def _add_dust_speckles(draw: ImageDraw, img: Image.Image, count: int = 30):
    """Add tiny dark specks as seen on real scans."""
    w, h = img.size
    for _ in range(count):
        x = _randint(0, w - 1)
        y = _randint(0, h - 1)
        r = _randint(1, 3)
        gray = _randint(100, 200)
        draw.ellipse(
            [x - r, y - r, x + r, y + r],
            fill=(gray, gray, gray),
        )


def _add_border_shadow(img: Image.Image, width: int = 8) -> Image.Image:
    """Add darker borders simulating scanner edge shadows."""
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for i in range(width):
        alpha = int(40 * (1 - i / width))
        # Top
        draw.rectangle([0, i, w, i + 1], fill=(0, 0, 0, alpha))
        # Bottom
        draw.rectangle([0, h - i - 1, w, h - i], fill=(0, 0, 0, alpha))
        # Left
        draw.rectangle([i, 0, i + 1, h], fill=(0, 0, 0, alpha))
        # Right
        draw.rectangle([w - i - 1, 0, w - i, h], fill=(0, 0, 0, alpha))

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _add_stamp(
    draw: ImageDraw, x: float, y: float, text: str = "GEPRÜFT",
    radius: int = 30, color: Tuple[int, int, int] = (180, 40, 40),
):
    """Draw a circular stamp mark."""
    draw.ellipse(
        [x - radius, y - radius, x + radius, y + radius],
        outline=color, width=2,
    )
    # Stamp text along arc - simplified as straight text
    try:
        font = _find_font(9)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((x - tw // 2, y - th // 2), text, fill=color, font=font)
    except Exception:
        draw.text((x - 15, y - 5), text, fill=color)


def _add_signature(draw: ImageDraw, x: float, y: float, width: float = 80):
    """Draw a simulated ink signature (wavy scribble)."""
    points: list[Point] = []
    cx, cy = x, y
    for i in range(int(width / 4)):
        cx += _rand(2, 5)
        cy += _rand(-4, 4)
        points.append((cx, cy))
    if len(points) > 1:
        draw.line(points, fill=(30, 30, 140), width=2)


def _add_fold_line(draw: ImageDraw, w: float, h: float):
    """Add a vertical fold line with slight shadow."""
    x = _rand(w * 0.25, w * 0.75)
    draw.line([(x, 0), (x, h)], fill=(180, 170, 150), width=1)
    draw.line([(x + 1, 0), (x + 1, h)], fill=(220, 210, 190), width=1)


def _rotate_scan(img: Image.Image, max_angle: float = 1.2) -> Image.Image:
    """Apply slight random rotation as seen in real scans."""
    angle = _rand(-max_angle, max_angle)
    if abs(angle) < 0.1:
        return img
    return img.rotate(angle, expand=False, fillcolor=(248, 245, 240), resample=Image.BICUBIC)


def _add_highlight(draw: ImageDraw, x: float, y: float, w: float, h: float):
    """Add a yellow highlighter mark over text."""
    draw.rectangle([x, y, x + w, y + h], fill=(255, 255, 0, 60))


def _add_hole_punch(draw: ImageDraw, x: float, y: float):
    """Add a hole-punch circle (dark edge, light center)."""
    r = 4
    draw.ellipse([x - r, y - r, x + r, y + r], outline=(100, 100, 100), fill=(220, 215, 200))
    draw.ellipse([x - r + 1, y - r + 1, x + r - 1, y + r - 1], fill=(248, 245, 240))

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_scanned_page(
    text_lines: list[str],
    *,
    page_width_pt: float = 595,
    page_height_pt: float = 842,
    dpi: int = 150,
    font_size: int = 10,
    margin: float = 50,
    line_spacing: float = 1.3,
    include_stamp: bool = False,
    include_signature: bool = False,
    include_highlight: bool = False,
    include_fold: bool = False,
    include_hole_punch: bool = False,
    rotation: float | None = None,
    noise_level: float | None = None,
    scan_quality: str = "normal",  # "draft", "normal", "high"
) -> bytes:
    """Generate a realistic scanned-document page image as PNG bytes.

    Args:
        text_lines: Lines of text to render on the page.
        page_width_pt: Page width in points (1/72 inch).
        page_height_pt: Page height in points.
        dpi: Output resolution.
        font_size: Font size in points.
        margin: Margin in points.
        line_spacing: Line spacing multiplier.
        include_stamp: Add a red circular stamp.
        include_signature: Add an ink signature.
        include_highlight: Add yellow highlighter marks.
        include_fold: Add a vertical fold line.
        include_hole_punch: Add hole punch artifacts.
        rotation: Manual rotation override (None = random).
        noise_level: Manual noise override.
        scan_quality: Affects blur, contrast, noise.

    Returns:
        PNG image bytes.
    """
    # Convert points to pixels at given DPI
    scale = dpi / 72.0
    pw = int(page_width_pt * scale)
    ph = int(page_height_pt * scale)

    # Paper background
    bg = _paper_color()
    img = Image.new("RGB", (pw, ph), bg)
    draw = ImageDraw.Draw(img, "RGBA")

    # Determine noise level from quality
    if noise_level is None:
        noise_level = {"draft": 0.05, "normal": 0.025, "high": 0.01}.get(scan_quality, 0.025)

    # Determine blur
    blur_radius = {"draft": 0.8, "normal": 0.3, "high": 0.0}.get(scan_quality, 0.3)

    # Render text
    try:
        font = _find_font(int(font_size * scale))
    except Exception:
        font = ImageFont.load_default()

    y = margin * scale
    x = margin * scale
    text_color = (25, 25, 25)

    for line in text_lines:
        if line.strip() == "":
            y += font_size * scale * 0.5
            continue
        try:
            draw.text((x, y), line, fill=text_color, font=font)
        except Exception:
            pass
        y += font_size * scale * line_spacing

    # Add scan artifacts
    _add_noise(draw, img, intensity=noise_level)
    _add_dust_speckles(draw, img, count=_randint(10, 50))
    img = _add_border_shadow(img)

    if include_stamp:
        sx = _rand(pw * 0.65, pw * 0.85)
        sy = _rand(ph * 0.08, ph * 0.2)
        _add_stamp(draw, sx, sy)

    if include_signature:
        sig_x = _rand(pw * 0.5, pw * 0.7)
        sig_y = _rand(ph * 0.8, ph * 0.9)
        _add_signature(draw, sig_x, sig_y)

    if include_highlight:
        for _ in range(_randint(1, 3)):
            hx = _rand(margin * scale, pw - margin * scale)
            hy = _rand(margin * scale, ph - margin * scale)
            hw = _rand(80, 200) * scale
            hh = font_size * scale * 1.2
            _add_highlight(draw, hx, hy, hw, hh)

    if include_fold:
        _add_fold_line(draw, pw, ph)

    if include_hole_punch:
        for hy in [ph * 0.1, ph * 0.5, ph * 0.9]:
            _add_hole_punch(draw, pw * 0.03, hy)

    # Apply blur for scan quality
    if blur_radius > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    # Apply rotation
    if rotation is None:
        img = _rotate_scan(img)
    elif abs(rotation) > 0.1:
        img = img.rotate(rotation, expand=False, fillcolor=bg, resample=Image.BICUBIC)

    # Convert to PNG bytes
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_certificate_page(
    cert_type: str = "Arbeitszeugnis",
    issuer: str = "Max-Planck-Institut für Quantenoptik",
    holder: str = "Dr. Jane Smith",
    date: str = "31.05.2020",
    body_text: list[str] | None = None,
    include_stamp: bool | None = None,
    include_signature: bool | None = None,
    **kwargs,
) -> bytes:
    """Generate a realistic scanned certificate page.

    Note: Does NOT set include_stamp/include_signature defaults so callers
    can control them via kwargs without duplication errors.
    """
    if body_text is None:
        body_text = [
            f"{cert_type}",
            "",
            f"{holder}",
            f"geboren am 15.03.1985,",
            f"war vom 01.06.2015 bis 31.05.2020",
            f"als Senior Researcher bei der",
            f"{issuer}",
            f"beschäftigt.",
            "",
            "Aufgabenbereich:",
            "- Leitung eines interdisziplinären Forschungsteams",
            "- Entwicklung und Umsetzung von Forschungsstrategien",
            "- Budgetplanung und -überwachung (bis zu 2 Mio. EUR p.a.)",
            "- Einwerbung von Drittmitteln",
            "- Vertretung des Instituts auf internationalen Konferenzen",
            "",
            "Frau Dr. Smith verfügt über herausragende fachliche",
            "Kompetenzen und ein hohes Maß an Eigeninitiative.",
            "",
            "München, den " + date,
            "Prof. Dr. Müller",
            "Direktor",
        ]

    # Forward include_stamp/include_signature if caller set them,
    # otherwise use certificate-appropriate defaults
    stamp = include_stamp if include_stamp is not None else True
    sig = include_signature if include_signature is not None else True

    return generate_scanned_page(
        body_text,
        include_stamp=stamp,
        include_signature=sig,
        **kwargs,
    )


def generate_cover_letter_page(
    applicant_name: str = "Dr. Jane Smith",
    **kwargs,
) -> bytes:
    """Generate a scanned cover letter page."""
    lines = [
        f"Bewerbung als Research Program Manager",
        "",
        "Sehr geehrte Damen und Herren,",
        "",
        "mit großem Interesse bewerbe ich mich auf die Position",
        "Research Program Manager im Rahmen der Stargate Initiative.",
        "Als promovierte Physikerin mit über zehn Jahren Erfahrung",
        "im Forschungsmanagement bringe ich die geforderten",
        "Kompetenzen mit.",
        "",
        "In meiner bisherigen Tätigkeit als Senior Researcher",
        "am Max-Planck-Institut für Quantenoptik leite ich ein",
        "interdisziplinäres Team von 12 Wissenschaftlern.",
        "",
        "Mit freundlichen Grüßen,",
        applicant_name,
    ]
    return generate_scanned_page(lines, include_signature=True, **kwargs)


def generate_passport_photo(
    gender: str = "female",
    width_pt: float = 120,
    height_pt: float = 150,
    dpi: int = 100,
) -> bytes:
    """Generate a fake passport-style photo as PNG bytes.

    Creates a programmatic headshot-like image with skin tone,
    hair, shoulders, and a plain background — fully synthetic,
    no real person.
    """
    scale = dpi / 72.0
    pw = int(width_pt * scale)
    ph = int(height_pt * scale)

    bg_color = (220, 225, 235)  # light blue/gray background (like German passport photo)

    img = Image.new("RGB", (pw, ph), bg_color)
    draw = ImageDraw.Draw(img)

    cx, cy = pw // 2, int(ph * 0.45)

    # Skin tone with variation
    skin = (
        _randint(200, 240),
        _randint(170, 210),
        _randint(150, 190),
    )
    skin_shadow = (
        max(0, skin[0] - 30),
        max(0, skin[1] - 25),
        max(0, skin[2] - 20),
    )

    # Hair color
    hair_colors = [(40, 35, 30), (60, 45, 35), (30, 25, 20), (80, 55, 40), (180, 140, 90)]
    hair_color = hair_colors[_randint(0, len(hair_colors) - 1)]

    # Shoulders / torso
    shoulder_w = int(pw * 0.75)
    shoulder_y = int(ph * 0.72)
    draw.ellipse(
        [cx - shoulder_w // 2, shoulder_y - int(ph * 0.15),
         cx + shoulder_w // 2, ph + 10],
        fill=(60, 55, 60),  # dark clothing
    )
    # Collar / shirt
    shirt_color = (240, 240, 245) if gender == "female" else (235, 235, 240)
    draw.ellipse(
        [cx - int(pw * 0.25), shoulder_y - int(ph * 0.05),
         cx + int(pw * 0.25), ph + 10],
        fill=shirt_color,
    )

    # Neck
    neck_w = int(pw * 0.12)
    neck_h = int(ph * 0.08)
    draw.ellipse(
        [cx - neck_w // 2, shoulder_y - neck_h,
         cx + neck_w // 2, shoulder_y],
        fill=skin,
    )

    # Head oval
    head_w = int(pw * 0.42)
    head_h = int(ph * 0.40)
    head_y = int(ph * 0.22)
    draw.ellipse(
        [cx - head_w // 2, head_y,
         cx + head_w // 2, head_y + head_h],
        fill=skin,
    )

    # Hair shape (above head, different style by gender)
    if gender == "female":
        # Longer hair on sides
        draw.ellipse(
            [cx - int(head_w * 0.55), head_y - int(head_h * 0.35),
             cx + int(head_w * 0.55), head_y + int(head_h * 0.5)],
            fill=hair_color,
        )
        # Hair on top
        draw.ellipse(
            [cx - int(head_w * 0.45), head_y - int(head_h * 0.4),
             cx + int(head_w * 0.45), head_y + int(head_h * 0.1)],
            fill=hair_color,
        )
    else:
        # Short hair
        draw.ellipse(
            [cx - int(head_w * 0.48), head_y - int(head_h * 0.3),
             cx + int(head_w * 0.48), head_y + int(head_h * 0.05)],
            fill=hair_color,
        )
        # Side hair
        draw.ellipse(
            [cx - int(head_w * 0.52), head_y - int(head_h * 0.1),
             cx - int(head_w * 0.38), head_y + int(head_h * 0.2)],
            fill=hair_color,
        )
        draw.ellipse(
            [cx + int(head_w * 0.38), head_y - int(head_h * 0.1),
             cx + int(head_w * 0.52), head_y + int(head_h * 0.2)],
            fill=hair_color,
        )

    # Re-draw face on top so skin covers hair overlap
    draw.ellipse(
        [cx - head_w // 2, head_y,
         cx + head_w // 2, head_y + head_h],
        fill=skin,
    )

    # Eyes
    eye_y = head_y + int(head_h * 0.42)
    eye_spacing = int(head_w * 0.22)
    eye_color = (60, 80, 110) if _randint(0, 1) else (90, 75, 55)
    for side in [-1, 1]:
        ex = cx + side * eye_spacing
        # White
        draw.ellipse([ex - 6, eye_y - 4, ex + 6, eye_y + 6], fill=(245, 245, 250))
        # Iris
        draw.ellipse([ex - 4, eye_y - 2, ex + 4, eye_y + 4], fill=eye_color)
        # Pupil
        draw.ellipse([ex - 2, eye_y - 1, ex + 2, eye_y + 2], fill=(10, 10, 10))
        # Eyebrow
        brow_y = eye_y - 8
        draw.arc([ex - 8, brow_y - 3, ex + 8, brow_y + 5], 180, 0, fill=hair_color, width=2)

    # Nose
    nose_y = eye_y + int(head_h * 0.15)
    draw.line([cx, eye_y + 4, cx, nose_y + 4], fill=skin_shadow, width=2)
    # Nostrils
    for side in [-1, 1]:
        draw.ellipse([cx + side * 4 - 1, nose_y + 3, cx + side * 4 + 2, nose_y + 6], fill=skin_shadow)

    # Mouth
    mouth_y = nose_y + int(head_h * 0.15)
    mouth_w = int(head_w * 0.2)
    draw.arc([cx - mouth_w, mouth_y - 3, cx + mouth_w, mouth_y + 5], 0, 180, fill=(160, 100, 100), width=2)

    # Ears
    ear_w = int(head_w * 0.08)
    for side in [-1, 1]:
        draw.ellipse(
            [cx + side * (head_w // 2) - ear_w // 2, head_y + int(head_h * 0.3),
             cx + side * (head_w // 2) + ear_w // 2, head_y + int(head_h * 0.52)],
            fill=skin,
        )

    # Add scan artifacts (noise, border shadow)
    _add_noise(draw, img, intensity=0.01)
    img = _add_border_shadow(img)

    # Slight rotation
    img = _rotate_scan(img, max_angle=0.8)

    # Convert to PNG bytes
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_reference_letter_page(
    referee: str = "Prof. Dr. Rossi",
    **kwargs,
) -> bytes:
    """Generate a scanned reference letter page."""
    lines = [
        "LETTER OF REFERENCE",
        "",
        "To Whom It May Concern,",
        "",
        "I am pleased to recommend Dr. Jane Smith for the",
        "position of Research Program Manager.",
        "",
        "Dr. Smith worked under my supervision from 2012 to 2016.",
        "During this time she demonstrated exceptional analytical",
        "skills and the ability to coordinate complex international",
        "collaborations.",
        "",
        "I give her my highest recommendation.",
        "",
        "Prof. Dr. Giovanni Rossi",
        "CERN, Geneva",
    ]
    return generate_scanned_page(lines, include_signature=True, **kwargs)
