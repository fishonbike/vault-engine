# Detection benchmark

How much identity does each detector actually catch? This harness measures it on
a labelled dataset, identically across engines, so the numbers in the main README
are reproducible — not hand-written.

## Metrics

- **Recall** *(the privacy metric — higher is better)*: of all gold identities,
  what share did the detector flag for redaction? A missed name is a leak, so
  recall is what matters most for a de-identifier.
- **Over-redaction** *(the utility cost — lower is better)*: of all spans the
  detector flagged, what share match **no** gold identity? High over-redaction
  means it's shredding innocent text and starving the downstream model of
  context.

Scoring is **engine-agnostic**: a gold entity counts as caught if any flagged
span overlaps it (substring either way, case-insensitive). The exact same
function scores vault-engine and Presidio.

Recall is scored over the categories a de-identifier is expected to remove —
`person, org, location, project, contact, id`. `role` and `date` are annotated
(so redacting them isn't counted as over-redaction) but **not** scored, because
they are the fuzziest, most arguable labels.

## Dataset

`dataset/docs.jsonl` — 15 bilingual (zh/en) **synthetic** documents, 77 scored
gold entities. All personal data is fabricated: no real individual, email, phone,
or ID (emails use reserved `.example` domains; phone/ID numbers are invalid). The
sentences do name well-known public organizations, used purely as detection
targets — they carry no private data. Contributions of harder,
realistic-but-synthetic cases are welcome.

## Run it

```bash
# regex baseline only — instant, no model, no deps
python eval/run_eval.py

# add the local LLM detector (Ollama + qwen3.6:27b running)
python eval/run_eval.py --provider ollama --out eval/results/latest.md

# show exactly which gold entities each engine missed
python eval/run_eval.py --provider ollama --show-leaks
```

### Comparing against Microsoft Presidio

Presidio is optional and not a dependency of vault-engine:

```bash
pip install presidio-analyzer
python -m spacy download en_core_web_lg
python -m spacy download zh_core_web_lg     # for the Chinese docs
python eval/run_eval.py --provider ollama --with-presidio
```

If a language model isn't installed, Presidio scores an empty set for those docs
(an honest "not configured for this language" result, not a crash).

## Limitations (read before quoting numbers)

- This is a **small synthetic evaluation set for regression testing and rough
  comparison only** — not evidence of legal anonymization or complete privacy.
- It demonstrates the *shape* of the difference (regex vs NER vs LLM); it is not
  a population estimate of real-world recall.
- LLM detection is **non-deterministic** — re-running can shift a point or two.
- Recall here means "flagged for redaction," not a guarantee of
  non-identifiability. Quasi-identifier combinations and writing style are out of
  scope of this metric (see the main README's threat model).
