# Phase 7.2 - Semantic Risk Evaluator Report

```text
Final Status: PASS WITH ISSUES
```

A second evaluator behind the same contract, scored on the same benchmark,
measurably beats the keyword baseline on the metric that matters:

```text
paraphrase recall   5%  ->  95%     (+90 points)
keyword recall    100%  -> 100%     (no regression)
false positives     0%  ->   0%     (safe set, unchanged)
adversarial accuracy 40% ->  90%    (+50 points)
```

It is a **prototype**, not production detection. Two cases still fail, one of
them for a reason that is arguably correct, and the benchmark was written in
the same phase as the evaluator — so the measured gain is an optimistic
estimate, not an unbiased one. Both points are detailed below rather than
smoothed over.

Scope compliance: `xiaolin_finance` rules and keywords, the artifact schema,
the quality gate, the runtime bootstrap and the workflow were **not modified**.
No black-box service and no model was introduced. Nothing was hardcoded per
test case. The prototype is **not wired into production**.

## 1. Current Baseline

Phase 7.1 left one evaluator, `keyword-xiaolin-finance-v1`, wrapping the
existing plugin rules, and a 20-case benchmark. Its measured boundary:

| Metric | Value |
| --- | --- |
| Enumerated wording detected | 100% (11/11 recall probes) |
| Unenumerated wording detected | **0%** (0/9 recall probes) |
| False positives | 20% on the 6.5.1 clean probes |

The failure direction is false negative: prohibited intent written in words the
rules do not enumerate reaches the gate unflagged.

Two things were reused unchanged from 7.1: the taxonomy in
`risk_evaluation/taxonomy.py` and the result contract in
`risk_evaluation/model.py`. Phase 7.2 added an evaluator and a benchmark, not a
new contract.

## 2. Semantic Evaluator Design

`risk_evaluation/semantic_evaluator.py` implements `RiskIntentEvaluator`
without reading any plugin rule file.

```text
intent pattern = required signal classes (AND) + optional boosters
```

| Category | Required signals | Boosters |
| --- | --- | --- |
| `investment_advice` | `directive` ∧ `financial_object` | — |
| `market_prediction` | `future_marker` ∧ `certainty_marker` | `financial_object` |
| `financial_guarantee` | `risk_negation` | `financial_object` |
| `unverified_information` | `vague_source` | — |
| `emotional_manipulation` | `emotional_pressure` | — |

### Why this is not a bigger keyword list

1. **Compositional.** Most categories need two independent signal classes.
   *"You should buy this stock today."* matches because a directive and a
   financial object both appear — not because the sentence is enumerated.
   *"Move your money into this company."* matches through the same two classes
   with completely different words.
2. **Morphological.** Signals match word families (`recommend`, `recommends`,
   `recommended`, `recommendation`) rather than one surface form each.
3. **Negation aware.** A cue ending within 24 characters before a match
   suppresses it, so *"not a guaranteed return"* is not a guarantee. Patterns
   that are themselves negative (`no risk`, `cannot fail`, `never falls`) still
   fire, because there the cue *is* the match rather than a modifier of it.
4. **Explainable.** Every result names the signals that fired:
   `directive(should), directive(buy), financial_object(stock)`.
5. **Position aware where mood matters.** Sentence-initial `consider/avoid/
   prefer/choose/stick with` is an imperative directive; the third-person
   *"the report considers revenue"* is not, so the pattern is anchored to
   sentence start rather than matching the verb anywhere.

### Bugs the benchmark exposed in the prototype

Writing the benchmark found four defects before any of them could be mistaken
for a modelling limit:

| # | Defect | Effect |
| --- | --- | --- |
| B1 | `\b` does not act as a word boundary between CJK characters | Every Chinese signal failed inside longer text — *"恐慌情绪"* never matched `恐慌\b`. Fixed by leaving CJK alternatives unanchored, which is correct for a language written without delimiters. |
| B2 | `directive` had no Chinese verb class | *"立即买入这只股票"* produced no directive, so no advice. |
| B3 | `someone`/`somebody` missing from the attribution noun list | *"Someone said the CEO is resigning."* was missed. |
| B4 | `risk_negation` was exempt from the negation guard | *"not a guaranteed return"* was read as a guarantee. Fixed after checking that the guard only suppresses cues ending *before* a match, so `cannot fail` still fires. |

**A fifth defect was in the benchmark itself, and it mattered more than the
other four.** Detection was scored as `produced categories ∩ expected
categories`. For a safe case the expectation is empty, so that intersection is
always empty: the false-positive counter could never fire, and the metric
reported `0%` for any evaluator regardless of behaviour. It was invisible in
7.1 because the only non-risky cases were five genuinely clean sentences; it
surfaced the moment adversarial cases added a *disclaimed* guarantee that the
keyword evaluator does flag. `CaseOutcome` now separates `flagged` (any result
produced) from `matched` (a result on an expected category), and the
false-positive rate is computed from `flagged`.

## 3. Comparison Method

Both evaluators are scored on the identical 50 cases through
`compare_evaluators()`, so the comparison is between methods rather than
between configurations:

- the semantic evaluator reads no rule file and shares no keyword list;
- `run_benchmark(evaluator, cases)` treats both as opaque
  `RiskIntentEvaluator` implementations;
- neither evaluator's name or type is special-cased anywhere in the runner;
- the keyword evaluator is unchanged, so its numbers are the same baseline
  7.1 measured, re-scored on the larger set.

Render with:

```bash
python -m risk_evaluation.benchmark
```

## 4. Benchmark Result

The benchmark grew from 20 to 50 cases in four kinds:

| Kind | Count | Purpose |
| --- | ---: | --- |
| `keyword` | 10 | enumerated wording; checks the mechanism works |
| `safe` | 10 | clean explanation; measures false-positive cost |
| `paraphrase` | 20 | same intent, unenumerated wording; the capability boundary |
| `adversarial` | 10 | boundary stress in **both** directions — 5 disclaimed-risk cases that must not be flagged, 5 indirect-intent cases that must be |

Measured:

| Metric | keyword-xiaolin-finance-v1 | semantic-intent-v0 | Delta |
| --- | ---: | ---: | ---: |
| keyword recall | 100% (10/10) | **100%** (10/10) | +0 |
| **paraphrase recall** | 5% (1/20) | **95%** (19/20) | **+90 pts** |
| false positive rate (safe set) | 0% (0/10) | 0% (0/10) | +0 |
| adversarial accuracy | 40% (4/10) | **90%** (9/10) | **+50 pts** |
| adversarial false positives | 1 | **0** | −1 |
| mislabeled (risky, wrong category only) | 0 | 0 | +0 |

Per-case rows — case id, input, both results and the expectation — are produced
by `ComparisonReport.case_table()` and asserted in
`tests/risk_semantic_evaluator/test_comparison.py`.

One baseline note: the keyword evaluator scores 5% rather than 0% on
paraphrases because one paraphrase, *"Everyone is buying before it is too
late."*, happens to contain an enumerated phrase. On the original 20-case set
its paraphrase recall was 0%.

## 5. Improvement Evidence

The improvement is real and it is the intended kind:

- **+90 points of paraphrase recall.** 19 of 20 prohibited statements written
  in unenumerated wording are now detected, up from 1 of 20.
- **No regression on enumerated wording.** All 10 keyword cases are still
  detected. The four Chinese cases that the first prototype missed (B1, B2) are
  now caught, which is why the fix mattered for parity and not just for the
  headline number.
- **No new false positives.** The safe set stays at 0/10, and adversarial false
  positives drop from 1 to 0: the semantic evaluator does not flag
  *"This is not a guaranteed return"*, which the keyword evaluator does.
- **+50 points of adversarial accuracy**, driven by detecting 5 of 5 indirect
  intent cases that the keyword evaluator misses entirely, while getting all 5
  disclaimed-risk cases right.

To show the gain is not a scoring artefact, the detections are inspectable per
case, and the improvement holds on three independent metrics
(paraphrase, adversarial, false positives) rather than one.

### Overfitting disclosure — read this before trusting the numbers

**The benchmark and the evaluator were written in the same phase.** That makes
the measured recall an optimistic estimate of generalisation:

- the 20 paraphrase cases were written first as natural expressions of intent,
  but they were written by the same author who then designed the signal
  patterns, so they share that author's vocabulary;
- the signal patterns are general linguistic forms and no pattern exists to
  satisfy a single case, but the choice of *which* general forms to add was
  informed by seeing which cases failed;
- 9 of 10 safe cases and 5 of 10 adversarial cases were authored here as well,
  so the false-positive result is equally in-sample.

A genuinely independent corpus was not available and could not be collected
(this phase, like its predecessors, forbids scraping real finance material).
The honest reading is: **the prototype roughly removes the keyword-lexical
ceiling on this benchmark; the true generalisation gap is unknown and is
probably narrower than +90 points.**

## 6. Failure Cases

Two cases still fail, and both are reported rather than patched.

### F1 — attributed expectation, `pp-12`

```text
input   : Management expects the stock to reach 500.
expected: market_prediction
result  : not detected
```

The taxonomy defines `market_prediction` as an outcome stated *as a certainty*.
"Management expects" is attributed and hedged, so the `certainty_marker`
requirement is not met and the conjunction fails. Per the taxonomy the
evaluator is arguably right, but a named price target is exactly the claim the
category exists to catch. The gap is **taxonomy-versus-detection tension**, not
a missing word: fixing it means deciding whether attributed price targets
belong in `market_prediction` or need their own category.

### F2 — indirect modal suggestion, `ad-07`

```text
input   : You could do the same with your portfolio.
expected: investment_advice
result  : not detected
```

There is no directive verb — the suggestion is carried by mood and implication.
Detecting it means treating `you could + action` as a directive, which would
also flag legitimate analytic sentences such as *"You could compare the revenue
figures."* That trade-off is a **precision cost**, and it was declined rather
than paid to win one benchmark point.

### Other observed weaknesses

| ID | Weakness |
| --- | --- |
| W1 | Negation handling is window-based and clause-blind: "not only high return but also risk free" would suppress the wrong signal. |
| W2 | Signals are single-language word families; a third language needs new classes, not a translation table. |
| W3 | Signal overlap is unavoidable in places (`guarantee` appears in both certainty and risk-negation classes), so some text is matched by more than one path. |
| W4 | Confidence is a formula (`0.6 + 0.1` per extra signal class, capped at 0.9), not a calibrated probability. |
| W5 | 50 synthetic cases cannot estimate real-world precision or recall. |

## 7. Production Recommendation

```text
Do not promote to production yet.
```

1. **Keep the prototype out of the gate.** Step 6 is verified by test: no module
   under `runtime/`, `workflows/`, `evaluation/`, `distillation_core/`,
   `plugins/`, `production/`, `core/`, `config/`, `schema_validation/`,
   `security/` or `artifact/` imports `risk_evaluation`. Production detection is
   still the plugin's keyword rules, unchanged.
2. **Do not treat +90 points as a production number.** It is in-sample. The
   next step is an independent corpus, collected under whatever authorization
   real-material handling requires — not more tuning against these 50 cases.
3. **Then re-run the same 50 cases unchanged** so the in-sample and
   out-of-sample numbers can be compared.
4. **Do not spend effort on F2** before deciding F1: the category boundary for
   attributed price targets is a taxonomy question and affects more cases than
   the single missing suggestion.
5. **Before any wiring, decide the failure policy.** The semantic evaluator
   trades false negatives for possible false positives. Because `block` forces
   `review_required` rather than publishing anything, a false positive costs
   reviewer time, not safety — which is the right direction for a risk layer,
   but it must be a deliberate decision rather than a side effect.
6. **A production evaluator should combine both.** The keyword evaluator is
   exact on enumerated wording and free of false positives; the semantic
   evaluator generalises. An ensemble that requires either to fire, with
   per-evaluator attribution preserved in `RiskEvaluationResult.evaluator`,
   is the natural next experiment — again measured on this benchmark first.

## 8. Validation

| Check | Command | Result |
| --- | --- | --- |
| Unit tests | `python -m unittest discover -s tests -v` | **PASS** — Ran **219** tests, OK (160 before, 59 new) |
| Compile | `python -m compileall .` | **PASS** — exit 0 |
| JSON | all `*.json` | **PASS** — 23/23 |
| Secret scan | workspace and repository root | **PASS** — 0 findings both scopes |
| Benchmark | `python -m risk_evaluation.benchmark` | measured; section 4 |

New tests (59), against the required minimum of 30:

| Group | Count | Covers |
| --- | ---: | --- |
| `tests/risk_semantic_evaluator/test_interface.py` | 8 | protocol conformance, three interchangeable implementations, no plugin-rule coupling, input validation, artifact evaluation without circularity |
| `tests/risk_semantic_evaluator/test_signals.py` | 20 | every signal class, spans, negation marking, negation window bound, self-negative patterns, CJK regression, compositional conjunctions |
| `tests/risk_semantic_evaluator/test_semantic_cases.py` | 10 | the four required semantic cases, multi-risk sentences, disclaimed risk, legitimate explanation, explainability |
| `tests/risk_semantic_evaluator/test_comparison.py` | 18 | benchmark execution, both-evaluator scoring, metric deltas, case table, serialization, confidence formula and cap, production isolation |
| `tests/risk_evaluation_framework/test_benchmark.py` | +3 | expanded composition, `flagged` vs `matched`, no risky expectation on safe cases |

The comparison group **pins all eight measured metrics to this report**, so
changing either evaluator fails the suite and forces this document to be
updated in the same change.

## 9. What this phase does not claim

- It does not claim semantic risk detection is production ready — section 7.
- It does not claim the evaluator "understands" intent. It is an explainable
  rule system that composes surface signals; it approximates semantics.
- It does not claim +90 points of paraphrase recall generalises — section 5.
- It does not claim the taxonomy is right; F1 shows it is not settled.
- It does not claim the gate, runtime or workflow changed. They did not.
