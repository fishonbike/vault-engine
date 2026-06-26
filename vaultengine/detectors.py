"""Deterministic detectors — the always-on, offline, no-LLM layer.

These catch structured PII that an LLM may paraphrase past or silently miss:
emails, phone numbers, URLs, handles, IP/MAC, government IDs, payment cards
(Luhn-checked), crypto addresses. They run with or without a model and give the
pipeline a reliable floor of coverage.

Every detector returns offset-anchored :class:`~vaultengine.spans.Span` objects,
so overlaps are resolved deterministically by ``spans.merge_overlapping``.
"""

from __future__ import annotations

import re
from typing import List

from .spans import (CAT_CONTACT, CAT_ID, Span)

# (sub-kind, category, compiled pattern). Order is informational only — overlap
# resolution is by offset/length, not declaration order.
_PATTERNS = [
    ("email", CAT_CONTACT,
     re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("url", CAT_CONTACT,
     re.compile(r"(?:https?://|www\.)[^\s<>()\[\]{}　，。]+",
                re.IGNORECASE)),
    ("cn-mobile", CAT_CONTACT, re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("phone-e164", CAT_CONTACT,
     re.compile(r"(?<![\w+])\+\d{1,3}[\s\-]?\d[\d\s\-]{6,}\d(?!\d)")),
    ("handle", CAT_CONTACT, re.compile(r"(?<![\w@./])@[A-Za-z0-9_]{2,30}\b")),
    ("ipv4", CAT_ID,
     re.compile(r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}"
                r"(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])")),
    ("ipv6", CAT_ID,
     re.compile(r"(?<![:\w])(?:[A-Fa-f0-9]{1,4}:){2,7}[A-Fa-f0-9]{1,4}(?![:\w])")),
    ("mac", CAT_ID,
     re.compile(r"(?<![\w:])(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}(?![\w:])")),
    ("cn-id", CAT_ID, re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("crypto-eth", CAT_ID, re.compile(r"\b0x[a-fA-F0-9]{40}\b")),
    ("crypto-btc", CAT_ID,
     re.compile(r"\b(?:bc1[a-z0-9]{25,39}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")),
]

# Payment cards need a checksum, so they get a dedicated pass.
_CARD_CANDIDATE = re.compile(r"(?<![\d\-])(?:\d[ \-]?){13,19}(?![\d\-])")
# Bare long digit runs (account-ish). Low confidence: only tokenized when the
# policy already redacts the `id` category.
_LONG_DIGITS = re.compile(r"(?<!\d)\d{9,}(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def detect(text: str, locale: str = "zh") -> List[Span]:
    """Run every deterministic detector over ``text``; return anchored Spans."""
    if not text:
        return []
    spans: List[Span] = []

    for kind, category, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            spans.append(Span(surface=m.group(0), category=category,
                              source=f"regex:{kind}", confidence=1.0,
                              start=m.start(), end=m.end(), note=kind))

    for m in _CARD_CANDIDATE.finditer(text):
        digits = re.sub(r"[ \-]", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            spans.append(Span(surface=m.group(0), category=CAT_ID,
                              source="regex:card", confidence=1.0,
                              start=m.start(), end=m.end(), note="card"))

    for m in _LONG_DIGITS.finditer(text):
        spans.append(Span(surface=m.group(0), category=CAT_ID,
                          source="regex:digits", confidence=0.5,
                          start=m.start(), end=m.end(), note="digits"))

    return spans
