"""Generates synthetic applicant profiles using a local LLM.

Phase C implementation: creates coherent, diverse fictional applicant profiles
with canonical JSON for ground truth.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .genconfig import Config
from .local_llm import LocalLLMClient
from .prompts import APPLICANT_SYSTEM, APPLICANT_USER, PROMPTS_VERSION
from .profile_quality import enrich_profile


# Fit categories and their career seeds for diversity
FIT_CATEGORIES = [
    ("strong_match", "Dr. rer. nat. in Astrophysik, 14 Jahre Erfahrung im Forschungsmanagement, "
     "Leitung eines interdisziplinären Zentrums für Quantenforschung, "
     "Budgetverantwortung über 10 Mio. EUR, zahlreiche internationale Kooperationen",
     "männlich, grobe Altersgruppe 45–55, Name beginnt mit A, studierte an zwei erfundenen naturwissenschaftlichen Hochschulen",
     "Akademie für Exoplanetare Systeme, Institut für Raumzeitmethodik, Helixkern Forschungskollektiv"),
    ("moderate_match", "Dr. phil. in Wissenschaftssoziologie, 7 Jahre als Koordinatorin "
     "eines EU-Forschungsprojekts, solide Erfahrung in Stakeholder-Kommunikation, "
     "aber wenig direkte Budgetverantwortung",
     "weiblich, grobe Altersgruppe 35–45, Name beginnt mit B, studierte an einer erfundenen Hochschule für Wissenschaftssoziologie",
     "Nordlicht-Akademie für Technikfolgen, Institut Wandelkern, Europäisches Forschungsnetzwerk Meridian"),
    ("weak_match", "Diplom-Informatiker, 10 Jahre in der Industrie (Quantencomputing-Software), "
     "Projektleitungserfahrung aber kein akademisches Forschungsmanagement, "
     "keine Promotion",
     "männlich, grobe Altersgruppe 35–45, Name beginnt mit C, studierte an einer erfundenen Fachhochschule",
     "Fachakademie Nordorbit, Quantenwerk Systems, NovaMatrix Forschung"),
    ("early_career", "Frisch promovierte Physikerin (2022), 3 Jahre Postdoc in der "
     "Quantenkommunikation, erste Erfahrung in der Betreuung von Studierenden, "
     "keine Budgetverantwortung",
     "weiblich, grobe Altersgruppe 25–35, Name beginnt mit D, studierte an zwei erfundenen technischen Hochschulen",
     "Technische Akademie Elara, Universität Morgenstern, Institut für Quantenkommunikation"),
    ("career_changer", "M.A. in Science and Technology Studies, 15 Jahre in der "
     "Wissenschaftsadministration und Forschungsförderung, jetzt Wechsel in "
     "aktives Forschungsmanagement, stark in Governance und Ethik",
     "divers, grobe Altersgruppe 45–55, Name beginnt mit E, studierte an einer erfundenen Hochschule für Governance",
     "Hochschule Westbogen, Forschungsförderwerk Meridian, Ministerium für Zukunftsfragen"),
]


def _extract_json(text: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown fences."""
    if not text or not text.strip():
        return None

    # Try to find ```json ... ``` block
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        text = m.group(1)

    # Clean the text: remove BOM, zero-width chars, normalize whitespace
    text = text.strip().lstrip("\ufeff")

    # Try parsing directly
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try finding first { to last }
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        candidate = text[start:end]
        return json.loads(candidate)
    except (ValueError, json.JSONDecodeError):
        pass

    # Try with line-by-line repair for common truncation issues
    try:
        # If the JSON is truncated at a comma or bracket, try to close it
        start = text.index("{")
        candidate = text[start:]
        # Try to fix truncated arrays/objects
        open_braces = candidate.count("{") - candidate.count("}")
        open_brackets = candidate.count("[") - candidate.count("]")
        if open_braces > 0:
            candidate += "}" * open_braces
        if open_brackets > 0:
            candidate += "]" * open_brackets
        # Fix trailing commas
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        return json.loads(candidate)
    except (ValueError, json.JSONDecodeError):
        return None


def generate_applicants(
    cfg: Config,
    output_dir: str | Path,
    count: int = 5,
    job_description: str | None = None,
    extra_attributes: str | None = None,
    client: LocalLLMClient | None = None,
    manifest: dict[str, Any] | None = None,
    structural_plans: list[dict[str, Any]] | None = None,
    dossier_plans: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Generate synthetic applicant profiles.

    Args:
        cfg: Full configuration.
        output_dir: Directory to write output files (ground_truth/).
        count: Number of applicants to generate (max 20).
        job_description: Pre-generated job posting text.
        extra_attributes: Pre-generated extra attributes text.
        client: Optional pre-configured LLM client.
        manifest: Optional dict for generation metadata.

    Returns:
        List of applicant profile dicts.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if manifest is None:
        manifest = {}
    manifest.setdefault("prompts_version", PROMPTS_VERSION)
    manifest.setdefault("phase", "C")
    manifest.setdefault("scenario", cfg.scenario.model_dump())

    close_client = False
    if client is None:
        llm_settings = cfg.resolve_llm_settings()
        client = LocalLLMClient(
            base_url=llm_settings["base_url"],
            model=llm_settings["model"],
            api_key=llm_settings["api_key"],
            timeout_seconds=llm_settings["timeout_seconds"],
            max_retries=llm_settings["max_retries"],
            temperature=llm_settings["temperature"],
            allow_non_loopback=False,
            trusted_hosts=llm_settings["trusted_hosts"],
        )
        close_client = True

    # Load job description and extra attributes from disk if not provided
    if job_description is None:
        stellen_path = output_path.parent / "stellenbeschreibungen" / "stellenbeschreibung.md"
        if stellen_path.exists():
            job_description = stellen_path.read_text()
        else:
            job_description = "Fictional Research Program Manager position at Interplanetary Research Directorate."

    if extra_attributes is None:
        extra_path = output_path.parent / "extra_attributes.txt"
        if extra_path.exists():
            extra_attributes = extra_path.read_text()
        else:
            extra_attributes = ""

    profiles: list[dict[str, Any]] = []
    applicant_usage: list[dict[str, Any]] = []

    # Ensure count doesn't exceed categories for diversity
    count = min(count, 20)

    # Assign fit categories round-robin for diversity
    fit_categories = FIT_CATEGORIES * ((count // len(FIT_CATEGORIES)) + 1)
    fit_categories = fit_categories[:count]

    try:
        for i, (fit_category, career_seed, demographics_hint, suggested_institutions) in enumerate(fit_categories):
            applicant_id = f"SG{i+1:03d}"

            system_prompt = APPLICANT_SYSTEM
            user_prompt = APPLICANT_USER.format(
                title=cfg.scenario.title,
                organization=cfg.scenario.organization,
                language=cfg.scenario.language,
                fictional_universe=cfg.scenario.fictional_universe,
                job_description=job_description,
                extra_attributes=extra_attributes,
                applicant_id=applicant_id,
                fit_category=fit_category,
                career_seed=career_seed,
                demographics_hint=demographics_hint,
                suggested_institutions=suggested_institutions,
                structural_plan=json.dumps(structural_plans[i], ensure_ascii=False) if structural_plans and i < len(structural_plans) else "not provided",
                dossier_plan=json.dumps(dossier_plans[i], ensure_ascii=False) if dossier_plans and i < len(dossier_plans) else "not provided",
            )

            print(f"  Generating {applicant_id} ({fit_category})...", flush=True)

            resp = client.chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=24576,
            )

            content = resp["choices"][0]["message"].get("content", "")
            usage = resp.get("usage", {})
            applicant_usage.append({
                "applicant_id": applicant_id,
                "fit_category": fit_category,
                "usage": usage,
            })

            profile = _extract_json(content)
            if profile is None:
                print(f"    WARNING: Could not parse JSON for {applicant_id}, saving raw response")
                profile = {
                    "applicant_id": applicant_id,
                    "target_fit_category": fit_category,
                    "_raw_response": content,
                    "_parse_error": True,
                }
            else:
                # Ensure applicant_id is set correctly
                profile["applicant_id"] = applicant_id
                profile["target_fit_category"] = fit_category
                if structural_plans and i < len(structural_plans):
                    profile["sampled_structural_plan"] = structural_plans[i]
                if dossier_plans and i < len(dossier_plans):
                    profile["sampled_dossier_plan"] = dossier_plans[i]
                profile = enrich_profile(
                    profile, client, cfg.scenario.title, cfg.scenario.organization,
                )

            profiles.append(profile)

    finally:
        if close_client and client:
            client.close()

    # Write profiles
    applicants_path = output_path / "applicants.json"
    tmp = applicants_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(profiles, indent=2, ensure_ascii=False))
    tmp.rename(applicants_path)

    manifest["applicant_count"] = len(profiles)
    manifest["applicant_usage"] = applicant_usage
    manifest["applicants_path"] = str(applicants_path)

    print(f"\n  Wrote {len(profiles)} applicant profiles to {applicants_path}")

    return profiles
