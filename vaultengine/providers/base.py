"""Provider protocol + registry — the swappable-LLM seam.

A provider only has to implement :meth:`Provider.complete` (prompt -> text). The
base class turns that into the two operations the pipeline needs — ``detect`` and
``critique`` — including chunking long inputs and tolerantly parsing the model's
JSON. Swapping qwen3.6:27b for any other model is a one-line config change.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List

from .. import prompts
from ..config import Config
from ..spans import Span, normalize_category

class ProviderError(Exception):
    """A model backend was requested but failed (unreachable, bad reply, …).

    Raised so the pipeline can record that LLM detection did NOT run and warn
    loudly — silently shipping regex-only output would be under-redacted.
    """


_REGISTRY: Dict[str, Callable[[Config], "Provider"]] = {}


def register(name: str):
    def deco(factory: Callable[[Config], "Provider"]):
        _REGISTRY[name] = factory
        return factory
    return deco


def available() -> List[str]:
    return sorted(_REGISTRY)


def get_provider(config: Config) -> "Provider":
    name = config.provider
    if name not in _REGISTRY:
        raise ValueError(
            f"未知 provider {name!r}（可用：{available()}）")
    return _REGISTRY[name](config)


# --- tolerant JSON-array extraction --------------------------------------
def parse_json_array(raw: str) -> List[Any]:
    """Pull the first balanced JSON array out of a model reply.

    Models wrap output in prose or ``` fences despite instructions; this scans
    for the first '[' and its matching ']' (string-aware) and parses that.
    Returns [] on any failure — detection degrades, it never crashes.
    """
    if not raw:
        return []
    text = raw.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start = text.find("[")
    if start == -1:
        return []
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    val = json.loads(text[start:i + 1])
                    return val if isinstance(val, list) else []
                except (ValueError, TypeError):
                    return []
    return []


class Provider:
    name = "base"
    is_remote = False   # True => sends text off-machine; pipeline warns loudly

    def __init__(self, config: Config):
        self.config = config

    # subclasses implement this one method
    def complete(self, prompt: str) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    # -- chunking ------------------------------------------------------------
    def _chunks(self, text: str) -> List[str]:
        size = max(512, self.config.chunk_chars)
        overlap = max(0, min(self.config.chunk_overlap, size - 1))
        if len(text) <= size:
            return [text]
        out, i = [], 0
        while i < len(text):
            out.append(text[i:i + size])
            if i + size >= len(text):
                break
            i += size - overlap
        return out

    # -- high-level operations ----------------------------------------------
    def detect(self, text: str) -> List[Span]:
        if not text or not text.strip():
            return []
        spans: List[Span] = []
        for chunk in self._chunks(text):
            raw = self.complete(prompts.detect_prompt(chunk, self.config.locale))
            for item in parse_json_array(raw):
                span = self._span_from(item)
                if span is not None:
                    spans.append(span)
        return spans

    def critique(self, text: str) -> List[Dict[str, str]]:
        if not text or not text.strip():
            return []
        findings: List[Dict[str, str]] = []
        for chunk in self._chunks(text):
            raw = self.complete(prompts.critic_prompt(chunk, self.config.locale))
            for item in parse_json_array(raw):
                if isinstance(item, dict) and item.get("quote"):
                    findings.append({
                        "quote": str(item.get("quote", "")),
                        "category": normalize_category(item.get("category", "")),
                        "why": str(item.get("why", "")),
                    })
        return findings

    @staticmethod
    def _span_from(item: Any):
        if not isinstance(item, dict):
            return None
        surface = (item.get("surface") or "").strip()
        if not surface:
            return None
        aliases = tuple(
            a.strip() for a in (item.get("aliases") or [])
            if isinstance(a, str) and a.strip())
        try:
            conf = float(item.get("confidence", 0.8))
        except (TypeError, ValueError):
            conf = 0.8
        return Span(surface=surface,
                    category=normalize_category(item.get("category", "")),
                    source="llm", confidence=max(0.0, min(1.0, conf)),
                    aliases=aliases)
