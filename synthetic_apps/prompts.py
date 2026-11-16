"""Prompt templates for the synthetic data generator.

All prompts are stored here for reproducibility. Version hashes
are tracked in the generation manifest.
"""

from __future__ import annotations

# Prompt template version — bump when prompts change
PROMPTS_VERSION = "0.2.0"

PROFILE_QUALITY_SYSTEM = """Du bist die redaktionelle Qualitätsprüfung für synthetische Bewerbungsprofile. Arbeite ausschließlich mit dem gelieferten Profil und der Stelle. Verändere niemals Namen, Zeiträume, Institutionen, Abschlüsse, Arbeitgeber oder vorhandene Fakten. Ergänze nur konkrete, daraus ableitbare Formulierungen für realistische Dokumente. Ausgabe ausschließlich als valides JSON."""

PROFILE_QUALITY_USER = """Prüfe und vervollständige dieses fiktive Bewerbungsprofil für die Stelle „{title}“ bei „{organization}“.

Profil:
{profile_json}

Erzeuge ausschließlich dieses JSON:
{{
  "professional_summary": "2-4 Sätze, fachlich konkret und nur aus dem Profil abgeleitet",
  "achievement_bullets": ["6 unterschiedliche, belegte Leistungs- oder Verantwortungsaspekte"],
  "project_details": [{{"project": "vorhandener Projektname", "contribution": "konkreter Beitrag", "method": "passende Methode oder Technologie", "result": "vorsichtige, profilgebundene Wirkung"}}],
  "competency_evidence": ["6 unterschiedliche Belege für Kompetenzen aus Ausbildung, Beruf, Projekten oder Zertifikaten"],
  "annex_topics": ["8 unterschiedliche sinnvolle Anlagenthemen, keine Platzhalter und kein unknown"]
}}

Keine neuen Arbeitgeber, Abschlüsse, Zertifikate, Messwerte oder Projekte erfinden. Keine Wiederholungen zwischen den Listen."""

JOB_DESCRIPTION_SYSTEM = """You are a synthetic data generation tool for fictional applicant documents. \
You generate entirely fictional job postings in German. All organizations, projects, and \
people are fictional. Never use real institutions, real people, or real addresses. \
Use 'example.com' for email domains. The setting is a fictional science-fiction universe."""

JOB_DESCRIPTION_USER = """Create a detailed German-language job posting for a fictional organization.

Organization: {organization}
Position: {title}
Language: {language}
Setting: {fictional_universe}

The job posting must include these sections in German:
1. **Über uns** (About us) — Describe the fictional Interplanetary Research Directorate
2. **Ihre Aufgaben** (Your responsibilities) — Research program coordination, wormhole transit safety, interdisciplinary collaboration, grant management, scientific governance, budget planning, risk management, stakeholder communication, ethical oversight
3. **Ihr Profil** (Your profile) — Required qualifications mixing research-management competencies with fictional domain knowledge
4. **Wir bieten** (We offer) — fictional benefits
5. **Kontakt** (Contact) — fictional contact details with example.com email

Requirements:
- Write entirely in {language}
- Make qualifications measurable and specific enough to be extracted by an applicant-analysis pipeline
- Include fictional project names, fictional department names, fictional technologies
- The position is NOT real — it exists only in a fictional universe
- Length: 400-800 words
- Use proper German job posting format with bullet points where appropriate
- The posting should feel authentic for a research management role

Output only the job posting text in Markdown format, no additional commentary."""

EXTRA_ATTRIBUTES_SYSTEM = """You are a synthetic data generation tool. \
Generate a list of characterics relevant for a fictional job posting. \
These will be used as extra attributes for an applicant-analysis pipeline to extract from documents."""

EXTRA_ATTRIBUTES_USER = """Based on the following fictional job posting, generate a list of 12-15 extra attributes \
that an applicant-analysis system should look for in applications.

Job posting:
{job_description}

Output one attribute per line in German. Each attribute should be a specific, measurable characteristic \
that can be extracted from CVs and cover letters. Examples of good attributes:

Promotion oder gleichwertige Forschungserfahrung
Jahre Erfahrung im Forschungsmanagement
Leitung interdisziplinärer Projekte
Budgetverantwortung
Drittmittel- und Fördermittelmanagement
Risikomanagement
Kommunikation mit wissenschaftlichen Stakeholdern
Deutschkenntnisse
Englischkenntnisse
Erfahrung mit internationalen Kooperationen
Erfahrung in sicherheitskritischen Forschungsumgebungen
Verfügbarkeit und möglicher Eintrittstermin

Output only the attributes, one per line, no numbering, no additional text."""

APPLICANT_SYSTEM = """You are a synthetic data generation tool for fictional applicant profiles. \
All organizations, projects, people, addresses, and credentials you generate must be entirely fictional. \
Never use real institutions, real people, real addresses, or real phone numbers. \
Use 'example.com' for all email domains. \
The setting is a fictional science-fiction universe (Interplanetary Research Directorate, Stargate Initiative). \
Each applicant must have an internally coherent, realistic career path. \
Applicants MUST be genuinely distinct — different names, different invented institutions, different career trajectories. \
Do NOT reuse the same invented university (e.g. 'Universität Neustadt') across multiple applicants. \
Do NOT reuse the same surname across applicants. \
Output valid JSON only, no additional text or markdown formatting."""

APPLICANT_USER = """Generate a fictional applicant profile for the following scenario.

## Context
- Position: {title}
- Organization: {organization}
- Language: {language}
- Setting: {fictional_universe}

## Job posting
{job_description}

## Extra attributes (the analysis pipeline will look for these)
{extra_attributes}

## Applicant specification
- Applicant ID: {applicant_id}
- Fit category: {fit_category}
- Career summary: {career_seed}
- Demographics hint: {demographics_hint} (use this for inspiration only, do NOT copy real people)
- Suggested institutions (invent freely, these are just examples): {suggested_institutions}
- Structural population plan (sampled from aggregate reference statistics): {structural_plan}
- Learned dossier/semantic plan (coarsened taxonomy only): {dossier_plan}

## Requirements for the profile
Generate a diverse, internally coherent fictional applicant. The applicant should have a realistic \
career path with invented but plausible institutions, projects, and credentials. \
IMPORTANT: Invent FRESH institutions for each applicant. Do not reuse institutions from other applicants. \
Use creative German-sounding names: different invented universities, different institutes, different companies.

Use the following JSON schema exactly:
{{
  "applicant_id": "{applicant_id}",
  "fictional_name": "string — full name with title (e.g., Dr. ...)",
  "fictional_email": "string — using example.com domain",
  "fictional_phone": "string — fictional German-style phone number starting with +49 1",
  "fictional_address": "string — German-style address with invented street and city",
  "target_fit_category": "{fit_category}",
  "education": [
    {{"degree": "string", "institution": "string", "year_start": int, "year_end": int, "grade": "string (optional)"}}
  ],
  "employment_history": [
    {{"position": "string", "employer": "string", "month_start": "MM/YYYY", "month_end": "MM/YYYY or 'present'", "description": "string"}}
  ],
  "research_projects": [
    {{"name": "string", "role": "string", "budget_credits": "string (optional)", "description": "string"}}
  ],
  "certifications": ["string"],
  "skills": ["string"],
  "languages": [{{"language": "string", "level": "string (CEFR or native)"}}],
  "budget_experience": "string — description of budget management experience",
  "leadership_experience": "string — description of team leadership experience",
  "document_plan": ["cv", "cover_letter", "certificate", "reference_letter"],
  "facts_to_disclose": ["list of factual claims the CV/cover letter WILL make"],
  "facts_to_omit": ["list of facts from the above that the applicant deliberately OMITS from their application"],
  "intentional_contradictions": [
    {{"fact_a": "string", "fact_b": "string", "description": "string"}}
  ],
  "expected_evaluation_attributes": {{
    "attribute_name": "string or number — expected value for this applicant"
  }}
}}

The expected_evaluation_attributes should include values for the attributes in the job posting. \
For example: Promotion, Budgetverantwortung, Deutschkenntnisse, etc.

Career contexts for each fit category:
- strong_match: Ideal candidate. All requirements exceeded. 12+ years experience, leadership, publications, international work.
- moderate_match: Good candidate but gaps. 5-8 years relevant experience, some but not all requirements met.
- weak_match: Relevant background but missing key qualifications. E.g., related field, limited management experience.
- early_career: PhD + 2-3 years postdoc. Strong academic record but limited management and budget experience.
- career_changer: Previously in adjacent field (e.g., industry R&D, science policy). Transferable skills but domain gaps.

Output valid JSON only (wrapped in ```json ... ``` or raw). No additional text."""
