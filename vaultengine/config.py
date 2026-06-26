"""Runtime configuration.

Resolution order (later wins):
    dataclass defaults  <  JSON config file  <  VAULT_* environment  <  CLI flags

Everything is plain stdlib so the package stays dependency-free.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, Optional

# Redaction policies — see README "脱敏力度 / aggressiveness".
POLICY_BALANCED = "balanced"  # typed reversible tokens; coarse structure kept
POLICY_MAX = "max"            # opaque tokens, dates coarsened — type hidden too
POLICY_LIGHT = "light"        # only persons + explicit PII; context untouched
POLICIES = (POLICY_BALANCED, POLICY_MAX, POLICY_LIGHT)

DEFAULT_MODEL = "qwen3.6:27b"   # the de-identification model, runtime-swappable
DEFAULT_PROVIDER = "ollama"


@dataclass
class Config:
    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    endpoint: str = ""          # provider default used when empty
    api_key: str = ""           # only for remote (openai-compat) providers
    policy: str = POLICY_BALANCED
    locale: str = "zh"          # selects regex sets / prompt language

    use_llm: bool = True        # False => deterministic detectors only (offline)
    critic: bool = True         # residual-risk second LLM pass

    num_ctx: int = 8192         # context window hint passed to local models
    timeout: int = 300          # seconds per model call
    chunk_chars: int = 6000     # long inputs are split for detection
    chunk_overlap: int = 400    # overlap so entities on a boundary aren't lost

    def validate(self) -> "Config":
        if self.policy not in POLICIES:
            raise ValueError(
                f"未知 policy {self.policy!r}（可选 {POLICIES}）")
        if self.chunk_overlap >= self.chunk_chars:
            raise ValueError("chunk_overlap 必须小于 chunk_chars")
        return self

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    # -- layered construction ------------------------------------------------
    @classmethod
    def _field_names(cls) -> set:
        return {f.name for f in fields(cls)}

    @classmethod
    def load(cls, path: Optional[str] = None,
             overrides: Optional[Dict[str, Any]] = None) -> "Config":
        """Build a Config from (optional) file + environment + overrides."""
        data: Dict[str, Any] = {}

        path = path or os.environ.get("VAULT_CONFIG")
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                file_data = json.load(fh)
            data.update({k: v for k, v in file_data.items()
                         if k in cls._field_names()})

        data.update(cls._from_env())

        if overrides:
            data.update({k: v for k, v in overrides.items()
                         if k in cls._field_names() and v is not None})

        return cls(**data).validate()

    @classmethod
    def _from_env(cls) -> Dict[str, Any]:
        names = cls._field_names()
        bool_fields = {"use_llm", "critic"}
        int_fields = {"num_ctx", "timeout", "chunk_chars", "chunk_overlap"}
        out: Dict[str, Any] = {}
        for name in names:
            raw = os.environ.get("VAULT_" + name.upper())
            if raw is None:
                continue
            if name in bool_fields:
                out[name] = raw.strip().lower() in ("1", "true", "yes", "on")
            elif name in int_fields:
                out[name] = int(raw)
            else:
                out[name] = raw
        return out
