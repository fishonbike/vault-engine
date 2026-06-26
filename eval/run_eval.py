#!/usr/bin/env python3
"""Benchmark harness — how much identity does each detector actually catch?

Runs one or more detectors over a labelled synthetic dataset and reports
per-category **recall** (the privacy-critical metric: was the real surface
flagged for redaction?) plus an **over-redaction** rate (flagged spans that
match no gold entity — a utility cost).

Engines, all scored identically (a gold entity is "caught" if any flagged span
overlaps it):
  - regex     : vault-engine deterministic layer only (Config(use_llm=False))
  - llm       : vault-engine with a model backend (default ollama/qwen3.6:27b)
  - presidio  : Microsoft Presidio (optional, --with-presidio; needs install)

Usage:
  python eval/run_eval.py                          # regex baseline only
  python eval/run_eval.py --provider ollama        # + local LLM
  python eval/run_eval.py --provider ollama --with-presidio
  python eval/run_eval.py --provider ollama --out eval/results/latest.md

Numbers are produced by actually running the detectors — never hand-written.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Set, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))   # repo root, for `vaultengine`
sys.path.insert(0, _HERE)                     # eval/, for the optional `adapters`

from vaultengine import Config, deidentify  # noqa: E402

# Recall is scored over the categories a de-identifier is expected to remove.
# (role/date are annotated for fair precision matching but not scored — they are
# the fuzziest, most arguable labels.)
SCORED = ("person", "org", "location", "project", "contact", "id")
DATASET = os.path.join(os.path.dirname(__file__), "dataset", "docs.jsonl")


def load_docs(path: str) -> List[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _overlap(a: str, b: str) -> bool:
    a, b = a.casefold(), b.casefold()
    return a in b or b in a


def _covered(surface: str, flagged: Set[str]) -> bool:
    return any(_overlap(surface, f) for f in flagged)


# --- detectors return the set of surfaces they would redact ---------------
def vault_flagged(text: str, config: Config) -> Tuple[Set[str], bool]:
    r = deidentify(text, config)
    surfaces: Set[str] = set()
    for entry in r.vault.tokens.values():
        surfaces.add(entry["surface"])
        surfaces.update(entry.get("aliases", []))
    return surfaces, r.llm_ok


def presidio_flagged(text: str, lang: str) -> Set[str]:
    from adapters.presidio_adapter import analyze  # type: ignore
    return analyze(text, lang)


# --- scoring --------------------------------------------------------------
def evaluate(docs: List[dict], flag_fn) -> dict:
    cat_total: Dict[str, int] = {c: 0 for c in SCORED}
    cat_caught: Dict[str, int] = {c: 0 for c in SCORED}
    flagged_total = matched = 0
    leaks: List[str] = []
    degraded = False

    for doc in docs:
        flagged, ok = flag_fn(doc)
        if not ok:
            degraded = True
        gold_all = {e["surface"] for e in doc["entities"]}
        for ent in doc["entities"]:
            if ent["category"] not in SCORED:
                continue
            cat_total[ent["category"]] += 1
            if _covered(ent["surface"], flagged):
                cat_caught[ent["category"]] += 1
            else:
                leaks.append(f'[doc {doc["id"]}] {ent["category"]}: {ent["surface"]}')
        for f in flagged:
            flagged_total += 1
            if any(_overlap(f, g) for g in gold_all):
                matched += 1

    total = sum(cat_total.values())
    caught = sum(cat_caught.values())
    return {
        "cat_total": cat_total, "cat_caught": cat_caught,
        "recall": caught / total if total else 0.0,
        "caught": caught, "total": total,
        "over_redaction": (flagged_total - matched) / flagged_total if flagged_total else 0.0,
        "flagged_total": flagged_total, "leaks": leaks, "degraded": degraded,
    }


def run_engine(name: str, docs: List[dict], flag_fn) -> dict:
    t0 = time.time()
    res = evaluate(docs, flag_fn)
    res["name"] = name
    res["seconds"] = time.time() - t0
    return res


# --- reporting ------------------------------------------------------------
def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def render(results: List[dict]) -> str:
    cats = list(SCORED)
    head = "| detector | " + " | ".join(cats) + " | **overall** | over-redaction |"
    sep = "|" + "---|" * (len(cats) + 3)
    lines = [head, sep]
    for r in results:
        cells = []
        for c in cats:
            tot = r["cat_total"][c]
            cells.append(f'{_pct(r["cat_caught"][c] / tot)}' if tot else "—")
        overall = f'**{_pct(r["recall"])}** ({r["caught"]}/{r["total"]})'
        flag = (f' ⚠️ degraded' if r.get("degraded") else "")
        lines.append(f'| {r["name"]}{flag} | ' + " | ".join(cells) +
                     f' | {overall} | {_pct(r["over_redaction"])} |')
    n_ent = results[0]["total"] if results else 0
    n_docs = len(load_docs(DATASET))
    note = (
        "\n_Recall = share of gold identities flagged for redaction "
        "(higher is better). Over-redaction = flagged spans matching no gold "
        "identity (lower is better). "
        f"Dataset: {n_ent} scored entities across {n_docs} bilingual synthetic docs._"
    )
    return "\n".join(lines) + "\n" + note


def main() -> int:
    ap = argparse.ArgumentParser(description="vault-engine detection benchmark")
    ap.add_argument("--dataset", default=DATASET)
    ap.add_argument("--provider", help="model backend for the 'llm' row (e.g. ollama)")
    ap.add_argument("--model", default="qwen3.6:27b")
    ap.add_argument("--policy", default="balanced")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--with-presidio", action="store_true")
    ap.add_argument("--out", help="also write the markdown table here")
    ap.add_argument("--show-leaks", action="store_true")
    args = ap.parse_args()

    docs = load_docs(args.dataset)
    results: List[dict] = []

    # 1) regex-only baseline — always runs, instant, no model
    regex_cfg = Config(use_llm=False, policy=args.policy)
    results.append(run_engine(
        "vault-engine (regex only)", docs,
        lambda d: vault_flagged(d["text"], regex_cfg)))

    # 2) local-LLM detector
    if args.provider:
        llm_cfg = Config(provider=args.provider, model=args.model, use_llm=True,
                         critic=False, policy=args.policy, timeout=args.timeout)
        results.append(run_engine(
            f"vault-engine ({args.model})", docs,
            lambda d: vault_flagged(d["text"], llm_cfg)))

    # 3) Presidio (optional)
    if args.with_presidio:
        try:
            results.append(run_engine(
                "Microsoft Presidio", docs,
                lambda d: (presidio_flagged(d["text"], d["lang"]), True)))
        except Exception as exc:  # noqa: BLE001
            print(f"[presidio] 跳过（未安装或加载失败）：{exc}", file=sys.stderr)

    table = render(results)
    print(table)
    for r in results:
        print(f'\n# {r["name"]}: {r["seconds"]:.1f}s', file=sys.stderr)
        if args.show_leaks and r["leaks"]:
            print("  漏检：", file=sys.stderr)
            for lk in r["leaks"]:
                print("   -", lk, file=sys.stderr)

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write("# Detection benchmark\n\n" + table + "\n")
        print(f"\n→ {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
