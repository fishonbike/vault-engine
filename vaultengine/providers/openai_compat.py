"""OpenAI-compatible provider — opt-in, for any /v1/chat/completions endpoint.

Covers hosted OpenAI, OpenRouter, vLLM, LM Studio, Ollama's OpenAI shim, etc.

PRIVACY WARNING: this provider sends the *raw, un-redacted* text to whatever
endpoint you configure — it is the detector, so it must see the original. Only
use it against an endpoint you trust as much as the data. The whole point of the
default local provider is to avoid exactly this. A warning is printed to stderr
on construction.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

from ..config import Config
from .base import Provider, ProviderError, register

DEFAULT_ENDPOINT = "https://api.openai.com/v1"


class OpenAICompatProvider(Provider):
    name = "openai-compat"
    is_remote = True

    def __init__(self, config: Config):
        super().__init__(config)
        self.endpoint = (config.endpoint or DEFAULT_ENDPOINT).rstrip("/")
        self.api_key = config.api_key
        print(
            "⚠️  vault-engine: provider 'openai-compat' 会把【未脱敏的原文】发送到 "
            f"{self.endpoint}。\n    仅在你完全信任该端点时使用；默认的本地 'ollama' "
            "provider 才能保证检测过程不出本机。",
            file=sys.stderr)

    def complete(self, prompt: str) -> str:
        payload = json.dumps({
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(
            self.endpoint + "/chat/completions", data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError) as exc:
            raise ProviderError(
                f"OpenAI 兼容端点调用失败（{self.endpoint}）：{exc}") from exc


@register("openai-compat")
def _factory(config: Config) -> Provider:
    return OpenAICompatProvider(config)
