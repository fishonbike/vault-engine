# vault-engine

**English** · [简体中文](README.zh-CN.md)

**A local-LLM privacy layer for anything you paste into a cloud model.**

Strip the identities out of your text *before* it reaches ChatGPT / Claude /
Gemini — a model running **on your own machine** finds the names, orgs, places
and quasi-identifiers, replaces them with stable tokens, and keeps the only
key-back-to-reality on disk. When the cloud answers in tokens, you put the real
identities back locally.

*Best-effort de-identification — not legal anonymization or a privacy guarantee.
Review high-risk material before sending.*

> 出云前做身份脱敏：本地模型检测 → 代号化 → 云端用代号分析 → 本地还原真身。
> 检测**不出本机**，身份映射**只存本地**，大模型**一行换**。零依赖。

<p align="center">
  <img src="docs/demo.svg" alt="vault-engine scrubs English and Chinese names and PII into tokens before the cloud sees them, then restores them locally" width="760">
</p>

![CI](https://github.com/fishonbike/vault-engine/actions/workflows/ci.yml/badge.svg)
&nbsp;·&nbsp; Python ≥3.9 &nbsp;·&nbsp; stdlib-only &nbsp;·&nbsp; Apache-2.0

```text
# notes.txt  ── private, on your machine
林若曦是星澜资本的合伙人，在深圳见了字节跳动的陈大壮，邮箱 lin@xinglan.example

        ▼  vault-engine scrub  (local qwen3.6:27b)

# safe.txt  ── what the cloud sees: identities swapped for tokens
P-n1 是 ORG_1 的合伙人，在 LOC_1 见了 ORG_2 的 P-n2，邮箱 EMAIL_1
```

---

## Why

You want a frontier cloud model to analyze sensitive notes — but you don't want
the cloud to learn *who* they're about. Masking only the names you already know
leaks everything you don't: an unregistered name, an employer, a city + a rare
title, a project codename. Pattern-based redaction never sees those at all.

`vault-engine` puts a **local model** in front as the detector, so the semantic
identifiers get caught too — and nothing but the sanitized text ever leaves.

## How it works

```
 private text                                    cloud model
      │                                          (sees only tokens)
      ▼                                                ▲
┌─────────────────────────── vault-engine ────────────┼───────────┐
│  ① regex PII detectors  (offline floor)              │           │
│  ② LLM detector         (local model finds names,    │           │
│                          orgs, places, quasi-IDs)    │           │
│  ③ consistent pseudonyms (张三→P-n1, 同名同号)        │           │
│  ④ residual-risk critic  (re-scan: anything left?)   │  ① send   │
│        │                                             │           │
│   sanitized text ────────────────────────────────────┘           │
│        ▲                                                          │
│   reverse map (token → real identity) ── stays LOCAL ──┐  ② reply │
│        └───────────────────── ⑤ rehydrate ◀────────────┘          │
└──────────────────────────────────────────────────────────────────┘
      ▼
 real identities restored locally → use in your own system
```

## Benchmark

How much identity each detector actually catches, on a labelled bilingual
dataset (reproduce with `python eval/run_eval.py`; methodology in
[`eval/`](eval/README.md)):

<!-- BENCHMARK:START -->
77 gold identities across 15 bilingual documents — easy PII plus hard cases
(ambiguous common-word names, abbreviations, transliterations, @handles, a badge
number, a license plate). Reproduce:
`python eval/run_eval.py --provider ollama --with-presidio`.

> ⚠️ A **small synthetic set** for regression testing and rough comparison —
> **not** evidence of legal anonymization or complete privacy. "Recall" means
> flagged-for-redaction; LLM detection is non-deterministic. See the
> [threat model](#threat-model--limitations-honest).

| detector | person | org | location | project | contact | id | **overall** | over-redaction |
|---|---|---|---|---|---|---|---|---|
| regex only | 0% | 0% | 0% | 0% | 69% | 33% | **13%** | 0% |
| Microsoft Presidio (en/zh `lg`) | 78% | 59% | 80% | 33% | 38% | 0% | **61%** | 4% |
| **vault-engine (qwen3.6:27b)** | 100% | 100% | 100% | 100% | 100% | 100% | **100%** | 0% |

Same set where Presidio's NER scores 61%, the local LLM clears 100% — gap widest
on codenames, @handles, IDs, and Chinese names/orgs. Trade-off is speed: Presidio
~6s, the LLM ~25s/doc.
<!-- BENCHMARK:END -->

The point isn't a leaderboard — it's the **shape**: pattern-only redaction can't
see names, organizations, locations, or codenames at all; a local LLM can.

## Install

```bash
pip install vault-engine
```

Or get the latest straight from source:

```bash
pip install git+https://github.com/fishonbike/vault-engine
```

For the default local backend, install [Ollama](https://ollama.com) and pull a
model:

```bash
ollama pull qwen3.6:27b
```

No model yet? The deterministic floor (emails, phones, IDs, cards, URLs) works
with zero setup via `--no-llm`.

## Quickstart

```bash
vault-engine scrub notes.txt -o notes.safe.txt
```

That writes `notes.safe.txt` (send this to the cloud) and
`notes.safe.txt.map.json` (**local only** — the identities). Paste the sanitized
text into your model, save its reply, then restore the real identities:

```bash
vault-engine rehydrate reply.json --map notes.safe.txt.map.json -o reply.real.json
```

### The clipboard one-liner

The fastest path — scrub whatever you're about to paste into a chatbot, in place:

```bash
vault-engine clip               # de-identifies the clipboard
#   …paste into ChatGPT/Claude, copy its reply, then:
vault-engine clip --rehydrate   # restores the real identities in the clipboard
```

Works on macOS, Windows, and Linux (with `xclip`/`xsel`/`wl-clipboard`).

Library:

```python
from vaultengine import deidentify, rehydrate, Config

result = deidentify(open("notes.txt").read(), Config(model="qwen3.6:27b"))
send_to_cloud(result.text)                  # tokens only
restored = rehydrate(get_cloud_reply(), result.vault)   # real identities, locally
result.vault.save("notes.map.json")         # the reverse map — keep it local
```

## Use cases

- **Pseudonymize before pasting into ChatGPT/Claude** — analyze private notes,
  contracts, or chats with direct identifiers stripped.
- **Redact logs & support tickets** before sharing them or feeding an LLM.
- **Anonymize a dataset** for LLM-assisted analysis, then map results back.
- **Air-gapped review loops** — a model on a locked-down box only ever sees
  tokens.

## How it compares

Presidio and LLM Guard are excellent, mature tools. vault-engine's bet is
different: a **local LLM** as the detector catches semantic/quasi-identifiers
that label-based NER misses, with **zero runtime deps** and first-class Chinese.

| | **vault-engine** | Presidio | LLM Guard (Anonymize) | regex / scrubadub |
|---|---|---|---|---|
| Detection | local LLM + regex | NER (spaCy) + regex | NER / transformers | patterns only |
| Unregistered names / orgs / quasi-IDs | ✅ LLM | ⚠️ NER labels only | ⚠️ NER-limited | ❌ |
| Reversible round-trip | ✅ local map | ✅ deanonymizer | ✅ Vault | ❌ |
| Fully local / offline | ✅ Ollama | ✅ | ⚠️ varies | ✅ |
| Runtime dependencies | **none (stdlib)** | spaCy + models | several | varies |
| Chinese (中文) | ✅ strong | ⚠️ needs model | ⚠️ | ❌ |
| Swap the model | ✅ one line | — | partial | — |
| Fail-loud if detector errors | ✅ degrades + non-zero exit | — | — | — |

## Redaction policy (privacy ↔ utility)

| `--policy`  | Persons | Orgs / places / roles | Dates | Token shape |
|-------------|---------|-----------------------|-------|-------------|
| `balanced` *(default)* | ✅ | ✅ typed (`ORG_1`, `LOC_2`) | kept | typed |
| `max`       | ✅ | ✅ opaque `R_1` (type hidden) | coarsened | opaque |
| `light`     | ✅ | left in place | kept | typed |

`balanced` keeps coarse structure — the cloud still reads "`ORG_1` hired `P-n2`
as `ROLE_1` in `LOC_1`" and can reason about it, while no real identity ships.
**Persons are tokenized in every policy.**

## Swap the model

```bash
vault-engine models                                   # list local Ollama tags
vault-engine scrub notes.txt --model qwen3.6:35b-a3b  # any local model
vault-engine scrub notes.txt --provider null          # offline, regex only
```

### Using LM Studio or OpenAI-Compatible APIs

The `openai-compat` provider works with any OpenAI-compatible API, including local servers like LM Studio.

```bash
# Example: Use LM Studio's local OpenAI-compatible server
# (Caveat: raw text leaves vault-engine and is sent to the endpoint)
vault-engine scrub notes.txt \
  --provider openai-compat \
  --endpoint http://localhost:1234/v1 \
  --model "meta-llama-3-8b-instruct"
```

Built-in providers: `ollama` (default), `openai-compat` (any OpenAI-style
endpoint — opt-in; sends raw text to that endpoint), `null` (offline). Add
your own by implementing one method (`complete`) and registering it.

## ⚠️ Security model — read this

- **The reverse map (`*.map.json`) *is* the identity.** It's the only thing that
  links tokens back to real people. Keep it local. Never send it to a cloud
  model, never commit it — `.gitignore` excludes `*.map.json` and the CLI warns
  every run. Use `--one-way` to produce no map (irreversible publish).
- **Detection stays local by default.** Only the sanitized text is meant to
  leave, and only when you send it.

## Threat model & limitations (honest)

- LLM detection is **best-effort, not a guarantee** of non-identifiability — a
  model can miss a name or a rare quasi-identifier. It is **not** k-anonymity or
  differential privacy.
- The critic pass and the risk report reduce and surface residual risk; they
  don't certify its absence. Writing style and domain-unique facts can still
  identify with names removed — use `max` for higher-stakes material.
- If the model backend is unreachable, the run **degrades to regex-only and
  exits non-zero** (`--allow-degraded` to override) — it will never silently ship
  under-redacted text.

## Protecting code & schemas (`--format markdown`)

With `--format markdown` (or `auto`, which switches on at a fenced block),
anything inside fenced code blocks is preserved verbatim — a JSON reply-schema or
code sample you include for the model survives untouched while the prose around
it is scrubbed. Pre-existing placeholder tokens (e.g. `P-7`) pass through
unchanged.

## Development

```bash
python -m unittest discover -t . -s tests -v   # 59 tests, offline, no model
python eval/run_eval.py --provider ollama       # reproduce the benchmark
```

Fully offline and deterministic (null/fake providers); every fixture is
synthetic — no real data lives in this repo.

## License

Apache-2.0 © 2026 fishonbike. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
