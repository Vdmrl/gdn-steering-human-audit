# GDN Steering Human Audit

Argilla application for blind human validation of the frozen steering Judge.

## Start annotation

Install Git, Docker Desktop and Python 3.10+. Start Docker Desktop, then:

```powershell
git clone https://github.com/Vdmrl/gdn-steering-human-audit.git
cd gdn-steering-human-audit
python start.py
```

Select **Вова / Стёпа / Слава / Петя** in the launch menu. The script starts Argilla and opens [http://localhost:6900](http://localhost:6900).

| Person | Login | Assigned sample |
|---|---|---|
| Вова | `vova` | A, 64 items |
| Стёпа | `stepa` | A, the same 64 items independently |
| Слава | `slava` | B, 64 different items |
| Петя | `petya` | B, the same 64 items independently |

Local default password: `password`. Use `.env.example` to configure passwords before first initialization. This stack is intended for local annotation, not an Internet-facing service. Progress persists in Docker volumes. Never remove volumes after annotation starts.

Each account sees four datasets with 16 tasks each. Each dataset contains eight English and eight Russian answers. A and B do not overlap. Submit a score for **one named feature per answer**. Judge scores, method labels, synthetic/real provenance and private mappings are not uploaded to Argilla.

The displayed score is the digit before the dash; small shortcut numbers in Argilla buttons are not scores. Full Russian explanations and the verbatim English Judge rubric are under **GUIDELINES**. No factual correctness, answer quality or content-preservation assessment is requested.

Scales: Numbered **0–4**, Probability **0–4**, Technical **0–3**, theistic framing **0–4**. French and Chinese are not annotated. Texts are displayed in full, without rewriting or truncation.

Before the main sample, read [TRAINING.md](TRAINING.md) and discuss those separate examples. Do not discuss main-sample answers with your partner or open private owner files.

## Export

When you have submitted your 64 answers:

```powershell
docker compose run --rm setup python scripts/export_annotations.py
```

Send `data/exports/annotations.jsonl` to the study owner. Do not send `.env` or Docker volumes. If everyone uses a different local installation, the owner merges the exports; only the assigned users' submitted responses count. Drafts and unsubmitted responses are excluded. Duplicate submitted `(item_id, username)` pairs are rejected rather than counted twice.

Stop/resume without losing progress:

```powershell
docker compose stop
docker compose start
```

## Owner: final metrics

Owner-only `data/private_manifest.jsonl` and `data/private-v2/judge-repeats/` must stay outside Git and outside annotators' folders. Keep independent exports in one combined JSONL, then run:

```powershell
python scripts/calculate_metrics.py --input data/exports/annotations.jsonl
```

Outputs: `data/exports/audit_metrics.json` and `.html`. They include exact Judge–human agreement, normalized MAE and signed bias in percentage points, linear-weighted Cohen's kappa, per-feature confusion matrices, human–human agreement, available-logprob expectation error and 95% bootstrap intervals. Bootstrap resamples whole source prompt clusters, keeping both human ratings together. Identical prompts with multiple method answers are not independent units. Kappa is not pooled across incompatible score scales. Human disagreement is preserved; no arbitrary majority label is invented for two raters.

Primary Judge reference is fresh **run-0 after sample freezing**, not the candidate score used to select diagnostic cases. Report agreement with each human, plus MAE against their mean. Human agreement is unavailable until real human annotations arrive; an empty export is not a passing result.

## Sample and limitations

Sample **2.0** contains 128 unique answer/feature assignments, 64 English and 64 Russian; 256 expected human ratings. **53 real answers and 75 authored examples**. Each feature/language stratum contains 16 items:

- English: eight random real answers per feature selected before candidate Judge calls, plus eight diagnostic answers chosen for actual Judge score coverage. The original English sample is unchanged.
- Russian: sixteen coherent, entirely Russian rubric-diagnostic answers per feature, authored for this audit. Both scenario and answer are Russian; there are no English/Chinese insertions or generated loops. Their actual candidate scores cover every score level. These are not unmodified steering outputs and not a representative sample of model generations.

Russian cases use four thematic prompt families per feature with different trait strengths. Sixteen answers are not sixteen independent situations; bootstrap keeps all answers from one prompt family together.

All score values are covered in candidate-selection scores for each feature/language. These are **Judge-confirmed scores, not human ground truth**, and subsequent runs may differ. Diagnostic selection is score-conditioned and must be reported separately from the random real sample; pooled descriptive agreement is not a population accuracy estimate.

Real English responses come from the earlier Qwen9B final cohort. Original English scenarios retain their historical instructions. Russian examples test how well people and Judge interpret the rubric on readable Russian, not how well Russian steering works. Report English random-real, English diagnostic and Russian curated results separately. This audit does not independently validate every later repaired cohort, other models, French or Chinese.

The previous mixed-language sample and its scores are archived privately as version1; they are not reused as scores for rewritten Russian texts. Version2 has separate Argilla workspaces and fresh five-repeat scores for the frozen sample. Old datasets and any earlier annotations remain preserved.

`sample_metadata.json` pins hashes and assignments. The private owner manifest additionally pins source paths/hashes/IDs, methods, selection scores and selection roles. Source generations are not included in Git. Do not regenerate a frozen public sample after annotation starts.

## Owner: repeatability and supplementation

The included `vendor/ready_judge` is a byte-identical copy of Judge **5.2.1-review1**. Scoring prompts/config remain unchanged: `deepseek/deepseek-v4.1-flash`, fixed CoreWeave routing, temperature 0, no reasoning, logprobs top 10. API keys are entered invisibly or read from the environment; never saved.

```powershell
python scripts/prepare_audit.py --run --repeats 5
```

This is an explicit **audit-only** paid action. It resumes only missing judgments using stable IDs and immutable inputs/config. Five independent requests per frozen item are sent with identical payloads. Report all-five exact stability, pairwise agreement, score ranges, available-expected-score SD/range and drift in normalized run means. This measures repeatability, not invariance to arbitrary paraphrases or agreement with humans. Missing logprob labels are not filled with zeros.

The owner preparation pool in `data/private/candidates.jsonl` contains the already frozen real candidates; additional locally authored candidates are optional `extra-candidates.jsonl`. Candidate-selection responses and unsuccessful attempts are retained privately. An unavailable desired score causes visible preparation failure; it is never assigned by hand. This command does not authorize evaluation of the entire steering experiment bank.

## Checks

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m unittest discover -s tests -v
```

Tests use fixtures/mocked objects and spend no API credits. Live smoke checks use a separate QA workspace and never submit ratings in study datasets. Setup is idempotent and refuses different data, labels or instructions on existing datasets.
