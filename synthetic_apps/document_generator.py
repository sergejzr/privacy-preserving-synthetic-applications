"""Generates synthetic document text for each applicant using a local LLM.

Phase D implementation: creates cover letter text, CV descriptions,
certificates, and reference letters per applicant profile.
"""

from __future__ import annotations

import json
import random
from typing import Any

from .genconfig import Config
from .document_prompts import (
    CERTIFICATE_SYSTEM,
    CERTIFICATE_USER,
    COVER_LETTER_SYSTEM,
    COVER_LETTER_USER,
    CV_DESCRIPTION_SYSTEM,
    CV_DESCRIPTION_USER,
    REFERENCE_LETTER_SYSTEM,
    REFERENCE_LETTER_USER,
    PARAGRAPH_EXPANSION_SYSTEM,
    PARAGRAPH_EXPANSION_USER,
    DOCUMENT_PROMPTS_VERSION,
)
from .local_llm import LocalLLMClient

_rng = random.Random(20261008)

# Fictional referee data for reference letters
REFEREES = [
    {"name": "Prof. Dr. Martina Bergmann", "position": "Direktorin",
     "organization": "Institut für Quantenforschung Köpenick",
     "contact": "m.bergmann@iqk.example.com"},
    {"name": "Prof. Dr. Thomas Werner", "position": "Bereichsleiter Forschung",
     "organization": "Forschungszentrum für Subraumtechnologie",
     "contact": "th.werner@fst.example.com"},
    {"name": "Dr. Susanne Lehmann", "position": "Leiterin Personalentwicklung",
     "organization": "QuantenSys GmbH Dresden",
     "contact": "s.lehmann@quantsys.example.com"},
    {"name": "Prof. Dr. Klaus Richter", "position": "Dekan der Fakultät für Physik",
     "organization": "Technische Universität Sternenau",
     "contact": "k.richter@tu-sternenau.example.com"},
    {"name": "Dr. Elena Fischer", "position": "Abteilungsleiterin Forschungsförderung",
     "organization": "Deutsche Stiftung für Wissenschaft und Technologie",
     "contact": "e.fischer@dswt.example.com"},
]


def _call_llm(
    client: LocalLLMClient,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 4096,
) -> str:
    """Call the LLM and return the response content."""
    resp = client.chat([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ], max_tokens=max_tokens)
    content = resp["choices"][0]["message"].get("content", "")
    return content.strip()


def _pick_referee(applicant_id: str) -> dict:
    """Deterministically pick a referee for an applicant."""
    idx = hash(applicant_id + "referee") % len(REFEREES)
    return dict(REFEREES[idx])


def _target_pages(output_plan: Any, subdoc_type: str) -> int:
    if output_plan is None:
        return 1
    for document in getattr(output_plan, "documents", []):
        for subdoc in getattr(document, "subdocuments", []):
            if getattr(subdoc, "subdoc_type", "") == subdoc_type:
                return max(1, int(getattr(subdoc, "page_target", 1)))
    return 1


def _expand_paragraphs(client: LocalLLMClient, text: str, profile: dict[str, Any],
                       document_kind: str, target_pages: int) -> str:
    """Expand existing paragraphs independently, avoiding generic page padding."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs or target_pages <= 1:
        return text
    target_chars = max(900, target_pages * 1550)
    profile_json = json.dumps(profile, ensure_ascii=False)
    used: list[str] = []
    rounds = 0
    while sum(len(p) for p in paragraphs) < target_chars and rounds < 3:
        for index, paragraph in enumerate(list(paragraphs)):
            if sum(len(p) for p in paragraphs) >= target_chars:
                break
            prompt = PARAGRAPH_EXPANSION_USER.format(
                document_kind=document_kind,
                applicant_json=profile_json,
                paragraph=paragraph,
                used_topics=", ".join(used[-8:]) or "keine",
            )
            try:
                expanded = _call_llm(client, PARAGRAPH_EXPANSION_SYSTEM, prompt, max_tokens=1800)
            except Exception:
                expanded = ""
            if expanded and len(expanded) > len(paragraph) + 40:
                paragraphs[index] = expanded
                used.append(f"Absatz {index + 1}, Runde {rounds + 1}")
        rounds += 1
    return "\n\n".join(paragraphs)


def _ensure_long_form(text: str, profile: dict[str, Any], target_pages: int) -> str:
    """Add distinct, profile-grounded paragraphs when an LLM underfills a target."""
    if target_pages <= 1:
        return text
    target_chars = target_pages * 1350
    if len(text) >= target_chars:
        return text
    content = profile.get("document_content", {}) or {}
    additions = []
    if content.get("professional_summary"):
        additions.append(str(content["professional_summary"]))
    additions.extend(str(x) for x in content.get("achievement_bullets", []))
    for item in content.get("project_details", []):
        if isinstance(item, dict):
            additions.append(
                f"Im Projekt {item.get('project', 'Forschungsprojekt')} "
                f"übernahm die Person {item.get('contribution', 'eine fachliche Aufgabe')}. "
                f"Dabei kamen {item.get('method', 'profilbezogene Methoden')} zum Einsatz; "
                f"als Ergebnis entstand {item.get('result', 'weitere belastbare Erfahrung')}."
            )
    existing = text.lower()
    for addition in additions:
        if len(text) >= target_chars:
            break
        if addition.strip().lower() not in existing:
            text = text.rstrip() + "\n\n" + addition.strip()
            existing += addition.lower()
    return text


def _generate_certificates(
    profile: dict[str, Any],
    name: str,
    applicant_id: str,
    max_certs: int = 12,
) -> list[dict[str, Any]]:
    """Generate diverse certificate texts up to max_certs, cycling through types."""
    emp_history = profile.get("employment_history", [])
    education = profile.get("education", [])

    cert_templates = [
        # (type, title, issuer_or_employer_key, needs_profile_emp)
        ("Arbeitszeugnis", "Berufliche Tätigkeit", "employer", True),
        ("Weiterbildungszertifikat", "Projektmanagement (PRINCE2)", "Akademie für Projektmanagement", False),
        ("Sprachzertifikat", "Cambridge English C1", "Cambridge English", False),
        ("Teilnahmebescheinigung", "Leadership in Research Organizations", "HSG St. Gallen", False),
        ("Promotionsurkunde", "Doktor der Naturwissenschaften (Dr. rer. nat.)", "Universität", False),
        ("Masterurkunde", "Master of Science in Physik", "Technische Universität", False),
        ("Bachelorurkunde", "Bachelor of Science in Physik", "Fachhochschule", False),
        ("Notenzeugnis", "Transcript of Records — Physik", "Prüfungsamt", False),
        ("Diplomurkunde", "Diplom-Physiker", "Technische Universität", False),
        ("Fortbildungszertifikat", "Data Science für Führungskräfte", "Harvard Online", False),
        ("Zertifikat", "Interkulturelle Kompetenz", "Goethe-Institut", False),
        ("Bescheinigung", "Mitgliedschaft im Forschungsbeirat", "DFG", False),
    ]

    certs: list[dict[str, Any]] = []
    for ci in range(max_certs):
        ctype, ctitle, issuer_or_key, needs_emp = cert_templates[ci % len(cert_templates)]
        if needs_emp and emp_history:
            emp = emp_history[ci % len(emp_history)]
            period = f"{emp.get('month_start', '?')} – {emp.get('month_end', '?')}"
            text = (
                f"{ctype}\n\n{name}\n\n"
                f"war vom {period} als {emp.get('position', 'Mitarbeiter')} "
                f"bei {emp.get('employer', issuer_or_key)} beschäftigt.\n\n"
                f"Aufgaben: {emp.get('description', '')}"
            )
            certs.append({
                "type": ctype,
                "employer": emp.get("employer", issuer_or_key),
                "text": text,
            })
        elif education and ctype in ("Promotionsurkunde", "Masterurkunde", "Bachelorurkunde",
                                      "Notenzeugnis", "Diplomurkunde"):
            edu = education[(ci // len(cert_templates)) % len(education)]
            degree_field = edu.get("field", "Physik")
            degree_institution = edu.get("institution", issuer_or_key)
            if ctype == "Promotionsurkunde":
                text = (
                    f"{ctype}\n\n{name}\n\n"
                    f"hat am {degree_institution} die Doktorprüfung im Fach {degree_field}\n"
                    f"mit Auszeichnung bestanden.\n\n"
                    f"Tag der mündlichen Prüfung: 15.03.20XX\n\n"
                    f"Promotionskommission:\n"
                    f"Prof. Dr. Vorsitz\n"
                    f"Prof. Dr. Erstgutachter\n"
                    f"Prof. Dr. Zweitgutachter"
                )
                certs.append({"type": ctype, "employer": degree_institution, "text": text, "title": ctitle})
            elif ctype == "Masterurkunde":
                text = (
                    f"{ctype}\n\n{name}\n\n"
                    f"hat den Masterstudiengang {degree_field}\n"
                    f"am {degree_institution} erfolgreich abgeschlossen.\n\n"
                    f"Gesamtnote: 1,3\n\n"
                    f"Masterarbeit: „Quantenverschränkung in optischen Gittern“"
                )
                certs.append({"type": ctype, "employer": degree_institution, "text": text, "title": ctitle})
            elif ctype == "Bachelorurkunde":
                text = (
                    f"{ctype}\n\n{name}\n\n"
                    f"hat den Bachelorstudiengang {degree_field}\n"
                    f"am {degree_institution} erfolgreich abgeschlossen.\n\n"
                    f"Gesamtnote: 1,7\n\n"
                    f"Bachelorarbeit: „Grundlagen der Quanteninformationsverarbeitung“"
                )
                certs.append({"type": ctype, "employer": degree_institution, "text": text, "title": ctitle})
            elif ctype == "Diplomurkunde":
                text = (
                    f"{ctype}\n\n{name}\n\n"
                    f"hat das Studium der {degree_field}\n"
                    f"am {degree_institution} mit dem akademischen Grad\n"
                    f"Diplom-Physiker abgeschlossen.\n\n"
                    f"Gesamtnote: 1,5"
                )
                certs.append({"type": ctype, "employer": degree_institution, "text": text, "title": ctitle})
            elif ctype == "Notenzeugnis":
                text = (
                    f"{ctype}\n\n{name}\n\n"
                    f"Studiengang: {degree_field}\n"
                    f"Institution: {degree_institution}\n\n"
                    f"Note  Gut (1,7)\n\n"
                    f"Semester: 1-6\n\n"
                    f"Leistungspunkte: 180 ECTS"
                )
                certs.append({"type": ctype, "employer": degree_institution, "text": text, "title": ctitle})
        else:
            issuer = issuer_or_key
            if "Harvard" in issuer or "Goethe" in issuer or "DFG" in issuer:
                text = (
                    f"{ctype}\n\n{ctitle}\n\n{name}\n\n"
                    f"hat die Prüfung erfolgreich abgelegt.\n\n"
                    f"Ausgestellt von: {issuer}"
                )
            else:
                text = (
                    f"{ctype}\n\n{ctitle}\n\n{name}\n\n"
                    f"hat die Prüfung erfolgreich abgelegt.\n\n"
                    f"Ausgestellt von: {issuer}"
                )
            certs.append({"type": ctype, "title": ctitle, "issuer": issuer, "text": text})

    return certs


def generate_document_texts(
    cfg: Config,
    profile: dict[str, Any],
    client: LocalLLMClient,
    job_description: str | None = None,
    scan_quality: str = "normal",
    output_plan: Any | None = None,
) -> dict[str, Any]:
    """Generate all document texts for a single applicant.

    Args:
        cfg: Configuration.
        profile: Canonical applicant profile dict.
        client: LLM client.
        job_description: Job posting text.
        scan_quality: Image quality for scanned pages.

    Returns:
        Dict with keys: cover_letter_body, cv_descriptions,
        certificates list, reference_letter, metadata.
    """
    name = profile.get("fictional_name", "?")
    aid = profile.get("applicant_id", "?")
    facts_to_disclose = profile.get("facts_to_disclose", [])
    facts_to_omit = profile.get("facts_to_omit", [])
    contradictions = profile.get("intentional_contradictions", [])

    if job_description is None:
        job_description = cfg.scenario.title

    result: dict[str, Any] = {
        "applicant_id": aid,
        "name": name,
        "cover_letter_body": "",
        "cv_descriptions": {},
        "certificates": [],
        "reference_letter": "",
        "scan_quality": scan_quality,
        "position_title": cfg.scenario.title,
        "organization": cfg.scenario.organization,
    }

    # --- Cover letter ---
    profile_json = json.dumps(profile, indent=2, ensure_ascii=False)
    cl_user = COVER_LETTER_USER.format(
        applicant_json=profile_json,
        position_title=cfg.scenario.title,
        organization=cfg.scenario.organization,
        job_description=job_description,
        facts_to_disclose="\n".join(f"- {f}" for f in facts_to_disclose),
        facts_to_omit="\n".join(f"- {f}" for f in facts_to_omit),
        intentional_contradictions=json.dumps(contradictions, indent=2, ensure_ascii=False),
    )
    cl_body = _call_llm(client, COVER_LETTER_SYSTEM, cl_user, max_tokens=4096)
    result["cover_letter_body"] = _expand_paragraphs(
        client, cl_body, profile, "Anschreiben",
        _target_pages(output_plan, "cover_letter"),
    )
    result["cover_letter_body"] = _ensure_long_form(
        result["cover_letter_body"], profile,
        _target_pages(output_plan, "cover_letter"),
    )

    # --- CV descriptions ---
    # Use profile employment descriptions directly (no extra LLM call needed)
    for i, e in enumerate(profile.get("employment_history", [])):
        key = f"emp_{i}"
        result["cv_descriptions"][key] = e.get("description", "")

    # --- Certificates (templated, no LLM needed) ---
    result["certificates"] = _generate_certificates(profile, name, aid)

    # --- Reference letter (LLM call) ---
    referee = _pick_referee(aid)
    key_strengths = profile.get("skills", [])
    if not key_strengths:
        key_strengths = ["Fachkompetenz", "Teamfähigkeit", "Projektmanagement"]

    emp_list = profile.get("employment_history", [])
    if emp_list:
        last_emp = emp_list[-1]
        relationship = f"{last_emp.get('position', 'Mitarbeiter')} im {last_emp.get('employer', 'Unternehmen')}"
        period_known = f"{last_emp.get('month_start', '?')} – {last_emp.get('month_end', 'present')}"
    else:
        relationship = "akademische Zusammenarbeit"
        period_known = "mehrere Jahre"

    ref_user = REFERENCE_LETTER_USER.format(
        name=name,
        referee_name=referee["name"],
        referee_position=referee["position"],
        referee_organization=referee["organization"],
        relationship=relationship,
        period_known=period_known,
        key_strengths="\n".join(f"- {s}" for s in key_strengths[:5]),
    )
    ref_text = _call_llm(client, REFERENCE_LETTER_SYSTEM, ref_user, max_tokens=4096)
    result["reference_letter"] = _expand_paragraphs(
        client, ref_text, profile, "Referenzschreiben",
        _target_pages(output_plan, "reference_letter"),
    )
    result["reference_letter"] = _ensure_long_form(
        result["reference_letter"], profile,
        _target_pages(output_plan, "reference_letter"),
    )
    result["referee"] = referee

    return result
