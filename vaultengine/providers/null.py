"""Null provider — deterministic, offline, zero model calls.

Returns no LLM detections, so the pipeline runs on the regex layer alone. This
is the backend used when ``use_llm=False`` and the default in tests, so the test
suite needs no network and no Ollama. It is a safe floor, not a full
de-identifier: without a model, only structured PII is caught.
"""

from __future__ import annotations

from ..config import Config
from .base import Provider, register


class NullProvider(Provider):
    name = "null"
    is_remote = False

    def complete(self, prompt: str) -> str:
        return "[]"


@register("null")
def _factory(config: Config) -> Provider:
    return NullProvider(config)
