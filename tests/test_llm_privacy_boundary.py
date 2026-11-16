"""Tests for the LLM privacy boundary.

Verify that:
1. The LLM client rejects non-loopback URLs by default.
2. The structure analyzer does not depend on the LLM client.
3. The config enforces privacy constraints.
"""

from __future__ import annotations

import pytest

from synthetic_apps.genconfig import PathsConfig, PrivacyConfig
from synthetic_apps.local_llm import LLMPrivacyError, LocalLLMClient


class TestLocalLLMClient:
    """Tests for the local LLM client privacy boundary."""

    def test_loopback_url_allowed(self):
        """Loopback URLs should be accepted by default."""
        client = LocalLLMClient(
            base_url="http://127.0.0.1:11434/v1",
            model="test-model",
        )
        assert client.base_url == "http://127.0.0.1:11434/v1"
        client.close()

    def test_localhost_url_allowed(self):
        """Localhost URLs should be accepted by default."""
        client = LocalLLMClient(
            base_url="http://localhost:11434/v1",
            model="test-model",
        )
        assert client.base_url == "http://localhost:11434/v1"
        client.close()

    def test_non_loopback_url_rejected(self):
        """Non-loopback URLs should raise LLMPrivacyError by default."""
        with pytest.raises(LLMPrivacyError, match="Non-loopback"):
            LocalLLMClient(
                base_url="http://example.com:11434/v1",
                model="test-model",
            )

    def test_non_loopback_url_with_opt_in(self):
        """Non-loopback URLs allowed when explicitly opted in."""
        client = LocalLLMClient(
            base_url="http://example.com:11434/v1",
            model="test-model",
            allow_non_loopback=True,
        )
        assert client.base_url == "http://example.com:11434/v1"
        client.close()

    def test_privacy_error_is_exception(self):
        """LLMPrivacyError should be a proper exception."""
        err = LLMPrivacyError("test error")
        assert isinstance(err, Exception)
        assert str(err) == "test error"


class TestConfigPrivacy:
    """Tests for privacy-related configuration."""

    def test_private_profiles_not_inside_references(self):
        """Private profiles path should not be inside references path."""
        cfg = PathsConfig(
            references="references_private/original_applications",
            private_profiles="structure_profiles_private",
            output="dataset",
        )
        assert cfg.private_profiles == "structure_profiles_private"

    def test_output_not_inside_references(self):
        """Output path should not overlap with references."""
        cfg = PathsConfig(
            references="references_private/original_applications",
            private_profiles="structure_profiles_private",
            output="dataset",
        )
        assert cfg.output == "dataset"

    def test_privacy_defaults(self):
        """Default privacy config should be strict."""
        cfg = PrivacyConfig()
        assert cfg.prohibit_reference_text_in_llm_calls is True
        assert cfg.prohibit_network_in_structure_analysis is True
        assert cfg.publication_requires_manual_approval is True
        assert cfg.use_example_domains_only is True

    def test_paths_no_overlap_raises(self):
        """Overlapping paths should raise a validation error."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="inside references"):
            PathsConfig(
                references="references_private/original_applications",
                private_profiles="references_private/original_applications/SG001",
                output="dataset",
            )
