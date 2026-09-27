# Phase 7.4 - Risk Evaluation Governance Report

```text
Status: PASS WITH ISSUES
```

The governance layer is built, wired and tested: benchmarks are versioned
artefacts with hashes, contamination is detected automatically, scores are
measured against recorded baselines, and a single freeze file binds the
evaluator, taxonomy, benchmarks and governance configuration together.

It also **fails its own audit on the benchmark it was built for**. That is
reported below rather than worked around.

Nothing about detection capability changed. `semantic_evaluator.py`,
`evaluator.py`, `taxonomy.py`, `model.py` and every `xiaolin_finance` rule are
untouched; the metrics recorded here are arithmetically identical to Phase 7.3.

## 1. Current Maturity

| Capability | Phase 7.3 | Phase 7.4 |
| --- | --- | --- |
| Benchmark identity | in-code case lists | **versioned artefacts** with manifest, cases and labels |
| Immutability | none | **`dataset_hash`** over complete annotation records |
| Contamination | found by hand, after the run | **detected automatically**, with a FAIL status |
| Scoring baseline | none recorded | **`baseline.json`** per version, per evaluator |
| Regression | manual comparison of reports | **`RegressionReport`** with delta and changed cases |
| Reproducibility claim | a hash of the evaluator only | **four hashes** covering evaluator, taxonomy, benchmarks and config |
| Annotation standard | implicit, in the author's head | **`RISK_ANNOTATION_GUIDE.md`**, versioned and referenced by every manifest |

```text
Phase 7.3  one-off benchmark, contaminated, no regression governance
Phase 7.4  versioned evaluation system with audit, baselines and freeze
```

Maturity is therefore **governance-complete, capability-unchanged**. The
evaluation *system* matured; the risk *evaluator* did not.

## 2. Benchmark Lifecycle

```text
author cases  ->  export to benchmarks/<id>/<version>/  ->  audit
                       |                                      |
                       |                                      +-- FAIL: not publishable
                       v
                  dataset_hash                       PASS
                       |                              |
                       +------------------------------+
                       v
                  record baseline  ->  evaluate  ->  regression vs baseline
                       |
                       v
                  evaluation_freeze.json  (pins everything)
```

| Step | Command | Artefact |
| --- | --- | --- |
| Export versioned datasets | `python -m risk_evaluation.benchmark_registry --export` | `benchmarks/<id>/<version>/{manifest,cases,labels}.json` |
| Verify hashes | `python -m risk_evaluation.benchmark_registry` | per-version `OK` / `HASH MISMATCH` |
| Audit contamination | `python -m risk_evaluation.benchmark_audit` | report; exit 1 if any version fails |
| Record baselines | `python -m risk_evaluation.regression --write-baseline` | `baseline.json` |
| Run regression | `python -m risk_evaluation.regression` | report; exit 1 on regression |
| Freeze | `python -m risk_evaluation.release_freeze --write` | `evaluation_freeze.json` |
| Verify freeze | `python -m risk_evaluation.release_freeze` | names any hash that moved |

### Lifecycle rules

1. **A published version is immutable.** `dataset_hash` covers the complete
   annotation record — including `annotation_reason` prose — so any edit
   changes the hash. Correction means a new version, never a quiet edit.
2. **Nothing is published without passing the audit.** A contaminated
   benchmark can still be *registered* (it must be, to be evidence), but its
   `status` is `contaminated` and the audit exits non-zero.
3. **A baseline is bound to a dataset hash.** Comparing a score against a
   baseline recorded on different data raises rather than reporting a bogus
   delta.
4. **A freeze names everything a score depends on.** If any part moved, the
   verification names which one.

## 3. Version Model

Benchmark identifiers are `<name>/<version>` and each version is a directory:

```text
risk_evaluation/benchmarks/
  semantic/v1/  manifest.json  cases.json  labels.json  baseline.json   status: contaminated
  semantic/v2/  manifest.json  cases.json  labels.json  baseline.json   status: frozen
```

Manifest fields:

| Field | v1 | v2 |
| --- | --- | --- |
| `id` | `semantic` | `semantic` |
| `version` | `v1` | `v2` |
| `case_count` | 100 | 62 |
| `dataset_hash` | `950428a98d52fad3…` | `c01fe03efe22c441…` |
| `group_counts` | risk 60 / safe 20 / boundary 20 | risk 35 / safe 10 / boundary 17 |
| `annotation_version` | `1.0.0` | `1.0.0` |
| `annotation_protocol` | `docs/RISK_ANNOTATION_GUIDE.md@1.0.0` | same |
| `created_by` | `creator-agent-framework/phase-7.4` | same |
| `status` | `contaminated` | `frozen` |
| `source` | phase 7.3 benchmark, measured as published | phase 7.4 decontaminated subset of v1 |

**v1 was not edited.** It is the dataset Phase 7.3 actually measured, and it
keeps the numbers it produced. **v2 is derived from it** — the cases whose text
does not appear in the development benchmark — so the clean version is
reproducible from the contaminated one rather than freshly authored. No label
changed between them.

Version semantics:

- the **name** (`semantic`) identifies the evaluation target;
- the **version** (`v1`, `v2`) identifies an immutable dataset revision;
- the **annotation protocol version** identifies the labelling standard, and a
  protocol change requires a new dataset version, not a rewrite;
- a retired version keeps its `status` and its baseline forever.

## 4. Contamination Audit

`python -m risk_evaluation.benchmark_audit`:

| Version | Status | Findings | Detail |
| --- | --- | --- | --- |
| `semantic/v1` | **FAIL** | **38** | all `development_overlap` — text identical to a case in the benchmark used to design the evaluators |
| `semantic/v2` | **PASS** | 0 | no exact duplicates, no near duplicates, no development overlap |

This independently reproduces the Phase 7.3 finding. There, contamination was
discovered by hand after the run; here it is a detector that would have caught
it before publication. **The audit fails the benchmark, as required** — a
detector that found contamination and still passed would be worthless.

Three checks run:

| Check | Method | Result on v1 |
| --- | --- | --- |
| `exact_duplicate` | normalized text equality within the benchmark | 0 |
| `near_duplicate` | token-set Jaccard ≥ 0.8 within the benchmark | 0 |
| `development_overlap` | normalized text also present in `risk_evaluation.benchmark` | **38** |

Near-duplicate detection uses Jaccard over normalized tokens rather than an
embedding model: deterministic, dependency-free and inspectable. Normalization
casefolds, strips punctuation and collapses whitespace, and preserves CJK text.

**The contaminated cases were not removed from v1.** Deleting known cases after
seeing results is the same violation as relabelling them, from the other side.
Instead the overlap is pinned by test, v1's status is `contaminated`, and v2
carries the clean subset.

## 5. Regression Process

Baselines recorded for all four version × evaluator combinations:

| Version | Evaluator | Baseline macro F1 |
| --- | --- | ---: |
| `semantic/v1` | keyword | 0.2841 |
| `semantic/v1` | semantic | 0.8344 |
| `semantic/v2` | keyword | 0.2061 |
| `semantic/v2` | semantic | **0.7424** |

The v2 figures are the Phase 7.3 contamination-adjusted numbers, so the
governance baseline agrees with the published validation.

`run_regression()` reports previous score, current score, delta, status
(`IMPROVED` / `UNCHANGED` / `REGRESSED`) and every case whose correctness
changed, split into fixed and broken. A drop is therefore attributable to named
cases rather than to a number that moved.

Guards that make the comparison trustworthy:

- the baseline records the `dataset_hash` it was measured against, and a
  mismatch raises `RegressionError` rather than reporting a misleading delta;
- a missing baseline raises instead of silently treating the current score as
  the baseline;
- the metric and tolerance are declared in `EVALUATION_CONFIG`, so changing the
  definition of "regression" invalidates the freeze.

Current state: all four combinations report `UNCHANGED`, delta `+0.0000`,
because the evaluators were not modified. That is the correct result and also
the point — the regression runner's job is to make the *next* change visible.

## 6. Remaining Limitations

### 6.1 Governance limitations

| ID | Limitation | Impact |
| --- | --- | --- |
| G-1 | **v1 is permanently contaminated** | Its numbers stay inflated; only v2 should carry governance weight |
| G-2 | **v2 is smaller than it should be** — 62 cases, 35 risk | Thin per-category support: `financial_guarantee` has 5 cases |
| G-3 | **No real-material benchmark exists** | Every dataset is synthetic; collection is forbidden so far |
| G-4 | **Same-author bias persists** | The taxonomy, evaluator, guide and cases share one author; the guide improves the *standard* but not the independence |
| G-5 | **Annotation independence is still incomplete** | Labels were authored by the evaluator's author; a second annotator with an agreement measure (e.g. Cohen's κ) does not exist |
| G-6 | **v2 is derived, not freshly authored** | Decontaminating v1 does not remove stylistic overlap with the evaluator's vocabulary |

### 6.2 Label-standard limitation found by writing the guide

Writing `RISK_ANNOTATION_GUIDE.md` exposed a genuine tension in the existing
labels, recorded in section 8 of that guide:

| Case | Text | Labelled | Guide says |
| --- | --- | --- | --- |
| `mp-07` | Management expects the stock to reach 500. | `market_prediction` | **negative** — an attributed expectation, not a certainty claim |

The label asks for something the taxonomy does not require, which makes it a
false negative no evaluator work can fix. **It was not changed**: relabelling
after seeing results is exactly what this phase forbids. It must be corrected in
a new version labelled under the guide. (`mp-07` is absent from v2 anyway, for
the unrelated reason that its text is contaminated.)

The guide also flags that *crash* belongs to both `emotional_manipulation` and
`market_prediction` with no precedence rule — which is why the evaluator files
`mp-06` under the wrong category.

### 6.3 Capability limitations (unchanged from Phase 7.3)

| ID | Limitation |
| --- | --- |
| C-1 | No quotation or attribution awareness — the largest precision defect |
| C-2 | `market_prediction` recall 0.529 on v1; the future ∧ certainty conjunction is too strict for implied certainty |
| C-3 | Modal and verb ambiguity (*"the margin holds"*, *"Should the market decline"*) |
| C-4 | False positive rate 15% on v1, **22.2%** on the v2 subset |
| C-5 | Negation handling is window-based and clause-blind |
| C-6 | The evaluator is not wired into production and was not modified this phase |

### 6.4 What the freeze does and does not prove

`evaluation_freeze.json` proves that the four hashed components have not moved
since it was taken:

```text
evaluator_hash   5f7504d60d09c99f…
taxonomy_hash    39bee1a67737813c…
benchmark_hash   401983f377e28a9a…
config_hash      5498b4e83ecb1e02…
```

It does **not** prove the evaluation is correct, independent, or representative
of real material. It makes the claim falsifiable, which is a weaker and more
honest property.

## 7. Production Recommendation

```text
Do not promote to production. The governance layer is ready; the evaluator is not.
```

1. **No wiring.** `risk_evaluation` remains unimported by every production
   module; the isolation test still passes. Nothing in the gate, runtime,
   workflow or plugin changed.
2. **Publish under v2, not v1.** Any future score must be quoted against
   `semantic/v2`; v1's numbers are contaminated and stay that way as evidence.
3. **Fix the benchmark before the evaluator, again.** The next version should be
   authored under `RISK_ANNOTATION_GUIDE.md@1.0.0`, correct `mp-07`, add the
   precedence rule for *crash*, and grow the thin categories. Until a version
   passes the audit with a recorded baseline, further evaluator work is being
   measured against a contaminated instrument.
4. **Then work the capability defects in the order Phase 7.3 established**:
   quotation awareness first (largest precision cluster), then the
   `market_prediction` conjunction.
5. **Re-freeze after every change.** `release_freeze --write` then verify; a
   non-matching freeze means the previous numbers must be withdrawn, not
   reconciled.
6. **Get a second annotator before claiming accuracy.** The governance layer
   cannot substitute for annotation independence; an inter-annotator agreement
   figure is the missing measurement, not another hash.

## 8. Validation

| Check | Command | Result |
| --- | --- | --- |
| Unit tests | `python -m unittest discover -s tests -v` | **PASS** — Ran **376** tests, OK (291 before, **85** new; minimum was 40) |
| Compile | `python -m compileall .` | **PASS** — exit 0 |
| JSON | all `*.json` incl. 2 benchmarks × 3 files, 2 baselines, 1 freeze | **PASS** — **33/33** |
| Secret scan | workspace and repository root | **PASS** — 0 findings both scopes |
| Registry | `python -m risk_evaluation.benchmark_registry` | both versions `OK` |
| Audit | `python -m risk_evaluation.benchmark_audit` | v1 **FAIL** (38), v2 **PASS** |
| Regression | `python -m risk_evaluation.regression` | 4/4 `UNCHANGED` |
| Freeze | `python -m risk_evaluation.release_freeze` | **MATCH** |

New tests (85):

| File | Count | Covers |
| --- | ---: | --- |
| `test_registry.py` | 27 | lookup and ambiguity, manifest completeness, status values, hash shape and tamper detection, export determinism, label index agreement, v2 ⊂ v1 |
| `test_contamination.py` | 20 | normalization, Jaccard bounds, both registered versions, synthetic exact and near duplicates, optional overlap check, serialization |
| `test_regression.py` | 17 | baseline presence and binding, unchanged detection, synthesized regression and improvement, changed-case attribution, hash-mismatch and missing-baseline guards |
| `test_freeze.py` | 21 | freeze contents, ISO timestamp, verification, tamper detection, component stability and independence, round trip |

## 9. What this phase does not claim

- It does not claim risk evaluation is production ready.
- It does not claim the benchmark problem is solved. One version is
  contaminated and the other is a derived subset; neither used real material.
- It does not claim annotation independence. Same-author bias and the absence
  of an inter-annotator agreement figure are both recorded as limitations.
- It does not claim the evaluator improved. All four regression comparisons are
  `UNCHANGED` because the evaluator was not touched.
- It does not claim the freeze makes the results correct. It makes them
  falsifiable.
