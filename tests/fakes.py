"""Deterministic fake providers for tests — no network, no Ollama.

``FakeProvider`` plays the role of qwen3.6:27b: it "detects" a fixed cast of
synthetic people/orgs/places by substring, and its critic re-flags any of those
real surfaces that survive into the sanitized text. ``RaisingProvider`` models a
backend that is unreachable, to exercise the degraded path.
"""

from __future__ import annotations

from typing import Dict, List

from vaultengine.config import Config
from vaultengine.providers.base import Provider, ProviderError
from vaultengine.spans import (CAT_LOCATION, CAT_ORG, CAT_PERSON, CAT_ROLE, Span)

# All synthetic. None of this is real data.
PEOPLE = {"张三": ["小张"], "李四": [], "老王": []}
ORGS = ["蚂蚁集团", "Acme Capital"]
LOCS = ["杭州"]
ROLES = ["风控总监"]
IDENTITY_SURFACES = list(PEOPLE) + [a for al in PEOPLE.values() for a in al] \
    + ORGS + LOCS + ROLES


class FakeProvider(Provider):
    name = "fake"
    is_remote = False

    def detect(self, text: str) -> List[Span]:
        spans: List[Span] = []
        for name, aliases in PEOPLE.items():
            present = [s for s in [name] + aliases if s in text]
            if present:
                spans.append(Span(surface=name, category=CAT_PERSON,
                                  source="llm", confidence=0.95,
                                  aliases=tuple(a for a in aliases if a in text)))
        for org in ORGS:
            if org in text:
                spans.append(Span(org, CAT_ORG, source="llm", confidence=0.9))
        for loc in LOCS:
            if loc in text:
                spans.append(Span(loc, CAT_LOCATION, source="llm", confidence=0.9))
        for role in ROLES:
            if role in text:
                spans.append(Span(role, CAT_ROLE, source="llm", confidence=0.85))
        return spans

    def critique(self, text: str) -> List[Dict[str, str]]:
        return [{"quote": s, "category": "person", "why": "real surface leaked"}
                for s in IDENTITY_SURFACES if s in text]


class RaisingProvider(Provider):
    name = "raising"

    def complete(self, prompt: str) -> str:  # pragma: no cover
        raise ProviderError("backend unreachable (test)")

    def detect(self, text: str):
        raise ProviderError("backend unreachable (test)")


def fake_config(**kw) -> Config:
    base = dict(provider="fake", policy="balanced", use_llm=True, critic=True)
    base.update(kw)
    return Config(**base)
