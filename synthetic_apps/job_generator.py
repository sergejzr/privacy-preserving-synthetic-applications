"""Generates fictional job description and extra attributes for the Stargate Initiative.

Phase B implementation: uses local LLM to create a coherent German-language
job posting for the fictional Interplanetary Research Directorate.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .genconfig import Config
from .local_llm import LocalLLMClient
from .prompts import (
    EXTRA_ATTRIBUTES_SYSTEM,
    EXTRA_ATTRIBUTES_USER,
    JOB_DESCRIPTION_SYSTEM,
    JOB_DESCRIPTION_USER,
    PROMPTS_VERSION,
)


def generate_job_description(
    cfg: Config,
    output_dir: str | Path,
    client: LocalLLMClient | None = None,
    manifest: dict[str, Any] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Generate a fictional job posting and extra attributes.

    Args:
        cfg: Full configuration.
        output_dir: Directory to write output files (stellenbeschreibungen/).
        client: Optional pre-configured LLM client. Creates one if None.
        manifest: Optional dict to populate with generation metadata.

    Returns:
        Tuple of (job_description_text, extra_attributes_text, manifest).
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if manifest is None:
        manifest = {}
    manifest["prompts_version"] = PROMPTS_VERSION
    manifest["phase"] = "B"
    manifest["scenario"] = cfg.scenario.model_dump()

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

    try:
        # --- Generate job description ---
        job_system = JOB_DESCRIPTION_SYSTEM
        job_user = JOB_DESCRIPTION_USER.format(
            organization=cfg.scenario.organization,
            title=cfg.scenario.title,
            language=cfg.scenario.language,
            fictional_universe=cfg.scenario.fictional_universe,
        )

        manifest["job_description_prompt"] = {
            "system": job_system[:100],
            "user": job_user[:200],
        }

        job_resp = client.chat(
            [
                {"role": "system", "content": job_system},
                {"role": "user", "content": job_user},
            ],
            max_tokens=32768,
        )
        job_text = job_resp["choices"][0]["message"].get("content", "")
        manifest["job_description_usage"] = job_resp.get("usage", {})

        # Ensure non-empty
        if not job_text.strip():
            raise RuntimeError("LLM returned empty job description")

        # Keep a machine-checkable marker even when the local model omits it.
        marker = "Synthetic fictional test data — not a real applicant"
        if marker.lower() not in job_text.lower():
            job_text = job_text.rstrip() + "\n\n---\n\n" + marker

        # Write stellenbeschreibung.md
        stellen_path = output_path / "stellenbeschreibung.md"
        stellen_path.write_text(job_text.strip() + "\n")
        manifest["job_description_path"] = str(stellen_path)

        # --- Generate extra attributes ---
        attr_system = EXTRA_ATTRIBUTES_SYSTEM
        attr_user = EXTRA_ATTRIBUTES_USER.format(job_description=job_text)

        manifest["extra_attributes_prompt"] = {
            "system": attr_system[:100],
            "user": attr_user[:200],
        }

        attr_resp = client.chat(
            [
                {"role": "system", "content": attr_system},
                {"role": "user", "content": attr_user},
            ],
            max_tokens=8192,
        )
        attr_text = attr_resp["choices"][0]["message"].get("content", "")
        manifest["extra_attributes_usage"] = attr_resp.get("usage", {})

        # Write extra_attributes.txt in dataset root (parent of stellenbeschreibungen/)
        extra_path = output_path.parent / "extra_attributes.txt"
        extra_path.write_text(attr_text.strip() + "\n")
        manifest["extra_attributes_path"] = str(extra_path)

        return job_text, attr_text, manifest

    finally:
        if close_client and client:
            client.close()
