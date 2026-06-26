"""Orchestration — defense-in-depth de-identification and the reverse path.

forward:  text ──▶ regex detectors ──▶ LLM detector ──▶ Vault (consistent
          tokens) ──▶ sanitized text  ──▶ LLM residual-risk critic ──▶ report

reverse:  cloud reply (references the tokens) ──▶ Vault reverse map ──▶ real
          identities restored locally, ready to use in your own system.

The Vault's reverse map stays local; only ``Result.text`` is meant to leave.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

from . import detectors, report as report_mod
from .config import Config
from .mapping import Vault, is_token_like
from .providers import ProviderError, get_provider
from .providers.base import Provider
from .spans import Span, merge_overlapping


@dataclass
class Result:
    text: str                                   # sanitized output (safe to send)
    vault: Vault                                # holds the reverse map
    report: "report_mod.Report"
    spans: List[Span] = field(default_factory=list)
    residual: List[Dict[str, str]] = field(default_factory=list)
    llm_requested: bool = True
    llm_ok: bool = True
    critic_ok: bool = True
    error: str = ""

    @property
    def map(self) -> Dict[str, Any]:
        return self.vault.to_map()

    @property
    def safe(self) -> bool:
        """True only if every requested protection layer actually ran."""
        return not (self.llm_requested and not self.llm_ok)


def _provider_for(config: Config, provider: Optional[Provider]) -> Provider:
    if provider is not None:
        return provider
    if not config.use_llm:
        return get_provider(replace(config, provider="null"))
    return get_provider(config)


def deidentify(text: str, config: Optional[Config] = None,
               provider: Optional[Provider] = None,
               reserved: Optional[List[str]] = None,
               segments: Optional[List[Tuple[str, str]]] = None) -> Result:
    """De-identify ``text`` and return the sanitized text plus the reverse map.

    ``segments`` is an optional ``formats`` plan of ``(kind, content)`` pairs;
    only ``'scrub'`` regions are detected over and rewritten, ``'keep'`` regions
    (instructions, fenced schemas) pass through verbatim. When omitted the whole
    text is scrubbed.
    """
    config = (config or Config()).validate()
    provider = _provider_for(config, provider)
    reserved = set(reserved or ())
    if segments is None:
        segments = [("scrub", text or "")]
    detect_text = "".join(c for k, c in segments if k == "scrub")

    # 1. deterministic layer — always runs, even offline
    regex_spans = detectors.detect(detect_text, config.locale)

    # 2. model layer — may be disabled or fail; failure is recorded, not hidden
    llm_spans: List[Span] = []
    llm_ok, error = True, ""
    try:
        llm_spans = provider.detect(detect_text)
    except (ProviderError, Exception) as exc:  # noqa: BLE001 - report, don't crash
        llm_ok = False
        error = str(exc)

    # 3. drop spans that are already placeholders or explicitly reserved
    raw = [s for s in regex_spans + llm_spans
           if not is_token_like(s.surface) and s.surface not in reserved]
    spans = merge_overlapping(raw)

    # 4. consistent pseudonymization (one Vault => same token everywhere)
    vault = Vault(policy=config.policy, reserved=reserved)
    pairs = vault.assign(spans)
    sanitized = "".join(
        vault.apply(content, pairs) if kind == "scrub" else content
        for kind, content in segments)

    # 5. residual-risk critic over the *sanitized* text (defense in depth)
    residual: List[Dict[str, str]] = []
    critic_ok = True
    if config.use_llm and config.critic and llm_ok:
        try:
            residual = provider.critique(sanitized)
        except (ProviderError, Exception):  # noqa: BLE001
            critic_ok = False

    vault.count_hits(sanitized)
    rep = report_mod.build_report(
        vault=vault, spans=spans, residual=residual,
        llm_requested=config.use_llm, llm_ok=llm_ok, critic_ok=critic_ok,
        policy=config.policy, provider_name=provider.name, model=config.model,
        error=error)

    return Result(text=sanitized, vault=vault, report=rep, spans=spans,
                  residual=residual, llm_requested=config.use_llm,
                  llm_ok=llm_ok, critic_ok=critic_ok, error=error)


def rehydrate(payload: Any, vault_or_map: Any) -> Any:
    """Translate placeholder tokens in ``payload`` back to real identities.

    ``payload`` may be a string or any JSON-ish structure (the cloud's reply).
    ``vault_or_map`` is a :class:`Vault` or a loaded ``*.map.json`` dict.
    """
    vault = (vault_or_map if isinstance(vault_or_map, Vault)
             else Vault.from_map(vault_or_map))
    return vault.rehydrate(payload)
