"""Optional Microsoft Presidio adapter — for an apples-to-apples comparison.

Presidio is the de-facto standard PII detector (spaCy/transformers NER under the
hood). This adapter exposes the same ``analyze(text, lang) -> set of surfaces``
contract the harness uses for every engine, so recall is scored identically.

Install (not a dependency of vault-engine):
    pip install presidio-analyzer
    python -m spacy download en_core_web_lg
    python -m spacy download zh_core_web_lg   # for the Chinese docs

If a language has no model loaded, this returns an empty set for that doc — an
honest "not configured for this language" result rather than a crash.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Set

_EN_MODELS = ("en_core_web_lg", "en_core_web_sm")
_ZH_MODELS = ("zh_core_web_lg", "zh_core_web_sm")
_MIN_SCORE = 0.3


def _first_loadable(candidates):
    import spacy
    for name in candidates:
        try:
            spacy.load(name)
            return name
        except Exception:  # noqa: BLE001
            continue
    return None


@lru_cache(maxsize=1)
def _analyzer():
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    models = []
    en = _first_loadable(_EN_MODELS)
    if en:
        models.append({"lang_code": "en", "model_name": en})
    zh = _first_loadable(_ZH_MODELS)
    if zh:
        models.append({"lang_code": "zh", "model_name": zh})
    if not models:
        raise RuntimeError(
            "未找到任何 spaCy 模型；先 python -m spacy download en_core_web_lg")

    provider = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy", "models": models})
    langs = [m["lang_code"] for m in models]
    return AnalyzerEngine(nlp_engine=provider.create_engine(),
                          supported_languages=langs), set(langs)


def analyze(text: str, lang: str = "en") -> Set[str]:
    engine, langs = _analyzer()
    if lang not in langs:
        return set()
    results = engine.analyze(text=text, language=lang)
    return {text[r.start:r.end].strip() for r in results if r.score >= _MIN_SCORE}
