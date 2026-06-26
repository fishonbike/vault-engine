"""The Vault — consistent pseudonymization and the reversible mapping.

Every distinct entity surface becomes a stable placeholder token; the same
surface (and its aliases) always maps to the same token across the whole
document. The token → real-surface table is the *reverse map*: it is what lets a
cloud reply that references the tokens be translated back into real identities
for use back in your own system.

SECURITY: the reverse map IS the identity. It stays local, is written only to a
``*.map.json`` sidecar, and must never be sent to a cloud model. ``.gitignore``
excludes it by default.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional

from . import config as cfg
from .spans import (CAT_CONTACT, CAT_DATE, CAT_ID, CAT_PERSON, Span)

MAP_VERSION = 1

# Token namespace per category (balanced/light: type is preserved in the name).
_PREFIX = {
    "org": "ORG", "location": "LOC", "role": "ROLE", "project": "PROJ",
    "date": "DATE", "id": "ID", "other": "X",
}
# contact sub-kinds get their own readable prefix.
_CONTACT_PREFIX = {
    "email": "EMAIL", "url": "URL", "handle": "HANDLE",
    "cn-mobile": "PHONE", "phone-e164": "PHONE",
}
PERSON_NEW_PREFIX = "P-n"     # new person token; the '-n' keeps it distinct from
                              # any pre-existing 'P-<number>' placeholder in input.
OPAQUE_PREFIX = "R"           # policy=max: type-hiding opaque token

# Strings already shaped like a placeholder token — never re-tokenize these.
_TOKEN_LIKE = re.compile(
    r"^(?:P-n?\d+|ORG_\d+|LOC_\d+|ROLE_\d+|PROJ_\d+|DATE_\d+|ID_\d+|X_\d+|"
    r"EMAIL_\d+|URL_\d+|HANDLE_\d+|PHONE_\d+|CONTACT_\d+|R_\d+)$")


def is_token_like(surface: str) -> bool:
    return bool(_TOKEN_LIKE.match((surface or "").strip()))


def _norm(surface: str) -> str:
    return " ".join((surface or "").split()).strip().casefold()


class Vault:
    def __init__(self, policy: str = cfg.POLICY_BALANCED,
                 reserved: Optional[Iterable[str]] = None):
        self.policy = policy
        self._by_norm: Dict[str, str] = {}            # norm surface -> token
        self._tokens: Dict[str, Dict[str, Any]] = {}  # token -> entry
        self._counters: Dict[str, int] = {}
        self.reserved = set(reserved or ())           # left verbatim, untouched

    # -- token allocation ----------------------------------------------------
    def _prefix_for(self, category: str, kind: str) -> str:
        if self.policy == cfg.POLICY_MAX:
            return OPAQUE_PREFIX
        if category == CAT_PERSON:
            return PERSON_NEW_PREFIX
        if category == CAT_CONTACT:
            return _CONTACT_PREFIX.get(kind, "CONTACT")
        return _PREFIX.get(category, "X")

    def _new_token(self, category: str, kind: str) -> str:
        prefix = self._prefix_for(category, kind)
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        sep = "" if prefix == PERSON_NEW_PREFIX else "_"
        return f"{prefix}{sep}{self._counters[prefix]}"

    def token_for(self, surface: str, category: str, kind: str = "",
                  aliases: Iterable[str] = ()) -> Optional[str]:
        """Stable token for one entity; registers aliases to the same token."""
        surface = (surface or "").strip()
        if len(surface) < 2 or is_token_like(surface) or surface in self.reserved:
            return None
        norm = _norm(surface)
        if norm in self._by_norm:
            token = self._by_norm[norm]
        else:
            token = self._new_token(category, kind)
            self._by_norm[norm] = token
            self._tokens[token] = {"surface": surface, "category": category,
                                   "kind": kind, "count": 0, "aliases": []}
        for alias in aliases:
            alias = (alias or "").strip()
            if len(alias) >= 2 and not is_token_like(alias):
                self._by_norm.setdefault(_norm(alias), token)
                rec = self._tokens[token]["aliases"]
                if alias != surface and alias not in rec:
                    rec.append(alias)
        return token

    # -- which categories are redacted under each policy ---------------------
    def _redacts(self, span: Span) -> bool:
        if span.category == CAT_PERSON:
            return True                      # persons: always, in every policy
        if self.policy == cfg.POLICY_LIGHT:
            # only explicit machine PII (contact/id) beyond persons
            return span.category in (CAT_CONTACT, CAT_ID)
        if span.category == CAT_DATE:
            return self.policy == cfg.POLICY_MAX   # balanced keeps dates
        if span.category == CAT_ID and span.note == "digits":
            # bare digit runs are low-confidence; only redact under max
            return self.policy == cfg.POLICY_MAX
        return True                          # balanced/max: everything else

    def assign(self, spans: List[Span]) -> Dict[str, str]:
        """Allocate tokens for the redactable spans; return surface -> token."""
        pairs: Dict[str, str] = {}
        # longest surface first => deterministic, alias-before-substring safe
        for span in sorted(spans, key=lambda s: len(s.surface or ""), reverse=True):
            if not self._redacts(span):
                continue
            token = self.token_for(span.surface, span.category, span.note,
                                   span.aliases)
            if token:
                pairs[span.surface] = token
                for alias in span.aliases:
                    if len((alias or "").strip()) >= 2:
                        pairs[alias] = token
        return pairs

    # -- text transforms -----------------------------------------------------
    def apply(self, text: str, pairs: Optional[Dict[str, str]] = None) -> str:
        """Replace every known surface with its token (longest surface first)."""
        if not text:
            return text
        pairs = pairs if pairs is not None else self.replacement_pairs()
        for surface in sorted(pairs, key=len, reverse=True):
            if surface and surface in text:
                token = pairs[surface]
                # Check if first and last characters are ASCII alphanumeric or underscore
                first = surface[0]
                last = surface[-1]
                is_ascii_word = (
                    ("a" <= first <= "z" or "A" <= first <= "Z" or "0" <= first <= "9" or first == "_") and
                    ("a" <= last <= "z" or "A" <= last <= "Z" or "0" <= last <= "9" or last == "_")
                )
                if is_ascii_word:
                    pattern = re.compile(r"\b" + re.escape(surface) + r"\b")
                    text = pattern.sub(token, text)
                else:
                    text = text.replace(surface, token)
        return text

    def replacement_pairs(self) -> Dict[str, str]:
        pairs: Dict[str, str] = {}
        for token, entry in self._tokens.items():
            pairs[entry["surface"]] = token
            for alias in entry["aliases"]:
                pairs[alias] = token
        return pairs

    def count_hits(self, text: str) -> None:
        """Record how many times each token now appears (for the report)."""
        for token, entry in self._tokens.items():
            entry["count"] = text.count(token)

    # -- reverse (rehydrate) -------------------------------------------------
    def _reverse_regex(self):
        toks = sorted(self._tokens, key=len, reverse=True)
        if not toks:
            return None
        alt = "|".join(re.escape(t) for t in toks)
        return re.compile(r"(?<![A-Za-z0-9_])(?:" + alt + r")(?![A-Za-z0-9_])")

    def rehydrate_text(self, text: str) -> str:
        rx = self._reverse_regex()
        if rx is None or not text:
            return text
        return rx.sub(lambda m: self._tokens[m.group(0)]["surface"], text)

    def rehydrate(self, obj: Any) -> Any:
        """Recursively replace tokens with real surfaces in any JSON-ish value."""
        if isinstance(obj, str):
            return self.rehydrate_text(obj)
        if isinstance(obj, list):
            return [self.rehydrate(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self.rehydrate(v) for k, v in obj.items()}
        return obj

    # -- persistence ---------------------------------------------------------
    def to_map(self) -> Dict[str, Any]:
        return {"vaultengine_map_version": MAP_VERSION, "policy": self.policy,
                "tokens": self._tokens}

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_map(), fh, ensure_ascii=False, indent=2)

    @classmethod
    def from_map(cls, data: Dict[str, Any]) -> "Vault":
        v = cls(policy=data.get("policy", cfg.POLICY_BALANCED))
        v._tokens = dict(data.get("tokens", {}))
        for token, entry in v._tokens.items():
            v._by_norm[_norm(entry["surface"])] = token
            for alias in entry.get("aliases", []):
                v._by_norm[_norm(alias)] = token
        return v

    @classmethod
    def load(cls, path: str) -> "Vault":
        with open(path, encoding="utf-8") as fh:
            return cls.from_map(json.load(fh))

    @property
    def tokens(self) -> Dict[str, Dict[str, Any]]:
        return self._tokens
