"""Prompt templates for document generation (Phase D).

All prompts stored for reproducibility with version tracking.
"""

from __future__ import annotations

DOCUMENT_PROMPTS_VERSION = "0.2.0"

PARAGRAPH_EXPANSION_SYSTEM = """Du erstellst synthetische Bewerbungsunterlagen auf Deutsch. Erweitere genau einen vorhandenen Absatz fachlich und natürlich. Erfinde keine Fakten, die nicht im Profil stehen, wiederhole keine Formulierungen aus dem Absatz und gib ausschließlich den erweiterten Absatz aus."""

PARAGRAPH_EXPANSION_USER = """Erweitere den folgenden Absatz für ein {document_kind} um konkrete, bereits im Profil belegte Details. Ziel ist ein längerer, glaubwürdiger Absatz mit neuen Aspekten, nicht eine Wiederholung.

Profil:
{applicant_json}

Bisheriger Absatz:
{paragraph}

Bereits verwendete Schwerpunkte:
{used_topics}

Gib nur den fertigen Absatz auf Deutsch aus."""

COVER_LETTER_SYSTEM = """You are a synthetic data generation tool. Generate a fictional cover letter in German. \
The applicant, position, and all details are entirely fictional. Use 'example.com' for emails. \
Never mention that this is synthetic or fictional within the letter text. \
Output only the letter body text (the paragraphs between salutation and closing)."""

COVER_LETTER_USER = """Write the body text (2-4 paragraphs) of a German cover letter for the following fictional applicant, \
applying for the position **{position_title}** at **{organization}**.

## Applicant profile
{applicant_json}

## Job posting context
{job_description}

## Guidelines
- Write in natural, professional German
- Refer specifically to the applicant's qualifications, experience, and motivation
- The letter should feel authentic for a research management application
- Do NOT mention that this is fictional or synthetic
- The applicant's name and contact info will be added automatically by the template
- Output ONLY the body paragraphs, separated by blank lines
- Length: 250-500 words total

## Additional instructions
- FACTS TO DISCLOSE (include these): {facts_to_disclose}
- FACTS TO OMIT (do NOT mention these): {facts_to_omit}
- INTENTIONAL CONTRADICTIONS (include subtly if applicable): {intentional_contradictions}

Output only the body text paragraphs."""

CV_DESCRIPTION_SYSTEM = """You are a synthetic data generation tool. Generate concise, factual descriptions for CV entries \
in German. All details are entirely fictional. Output only the plain text description."""

CV_DESCRIPTION_USER = """For the following applicant profile, generate a short 1-2 sentence description in German \
for each employment entry, explaining responsibilities and achievements. Use professional, factual language.

Applicant: {name}
Employment entries to describe:
{employment_entries}

Output as a JSON object mapping each position to a description string like:
{{"position_key": "description text"}}

Output only the JSON object, no additional text."""

CERTIFICATE_SYSTEM = """You are a synthetic data generation tool. Generate fictional employment certificates \
(Arbeitszeugnisse) in German. All details are entirely fictional. Use formal, letter-style German. \
The certificate should read like an authentic document issued by the employer."""

CERTIFICATE_USER = """Generate a fictional employment certificate (Arbeitszeugnis) in German for:

Applicant: {name}
Position at employer: {position}
Employer: {employer}
Employment period: {period}
Job description: {description}

The certificate should:
1. State the employee's name, birth date, employment period
2. Describe duties and responsibilities
3. Evaluate performance and conduct (use typical German Arbeitszeugnis phrasing)
4. Include closing statement and thanks
5. Be signed by a fictional manager

Output only the certificate text in German, in formal letter style. Do NOT include HTML formatting."""

REFERENCE_LETTER_SYSTEM = """You are a synthetic data generation tool. Generate a fictional reference letter \
(Referenzschreiben) in German. All details are entirely fictional. The letter should be written from the \
perspective of a former supervisor or colleague."""

REFERENCE_LETTER_USER = """Generate a fictional reference letter in German for:

Applicant: {name}
Referee: {referee_name}, {referee_position} at {referee_organization}
Relationship: {relationship}
Known for: {period_known}

The applicant's key strengths include:
{key_strengths}

The letter should:
1. Introduce the referee and their relationship to the applicant
2. Describe the applicant's qualifications and personal qualities
3. Give an overall recommendation
4. Include contact details of the referee

Output only the reference letter text in German. Do NOT include HTML formatting."""
