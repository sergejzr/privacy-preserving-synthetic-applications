"""Second-pass, profile-grounded content enrichment for document rendering."""

from __future__ import annotations

import json
from typing import Any

from .local_llm import LocalLLMClient
from .prompts import PROFILE_QUALITY_SYSTEM, PROFILE_QUALITY_USER


def _fallback(profile: dict[str, Any]) -> dict[str, Any]:
    employment = profile.get("employment_history", []) or []
    projects = profile.get("research_projects", []) or []
    skills = profile.get("skills", []) or []
    bullets = []
    for e in employment:
        bullets.append(f"{e.get('position', 'Tätigkeit')} bei {e.get('employer', 'Organisation')}: {e.get('description', '')}")
    for p in projects:
        bullets.append(f"{p.get('role', 'Mitarbeit')} im Projekt {p.get('name', 'Forschungsprojekt')}: {p.get('description', '')}")
    bullets.extend(str(s.get('name', s) if isinstance(s, dict) else s) for s in skills)
    bullets = list(dict.fromkeys(x for x in bullets if x))[:8]
    details = [{
        "project": p.get("name", "Forschungsprojekt"),
        "contribution": p.get("description", "Projektbezogene Mitarbeit"),
        "method": ", ".join(str(s) for s in skills[:2]) or "interdisziplinäre Analyse",
        "result": "Aufbau belastbarer wissenschaftlicher und organisatorischer Erfahrung",
    } for p in projects]
    return {
        "professional_summary": (
            f"{profile.get('fictional_name', 'Die Person')} verbindet "
            f"{len(employment)} berufliche Stationen mit {len(projects)} dokumentierten Projekten "
            "und einem fachlichen Schwerpunkt aus Ausbildung und Kompetenzen."
        ),
        "achievement_bullets": bullets or ["Fachliche Mitarbeit an dokumentierten Aufgaben und Projekten."],
        "project_details": details,
        "competency_evidence": bullets[:6] or ["Nachweisbare fachliche Qualifikation aus dem Profil."],
        "annex_topics": [
            "Beruflicher Werdegang", "Ausbildung und Abschlüsse", "Projektbeiträge",
            "Methodische Kompetenzen", "Sprach- und Kooperationsprofil",
            "Zertifikate und Nachweise", "Verantwortungsbereiche", "Forschungsinteressen",
        ],
    }


def enrich_profile(profile: dict[str, Any], client: LocalLLMClient | None,
                   title: str, organization: str) -> dict[str, Any]:
    """Attach a quality-reviewed content blueprint without changing source facts."""
    fallback = _fallback(profile)
    if client is None:
        profile["document_content"] = fallback
        return profile
    try:
        response = client.chat([
            {"role": "system", "content": PROFILE_QUALITY_SYSTEM},
            {"role": "user", "content": PROFILE_QUALITY_USER.format(
                title=title, organization=organization,
                profile_json=json.dumps(profile, ensure_ascii=False),
            )},
        ], max_tokens=6000)
        content = response["choices"][0]["message"].get("content", "")
        start, end = content.find("{"), content.rfind("}")
        reviewed = json.loads(content[start:end + 1]) if start >= 0 and end > start else {}
        if not isinstance(reviewed, dict):
            reviewed = {}
        for key, value in fallback.items():
            if not reviewed.get(key):
                reviewed[key] = value
        profile["document_content"] = reviewed
    except Exception:
        profile["document_content"] = fallback
    return profile
