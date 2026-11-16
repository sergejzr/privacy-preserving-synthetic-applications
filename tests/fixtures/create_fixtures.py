"""Create synthetic fixture PDFs for testing the structure analyzer.

These are entirely fictional and contain no real applicant data.
Patterns mirror the real reference corpus structure:
- Every applicant has Ausdruck.pdf + Bewerbung.pdf
- Bewerbung.pdf is image-heavy (scanned certs) with mixed page sizes
- Ausdruck.pdf is a 2-page cover sheet with text + embedded images
- Scanned pages use programmatically generated realistic-looking images
"""

from __future__ import annotations

import io
import os
import random
from pathlib import Path

try:
    import fitz
except ImportError:
    fitz = None

from synthetic_apps.scanned_image import (
    generate_scanned_page,
    generate_certificate_page,
    generate_cover_letter_page,
    seed_rng,
)

FIXTURE_DIR = Path(__file__).parent
SEED = 20261008
rng = random.Random(SEED)


def _insert_scanned_image(
    page,
    image_bytes: bytes,
    x0: float = 0,
    y0: float = 0,
    x1: float | None = None,
    y1: float | None = None,
):
    """Insert a scanned document image into a PDF page."""
    if x1 is None:
        x1 = page.rect.width
    if y1 is None:
        y1 = page.rect.height
    try:
        page.insert_image(fitz.Rect(x0, y0, x1, y1), stream=image_bytes)
    except Exception:
        pass


def _add_text_block(
    page, x0, y0, x1, y1, text: str, fontsize: int = 11,
    fontname: str = "helv", color=None,
):
    """Draw a text block on the page."""
    if color is None:
        color = (0, 0, 0)
    try:
        rect = fitz.Rect(x0, y0, x1, y1)
        light_gray = (0.97, 0.97, 0.97)
        page.draw_rect(rect, color=None, fill=light_gray, width=0)
        page.insert_text(
            fitz.Point(x0 + 3, y0 + 14),
            text,
            fontsize=fontsize,
            fontname=fontname,
            color=color,
        )
    except Exception:
        pass


def _random_page_size():
    """Return a slightly varied A4 size."""
    return 595 + rng.randint(-8, 8), 842 + rng.randint(-8, 8)


# ---------------------------------------------------------------------------
# Ausdruck.pdf — 2-page cover sheet
# ---------------------------------------------------------------------------

def create_ausdruck(path: Path, applicant_name: str, applicant_id: str):
    """Create Ausdruck.pdf - a 2-page cover letter/overview sheet."""
    doc = fitz.open()

    # Page 1: Cover overview with text + embedded image
    page = doc.new_page(width=595, height=842)
    y = 40

    _add_text_block(page, 40, y, 555, y + 45,
                    f"Bewerbungsübersicht — {applicant_name}", fontsize=16)
    y += 65
    _add_text_block(page, 40, y, 555, y + 30,
                    "Bewerbung als Research Program Manager (m/f/d) — Stargate Initiative",
                    fontsize=12)
    y += 45
    _add_text_block(page, 40, y, 555, y + 25,
                    f"Bewerber-ID: {applicant_id}", fontsize=10)
    y += 35
    _add_text_block(page, 40, y, 555, y + 20,
                    f"Name: {applicant_name}", fontsize=10)
    y += 28
    _add_text_block(page, 40, y, 555, y + 20,
                    "Dokumente: Bewerbungsschreiben, Lebenslauf, Zeugnisse, Zertifikate",
                    fontsize=10)
    y += 35

    # Table-like overview
    _add_text_block(page, 40, y, 555, y + 25,
                    "Dokument                              Seiten   Bemerkung", fontsize=9)
    y += 28
    for doc_name, pages, note in [
        ("Anschreiben", "1", "—"),
        ("Lebenslauf", "2-3", "tabellarisch"),
        ("Motivationsschreiben", "1", "zur Position"),
        ("Zeugnisse", "5", "HQ-scan"),
        ("Zertifikate", "4", "Farbe"),
        ("Referenzen", "1", "Prof. Dr. Müller"),
    ]:
        _add_text_block(page, 40, y, 555, y + 20,
                        f"{doc_name:40s} {pages:15s} {note}", fontsize=8)
        y += 22

    y += 20
    _add_text_block(page, 40, y, 555, y + 30,
                    "Die vollständigen Bewerbungsunterlagen befinden sich in der "
                    "beigefügten PDF.\nBewertung: vollständig, geprüft am "
                    f"{rng.randint(1,28):02d}.{rng.randint(1,12):02d}.2024",
                    fontsize=9)

    # Insert a scanned photo image
    photo_img = generate_scanned_page(
        ["Passbild — " + applicant_name],
        page_width_pt=100, page_height_pt=130, dpi=100, font_size=8,
        include_hole_punch=True, scan_quality="normal",
    )
    _insert_scanned_image(page, photo_img, x0=430, y0=y - 60, x1=530, y1=y + 10)

    _add_page_variation(page)

    # Page 2: continuation with summary + signature image
    page = doc.new_page(width=595, height=842)
    _add_text_block(page, 40, 40, 555, 70,
                    "Bewerbungsübersicht (Fortsetzung)", fontsize=11)
    _add_text_block(page, 40, 80, 555, 100, "Qualifikationsprofil", fontsize=10)
    _add_text_block(page, 40, 110, 555, 200,
                    "Forschungserfahrung: 12 Jahre\n"
                    "Projektleitung: 8 Jahre\n"
                    "Budgetverantwortung: bis 3 Mio. EUR\n"
                    "Internationale Kooperationen: EU, USA, Japan\n"
                    "Sprachen: Deutsch (M), Englisch (C1), Französisch (B1)", fontsize=9)

    # Signature image
    sig_img = generate_scanned_page(
        ["Unterschrift", applicant_name],
        page_width_pt=120, page_height_pt=60, dpi=100, font_size=8,
        include_signature=True, scan_quality="draft",
    )
    _insert_scanned_image(page, sig_img, x0=440, y0=110, x1=540, y1=170)

    _add_page_variation(page)

    doc.save(str(path))
    doc.close()


# ---------------------------------------------------------------------------
# Scanned certificate pages for Bewerbung.pdf
# ---------------------------------------------------------------------------

def _generate_cert_variants(applicant_name: str) -> list[tuple[str, bytes]]:
    """Generate a set of scanned certificate images with variation."""
    certs = []

    cert_specs = [
        ("Promotionsurkunde", "Dr. rer. nat.", "Universität Heidelberg",
         "15.03.2014",
         ["Promotionsurkunde", "", "Der Dekan der Fakultät für Physik",
          "der Universität Heidelberg", "",
          "verleiht", "Frau " + applicant_name, "", "den Doktorgrad",
          "Dr. rer. nat."]),
        ("Masterzeugnis", "M.Sc. Physics", "LMU München", "30.09.2009",
         ["Masterzeugnis", "", "Frau " + applicant_name, "",
          "hat am 30.09.2009 die Masterprüfung", "im Studiengang Physik",
          "mit dem Gesamturteil", "SEHR GUT (1,2)", "", "bestanden."]),
        ("Arbeitszeugnis 1", "", "Max-Planck-Institut für Quantenoptik",
         "31.05.2020",
         ["Arbeitszeugnis", "", "Frau Dr. " + applicant_name, "",
          "war vom 01.06.2015 bis 31.05.2020",
          "als Senior Researcher", "am Max-Planck-Institut für Quantenoptik",
          "beschäftigt.", "", "Sie führte ihre Aufgaben stets",
          "zu unserer vollsten Zufriedenheit aus."]),
        ("Arbeitszeugnis 2", "", "Helmholtz-Zentrum Berlin",
         "31.12.2018",
         ["Arbeitszeugnis", "", "Frau Dr. " + applicant_name, "",
          "war vom 15.06.2014 bis 31.12.2018",
          "als wissenschaftliche Mitarbeiterin",
          "am Helmholtz-Zentrum Berlin",
          "beschäftigt.", "", "Wir danken für die gute Zusammenarbeit."]),
        ("Zertifikat Projektmanagement", "IPMA Level C",
         "IPMA Deutschland", "12.03.2022",
         ["Zertifikat", "", "IPMA Level C", "",
          "Frau " + applicant_name, "",
          "hat am 12.03.2022 die Prüfung",
          "zum Certified Project Manager",
          "erfolgreich abgelegt."]),
        ("Zertifikat Leadership", "Leadership in Research",
         "HSG St. Gallen", "18.09.2023",
         ["Teilnahmebescheinigung", "", "Leadership in Research",
          "", "Frau Dr. " + applicant_name, "",
          "hat am Programm", "Leadership in Research Organizations",
          "vom 01.09.2023 bis 15.09.2023", "teilgenommen."]),
        ("Sprachzertifikat", "English C1", "Cambridge English",
         "05.06.2021",
         ["Cambridge English Certificate", "",
          "Frau " + applicant_name, "",
          "hat die Prüfung", "C1 Advanced (CAE)",
          "mit der Gesamtbewertung", "C1", "", "bestanden."]),
        ("Fortbildungsnachweis", "Drittmittelmanagement",
         "DFG", "22.04.2023",
         ["Fortbildungsnachweis", "", "Drittmittelmanagement",
          "", "Frau Dr. " + applicant_name, "",
          "hat am Workshop", "Drittmittelakquise und Fördermittelmanagement",
          "der Deutschen Forschungsgemeinschaft",
          "am 22.04.2023 teilgenommen."]),
    ]

    for cert_type, degree, issuer, date, body_lines in cert_specs:
        try:
            img_bytes = generate_certificate_page(
                cert_type=cert_type,
                issuer=issuer,
                holder=applicant_name,
                date=date,
                body_text=body_lines,
                dpi=100,
                scan_quality=rng.choice(["draft", "normal", "normal", "high"]),
                include_stamp=rng.random() < 0.7,
                include_signature=rng.random() < 0.6,
                include_fold=rng.random() < 0.15,
                include_hole_punch=rng.random() < 0.1,
                noise_level=rng.uniform(0.01, 0.04),
            )
            certs.append((cert_type, img_bytes))
        except Exception as e:
            print(f"    Warning: failed to generate '{cert_type}' image: {e}")

    return certs


# ---------------------------------------------------------------------------
# Bewerbung.pdf — multi-page application with text + scanned images
# ---------------------------------------------------------------------------

def create_bewerbung(path: Path, applicant_name: str, applicant_id: str):
    """Create Bewerbung.pdf - multi-page application with mixed content.

    Order: text pages (cover letter, CV) first, then scanned certificates.
    """
    doc = fitz.open()

    # --- Text pages ---
    _add_cover_letter_page(doc, applicant_name)
    _add_cv_pages(doc, applicant_name)
    _add_research_page(doc, applicant_name)

    # --- Scanned certificate pages ---
    num_cert_pages = rng.randint(8, 14)
    cert_variants = _generate_cert_variants(applicant_name)

    for i in range(num_cert_pages):
        w, h = _random_page_size()
        page = doc.new_page(width=w, height=h)

        # Pick a certificate image, cycling through variants
        cert_type, img_bytes = cert_variants[i % len(cert_variants)]
        _insert_scanned_image(page, img_bytes, x0=0, y0=0, x1=w, y1=h)

    doc.save(str(path))
    doc.close()


def _add_cover_letter_page(doc, applicant_name: str):
    """Add a cover letter text page."""
    page = doc.new_page(width=595, height=842)
    _add_text_block(page, 50, 50, 545, 100,
                    "Bewerbung als Research Program Manager", fontsize=16)
    _add_text_block(page, 50, 120, 545, 160,
                    "Sehr geehrte Damen und Herren,", fontsize=11)
    _add_text_block(page, 50, 180, 545, 320,
                    "mit großem Interesse bewerbe ich mich auf die Position "
                    "Research Program Manager im Rahmen der Stargate Initiative. "
                    "Als promovierte Physikerin mit über zehn Jahren Erfahrung "
                    "im Forschungsmanagement bringe ich die geforderten Kompetenzen "
                    "mit.", fontsize=10, fontname="helv")
    _add_text_block(page, 50, 340, 545, 480,
                    "In meiner aktuellen Position als Senior Researcher am "
                    "Max-Planck-Institut für Quantenoptik leite ich ein Team "
                    "von 12 Wissenschaftlerinnen und Wissenschaftlern. Ich "
                    "verantworte ein Jahresbudget von über 2 Mio. EUR und "
                    "konnte in den letzten fünf Jahren Drittmittel in Höhe "
                    "von 5 Mio. EUR einwerben.", fontsize=10, fontname="helv")
    _add_text_block(page, 50, 500, 545, 640,
                    "Die Möglichkeit, an einer so visionären Initiative wie "
                    "dem Stargate-Projekt mitzuwirken, begeistert mich sehr. "
                    "Ich bin überzeugt, dass meine Erfahrung in der Koordination "
                    "internationaler Forschungsprojekte und meine Kenntnisse "
                    "im Risikomanagement sicherheitskritischer Infrastrukturen "
                    "einen wertvollen Beitrag leisten können.",
                    fontsize=10, fontname="helv")
    _add_text_block(page, 50, 660, 545, 720,
                    "Mit freundlichen Grüßen\n" + applicant_name,
                    fontsize=10, fontname="helv")
    _add_page_variation(page)


def _add_cv_pages(doc, applicant_name: str):
    """Add CV text pages."""
    # CV page 1
    w2, h2 = 595 + rng.randint(-3, 3), 842 + rng.randint(-3, 3)
    page = doc.new_page(width=w2, height=h2)
    _add_text_block(page, 40, 40, 555, 85,
                    "Lebenslauf — " + applicant_name, fontsize=16, fontname="helv")
    _add_text_block(page, 40, 105, 555, 140,
                    "Persönliche Daten", fontsize=12, fontname="helv")
    _add_text_block(page, 40, 150, 300, 220,
                    "Geburtsdatum: 15.03.1985\n"
                    "Nationalität: Deutsch\n"
                    "E-Mail: " + applicant_name.lower().replace(" ", ".").replace("__", ".") + "@example.com\n"
                    "Telefon: +49 123 456789", fontsize=9, fontname="helv")
    _add_text_block(page, 40, 240, 555, 280,
                    "Berufserfahrung", fontsize=12, fontname="helv")
    _add_text_block(page, 40, 290, 555, 410,
                    "01/2019 – heute: Senior Researcher, Max-Planck-Institut\n"
                    "  Leitung eines interdisziplinären Forschungsteams (12 MA)\n"
                    "  Budgetverantwortung: 2 Mio. EUR p.a.\n"
                    "  Drittmittelakquise: 5 Mio. EUR\n"
                    "  Risikomanagement für sicherheitskritische Experimente",
                    fontsize=9, fontname="helv")
    _add_text_block(page, 40, 425, 555, 520,
                    "06/2014 – 12/2018: Wissenschaftlicher Mitarbeiter,\n"
                    "  Helmholtz-Zentrum Berlin\n"
                    "  Koordination von 20 Partnern aus 8 Ländern\n"
                    "  Projektmanagement für EU-Forschungsprojekte",
                    fontsize=9, fontname="helv")
    _add_text_block(page, 40, 540, 555, 630,
                    "Bildungsweg", fontsize=12, fontname="helv")
    _add_text_block(page, 40, 640, 555, 730,
                    "2009–2014: Promotion in Physik, Universität Heidelberg\n"
                    "  Thema: Quanteninformationsverarbeitung\n"
                    "2004–2009: Studium der Physik, LMU München\n"
                    "  Abschluss: M.Sc. (1,0)", fontsize=9, fontname="helv")
    _add_page_variation(page)

    # CV page 2
    w3, h3 = 595 + rng.randint(-5, 5), 842 + rng.randint(-5, 5)
    page = doc.new_page(width=w3, height=h3)
    _add_text_block(page, 40, 40, 555, 80,
                    "Qualifikationen und Kompetenzen", fontsize=14, fontname="helv")
    _add_text_block(page, 40, 100, 555, 200,
                    "Forschungskompetenzen:\n"
                    "  \u2022 Forschungsmanagement und -koordination\n"
                    "  \u2022 Interdisziplinäre Projektleitung\n"
                    "  \u2022 Wissenschaftliche Governance\n"
                    "  \u2022 Ethische Bewertung von Forschungsvorhaben\n"
                    "  \u2022 Publikationstätigkeit (25 peer-reviewed papers)",
                    fontsize=9, fontname="helv")
    _add_text_block(page, 40, 215, 555, 310,
                    "Managementkompetenzen:\n"
                    "  \u2022 Budgetplanung und -überwachung (bis 3 Mio. EUR)\n"
                    "  \u2022 Drittmittel- und Fördermittelmanagement\n"
                    "  \u2022 Personalverantwortung (bis 15 MA)\n"
                    "  \u2022 Risikomanagement und Compliance",
                    fontsize=9, fontname="helv")
    _add_text_block(page, 40, 325, 555, 400,
                    "Sprachen:\n"
                    "  \u2022 Deutsch: Muttersprache\n"
                    "  \u2022 Englisch: Verhandlungssicher (C1)\n"
                    "  \u2022 Französisch: Grundkenntnisse (A2)",
                    fontsize=9, fontname="helv")
    _add_text_block(page, 40, 420, 555, 480,
                    "Weiterbildungen:\n"
                    "  \u2022 2023: Leadership in Research Organizations (HSG)\n"
                    "  \u2022 2022: Project Management Professional (PMP)\n"
                    "  \u2022 2021: IPMA Level C (Projektmanagement)",
                    fontsize=9, fontname="helv")
    _add_text_block(page, 40, 500, 555, 580,
                    "Publikationen (Auswahl):\n"
                    "  \u2022 Smith, J. et al. (2023): Interdisciplinary Research "
                    "Management, Journal of Research Administration\n"
                    "  \u2022 Smith, J. et al. (2021): Large-Scale Project "
                    "Coordination, Project Management Journal\n"
                    "  \u2022 Smith, J. et al. (2019): Data Analysis Methods, "
                    "Nature Physics",
                    fontsize=8, fontname="helv")
    _add_page_variation(page)


def _add_research_page(doc, applicant_name: str):
    """Add a mixed text+image research projects page."""
    w4, h4 = 595 + rng.randint(-4, 4), 842 + rng.randint(-2, 2)
    page = doc.new_page(width=w4, height=h4)
    _add_text_block(page, 50, 40, 545, 80,
                    "Forschungsprojekte", fontsize=12, fontname="helv")
    _add_text_block(page, 50, 95, 545, 180,
                    "EU-Horizont 2020: QUANTUM-NET (2020-2023)\n"
                    "Koordinator eines Konsortiums aus 12 europäischen Partnern.\n"
                    "Gesamtbudget: 8 Mio. EUR.",
                    fontsize=9, fontname="helv")

    # Insert small figure image
    fig_img = generate_scanned_page(
        ["Fig 1: Quanten-Netzwerk Topologie"],
        page_width_pt=120, page_height_pt=80, dpi=100, font_size=7,
        scan_quality="high",
    )
    _insert_scanned_image(page, fig_img, x0=400, y0=95, x1=520, y1=170)

    _add_text_block(page, 50, 195, 545, 280,
                    "DFG-Schwerpunktprogramm: SPP 1929 (2018-2022)\n"
                    "Teilprojektleiter. Fördervolumen: 1,2 Mio. EUR.",
                    fontsize=9, fontname="helv")
    _add_page_variation(page)


def _add_page_variation(page):
    """Add small realistic variations."""
    try:
        if rng.random() < 0.12:
            sx = rng.randint(400, 520)
            sy = rng.randint(50, 150)
            page.draw_circle(
                fitz.Point(sx, sy), 22,
                color=(0.8, 0.2, 0.2), width=1.5, fill=(0.95, 0.8, 0.8),
            )
            page.insert_text(
                fitz.Point(sx - 12, sy + 4),
                "GEPRÜFT",
                fontsize=6, color=(0.6, 0.1, 0.1),
            )
        if rng.random() < 0.06:
            cx = rng.randint(280, 310)
            page.draw_line(
                fitz.Point(cx, 8), fitz.Point(cx, 35),
                color=(0.6, 0.6, 0.6), width=2,
            )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    seed_rng(SEED)
    pdf_dir = FIXTURE_DIR / "pdfs"
    pdf_dir.mkdir(exist_ok=True)

    applicants = [
        ("SG001", "Dr. Jane Smith"),
        ("SG002", "Dr. John Doe"),
        ("SG003", "Dr. Maria Schmidt"),
        ("SG004", "Max Mustermann"),
        ("SG005", "Anna Weber"),
    ]

    for applicant_id, applicant_name in applicants:
        applicant_dir = pdf_dir / applicant_id
        applicant_dir.mkdir(exist_ok=True)

        ausdruck_path = applicant_dir / "Ausdruck.pdf"
        if not ausdruck_path.exists():
            create_ausdruck(ausdruck_path, applicant_name, applicant_id)
            print(f"  Created: {applicant_id}/Ausdruck.pdf")

        bewerbung_path = applicant_dir / "Bewerbung.pdf"
        if not bewerbung_path.exists():
            create_bewerbung(bewerbung_path, applicant_name, applicant_id)
            print(f"  Created: {applicant_id}/Bewerbung.pdf")

    print(f"\nFixture PDFs in: {pdf_dir}")
    print(f"Total applicants: {len(applicants)}")
    print("Each has Ausdruck.pdf (2p text+scanned image) + "
          "Bewerbung.pdf (text pages + scanned certificates)")


if __name__ == "__main__":
    if fitz is None:
        print("PyMuPDF not installed. Cannot create fixture PDFs.")
    else:
        main()
