"""Strict loopback-only adapter for an optional local OpenAI-compatible model."""

from __future__ import annotations

import json
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class LocalModelError(RuntimeError):
    pass


class LocalModelClient:
    def __init__(self, endpoint: str, *, timeout: int = 180):
        parsed = urlparse(endpoint)
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("local model endpoint must resolve to loopback")
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("local model endpoint must be HTTP(S)")
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    def chat_json(self, *, model: str, system: str, user: str) -> dict:
        payload = {"model": model, "temperature": 0, "response_format": {"type": "json_object"}, "messages": [
            {"role": "system", "content": system}, {"role": "user", "content": user}
        ]}
        request = Request(self.endpoint + "/chat/completions", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as exc:
            raise LocalModelError("local model request failed; no remote fallback is permitted") from exc
