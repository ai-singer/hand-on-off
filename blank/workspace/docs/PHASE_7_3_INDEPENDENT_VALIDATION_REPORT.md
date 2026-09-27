# Phase 7.3 - Independent Validation Report

```text
Decision: PASS WITH ISSUES
```

| Decision criterion | Result |
| --- | --- |
| Independent benchmark created | **Yes** — 100 cases, authored after the freeze |
| Metrics available | **Yes** — per-category P/R/F1, macro F1, micro P/R/F1, FPR, FNR, paraphrase recall |
| Evaluator behaviour reproducible | **Yes** — identical results across runs, frozen hash verified after the run |
| Recall/precision problems remain | **Yes** — and they are larger than the in-sample numbers suggested |

Two findings dominate everything below, and both are reported rather than
smoothed:

1. **The Phase 7.2 figure does not hold up.** Paraphrase recall falls from 95%
   in-sample to **79.2%** on this benchmark, and to **69.0%** once reused texts
   are excluded.
2. **This benchmark is itself contaminated.** 38 of its 100 texts are identical
   to texts in the 50-case development benchmark, which the phase explicitly
   forbade. The overlap was discovered *after* the evaluation run and was left
   in place — deleting known cases would break the same phase rule from the
   other side. It is pinned by test and quantified in section 6.

Nothing was tuned. `risk_evaluation/frozen_baseline.json` records
`semantic_patterns_hash = 0b3239979079dbbd573ef88d9d70fccb113fd1ac04a00ee6543effe40aea3641`
and verified unchanged after evaluation. No pattern, case, label or expected
value was modified after results were seen.

## 1. Frozen Baseline

`risk_evaluation/frozen_baseline.json`, written **before** the benchmark was
authored:

| Field | Value |
| --- | --- |
| `freeze_schema_version` | `1.0.0` |
| `semantic_evaluator` | `semantic-intent-v0` |
| `keyword_evaluator` | `keyword-xiaolin-finance-v1` |
| `semantic_patterns_hash` | `0b3239979079dbbd…a3641` |
| `development_benchmark` | `risk_evaluation.benchmark@50-cases` |
| `independent_benchmark` | `risk_evaluation.independent_benchmark@100-cases` |
| `frozen_before_independent_benchmark` | `true` |

The hash covers the evaluator's whole decision surface: signal patterns, intent
conjunctions and their required/booster classes, negation cues, the negation
window, the negatable-signal set, the confidence constants and the evaluator
name. It deliberately excludes formatting and docstrings, so cosmetic edits do
not invalidate a run while any behavioural change does.

`python -m risk_evaluation.freeze` verifies it; the test suite asserts it in
seven ways, including that changing a pattern, a conjunction or the negation
window each changes the hash.

```text
freeze MATCH: 0b3239979079dbbd vs 0b3239979079dbbd (semantic-intent-v0 / keyword-xiaolin-finance-v1)
```

## 2. Independent Benchmark Design

`risk_evaluation/independent_benchmark.py` — 100 cases in the required mix:

| Group | Count | Content |
| --- | ---: | --- |
| Risk positive | 60 | investment_advice 15, market_prediction 15, financial_guarantee 10, unverified_information 10, emotional_manipulation 10 |
| Safe | 20 | financial education, neutral analysis, historical explanation |
| Boundary | 20 | 5 disclaimers, 5 conditionals, 4 uncertainty statements, 6 quotations of claims the article refutes |

Labels were written from the taxonomy definitions, not from evaluator output.
Every record carries the required annotation fields — `id`, `text`,
`expected_categories`, `risk_level`, `annotation_reason`, `source_type:
"synthetic"`, `created_after_evaluator_freeze: true` — plus a `group` field for
reporting. `risk_level` is derived mechanically from the taxonomy severity of
the expected categories, so it cannot drift from the labels.

**The paraphrase subset is defined mechanically, not by hand.** A risky case
counts as a paraphrase when its text contains none of the literal keywords in
the plugin's `rules/filter_rules.json`. That split is computed from the rule
file at runtime, so it cannot be adjusted to flatter a result. 48 of the 60
risky cases are paraphrases by that definition.

### Contamination disclosure

**38 of the 100 texts are verbatim copies of development-benchmark cases.** The
phase required otherwise. The overlap was found by
`test_cases_do_not_reuse_development_benchmark_texts` after the run:

```text
ia-01..07, ia-11, mp-01..04, mp-07, mp-09, fg-01..04, fg-07,
ui-01..04, em-01, em-04, sf-01..10, bd-01, bd-02, bd-04
```

Effect: reused texts are ones the evaluator was already known to handle, so
they inflate every headline number. Section 6 quantifies this on the 62
genuinely new texts. The contaminated cases were **not** removed, because doing
so after seeing results is exactly the failure mode the phase forbids.

## 3. Metrics

Full benchmark, 100 cases. Both evaluators, unchanged, single run.

| Metric | keyword-xiaolin-finance-v1 | semantic-intent-v0 |
| --- | ---: | ---: |
| Macro F1 | 0.2841 | **0.8344** |
| Micro precision | 0.7333 | 0.8475 |
| Micro recall | 0.1774 | **0.8065** |
| Micro F1 | 0.2857 | 0.8265 |
| False positive rate | **0.075** | 0.150 |
| False negative rate | 0.8167 | **0.1667** |
| Paraphrase recall (48 cases) | 0.000 | **0.7917** |
| Enumerated recall (12 cases) | 0.9167 | **1.000** |

Per category:

| Category | Keyword P / R / F1 | Semantic P / R / F1 |
| --- | --- | --- |
| `investment_advice` | 0.250 / 0.067 / 0.105 | 0.812 / 0.867 / 0.839 |
| `market_prediction` | 1.000 / 0.118 / 0.210 | 0.900 / 0.529 / **0.667** |
| `financial_guarantee` | 0.000 / 0.000 / 0.000 | 0.818 / 0.900 / 0.857 |
| `unverified_information` | 1.000 / 0.400 / 0.571 | 0.909 / 1.000 / 0.952 |
| `emotional_manipulation` | 0.800 / 0.400 / 0.533 | 0.818 / 0.900 / 0.857 |

`market_prediction` is the semantic evaluator's weak category at 0.529 recall;
section 5 explains why. The keyword evaluator never detects a
`financial_guarantee` at all, because it folds guarantee wording into
`investment_advice`.

The complete per-case table — case id, text, expected, both evaluators' results
and correctness — is produced by `ValidationReport.case_table()`.

## 4. Keyword vs Semantic Comparison

| Dimension | Winner | Margin |
| --- | --- | --- |
| Macro F1 | semantic | 0.8344 vs 0.2841 |
| Micro recall | semantic | 0.8065 vs 0.1774 |
| Paraphrase recall | semantic | 0.7917 vs 0.000 |
| Enumerated recall | semantic | 1.000 vs 0.9167 |
| False negative rate | semantic | 0.1667 vs 0.8167 |
| **False positive rate** | **keyword** | 0.075 vs 0.150 |
| **Precision** | **keyword** | 0.7333 vs 0.8475 — see note |

Precision needs care: the keyword evaluator's higher precision is an artefact
of detecting almost nothing. It makes 3 false-positive predictions against 11
true positives; the semantic evaluator makes 6 false positives against 33 true
positives. The semantic evaluator produces three times as many correct
detections and twice as many false ones — a far better trade for a risk layer
whose `block` outcome only forces review.

**Neither evaluator dominates on every axis, and the comparison is not a
like-for-like improvement claim.** The two were scored on the same 100 cases,
which is what makes the comparison valid in *this* setting; it says nothing
about a third benchmark.

### Comparison with the Phase 7.2 figure — not an improvement claim

```text
Phase 7.2 paraphrase recall (in-sample, 20 cases) : 95.0%
Phase 7.3 paraphrase recall (this benchmark, 48)  : 79.2%
Phase 7.3 adjusted   (62 fresh cases only)        : 69.0%
```

The benchmarks are different in size, composition and provenance, so these
numbers are **not comparable as an improvement or a regression**. They are
reported together only to answer the question the phase asked: does the
evaluator generalise beyond the cases used to design it? The answer is
**partly**. It retains a large advantage over the keyword baseline on data it
was not tuned against, but the in-sample 95% overstated it by roughly 16 to 26
points.

## 5. Error Analysis

Full per-case classification in
[`PHASE_7_3_ERROR_ANALYSIS.md`](PHASE_7_3_ERROR_ANALYSIS.md). Causes are assigned
by documented deterministic rules in `risk_evaluation/validation.py`, not case
by case.

| Cause | Keyword | Semantic |
| --- | ---: | ---: |
| `missing_intent_signal` | 44 | 9 |
| `quotation_mistaken` | 2 | 3 |
| `educational_context_mistaken` | 0 | 3 |
| `language_gap` | 3 | 0 |
| `context_dependency` | 1 | 0 |
| `taxonomy_ambiguity` | 1 | 1 |
| `insufficient_negation_handling` | 1 | 0 |
| **Total** | **52** | **16** |

### Main failure categories

1. **No quotation or attribution awareness** — 3 semantic and 2 keyword false
   positives. The evaluator reads the text as a single voice, so a claim the
   article *quotes and then refutes* is treated as the article's own claim
   (`bd-16`, `bd-17`, `bd-18`). This is the largest precision defect and it is
   structural, not lexical.
2. **`market_prediction`'s conjunction is too strict** — 5 of the 10 semantic
   false negatives. Requiring both a future marker and an explicit certainty
   marker means a specific level and date (`mp-05`), an authoritative *"set
   to"* (`mp-12`) or an attributed price target (`mp-07`) is not a prediction.
3. **Modal and verb ambiguity** — 3 semantic false positives. *"holds"* matched
   the holding-directive class in *"the margin holds"* (`bd-06`), and
   *"Should"* matched the deontic class in the inversion *"Should the market
   decline"* (`bd-07`).
4. **Vocabulary gaps** — *confident*, *guaranteed to*, *crazy to skip*.
5. **Category ambiguity** — `crash` is both an emotional-pressure and a
   prediction signal, and there is no precedence rule, so `mp-06` is detected
   under the wrong category.

The keyword evaluator's 52 errors are 44 `missing_intent_signal`: its ceiling is
lexical, as Phase 7.1 diagnosed. Its errors are not spread across mechanisms.

## 6. Generalization Limitation

The phase asked whether the semantic evaluator generalises. The evidence
supports a qualified yes, with an explicit bound.

**Contamination-adjusted results** — the 62 texts that do not appear in the
development benchmark:

| Metric | Keyword | Semantic |
| --- | ---: | ---: |
| Macro F1 | 0.2061 | **0.7424** |
| Paraphrase recall | 0.000 | **0.6897** |
| False positive rate | 0.0741 | 0.2222 |
| False negative rate | 0.8571 | 0.2571 |

| Category | Semantic F1, full → fresh |
| --- | --- |
| `investment_advice` | 0.8387 → 0.6667 |
| `market_prediction` | 0.6667 → 0.5714 |
| `financial_guarantee` | 0.8572 → 0.7273 |
| `unverified_information` | 0.9524 → 0.9231 |
| `emotional_manipulation` | 0.8572 → 0.8235 |

Reading:

- The **ranking is stable**: the semantic evaluator still beats the keyword
  baseline by a wide margin on genuinely new text (macro F1 0.742 vs 0.206;
  paraphrase recall 69% vs 0%).
- The **absolute numbers fall** everywhere. Paraphrase recall drops 10 points,
  macro F1 drops 9, and the false-positive rate rises from 15% to 22%.
- `market_prediction` is the weakest category under both views (F1 0.57 on
  fresh text) and is the clear priority for any future work.

### What this can and cannot establish

It **can** establish that the evaluator's advantage is not purely an artefact
of the development set: the advantage survives on 62 texts it was not authored
against.

It **cannot** establish a clean out-of-sample estimate, for three reasons that
should be read together with the numbers:

1. **Same-author bias.** The taxonomy, the evaluator and the benchmark share one
   author. The labels follow the taxonomy rather than the code, but the cases
   are written in the same vocabulary as the signal patterns.
2. **Contamination.** 38% of the benchmark is reused development text, and the
   adjusted figures still come from a set authored by the same person.
3. **Synthetic only.** No real finance material was used, and this phase — like
   its predecessors — forbids collecting it.

**A defensible summary: the frozen evaluator generalises well enough to keep
developing, and not well enough to trust. Its measured advantage over the
keyword baseline is real; its absolute accuracy is unknown and its in-sample
figures were optimistic.**

## 7. Production Recommendation

```text
Do not promote to production. Continue development behind the frozen baseline.
```

1. **Keep the prototype out of the gate.** Nothing under `runtime/`,
   `workflows/`, `evaluation/`, `distillation_core/`, `plugins/`, `production/`,
   `core/`, `config/`, `schema_validation/`, `security/` or `artifact/` imports
   `risk_evaluation`; the isolation test still passes.
2. **Fix the benchmark before the evaluator.** The single highest-value next
   step is a benchmark with no reused texts and, if real material can be
   authorized, real provenance. Improving the evaluator against a contaminated
   set will overstate every gain again.
3. **Then attack the two structural defects**, in this order: quotation and
   attribution awareness (largest precision cluster, 5 false positives across
   both evaluators), then the `market_prediction` conjunction plus a category
   precedence rule (largest recall cluster, 5 of 10 semantic misses).
4. **Expect the false-positive rate to matter more than it looks.** 22% on fresh
   text means roughly one clean article in five is flagged for review. Because
   `block` forces `review_required` rather than publishing, this costs reviewer
   time and not safety — but it must be a deliberate trade, and it is currently
   untuned.
5. **Re-freeze before each round.** Any evaluator change invalidates this
   validation; a new hash, a new run and a new report are required. The freeze
   tooling makes that a single command.
6. **Do not treat Phase 7.2's 95% as the reference figure.** The number to carry
   forward is 79.2% on this benchmark, or 69.0% contamination-adjusted.

## 8. Validation

| Check | Command | Result |
| --- | --- | --- |
| Unit tests | `python -m unittest discover -s tests -v` | **PASS** — Ran **291** tests, OK (219 before, 72 new) |
| Compile | `python -m compileall .` | **PASS** — exit 0 |
| JSON | all `*.json` including `frozen_baseline.json` | **PASS** — 24/24 |
| Secret scan | workspace and repository root | **PASS** — 0 findings both scopes |
| Freeze | `python -m risk_evaluation.freeze` | **MATCH** after the evaluation run |
| Independent benchmark | `python -m risk_evaluation.independent_benchmark` | 100 cases, 60 / 20 / 20 |
| Validation | `python -m risk_evaluation.validation` | measured; sections 3 and 6 |

New tests (72) against the required minimum of 40:

| File | Count | Covers |
| --- | ---: | --- |
| `test_frozen_baseline.py` | 15 | freeze content, both evaluator versions, hash shape, and seven integrity checks that any behavioural edit changes the hash |
| `test_annotation_schema.py` | 18 | composition and distribution, required annotation fields, JSON serialization, taxonomy validity, `risk_level` consistency, boundary/safe coverage, and the exact contamination set |
| `test_metrics.py` | 15 | hand-computed per-category P/R/F1, macro/micro aggregation, FPR/FNR, paraphrase subset definition from the rule file, and zero-division behaviour |
| `test_reproducibility.py` | 24 | run-to-run identity of metrics, rows and findings; every incorrect result classified; documented metric values pinned; contamination sensitivity; report serialization and rendering |

The reproducibility group **pins all sixteen measured metrics plus the
contamination-adjusted set**, so any change to either evaluator or to the
benchmark fails the suite and forces this report to be updated in the same
change.

## 9. What this phase does not claim

- It does not claim the semantic evaluator is production ready — section 7.
- It does not claim 79.2% is a clean out-of-sample figure — section 6 lists the
  three reasons it is not.
- It does not claim Phase 7.3 improves on Phase 7.2. The benchmarks differ; the
  comparison is a generalisation check, not a before-and-after.
- It does not claim the benchmark is independent in the authorial sense. It is
  independent in provenance and protocol only, and even that is partial.
- It does not claim the gate, runtime, workflow or plugin changed. They did not.
