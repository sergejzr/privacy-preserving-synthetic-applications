"""Release packaging with allowlist-based filtering.

Only approved files are included in the release archive.
Fails closed if unexpected files are found.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any


RELEASE_ALLOWLIST = [
    "applications_pdf/SG*/CV.pdf",
    "applications_pdf/SG*/Cover_Letter.pdf",
    "applications_pdf/SG*/Certificates.pdf",
    "applications_pdf/SG*/Reference_Letter.pdf",
    "stellenbeschreibungen/stellenbeschreibung.md",
    "extra_attributes.txt",
    "ground_truth/applicants.json",
    "ground_truth/document_evidence.json",
    "DATASET_CARD.md",
    "generation_manifest.json",
]


def create_release_archive(
    dataset: str | Path,
    output: str | Path,
    manifest: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> str:
    """Create a publication-ready release archive with allowlist filtering.

    Args:
        dataset: Path to the dataset/ directory.
        output: Path for the output .zip archive.
        manifest: Optional manifest dict to update.
        dry_run: If True, only list what would be included without creating archive.

    Returns:
        Path to the created archive (or listing if dry_run).
    """
    dataset_path = Path(dataset)
    output_path = Path(output)

    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset directory not found: {dataset_path}")

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # Collect all files that match the allowlist
    release_files: list[tuple[Path, str]] = []
    unexpected_files: list[str] = []

    for f in sorted(dataset_path.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(dataset_path)
        rel_str = str(rel)

        # Check against allowlist patterns
        from fnmatch import fnmatch
        matched = any(fnmatch(rel_str, p) for p in RELEASE_ALLOWLIST)

        if matched:
            release_files.append((f, rel_str))
        else:
            unexpected_files.append(rel_str)

    # Fail closed if unexpected files found
    if unexpected_files and not dry_run:
        file_list = "\n  ".join(unexpected_files)
        raise RuntimeError(
            f"Unexpected files in dataset directory ({len(unexpected_files)}):\n  {file_list}\n"
            "Remove these files or add them to the allowlist."
        )

    if dry_run:
        lines = [f"Release archive would include {len(release_files)} files:"]
        for _, rel in release_files:
            lines.append(f"  {rel}")
        if unexpected_files:
            lines.append(f"\n{len(unexpected_files)} unexpected files would be EXCLUDED:")
            for uf in unexpected_files:
                lines.append(f"  (excluded) {uf}")
        return "\n".join(lines)

    # Create ZIP archive
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path, rel_path in release_files:
            zf.write(file_path, rel_path)

    # Update manifest
    if manifest is not None:
        manifest["release_archive"] = str(output_path.resolve())
        manifest["release_file_count"] = len(release_files)
        manifest["release_allowlist"] = sorted(RELEASE_ALLOWLIST)

        manifest_path = dataset_path / "generation_manifest.json"
        if manifest_path.exists():
            existing = json.loads(manifest_path.read_text())
            existing.update(manifest)
            tmp = manifest_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
            tmp.rename(manifest_path)

    return str(output_path.resolve())
