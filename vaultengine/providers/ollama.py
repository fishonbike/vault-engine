"""Local Ollama provider — the default, fully offline-capable backend.

Talks to a local Ollama daemon over ``urllib`` (no third-party SDK). Default
model is qwen3.6:27b, swappable at runtime via config/CLI. Because the daemon
listens on localhost, the de-identification model itself never leaves the
machine — only the *sanitized* text is later handed to a cloud model, by you.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import List

from ..config import Config
from .base import Provider, ProviderError, register

DEFAULT_ENDPOINT = "http://localhost:11434"


class OllamaProvider(Provider):
    name = "ollama"
    is_remote = False

    def __init__(self, config: Config):
        super().__init__(config)
        self.endpoint = (config.endpoint or DEFAULT_ENDPOINT).rstrip("/")

    def complete(self, prompt: str) -> str:
        payload = json.dumps({
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            # Detection is structured extraction — no chain-of-thought needed.
            # Disabling it cuts latency/tokens on reasoning models (Qwen3.x);
            # ignored by models without a thinking mode.
            "think": False,
            "options": {"num_ctx": self.config.num_ctx, "temperature": 0},
        }).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint + "/api/generate", data=payload,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ProviderError(
                f"Ollama 不可达或返回异常（{self.endpoint}，模型 "
                f"{self.config.model}）：{exc}") from exc
        return data.get("response", "")


def installed_models(endpoint: str = DEFAULT_ENDPOINT, timeout: int = 5) -> List[str]:
    """Best-effort list of locally installed model tags ('/api/tags')."""
    try:
        req = urllib.request.Request(endpoint.rstrip("/") + "/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return sorted(m.get("name", "") for m in data.get("models", []))
    except Exception:  # noqa: BLE001 - listing is advisory only
        return []


@register("ollama")
def _factory(config: Config) -> Provider:
    return OllamaProvider(config)
