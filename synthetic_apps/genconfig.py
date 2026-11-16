"""Configuration management for the synthetic generator."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator


class ScenarioConfig(BaseModel):
    title: str = "Research Program Manager (m/f/d) — Stargate Initiative"
    organization: str = "Interplanetary Research Directorate"
    language: str = "de"
    fictional_universe: str = "Original fictional science-fiction setting"


class DifficultyDistribution(BaseModel):
    strong_match: float = 0.20
    moderate_match: float = 0.35
    weak_match: float = 0.15
    career_changer: float = 0.10
    early_career: float = 0.10
    incomplete_or_inconsistent: float = 0.10

    @model_validator(mode="after")
    def check_sum(self):
        total = sum(
            v for v in [
                self.strong_match,
                self.moderate_match,
                self.weak_match,
                self.career_changer,
                self.early_career,
                self.incomplete_or_inconsistent,
            ]
        )
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"difficulty_distribution probabilities sum to {total}, expected 1.0")
        return self


class GenerationConfig(BaseModel):
    seed: int = 20261008
    applicant_count: int = Field(default=20, ge=1)
    difficulty_distribution: DifficultyDistribution = Field(default_factory=DifficultyDistribution)
    min_documents: int = Field(default=1, ge=1)
    max_documents: int = Field(default=5, ge=1)
    pdf_layouts: list[str] = Field(default_factory=lambda: ["standard", "two_column", "tables"])
    include_scanned_like_pdf_probability: float = 0.10
    include_merged_pdf_probability: float = 0.15
    include_multilingual_probability: float = 0.20

    @model_validator(mode="after")
    def check_document_range(self):
        if self.min_documents > self.max_documents:
            raise ValueError("min_documents must be <= max_documents")
        return self

    @model_validator(mode="after")
    def check_probabilities(self):
        for field_name in [
            "include_scanned_like_pdf_probability",
            "include_merged_pdf_probability",
            "include_multilingual_probability",
        ]:
            val = getattr(self, field_name)
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"{field_name} must be between 0 and 1, got {val}")
        return self


class LLMConfig(BaseModel):
    base_url_env: str = "SYNTH_LLM_BASE_URL"
    model_env: str = "SYNTH_LLM_MODEL"
    api_key_env: str = "SYNTH_LLM_API_KEY"
    timeout_seconds: int = Field(default=180, ge=1)
    max_retries: int = Field(default=3, ge=0)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    trusted_hosts: list[str] = Field(default_factory=list)
    trusted_hosts_env: str = "SYNTH_LLM_TRUSTED_HOSTS"


class PathsConfig(BaseModel):
    references: str = "references_private/original_applications"
    private_profiles: str = "structure_profiles_private"
    output: str = "dataset"
    structural_model: str | None = None

    @model_validator(mode="after")
    def check_no_overlap(self):
        ref = Path(self.references).resolve()
        for name, val in [("output", self.output), ("private_profiles", self.private_profiles)]:
            p = Path(val).resolve()
            try:
                p.relative_to(ref)
            except ValueError:
                pass
            else:
                raise ValueError(
                    f"{name} path '{val}' is inside references path '{self.references}'"
                )
        return self


class PrivacyConfig(BaseModel):
    prohibit_reference_text_in_llm_calls: bool = True
    prohibit_network_in_structure_analysis: bool = True
    publication_requires_manual_approval: bool = True
    use_example_domains_only: bool = True


class Config(BaseModel):
    scenario: ScenarioConfig = Field(default_factory=ScenarioConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> Config:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    @classmethod
    def from_env_defaults(cls) -> Config:
        return cls()

    def resolve_llm_settings(self) -> dict[str, Any]:
        """Resolve LLM settings from environment variables."""
        base_url = os.environ.get(self.llm.base_url_env, "http://127.0.0.1:11434/v1")
        model = os.environ.get(self.llm.model_env, "")
        api_key = os.environ.get(self.llm.api_key_env, "local-only-placeholder")
        trusted_hosts = list(self.llm.trusted_hosts)
        env_hosts = os.environ.get(self.llm.trusted_hosts_env, "")
        trusted_hosts.extend(h.strip() for h in env_hosts.split(",") if h.strip())
        return {
            "base_url": base_url,
            "model": model,
            "api_key": api_key,
            "timeout_seconds": self.llm.timeout_seconds,
            "max_retries": self.llm.max_retries,
            "temperature": self.llm.temperature,
            "trusted_hosts": set(trusted_hosts),
        }
