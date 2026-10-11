"""PDF rendering using Jinja2 HTML templates and WeasyPrint.

Generates realistic PDFs exactly matching the real structure:
  - Ausdruck.pdf  (2-page cover sheet)
  - Bewerbung.pdf (merged — Cover Letter + CV + Certificates + Reference Letters)

Sub-documents within Bewerbung.pdf are rendered sequentially and merged.
"""

from __future__ import annotations

import io
import html
import base64
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from .scanned_image import generate_passport_photo, generate_scanned_page

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None


class PDFRenderer:
    """Renders applicant documents as PDFs using HTML templates + WeasyPrint."""

    def __init__(self, template_dir: str | Path = "templates"):
        self.template_dir = Path(template_dir)
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=False,
        )

    def render_merged_dossier(
        self,
        dossier_plan: Any,
        profile: dict[str, Any],
        doc_texts: dict[str, Any] | None = None,
    ) -> bytes:
        """Render a complete dossier applicant as a single merged PDF.

        Produces exactly the sub-documents from the plan, merged into one PDF.
        Returns the PDF bytes for Bewerbung.pdf.
        """
        plan = dossier_plan
        if not hasattr(plan, 'documents'):
            plan_dict = plan
            from .modeling.output_plan import DossierOutputPlan
            plan = DossierOutputPlan.from_dict(plan_dict)

        # Collect all sub-document PDFs in order
        subdoc_pdfs: list[bytes] = []
        cert_index = 0
        for doc_plan in plan.documents:
            if doc_plan.doc_type == "bewerbung":
                for subdoc in doc_plan.subdocuments:
                    try:
                        sd_type = subdoc.subdoc_type if hasattr(subdoc, 'subdoc_type') else subdoc.get("subdoc_type", "cv")
                        if sd_type in ("certificate",):
                            pdf = self._render_subdoc(subdoc, profile, doc_texts, cert_index=cert_index,
                                                      variant=cert_index)
                            cert_index += 1
                        else:
                            pdf = self._render_subdoc(
                                subdoc, profile, doc_texts,
                                variant=(getattr(subdoc, "order", 0)),
                            )
                        subdoc_pdfs.append(pdf)
                    except Exception as e:
                        print(f"      Warning: subdoc {subdoc.subdoc_type} failed: {e}")
            elif doc_plan.doc_type == "ausdruck":
                # Ausdruck is rendered separately
                pass

        # Merge all sub-documents into one PDF
        if not subdoc_pdfs:
            subdoc_pdfs.append(self._render_fallback(profile))

        merged = self._merge_pdf_list(subdoc_pdfs)
        package_plan = next(
            (d for d in plan.documents if d.doc_type == "bewerbung"), None
        )
        if package_plan is not None:
            merged = self._fit_pdf_to_target(
                merged, package_plan.page_target, "Bewerbung / Anlagen", profile
            )
            # Use scan indices and mode from the structural plan
            scan_indices = getattr(package_plan, 'scan_indices', None) or []
            scan_mode = getattr(package_plan, 'scan_mode', 'full_raster')
            if scan_indices:
                merged = self._apply_scan(merged, scan_indices, scan_mode)
        return merged

    def render_ausdruck(
        self,
        dossier_plan: Any,
        profile: dict[str, Any],
    ) -> bytes:
        """Render Ausdruck.pdf — the cover sheet with personal data and document list."""
        plan = dossier_plan
        if not hasattr(plan, 'to_dict'):
            from .modeling.output_plan import DossierOutputPlan
            plan = DossierOutputPlan.from_dict(plan)

        # Get subdoc list for the document table
        subdoc_list = []
        for doc_plan in plan.documents:
            if doc_plan.doc_type == "bewerbung":
                subdoc_list = [
                    {"type": s.subdoc_type, "pages": s.page_target}
                    for s in doc_plan.subdocuments
                ]

        html = self._ausdruck_html(profile, subdoc_list)
        target = next(
            (d.page_target for d in plan.documents if d.doc_type == "ausdruck"), 2
        )
        return self._fit_pdf_to_target(
            self._html_to_pdf(html, apply_scan=False), target, "Ausdruck", profile
        )

    def _render_subdoc(
        self,
        subdoc: Any,
        profile: dict[str, Any],
        doc_texts: dict[str, Any] | None = None,
        cert_index: int = 0,
        variant: int = 0,
    ) -> bytes:
        """Render a single sub-document as PDF bytes — no padding, natural length."""
        sd_type = subdoc.subdoc_type if hasattr(subdoc, 'subdoc_type') else subdoc.get("subdoc_type", "cv")
        template = subdoc.template if hasattr(subdoc, 'template') else subdoc.get("template", "cv_standard")
        target = subdoc.page_target if hasattr(subdoc, "page_target") else subdoc.get("page_target", 1)

        # Unknown/source-section pages are real annex pages in the learned
        # package count. Render each page as a distinct, content-bearing
        # profile section instead of padding one sparse page repeatedly.
        if sd_type in ("personal", "cv_section", "unknown") and int(target) > 1:
            pages = [
                self._html_to_pdf(
                    self._section_html(profile, sd_type, variant=variant + page_no),
                    apply_scan=False,
                )
                for page_no in range(int(target))
            ]
            return self._merge_pdf_list(pages)

        if sd_type == "cover_letter" and doc_texts:
            body = doc_texts.get("cover_letter_body", "Cover letter text.")
            html = self._cover_letter_html(
                profile, body,
                title=doc_texts.get("position_title"),
                organization=doc_texts.get("organization"),
            )
        elif sd_type in ("certificate",) and doc_texts:
            certs = doc_texts.get("certificates", [])
            if certs:
                cert = certs[cert_index % len(certs)]
                html = self._certificate_html(profile, cert, cert_index=cert_index)
            else:
                html = self._section_html(profile, "certificate", variant=cert_index)
        elif sd_type in ("reference_letter",) and doc_texts:
            ref_text = doc_texts.get("reference_letter", "")
            referee = doc_texts.get("referee", {})
            html = self._reference_letter_html(profile, ref_text, referee)
        elif sd_type in ("personal", "cv_section", "unknown"):
            html = self._section_html(profile, sd_type, variant=variant)
        elif sd_type == "cv":
            templ = getattr(subdoc, 'template', None) or 'cv_standard'
            html = self._cv_two_column_html(profile) if templ == 'cv_two_column' else self._cv_html(profile)
        else:
            html = self._section_html(profile, sd_type, variant=variant)

        rendered = self._html_to_pdf(html, apply_scan=False)
        if sd_type in ("cover_letter", "reference_letter") and int(target) > 1:
            existing_pages = len(fitz.open(stream=rendered, filetype="pdf")) if fitz is not None else 1
            if existing_pages < int(target):
                continuation = [rendered]
                for page_no in range(existing_pages, int(target)):
                    continuation.append(self._html_to_pdf(
                        self._section_html(
                            profile, "cv_section", variant=variant + page_no + 20,
                        ),
                        apply_scan=False,
                    ))
                rendered = self._merge_pdf_list(continuation)
        return self._fit_pdf_to_target(rendered, target, sd_type, profile)

    def _ausdruck_html(self, profile: dict[str, Any], subdoc_list: list[dict]) -> str:
        """Generate HTML for Ausdruck.pdf cover sheet."""
        template = self.env.get_template("ausdruck.html")
        subdocs_html = "\n".join(
            f"<tr><td>{s['type'].replace('_', ' ').title()}</td><td>{s['pages']}</td><td>—</td></tr>"
            for s in subdoc_list
        )
        return template.render(
            name=profile.get("fictional_name", ""),
            email=profile.get("fictional_email", ""),
            phone=profile.get("fictional_phone", ""),
            address=profile.get("fictional_address", ""),
            subdocs_table=subdocs_html,
        )

    def _cover_letter_html(
        self,
        profile: dict[str, Any],
        body_text: str,
        title: str | None = None,
        organization: str | None = None,
    ) -> str:
        template = self.env.get_template("cover_letter.html")
        return template.render(
            name=profile.get("fictional_name", ""),
            email=profile.get("fictional_email", ""),
            phone=profile.get("fictional_phone", ""),
            address=profile.get("fictional_address", ""),
            body_text=body_text.replace("\n", "</p><p>"),
            position_title=title or "Research Program Manager (m/f/d)",
            organization=organization or "Interplanetary Research Directorate",
        )

    def _cv_two_column_html(self, profile: dict[str, Any]) -> str:
        template = self.env.get_template("cv_two_column.html")
        return template.render(
            name=profile.get("fictional_name", ""),
            email=profile.get("fictional_email", ""),
            phone=profile.get("fictional_phone", ""),
            address=profile.get("fictional_address", ""),
            education=profile.get("education", []),
            employment_history=profile.get("employment_history", []),
            research_projects=profile.get("research_projects", []),
            skills=profile.get("skills", []),
            languages=profile.get("languages", []),
            certifications=profile.get("certifications", []),
            photo_html=self._photo_html(profile),
        )

    def _cv_html(self, profile: dict[str, Any]) -> str:
        template = self.env.get_template("cv_standard.html")
        return template.render(
            name=profile.get("fictional_name", ""),
            email=profile.get("fictional_email", ""),
            phone=profile.get("fictional_phone", ""),
            address=profile.get("fictional_address", ""),
            education=profile.get("education", []),
            employment_history=profile.get("employment_history", []),
            research_projects=profile.get("research_projects", []),
            skills=profile.get("skills", []),
            languages=profile.get("languages", []),
            certifications=profile.get("certifications", []),
            photo_html=self._photo_html(profile),
        )

    @staticmethod
    def _photo_html(profile: dict[str, Any]) -> str:
        """Return a fully synthetic portrait only when the structural sample says so."""
        plan = profile.get("sampled_structural_plan", {}) or {}
        bewerbung = plan.get("bewerbung", {}) or {}
        present = bool(bewerbung.get("photo_present", False)) or bool(plan.get("photo_present", False))
        if not present:
            return ""
        gender = str(profile.get("gender", "female"))
        photo = generate_passport_photo(gender=gender)
        encoded = base64.b64encode(photo).decode("ascii")
        return f'<img src="data:image/png;base64,{encoded}" style="width:110px;height:138px;object-fit:cover;border:1px solid #777;" />'

    def _section_html(
        self,
        profile: dict[str, Any],
        section_type: str,
        variant: int = 0,
    ) -> str:
        """Render a compact annex for learned source sections.

        Unknown/personal/CV-section classes must not accidentally render the
        complete CV repeatedly inside a merged application package.
        """
        name = html.escape(str(profile.get("fictional_name", "")))
        labels = {
            "personal": "Persönliche Angaben",
            "cv_section": "Lebenslauf — ergänzender Abschnitt",
            "unknown": "Bewerbungsanlage",
            "certificate": "Nachweis und Zertifikat",
        }
        sections = PDFRenderer._continuation_sections(profile, "Anlage")
        section_title, section_lines = sections[variant % len(sections)]
        title = f"{html.escape(section_title)} — Anlage {variant + 1}"
        if section_type == "personal":
            title = f"Persönliches Profil — Anlage {variant + 1}"
        elif section_type == "cv_section":
            title = f"Lebenslauf: {html.escape(section_title)} — Anlage {variant + 1}"
        detail_lines = [html.escape(str(line)) for line in section_lines if str(line).strip()]
        # Add a second, distinct evidence block so every learned page carries
        # real profile material rather than a repeated placeholder.
        employment = profile.get("employment_history", []) or []
        projects = profile.get("research_projects", []) or []
        education = profile.get("education", []) or []
        skills = profile.get("skills", []) or []
        languages = profile.get("languages", []) or []
        certificates = profile.get("certifications", []) or []
        reviewed = profile.get("document_content", {}) or {}
        pools = [
            employment, education, projects, skills, languages, certificates,
            reviewed.get("achievement_bullets", []),
            reviewed.get("competency_evidence", []),
            reviewed.get("project_details", []),
        ]
        pool = pools[variant % len(pools)]
        if pool:
            item = pool[(variant // len(pools)) % len(pool)]
            if isinstance(item, dict):
                detail_lines.extend(html.escape(str(v)) for v in list(item.values())[:4] if str(v).strip())
            else:
                detail_lines.append(html.escape(str(item)))
        if reviewed.get("professional_summary"):
            detail_lines.append(html.escape(str(reviewed["professional_summary"])))
        detail_lines.append(
            html.escape(
                f"Ergänzende Angaben zu Anlage {variant + 1}: "
                "Die Darstellung folgt dem gesampelten Bewerbungsprofil und ordnet "
                "die vorhandenen Nachweise in einen eigenständigen Kontext ein."
            )
        )
        skills_block = f"<h2>{html.escape(section_title)}</h2><p>" + "</p><p>".join(detail_lines) + "</p>"
        return f"""<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\">
<style>@page {{ size:A4; margin:2.5cm; }} body {{ font-family:Arial,sans-serif;
font-size:10.5pt; color:#222; line-height:1.45; }} h1 {{ font-size:16pt;
border-bottom:2px solid #333; padding-bottom:5pt; }} h2 {{ font-size:12pt;
margin-top:20pt; border-bottom:1px solid #aaa; }} .footer {{ margin-top:30pt;
font-size:8pt; color:#888; }}</style></head><body>
<h1>{title}</h1><p><strong>{name}</strong></p>
<h2>Profilbezogene Ergänzung</h2><p>Diese Anlage führt konkrete Angaben aus dem Bewerbungsprofil eigenständig aus.</p>
{skills_block}
<div class=\"footer\">Synthetic fictional test data — not a real applicant</div>
</body></html>"""

    def _certificate_html(
        self,
        profile: dict[str, Any],
        cert_data: dict,
        cert_index: int = 0,
    ) -> str:
        template = self.env.get_template("certificate.html")
        title = cert_data.get("type", "Arbeitszeugnis")
        if cert_index:
            title = f"{title} — Nachweis {cert_index + 1}"
        body = cert_data.get("text", "")
        if cert_index:
            body = body.rstrip() + (
                f"\n\nAnlagennummer: {cert_index + 1:02d}\n"
                "Dieser Nachweis gehört zum fiktiven Bewerbungsdossier."
            )
        return template.render(
            organization=cert_data.get("employer", cert_data.get("issuer", "Institut")),
            org_subtitle="Abteilung Personal",
            document_title=title,
            body_text=body.replace("\n", "</p><p>"),
            location="München",
            date="TT.MM.JJJJ",
            signature_name="Prof. Dr. Mustermann",
            signature_title="Direktor",
        )

    def _reference_letter_html(self, profile: dict[str, Any], ref_text: str, referee: dict) -> str:
        template = self.env.get_template("reference_letter.html")
        return template.render(
            referee_name=referee.get("name", "Prof. Dr. Referenz"),
            referee_position=referee.get("position", ""),
            referee_organization=referee.get("organization", ""),
            referee_contact=referee.get("contact", ""),
            subject="Referenzschreiben für " + profile.get("fictional_name", ""),
            body_text=ref_text.replace("\n", "</p><p>"),
        )

    def _render_fallback(self, profile: dict[str, Any]) -> bytes:
        """Fallback if no subdocuments are available."""
        html = self._cv_html(profile)
        return self._html_to_pdf(html, apply_scan=True)

    def _merge_pdf_list(self, pdf_list: list[bytes]) -> bytes:
        """Merge multiple PDF byte streams into one PDF using PyMuPDF."""
        if not pdf_list:
            return b""
        if len(pdf_list) == 1:
            return pdf_list[0]
        if fitz is None:
            return pdf_list[0]
        merged = fitz.open()
        for pdf_bytes in pdf_list:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            merged.insert_pdf(doc)
            doc.close()
        buf = io.BytesIO()
        merged.save(buf)
        merged.close()
        return buf.getvalue()

    def _html_to_pdf(self, html: str, apply_scan: bool = False, scan_fraction: float = 0.85,
                      scan_page_indices: list[int] | None = None,
                      page_target: int | None = None,
                      continuation_label: str = "Dokument") -> bytes:
        """Convert HTML string to PDF bytes using WeasyPrint."""
        from weasyprint import HTML as WHTML
        pdf_bytes = WHTML(string=html).write_pdf()
        if page_target:
            pdf_bytes = self._pad_pdf_to_target(pdf_bytes, page_target, continuation_label)
        if apply_scan:
            from .scan_postprocess import convert_pdf_to_scanned
            kwargs = {"dpi": 72}
            if scan_page_indices is not None:
                kwargs["scan_page_indices"] = scan_page_indices
            else:
                kwargs["scan_fraction"] = scan_fraction
            pdf_bytes = convert_pdf_to_scanned(pdf_bytes, **kwargs)
        return pdf_bytes

    @staticmethod
    def _pad_pdf_to_target(
        pdf_bytes: bytes,
        page_target: int,
        label: str,
        profile: dict[str, Any] | None = None,
    ) -> bytes:
        """Fill short output with varied, profile-grounded continuation pages."""
        if fitz is None or page_target <= 0:
            return pdf_bytes
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        current = len(doc)
        sections = PDFRenderer._continuation_sections(profile or {}, label)
        while len(doc) < page_target:
            section_name, lines = sections[(len(doc) - current) % len(sections)]
            page_no = len(doc) + 1
            page = doc.new_page()
            page.insert_text((72, 90), f"{section_name} — {label}", fontsize=15)
            page.draw_line((72, 105), (520, 105), color=(0.35, 0.35, 0.35), width=0.8)
            page.insert_textbox(
                fitz.Rect(72, 135, 520, 240),
                "\n".join(lines) or "Ergänzende Angaben zum fiktiven Bewerbungsdossier.",
                fontsize=11,
                lineheight=1.45,
            )
            page.insert_text((72, 270), f"Seite {page_no} — strukturierte Fortsetzung", fontsize=9,
                             color=(0.35, 0.35, 0.35))
            page.insert_text(
                (72, 790),
                "Synthetic fictional test data — not a real applicant",
                fontsize=7,
                color=(0.45, 0.45, 0.45),
            )
        out = io.BytesIO()
        doc.save(out)
        doc.close()
        return out.getvalue()

    @staticmethod
    def _continuation_sections(profile: dict[str, Any], label: str) -> list[tuple[str, list[str]]]:
        """Build distinct continuation material from generated profile fields."""
        sections: list[tuple[str, list[str]]] = []
        employment = profile.get("employment_history", []) or []
        education = profile.get("education", []) or []
        projects = profile.get("research_projects", []) or []
        skills = profile.get("skills", []) or []
        languages = profile.get("languages", []) or []
        certs = profile.get("certifications", []) or []
        reviewed = profile.get("document_content", {}) or {}
        if employment:
            content = []
            for e in employment:
                content.extend([
                    f"{e.get('position', 'Tätigkeit')} — {e.get('employer', 'Organisation')}",
                    str(e.get('description', 'Ergänzende berufliche Angaben.')),
                ])
            sections.append(("Berufserfahrung", content))
        if education:
            content = []
            for e in education:
                content.extend([
                    f"{e.get('degree', 'Studium')} — {e.get('institution', 'Hochschule')}",
                    f"Zeitraum: {e.get('year_start', '')} – {e.get('year_end', '')}",
                ])
            sections.append(("Bildungsweg", content))
        if projects:
            content = []
            for p in projects:
                content.extend([
                    f"{p.get('name', 'Projekt')} — {p.get('role', 'Mitarbeit')}",
                    str(p.get('description', 'Projektbezogene Angaben.')),
                ])
            sections.append(("Forschungsprojekte", content))
        if skills:
            sections.append(("Kompetenzprofil", [
                " • ".join(str(s.get('name', s) if isinstance(s, dict) else s) for s in skills),
                "Fachliche und methodische Schwerpunkte des fiktiven Profils.",
            ]))
        if languages:
            sections.append(("Sprachkenntnisse", [
                ", ".join(f"{l.get('language', 'Sprache')} ({l.get('level', 'Kenntnisse')})" for l in languages if isinstance(l, dict)),
                "Weitere Angaben zu Kommunikation und Zusammenarbeit.",
            ]))
        if certs:
            sections.append(("Zertifikate und Anlagen", [
                " • ".join(str(c.get('name', c) if isinstance(c, dict) else c) for c in certs),
                "Nachweise und ergänzende Qualifikationen.",
            ]))
        if reviewed.get("achievement_bullets"):
            sections.append(("Nachweisbare Leistungen", list(reviewed["achievement_bullets"])))
        if reviewed.get("competency_evidence"):
            sections.append(("Kompetenzbelege", list(reviewed["competency_evidence"])))
        if not sections:
            sections.append(("Weitere Anlagen", [
                f"Ergänzende Seite {label} des fiktiven Bewerbungsdossiers.",
                "Die Darstellung folgt dem gesampelten Dokumentplan.",
            ]))
        # Materialize generator expressions once and rotate their entries.
        normalized: list[tuple[str, list[str]]] = []
        for title, content in sections:
            if not isinstance(content, list):
                content = list(content)
            normalized.append((title, content))
        return normalized

    @classmethod
    def _fit_pdf_to_target(
        cls,
        pdf_bytes: bytes,
        page_target: int,
        label: str,
        profile: dict[str, Any] | None = None,
    ) -> bytes:
        """Materialize exactly the sampled page target.

        Natural HTML pagination can exceed a small learned target. In that
        case retain the leading pages of the synthetic section; this keeps the
        merged package aligned with the population model instead of allowing
        one verbose template to distort the sampled distribution.
        """
        if fitz is None or page_target <= 0:
            return pdf_bytes
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if len(doc) > page_target:
            doc.delete_pages(page_target, len(doc) - 1)
            out = io.BytesIO()
            doc.save(out)
            doc.close()
            return out.getvalue()
        doc.close()
        return cls._pad_pdf_to_target(pdf_bytes, page_target, label, profile)

    @staticmethod
    def _apply_scan(pdf_bytes: bytes, scan_indices: list[int], scan_mode: str) -> bytes:
        if not scan_indices:
            return pdf_bytes
        from .scan_postprocess import convert_pdf_to_scanned
        return convert_pdf_to_scanned(
            pdf_bytes, dpi=72, scan_page_indices=scan_indices
        )
