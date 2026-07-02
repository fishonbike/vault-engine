# Detection benchmark

77 gold identities across 15 bilingual synthetic documents (easy PII + hard
cases). Reproduce: `python eval/run_eval.py --provider ollama --with-presidio`
(pass `--model <tag>` to test other local models).

| detector | person | org | location | project | contact | id | **overall** | over-redaction |
|---|---|---|---|---|---|---|---|---|
| vault-engine (regex only) | 0% | 0% | 0% | 0% | 69% | 33% | **13%** (10/77) | 0% |
| Microsoft Presidio (en/zh `lg`) | 78% | 59% | 80% | 33% | 38% | 0% | **61%** (47/77) | 4% |
| vault-engine (qwen2.5:7b) | 100% | 100% | 100% | 100% | 100% | 100% | **100%** (77/77) | 2% |
| vault-engine (qwen3.5:9b) | 100% | 94% | 100% | 100% | 100% | 100% | **99%** (76/77) | 0% |
| vault-engine (qwen3.6:27b) | 100% | 100% | 100% | 100% | 100% | 100% | **100%** (77/77) | 0% |

Approx. wall-clock for the 15-doc set: regex <0.1s · Presidio ~6s · 7b ~61s ·
9b ~100s · 27b ~400s. Detection does not need a big model: a 4.7 GB `qwen2.5:7b`
matches the 27b's recall on this set.

_Recall = share of gold identities flagged for redaction (higher is better).
Over-redaction = flagged spans matching no gold identity (lower is better).
Presidio uses `en_core_web_lg` + `zh_core_web_lg`. Small synthetic set for
regression testing and rough comparison — not evidence of legal anonymization.
LLM detection is non-deterministic; numbers are produced by `eval/run_eval.py`,
never hand-written._
