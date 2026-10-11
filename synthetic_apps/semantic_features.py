"""Coarsened, deterministic semantic signals.

Text is inspected ephemerally and only taxonomy codes are returned. No text,
names, institutions, dates, or quotations are persisted.
"""

from __future__ import annotations

import re

TAXONOMY: dict[str, dict[str, tuple[str, ...]]] = {
    "discipline": {
        "computer_science": ("informatik", "software", "programmier", "algorithm", "python", "java", "c++", "datenbank"),
        "biology": ("biologie", "biolog", "zelle", "genom", "ökologie", "molekular", "mikrobi"),
        "physics": ("physik", "quanten", "teilchen", "mechanik", "optik", "astronom"),
        "chemistry": ("chemie", "molekül", "synthese", "spektroskop"),
        "engineering": ("ingenieur", "konstruktion", "maschinenbau", "elektrotechnik", "automatisierung"),
        "social_sciences": ("soziolog", "politik", "governance", "gesellschaft", "ökonom", "wirtschaft"),
        "humanities": ("geschichte", "sprach", "kultur", "philosoph", "literatur"),
        "medicine": ("medizin", "klinisch", "patient", "diagnost", "gesundheit"),
    },
    "skill_family": {
        "programming": ("python", "java", "c++", "r-programm", "sql", "programmier", "softwareentwicklung"),
        "data_analysis": ("datenanalyse", "machine learning", "statistik", "modellierung", "ki", "data science"),
        "laboratory": ("labor", "assay", "pcr", "zellkultur", "sequenzier", "experiment"),
        "project_management": ("projektleitung", "projektmanagement", "meilenstein", "portfolio", "risiko"),
        "funding": ("drittmittel", "fördermittel", "grant", "antrag", "budget"),
        "communication": ("stakeholder", "kommunikation", "präsentation", "publikation", "bericht"),
        "leadership": ("leitung", "teamleitung", "führung", "personalverantwortung"),
    },
}


def extract_taxonomy_codes(text: str) -> dict[str, list[str]]:
    lowered = text.casefold()
    result: dict[str, list[str]] = {}
    for family, codes in TAXONOMY.items():
        found = []
        for code, keywords in codes.items():
            if any(re.search(r"(?<!\w)" + re.escape(keyword) + r"", lowered) for keyword in keywords):
                found.append(code)
        result[family] = sorted(found)
    return result
