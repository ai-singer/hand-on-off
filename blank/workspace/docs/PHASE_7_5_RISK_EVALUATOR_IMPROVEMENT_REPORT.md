# Phase 7.5 - Risk Evaluator Improvement and Taxonomy Repair

Phase: 7.5
Status: **PASS WITH ISSUES**
Date: 2026-09-27
Evaluator under test: `semantic-intent-v2`
Benchmarks: `semantic/v3` (measured, contaminated), `semantic/v4` (governed, frozen)

---

## 1. What was asked and what was delivered

Phase 7.4 left the framework with a working governance layer and a measured
capability boundary. Phase 7.5 was asked to make the *evaluator* better without
weakening the governance that measures it.

| Deliverable | State | Evidence |
| --- | --- | --- |
| `taxonomy_v2` with orthogonal `statement_source` / `certainty_level` | delivered | `risk_evaluation/taxonomy_v2.py`, 37 tests |
| Separate `market_prediction` into three claim cases | delivered | `MARKET_CLAIM_CASES`, 13 tests |
| Annotation guide v2 | delivered | `docs/RISK_ANNOTATION_GUIDE_v2.md` |
| Benchmark `semantic/v3`, >= 120 cases, 70/25/25, >= 20 per focus | delivered | 120 cases, 70/25/25, attribution 26, conditional 20, market-boundary 22 |
| `semantic_evaluator_v2` with attribution and conditional awareness | delivered | `risk_evaluation/semantic_evaluator_v2.py` |
| Old-versus-new comparison on the same benchmark | delivered | `risk_evaluation/validation_v2.py` |
| `evaluation_freeze_v2.json` | delivered | taxonomy, evaluator, benchmark, annotation version, config |
| >= 60 tests | delivered | **279 tests** in this phase's package, all passing |
| This report | delivered | 5 guide/implementation defects and 6 limitations stated |

Two things did **not** go as planned and are the substance of this report:

1. `semantic/v3` **fails its own contamination audit** (32 reused development
   texts). It is published as measured, marked `contaminated`, and a
   decontaminated subset is published alongside it as `semantic/v4`.
2. Five examples published in the new annotation guide are **not reproduced by
   the new evaluator**. They are enumerated as defects in section 6.

Neither was hidden, and neither was repaired after measurement.

---

## 2. Taxonomy v2: two orthogonal dimensions

v1 had one axis: five risk categories. That axis could not express the
difference between *the author predicts X* and *the author reports that someone
else predicts X*, which is the difference between a risky claim and a citation.
v2 adds two dimensions beside the categories rather than adding categories.

`statement_source` (4 values): `author`, `third_party`, `quoted`, `unknown`.
`certainty_level` (4 values): `certain`, `probable`, `possible`, `hypothetical`.

They are orthogonal: no value is shared, and the two dimensions cross to produce
16 states against the same five categories. The five v1 categories and their
severities are unchanged; v2 adds no category.

The dimension that does the work is attribution. v1's `market_prediction`
conjunction fired on any future-facing certainty, whoever was speaking, so
`Management expects the stock to reach 500.` and `The stock will reach 500.`
scored identically. v2 splits the market claim three ways:

| Case | Definition | Category |
| --- | --- | --- |
| explicit prediction | author's own voice, asserted as certain | `market_prediction` |
| attribution expectation | someone else's expectation or estimate | not `market_prediction` |
| scenario analysis | conditional or hypothetical outcome | not `market_prediction` |

Formally: `market_prediction` iff `statement_source == author` **and**
`certainty_level == certain`.

Four categories are author-voice claims and are withdrawn when a claim is
attributed; `unverified_information` is attribution-agnostic, because reporting
an uncheckable source is a risk whatever the voice.

---

## 3. Benchmarks: v3 as measured, v4 as governed

### 3.1 Composition

`semantic/v3` was authored fresh for this phase under guide v2: 120 cases.

| Dimension | Distribution |
| --- | --- |
| group | risk 70, safe 25, boundary 25 |
| focus | attribution 26, conditional 20, market-boundary 22, general 52 |
| statement_source | author 82, unknown 18, third_party 13, quoted 7 |
| certainty_level | certain 92, hypothetical 20, probable 5, possible 3 |
| labels | investment_advice 18, unverified_information 18, market_prediction 16, emotional_manipulation 10, financial_guarantee 10 |

Every Phase 7.5 minimum is met, including the three >= 20 focus requirements.

### 3.2 The audit failed

The Phase 7.4 contamination auditor was run on v3 as published. It failed:

```
benchmark      : semantic/v3
cases          : 120
status         : FAIL
findings       : 32
  development_overlap    32
affected cases : 32
```

32 of the 120 texts are sentences reused from `risk_evaluation.benchmark`, the
set the evaluators were designed against. There are **no** exact or near
duplicates inside v3, so this is not a self-duplication problem: it is genuine
development-set leakage, and it is the same class of failure Phase 7.3 found in
v1 (38 of 100).

The affected identifiers: `ae-01`, `ae-02`, `bp-01`, `bp-02`, `em-01`, `em-04`,
`fg-01`–`fg-04`, `fg-07`, `gs-01`–`gs-04`, `gs-07`, `ia-01`–`ia-07`, `ia-11`,
`mp-01`–`mp-03`, `mp-06`, `ui-01`–`ui-04`.

### 3.3 Why v3 was not repaired

The obvious response is to rewrite those 32 texts. It was rejected for the same
reason Phase 7.4 rejected deleting v1's contaminated cases: the comparison had
already been run, and editing a benchmark after seeing what it measures is not
authoring, it is tuning. Relabelling the cases that the evaluator fails is
indistinguishable from relabelling the cases that flatter it.

Instead v3 is registered with `status: contaminated` and kept exactly as
measured, and the 88 cases that do not overlap the development set are published
as a second version:

| Version | Cases | Status | `dataset_hash` |
| --- | --- | --- | --- |
| `semantic/v1` | 100 | contaminated (38) | `950428a98d52fad3…` |
| `semantic/v2` | 62 | frozen | `c01fe03efe22c441…` |
| `semantic/v3` | 120 | contaminated (32) | `1432cda8ed1d7fc4…` |
| `semantic/v4` | 88 | frozen | `8765b6fec4a115a9…` |

`semantic/v4` passes its audit with zero findings. It is the version the freeze
rests on. This is the same pattern Phase 7.4 applied to v1/v2, and it means the
governance layer caught a defect introduced in the same phase that extended it.

### 3.4 v4's own weakness

v4 is clean but thin, and the thinning is not neutral. It loses 23 risk cases
and 5 safe cases, and it drops below one of the phase's own minima:

| Focus | v3 | v4 | Minimum |
| --- | --- | --- | --- |
| attribution | 26 | 22 | >= 20 |
| conditional | 20 | 20 | >= 20 |
| market-boundary | 22 | **16** | >= 20 |

Five of the six removed market-boundary cases were reused development sentences.
So the decontaminated benchmark is weakest in exactly the dimension this phase
wanted to measure, and the market-boundary measurements in section 5 should be
read as directional rather than settled. Closing that gap needs fresh
market-boundary cases in a later phase.

---

## 4. `semantic-intent-v2`

v2 reuses v1's signal layer and adds three analyses on top: `analyze_attribution`,
`analyze_certainty` and `detect_reader_pressure`. The categories are then
resolved by `resolve_category_conflicts`, which encodes the rule that v1 left
implicit: **dramatic market vocabulary is not emotional manipulation.**
Manipulation requires pressure aimed at the reader — an imperative, a deadline,
or herd framing — not merely a dramatic word.

The evaluator reports not only what it decided but what it suppressed and why,
so a disagreement can be audited instead of guessed at:

```
Sources say the market will certainly crash.
  statement_source   unknown          (v1: implicit author voice)
  certainty_level    certain
  market_claim_case  attribution_expectation
  categories         (unverified_information,)
  suppressed         (market_prediction,)
  v1 categories      (emotional_manipulation, market_prediction, unverified_information)
```

v2 remains protocol-compatible with `RiskIntentEvaluator`: `evaluate_text`,
`evaluate_artifact`, `source_ids` propagation and the result contract are
unchanged, so it is drop-in replaceable without touching any caller.

---

## 5. Old versus new

Both benchmarks were scored with the same three evaluators, the same cases and
the same metric code. `keyword` is `keyword-xiaolin-finance-v1`, `semantic_v1`
is `semantic-intent-v0`.

### 5.1 On `semantic/v3` (120 cases, as published)

| Metric | keyword | semantic_v1 | semantic_v2 |
| --- | --- | --- | --- |
| macro F1 | 0.2412 | 0.7721 | **0.8174** |
| micro precision | 0.6875 | 0.8125 | **0.8966** |
| micro recall | 0.1528 | 0.7222 | 0.7222 |
| false positive rate | 8.00% | 18.00% | **8.00%** |
| false negative rate | 84.29% | 25.71% | 25.71% |
| paraphrase recall | 0.00% | 68.97% | **70.69%** |

v1 → v2: `macro_f1 +0.0453`, `micro_precision +0.0841`, `micro_recall +0.0000`,
`false_positive_rate -0.1000`, `false_negative_rate +0.0000`.

Per-category F1, v1 → v2:

| Category | v1 | v2 |
| --- | --- | --- |
| emotional_manipulation | 0.857 | **0.947** |
| financial_guarantee | 0.857 | **0.947** |
| investment_advice | 0.757 | 0.778 |
| market_prediction | 0.615 | 0.640 |
| unverified_information | 0.774 | 0.774 |

### 5.2 On `semantic/v4` (88 clean cases) — the decontamination check

| Metric | keyword | semantic_v1 | semantic_v2 |
| --- | --- | --- | --- |
| macro F1 | 0.1433 | 0.6636 | **0.7236** |
| micro precision | 0.5556 | 0.7250 | **0.8286** |
| micro recall | 0.1042 | 0.6042 | 0.6042 |
| false positive rate | 7.32% | 19.51% | **9.76%** |
| false negative rate | 89.36% | 38.30% | 38.30% |

v1 → v2: `macro_f1 +0.0600`, `micro_precision +0.1036`, `micro_recall +0.0000`,
`false_positive_rate -0.0975`, `false_negative_rate +0.0000`.

### 5.3 What this does and does not support

**Supported.** The headline gain is real and it is not contamination:

- the macro-F1 gain **grows** from +0.0453 to +0.0600 when the 32 reused texts
  are removed;
- the false-positive-rate gain is essentially unchanged (−0.1000 → −0.0975).

The mechanism is visible in the cases. `The market will certainly crash.` is
`(emotional_manipulation, market_prediction)` under v1 and `(market_prediction,)`
under v2. `Sources say the market will certainly crash.` is three categories
under v1 and `(unverified_information,)` under v2. `You would be crazy not to
buy.` is nothing under v1 and `(emotional_manipulation,)` under v2 — a genuine
new true positive, not merely a removed false one.

The gain is **precision, not recall**: recall is identical to four decimal places
on both benchmarks. v2 removes false positives; it does not find more risk.

**Not supported.** Two claims this phase might have made are false:

- **The market-prediction advantage is contamination.** On all 120 cases v2
  scores 81.8% against v1's 77.3%. On the 88 clean cases both score exactly
  **75.0%**. The apparent advantage came entirely from the reused development
  sentences — precisely the cases an evaluator designed on that material is
  expected to win. There is no demonstrated market-prediction improvement.
- **Attribution awareness is close to solved.** Accuracy is 91.7% on v3 but
  **88.6%** on the clean subset, and the errors are systematic, not noise: all
  ten are the same defect (section 6.2).

**Not measured at all.** No real-material corpus, no out-of-domain finance text,
and no independent annotator. Every case is synthetic and labelled by the same
author who wrote the evaluator. `semantic/v4`'s market-boundary sample is 16
cases, below the phase's own minimum.

---

## 6. Defects and limitations

### 6.1 Five guide examples the evaluator does not reproduce

These are the guide's own published examples. Each is a case where the normative
document states one outcome and the implementation produces another. They are
pinned by `tests/risk_evaluator_v2/test_guide_conformance.py` so that fixing one
is a deliberate, visible act.

| # | Guide says | Evaluator does | Cause |
| --- | --- | --- | --- |
| 1 | `The stock will rise.` → `market_prediction` | no category | `market_prediction` still requires an explicit certainty marker, so implied certainty is missed |
| 2 | `If the margin holds, the company could grow, but that is uncertain.` → no category | `investment_advice` | `holds` is a v1 directive verb; "the margin holds" is not a directive |
| 3 | `Should the market decline, the position would lose value.` → no category | `investment_advice` | `should` is a v1 directive verb; the sentence-initial conditional pattern does not withdraw it |
| 4 | `Were the deal to close, revenue might rise.` → `hypothetical` | `possible` | the `were … to` pattern spans only a one-word subject |
| 5 | section 6.2 precedence orders the report | alphabetical order | `resolve_category_conflicts` returns precedence order but the caller converts it to a set, so precedence selects and orders nothing |

Defect 1 is the most serious: the taxonomy layer classifies
`The share price will double next year.` as `explicit_prediction` with
`certainty_level = certain`, and the category layer then reports nothing. The
declared definition and the implemented one are not the same, which is a
specification gap rather than a recall miss. It is a direct contributor to
`market_prediction` being the weakest category (F1 0.640).

Defect 5 is why `CATEGORY_PRECEDENCE` should currently be read as documentation
of intent rather than as a rule in force.

### 6.2 The source lexicon is thin

Eight of the ten attribution errors are author-voice false negatives with one
shared cause: the phrase has no marker, so an attributed claim is read as the
author's own.

| Case | Text | Labelled | Detected |
| --- | --- | --- | --- |
| `ui-12` | I was told the factory is closing. | unknown | author |
| `ui-14` | 网上传该公司即将退市。 | unknown | author |
| `ui-15` | A source close to the deal mentioned a delay. | unknown | author |
| `ui-16` | Everybody says the founder is leaving. | unknown | author |
| `ui-17` | Leaked internal documents suggest a restatement. | unknown | author |
| `as-02` | The audit confirmed the figures reported in the annual filing. | third_party | author |
| `as-03` | The company disclosed a change in accounting policy. | third_party | author |
| `as-04` | The exchange published the revised listing rules. | third_party | author |
| `ui-18` | An unnamed banker says the deal is off. | unknown | third_party |
| `bd-03` | The broker note says the stock is a buy, which the article does not endorse. | third_party | quoted |

The first eight are vocabulary. `ui-18` is the same vocabulary problem in the
other direction (`unnamed` is not a vague marker but `banker` is a named party).
Only `bd-03` is a logic consequence: the rejection rule of guide section 4
outranks a named source.

The precedence logic, the orthogonality of the dimensions and the suppression
mechanism are **not** what is failing. Widening the lexicon is the highest-value
next step and it is a bounded change.

### 6.3 Carried over from v1, unresolved

- no quotation awareness in the signal layer (v2 adds it at the attribution
  layer only);
- `the margin holds` type modal/verb ambiguity;
- hedged author claims (`probable`/`possible`) cannot be `market_prediction`,
  which may under-report genuinely risky hedged promotion;
- same-author labelling and synthetic-only corpus;
- annotation independence remains incomplete.

---

## 7. Governance, freeze and verification

`evaluation_freeze.json` (v1) is **not** rewritten and `evaluation_freeze_v2.json`
is added beside it. The v2 freeze records five verified components:

| Component | Value |
| --- | --- |
| evaluator | `semantic-intent-v2` / `cbe305aa1b4648c0…` |
| taxonomy | `2.0.0` / `a18bfad9f9608a55…` |
| benchmark | `semantic/v3` + `semantic/v4` / `58c3bf8da3e4a2d5…` |
| annotation | `docs/RISK_ANNOTATION_GUIDE_v2.md@2.0.0` / `2.0.0` |
| config | `d3cb2f0130659f6b…` |
| governed benchmark | `semantic/v4` (88 cases, frozen) |
| measured benchmark | `semantic/v3` (120 cases, contaminated) |

### 7.1 A governance conflict found and fixed

Registering `semantic/v3` and `semantic/v4` broke verification of the **Phase 7.4
freeze**. `benchmark_hash` hashed *every registered version*, so adding a
benchmark retroactively invalidated a freeze that never covered it —
`verify_evaluation_freeze()` reported `CHANGED: benchmark_hash`.

Rewriting the old freeze was not an option: it is the historical record of the
Phase 7.2 evaluation. The fix is that a freeze now declares its scope, via
`FROZEN_VERSION_SCOPE = ("semantic/v1", "semantic/v2")`, and `benchmark_hash`
hashes exactly that scope. The payload is byte-identical to what was recorded,
so `evaluation_freeze.json` still verifies against its original digest
`401983f377e28a9a…` and nothing historical was altered.

Without this, a project could never add a benchmark version without appearing to
have changed its past results.

### 7.2 Verification

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests` | **658 passed, 0 failed** (was 376 at phase start) |
| Phase 7.5 suite (`tests/risk_evaluator_v2/`) | 279 passed (requirement: 60) |
| `python -m compileall` | PASS |
| JSON validity (all workspace JSON) | 42/42 PASS |
| Secret scan (workspace + repository root) | PASS |
| `release_freeze.verify_evaluation_freeze()` | MATCH |
| `release_freeze_v2.verify_evaluation_freeze()` | MATCH |
| `benchmark_registry.verify_all()` | all True |
| contamination audit `semantic/v1` | FAIL, 38 (unchanged from 7.3) |
| contamination audit `semantic/v2` | PASS |
| contamination audit `semantic/v3` | **FAIL, 32** |
| contamination audit `semantic/v4` | PASS |
| `risk_evaluation` imported by production code | none (isolation test passes) |

Baseline before this phase was 376 tests. 279 were added in the new package and
3 in the Phase 7.4 governance suites; one Phase 7.4 test was replaced by three
narrower ones. No test was deleted.

### 7.3 What the grown registry required

Adding two benchmark versions exposed three Phase 7.4 assumptions that were
written when only v1 and v2 existed. All three were updated to describe the
registry as it now is, not to accommodate Phase 7.5:

- `test_registry_lists_both_versions` now asserts all four versions;
- `test_manifest_records_the_annotation_contract` now expects guide v1's
  protocol for v1/v2 and guide v2's for v3/v4, since a version's protocol is
  fixed at export;
- `test_every_version_and_evaluator_runs` now expects 4 versions x 2 frozen
  evaluators = 8 regression runs.

`semantic/v3` and `semantic/v4` also needed recorded baselines, because a
benchmark version without one cannot be governed. Both were written
(`benchmarks/semantic/v3/baseline.json`, `v4/baseline.json`) using the **frozen**
v1 evaluators, so they record v1's scores as the reference point: v3 keyword
0.2412 / semantic 0.7721, v4 keyword 0.1433 / semantic 0.6636.

`write_baseline()` gained a `versions` filter so the v1 and v2 baselines could
be proven byte-identical rather than merely assumed so; both were verified
unchanged before and after.

The regression framework still covers only the two frozen evaluators. The
old-versus-new comparison of `semantic-intent-v2` deliberately lives in
`validation_v2`, not in `EVALUATORS`, so that the Phase 7.4 regression process
keeps meaning "has a frozen evaluator moved on a frozen benchmark" and is not
entangled with a prototype that is still changing.

---

## 8. Production recommendation

**Do not connect `semantic-intent-v2` to the Quality Gate.** The Phase 7.4
prohibition stands and this phase does not lift it. The reasons are specific:

- five published guide examples are not implemented, one of which is a
  definition/implementation disagreement about what a prediction *is*;
- attribution accuracy on clean data is 88.6% and its failures are systematic,
  concentrated in exactly the unattributed-hearsay phrasing that finance content
  uses most;
- the only clean benchmark has 16 market-boundary cases, so performance in the
  dimension this phase targeted is not established;
- every case is synthetic and labelled by the evaluator's own author.

What Phase 7.5 *does* establish, with evidence: v2 is a strictly better
**offline analysis** evaluator than v1 on precision and false-positive rate, the
gain survives decontamination, and the taxonomy can now express the distinction
between making a claim and reporting one. That is a real capability increase. It
is not a production gate.

### What the next phase should do, in order

1. Widen the source lexicon (`I was told`, `a source close to`, `everybody
   says`, `leaked documents suggest`, `the company said`, `the report
   estimates`, `unnamed`, and Chinese hearsay markers). This is the single
   highest-value change and it is bounded.
2. Resolve defect 1 by making the `market_prediction` pattern accept implied
   certainty, so the implemented definition matches the published one.
3. Fix the `were … to` pattern (defect 4) and make precedence either functional
   or explicitly documentary (defect 5).
4. Author fresh market-boundary cases to restore v4's focus minimum to >= 20.
5. Obtain a real-material corpus and an independent annotator before any further
   capability claim.

---

## 9. What this phase does not claim

- It does not claim `semantic-intent-v2` is correct. Five guide/implementation
  defects and six limitations are stated above, each pinned by a test.
- It does not claim `semantic/v3` is a valid benchmark. It fails its own audit
  and is published as contaminated.
- It does not claim a market-prediction improvement. On clean data there is
  none.
- It does not claim recall improved. It did not move at all.
- It does not claim the v2 measurements generalise. They are synthetic,
  self-annotated and concentrated on one domain.
- It does not claim the frozen v1 artefacts changed. They did not; their
  recorded digests still verify, and the v1 freeze's `benchmark_hash` is still
  the digest recorded in Phase 7.4.
- It does not claim the new benchmark's market-boundary dimension is settled.
  `semantic/v4` has 16 such cases, below this phase's own minimum of 20.
