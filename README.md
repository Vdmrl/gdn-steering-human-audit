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

Scales: Numbered **0–4**, Probability **0–3**, Technical **0–3**, theistic framing **0–4**. French and Chinese are not annotated. Texts are displayed in full, without rewriting or truncation.

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

Owner-only `data/private_manifest.jsonl` and `data/private-v3/judge-repeats/` must stay outside Git and outside annotators' folders. Keep independent exports in one combined JSONL, then run:

```powershell
python scripts/calculate_metrics.py --input data/exports/annotations.jsonl
```

Outputs: `data/exports/audit_metrics.json` and `.html`. They include exact Judge–human agreement, normalized MAE and signed bias in percentage points, linear-weighted Cohen's kappa, per-feature confusion matrices, human–human agreement, available-logprob expectation error and 95% bootstrap intervals. Bootstrap resamples whole source prompt clusters, keeping both human ratings together. Identical prompts with multiple method answers are not independent units. Kappa is not pooled across incompatible score scales. Human disagreement is preserved; no arbitrary majority label is invented for two raters.

Primary Judge reference is fresh **run-0 after sample freezing**, not the candidate score used to select diagnostic cases. Report agreement with each human, plus MAE against their mean. Human agreement is unavailable until real human annotations arrive; an empty export is not a passing result.

## Sample and limitations

Sample **3.0** contains128 fully authored coherent diagnostic examples:64 English and64 Russian,16 per feature/language. All texts have complete endings, no generation loops, no mixed languages. This study measures Judge agreement on prepared rubric examples, not the quality or prevalence of traits in real steering generations.

Technical and uncertainty use the new concrete6.0.0-concrete-audit-review1 rubric. Probability now has0–3: absent, isolated weak hedge, generally mild uncertainty, explicit central uncertainty. Technical0–3: everyday language, one local specialized term/phrase, generally elevated language, dense demanding text. Numbered and theistic scales remain0–4. Full versioned definitions are in data/rubric.json and the vendored candidate resources; these are provisional scales undergoing human validation.

The128 texts and assignments were frozen before Judge scoring. Intended author levels are private design strata, not human gold or fabricated Judge labels. Fresh run0 is the primary Judge reference; five repeats quantify repeatability. No cases are removed based on Judge scores. All cases belong to the diagnostic subset. Bootstrap groups the four topic families within each feature/language; language counterparts and template-family dependencies limit generalization. Do not interpret repeated wording variants as128 independent situations.

V2 datasets and eight existing human submissions were preserved separately before migration. New workspaces steering-v3-a/b replace earlier versions for annotators; old responses are never transferred to modified answers or new scales. Old raw scores remain private-archives/v2 and private-v2. Run the same setup to create the new version; changing an already annotated dataset in place is forbidden.
