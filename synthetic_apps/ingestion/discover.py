from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiscoveredDossier:
    relative_path: str
    files: tuple[Path, ...]


def discover_dossiers(input_dir: Path, ocr_dir: Path | None = None) -> list[DiscoveredDossier]:
    """Discover nested dossier directories without using names as identities."""
    pdfs = sorted(input_dir.rglob("*.pdf"))
    grouped: dict[Path, list[Path]] = {}
    for pdf in pdfs:
        rel = pdf.relative_to(input_dir)
        dossier = Path(rel.parts[0]) if len(rel.parts) > 1 else Path("root")
        grouped.setdefault(dossier, []).append(pdf)
    return [
        DiscoveredDossier(str(dossier), tuple(files))
        for dossier, files in sorted(grouped.items(), key=lambda item: str(item[0]))
    ]
