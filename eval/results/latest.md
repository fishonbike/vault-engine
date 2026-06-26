# Detection benchmark

| detector | person | org | location | project | contact | id | **overall** | over-redaction |
|---|---|---|---|---|---|---|---|---|
| vault-engine (regex only) | 0% | 0% | 0% | 0% | 69% | 33% | **13%** (10/77) | 0% |
| vault-engine (qwen3.6:27b) | 100% | 100% | 100% | 100% | 100% | 100% | **100%** (77/77) | 0% |
| Microsoft Presidio | 78% | 59% | 80% | 33% | 38% | 0% | **61%** (47/77) | 4% |

_Recall = share of gold identities flagged for redaction (higher is better). Over-redaction = flagged spans matching no gold identity (lower is better). Dataset: 77 scored entities across 15 bilingual synthetic docs._
