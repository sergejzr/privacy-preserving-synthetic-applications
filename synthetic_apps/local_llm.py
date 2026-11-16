"""Local LLM client with an OpenAI-compatible API.

Enforces loopback-only URL policy by default.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class LLMPrivacyError(Exception):
    """Raised when an LLM operation would violate privacy policy."""


class LocalLLMClient:
    """Client for a local OpenAI-compatible LLM endpoint.

    By default, only loopback addresses are allowed. This prevents
    accidental data leakage to external services.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434/v1",
        model: str = "",
        api_key: str = "local-only-placeholder",
        timeout_seconds: int = 180,
        max_retries: int = 3,
        temperature: float = 0.7,
        allow_non_loopback: bool = False,
        trusted_hosts: set[str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.temperature = temperature
        self.trusted_hosts = trusted_hosts or set()

        if not allow_non_loopback:
            self._check_loopback()

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def _check_loopback(self):
        """Verify the base URL points to a loopback address."""
        import urllib.parse

        parsed = urllib.parse.urlparse(self.base_url)
        host = parsed.hostname or ""
        if host not in ("127.0.0.1", "localhost", "::1") and host not in self.trusted_hosts:
            raise LLMPrivacyError(
                f"Non-loopback LLM endpoint '{self.base_url}' is not loopback or explicitly trusted. "
                "Add its hostname to the configured trusted_hosts only after local policy approval."
            )

    def chat(self, messages: list[dict], **kwargs) -> dict[str, Any]:
        """Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            **kwargs: Overrides for default parameters.

        Returns:
            The JSON response from the API.

        Raises:
            httpx.HTTPError: On connection or response errors.
        """
        body = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        response = self._client.post("/chat/completions", json=body)
        response.raise_for_status()
        return response.json()

    def close(self):
        self._client.close()
