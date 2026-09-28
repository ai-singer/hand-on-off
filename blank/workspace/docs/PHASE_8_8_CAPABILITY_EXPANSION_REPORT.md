# Phase 8.8 - Risk Evaluation v3.1 Capability Expansion

Phase: 8.8
Status: **PASS WITH ISSUES**
Date: 2026-09-28
Subject: `risk_evaluation/v3` (four files) and the new `risk_evaluation/v3_1`
Capabilities: P1 modal prediction detection, P2 advice boundary detection
Benchmark: `capability_v3_1/v1` (80 cases, synthetic, **not independent**)
Production changed: **no**

> Phase 8.8 extends measured risk detection capability under frozen evaluation
> constraints.

---

## 1. Objectives

The phase asked for two capability gaps to be closed, for a benchmark to measure
them, and for the whole of Phase 8.7's regression to stay green.

| Objective | Result |
| --- | --- |
| P1 modal prediction detection | **met**: 60/60 capability verdicts, 18/18 PREDICTION relations |
| P2 advice boundary detection | **met**: 22/22 ADVICE relations, 8/8 education cases declined |
| Independent annotation preparation | **met**: `docs/INDEPENDENT_ANNOTATION_PROTOCOL_V2.md` |
| Benchmark ≥ 80 cases in three groups | **met**: 80 = 30 + 30 + 20 |
| Contamination audit, FAIL kept as FAIL | **met**: PASS after one blocking finding was recorded and resolved |
| Phase 8.7 regression `broken = 0` | **met**: 0 across 280 cases in six sets |
| ≥ 100 new tests | **met**: 169 |
| No other track touched | **met**: section 8 |

### 1.1 The two gaps, as measured before any Phase 8.8 code existed

The capabilities were not designed from a description. Two probe sets were run
against the pipeline as Phase 8.7 left it, and every case in them became a test.

| Probe | Cases | Wrong | False positives | False negatives |
| --- | --- | --- | --- | --- |
| capability gap (modal + advice shapes) | 60 | 9 | 3 | 6 |
| capability defect (`will probably`, `hold`/`keep`/`stay`/`remain`) | 28 | 8 | 4 | 4 |
| **total** | **88** | **17** | **7** | **10** |

All 17 are now correct, and all 88 sentences are covered by the test suite or by
the benchmark. The two findings that decided the design were these:

```
The market will probably crash next month.   was market_prediction   -> FP
```

`will` is a `certain` marker on its own and `probably` is a `probable` one, and the
sentence is the weaker of the two. Guide v2 section 2 raises `market_prediction`
only at `certain`, so this was a false positive produced by a frame that could see
one modal and not the other.

```
Custodians hold fund assets in safekeeping.  was investment_advice    -> FP
```

`hold` is a directive verb and the sentence has a financial object, so the ADVICE
frame matched. The verb has a subject, so the sentence is a statement about
custodians. The phase names this surface and forbids the obvious fix of disabling
`hold`, which would lose `Hold this fund through the downturn.`

---

## 2. New files

```
risk_evaluation/v3_1/__init__.py                             lazy exports
risk_evaluation/v3_1/signals.py                              the signal vocabulary
risk_evaluation/v3_1/certainty.py                            modal strength -> taxonomy certainty
risk_evaluation/v3_1/modal.py                                Capability 1
risk_evaluation/v3_1/advice.py                               Capability 2
risk_evaluation/v3_1/detectors.py                            both layers over one claim
risk_evaluation/v3_1/audit.py                                contamination audit
risk_evaluation/v3_1/evaluation.py                           metrics and error analysis
risk_evaluation/v3_1/regression.py                           the six-set gate
risk_evaluation/v3_1/freeze.py                               baseline verification and the v3.1 freeze
risk_evaluation/v3_1/benchmark/__init__.py
risk_evaluation/v3_1/benchmark/cases.py                      the 80 cases
risk_evaluation/v3_1/phase_8_8_baseline_freeze.json          taken before the first change
risk_evaluation/v3_1/evaluation_freeze_v3_1.json             the state these numbers were measured on
risk_evaluation/v3_1/benchmark/capability_v3_1.json          the dataset
risk_evaluation/v3_1/audit_report_v3_1.json                  governance, incl. the pre-publication finding
risk_evaluation/v3_1/predictions_v3_1.json                   blind predictions
risk_evaluation/v3_1/metrics_v3_1.json                       metrics, per case and per category
risk_evaluation/v3_1/error_analysis_v3_1.json                every failure classified
risk_evaluation/v3_1/regression_v3_1.json                    the six-set gate
tests/risk_evaluation_v3_1/__init__.py
tests/risk_evaluation_v3_1/test_capability_layers.py         69 tests
tests/risk_evaluation_v3_1/test_benchmark_and_governance.py  100 tests
docs/INDEPENDENT_ANNOTATION_PROTOCOL_V2.md
docs/PHASE_8_8_CAPABILITY_EXPANSION_REPORT.md
```

Modified, all inside `risk_evaluation/v3/` and all listed in section 8:

| File | Change | Why it is the minimum |
| --- | --- | --- |
| `model.py` | `IntentEvidence` gains `signals`, `certainty`, `boundary`; `RiskClaim` gains `boundary_declined`, `capabilities` | a frame matches or does not and cannot carry a signal list; the phase requires one |
| `adapters/intent_pattern.py` | runs the two layers, amends or vetoes frame findings, exposes `capabilities=False` | the layers belong to the intent stage, not beside it |
| `decision.py` | a declined boundary joins `declined` as evidence against the fallback | a layer that examined a structure and declined it outranks a keyword evaluator |
| `pipeline.py` | passes `boundary_declined` and `capabilities` onto the claim | claim-level evidence, as section 7 of the phase requires |

**The Phase 8.4 pattern set was not touched.** `risk_evaluation/v3/patterns.py` is
byte-identical, and the freeze says so: `evaluator_hash` is `6768eb66…` in the
Phase 8.7 freeze and `6768eb66…` here. The capability owns its two verb families
outright rather than adding frames for other phases to share.

---

## 3. Baseline freeze

Taken at `8b627c8` with a clean working tree, before the first Phase 8.8 change,
and re-verified after the last one.

| Component | At baseline | After Phase 8.8 | Moved |
| --- | --- | --- | --- |
| evaluator (pattern set) | `6768eb66f7e28d2c…` | `6768eb66f7e28d2c…` | **no** |
| taxonomy | `a18bfad9f9608a55…` | `a18bfad9f9608a55…` | **no** |
| decision policy | `28f446e583d1ce77…` | `28f446e583d1ce77…` | **no** |
| benchmark (Phase 8.6 `independent_v1`) | `1bf9c9bdc4a78ed0…` | `1bf9c9bdc4a78ed0…` | **no** |
| configuration | `c6aa35c480548563…` | `c6aa35c480548563…` | **no** |

`verify_baseline()` reports **MATCH: no inherited component moved**, and the
Phase 8.7 repair freeze still verifies MATCH at this commit.

Phase 8.7's regression was re-run before the first change and reproduced exactly:
200 cases, 168 → 183 correct, `broken 0`.

That "no inherited component moved" is the strongest single statement in this
report, and it has a boundary worth naming. The `decision_policy_hash` covers the
rule table, the actions and the relation-to-category map. It does **not** cover the
new boundary channel, because the Phase 8.6 schema has no slot for a second source
of fallback evidence. That change is frozen separately, in
`capability_table_hash = 44bee1c0f239d5a7…`.

The Phase 8.8 freeze records what the earlier schemas could not:

```
capability_table_hash        44bee1c0f239d5a7   verdicts, signals, directives, carriers, rules
capability_benchmark_hash    aee706cfd6647171   the 80 cases
baseline_hash                bfeb733a6c5a42ae   the pre-change baseline
capability:signals           9414436a5dde2922
capability:certainty         e836b31987058f5b
capability:modal             054694020beb58ae
capability:advice            6f59933aa0a98f14
capability:detectors         447f792321039f58
gate                         PASS, broken 0, 6 sets
```

The gate verdict is inside the freeze rather than only in this document. A freeze
that hashed a pipeline which had broken a case would be a freeze of a failure, and
putting the verdict in the same artifact makes that visible.

---

## 4. Capability changes

### 4.1 P1 - modal prediction detection

The layer answers one question: **at which of the taxonomy's four certainty levels
is this statement put?** Guide v2 section 2 makes that the whole of the category
rule, and the four levels are imported from `taxonomy_v2` rather than invented, so
the layer and the guide cannot drift apart.

Four signals, the first three of which the phase names:

| Signal | What it is | What it excludes |
| --- | --- | --- |
| `market_entity` | a financial target, from the Phase 8.4 entity lexicon | a modal about a fee or a document |
| `outcome_expression` | a **directional** outcome | `fluctuate`, `vary`, `differ`, `change` |
| `uncertain_prediction_modal` | a strength carrier, classified | — |
| `future_marker` | a horizon, or a construction future by grammar | a statement about what is already true |

`outcome_expression` does the most work. `may fluctuate`, `may vary` and
`may differ` are disclosures that name no direction, so requiring a directional
outcome answers the whole `educational_uncertainty` group without a list of
disclosure formulas.

**Strength is read from the sentence, not from the verb, and the weakest carrier
wins.** `Perhaps the fund will outperform` puts its possibility before the subject
and outside any frame; `The market will probably crash` puts it after the verb. Both
are `probable` or `possible`, and both are therefore not predictions.

Verdicts, each named in the trace:

| Verdict | Meaning | Decision |
| --- | --- | --- |
| `prediction` | author voice, `certain`, all four signals | relation asserted → `market_prediction` |
| `weak_prediction` | a prediction below `certain` | relation hedged → suppressed |
| `non_directional` | a symmetric pair, or a directionless verb | declined |
| `non_prediction_modal` | the modal's complement explains | declined |
| `conditional_scenario` | guide 5: asserts nothing unconditionally | declined, **no relation** |
| `no_modal` / `no_outcome` / `no_market_entity` / `no_future_orientation` | not this layer's shape | **not** declined |

The last row is the design decision that keeps the layer honest. "Not my shape" is
not evidence that no prediction is present, so those four verdicts do not veto a
frame and do not decline a category. `Turnover expands sharply next quarter.` has no
modal at all, and the Phase 8.4 horizon frame is right to call it a prediction; a
layer that vetoed on `no_modal` would have broken a case Phase 8.7 had fixed.

### 4.2 P2 - advice boundary detection

Guide v2 section 7 gives advice one sentence of definition and one of boundary: an
action-directive aimed at the reader *and* a financial object, with educational
explanation and method guidance negative. Both halves were broken.

Four signals, all four the phase names: `addressee`, `imperative_structure`,
`financial_action_object`, `position_action`.

**The imperative test is clause position.** A directive in the imperative mood has
no subject, so its verb begins its clause:

```
Hold this fund through the downturn.          clause-initial   -> a directive
Custodians hold fund assets in safekeeping.   not              -> a statement
When rates hold steady, income is unchanged.  not              -> a statement
If you want higher returns, buy this stock.   clause-initial   -> still a directive
```

The fourth row is why it is clause position and not sentence position: guide 5 keeps
a conditional *directive* as advice, and `buy` begins its clause without beginning
the sentence.

Verb form is the second half. A gerund or infinitive heading a clause is that
clause's subject, so `Holding diversified assets reduces risk.` and
`To hold a fund is to accept its charges.` contain no directive. A gerund that is
the head of a noun phrase is not a verb at all: `any single holding` is a noun, and
reading it as one produced a "third person subject" verdict for a sentence with no
verb in it.

**The method test is the object's specificity, not the verb's identity.**
`hold a diversified portfolio` and `hold this fund` are the same verb in the same
frame; one names a practice and the other a position, and guide 7 makes practice
guidance negative. An acquisition verb settles it on its own, because you cannot buy
or sell a practice: `buy the dip` names a position in market shorthand no noun list
carries.

**`would` is constitutive inside a declared advisory frame.** `A sensible investor
would avoid this fund.` was declined before this phase because Phase 8.4 marks
`would` as a hedge. Phase 8.5 already made this decision for `should` in
`DIRECTIVE_MODALS`: a marker that constitutes a relation cannot also hedge it. The
advisory frames are declared and named — `it would be prudent to`, `a sensible
investor would`, `investors would be wise to`, `we would suggest`, `now is the time
to`, and four more — so `would` never becomes constitutive on its own.

### 4.3 How the layers reach the pipeline

```
Claim -> Attribution -> Intent -> Decision
                            |
                    Phase 8.4 frames
                            |
                    v3.1 signal layers
                     amend | veto | add
```

A layer that reached a verdict **amends** the frame's finding on its span rather
than replacing it, and the amendment keeps the matcher's negation and its reporting
hedge. That is not tidiness. The first version replaced the finding outright, and
`The claim that the stock will certainly double is incorrect.` — reported speech the
matcher had correctly hedged with `claim` — became a kept `market_prediction`. It
broke Phase 8.5's `AR-08`, and the Phase 8.7 regression caught it.

A layer with **positive evidence against** a relation vetoes it: `method_guidance`,
`third_person_subject`, `non_directional`, `conditional_scenario` and the other
declining verdicts remove the frame's finding and name the category they declined.
That last part reaches the decision policy, so the semantic fallback cannot
reinstate a category a structural layer examined and rejected.

The two hedge policies differ on purpose and the guide decides the difference. For a
prediction the matcher's hedge is **preserved**, because nothing in the guide makes a
hedge constitutive of a prediction and dropping one could only raise a statement's
strength. For advice it is **constitutive**, because guide 5 says a conditional
directive is still advice — except for reporting hedges, which record that somebody
else is advising and belong to the attribution layer.

---

## 5. Benchmark result

`capability_v3_1/v1`: 80 cases. **Synthetic, single-annotator, and not
independent** — see section 5.4.

| | |
| --- | --- |
| capability verdict accuracy | **60/60 = 1.0000** |
| relation recall | **45/45 = 1.0000** |
| relation precision | **45/45 = 1.0000** |
| decisions correct | **79/80** |
| decision precision / recall / F1 | **1.0000 / 1.0000 / 1.0000** |
| tp / fp / fn / tn | 44 / **0** / **0** / 36 |
| claim evidence | 83/83 = 100% |
| claims carrying signals | 60 |
| claims carrying capability verdicts | 83 |

### 5.1 Per category, not one F1

| Category | Precision | Recall | F1 | tp / fp / fn |
| --- | --- | --- | --- | --- |
| `market_prediction` | **1.0000** | **1.0000** | 1.0000 | 9 / 0 / 0 |
| `investment_advice` | **1.0000** | **1.0000** | 1.0000 | 19 / 0 / 0 |
| `financial_guarantee` | 1.0000 | 1.0000 | 1.0000 | 9 / 0 / 0 |
| `unverified_information` | 0.8750 | 1.0000 | 0.9333 | 7 / 1 / 0 |
| `emotional_manipulation` | — | — | — | 0 / 0 / 0 |

`emotional_manipulation` has no cases because neither capability is about it, and
reporting 0.0000 as though it were a failure would misdescribe an untested category.

### 5.2 Per group and per sub-group

| Group | Cases | Correct | Accuracy |
| --- | --- | --- | --- |
| `modal_prediction` | 30 | 30 | **1.0000** |
| `advice_boundary` | 30 | 30 | **1.0000** |
| `regression` (frozen) | 20 | 19 | 0.9500 |

| Sub-group | Cases | Correct | fp | fn |
| --- | --- | --- | --- | --- |
| strong_prediction | 8 | 8 | 0 | 0 |
| weak_prediction | 8 | 8 | 0 | 0 |
| educational_uncertainty | 8 | 8 | 0 | 0 |
| non_financial_modal | 6 | 6 | 0 | 0 |
| direct_advice | 8 | 8 | 0 | 0 |
| indirect_advice | 8 | 8 | 0 | 0 |
| education | 8 | 8 | 0 | 0 |
| quoted_advice | 6 | 6 | 0 | 0 |
| frozen | 20 | 19 | 0 | 0 |

Both capability groups are perfect and the single imperfect group is the frozen one,
which is the right way round: the capability was not tuned on the labelled groups and
the one case it disagrees with is `83-ATT-01`, classified in section 7 as an
annotation issue rather than a detection failure. It is counted `tp` — the label
expects a risk and a risk was flagged — and `correct` is exact category match, so it
fails on the extra category only.

### 5.3 What the layer verdicts add over the decisions

A layer can reach the right decision for the wrong reason. `The stock may rise.`
comes out with no category whether the layer classified it as a `possible`
prediction or never looked at it, so the benchmark scores the **verdict** as well as
the decision. That is what the 60/60 is: for every authored case the layer reached
the verdict the label names, and the confusion matrix in `metrics_v3_1.json` is
empty.

60 of 83 claims carry a signal list, and every claim carries both capability
verdicts whether or not either fired — so a trace shows that a layer looked and
declined rather than never looked. That is the Phase 8.4 principle, applied to the
new layers.

### 5.4 Provenance, and why no number here is a real-world accuracy

The provenance block is inside the dataset artifact, and its two load-bearing
fields are:

```json
"synthetic": true,
"independent": false,
"annotation": "single-annotator engineering validation only"
```

Groups A and B were written by the same author as the capability they measure, and
by the same author who wrote the pipeline. That is the arrangement Phase 8.6 exists
to expose: the architecture scored 96.8% speaker accuracy and 100% relation recall
on Phase 8.5's own benchmark, and 74.0% and 67.5% on sentences it had not seen.

**Nothing in section 5 has that protection.** It is a development benchmark. Its
value is that it makes the capability falsifiable on named sentences, not that it
estimates accuracy on anything.

Group C is the partial answer: 20 cases whose labels were written before this phase
existed and are read from the frozen artifacts at import time rather than
re-annotated. It is a regression set, not an independence claim.

---

## 6. Regression result

Six sets, 280 cases. `broken` is measured against the pre-Phase-8.7 pipeline, so a
case Phase 8.7 fixed and Phase 8.8 damaged is caught rather than hidden behind an
unchanged total.

| Set | Cases | before → after | fixed | **broken** | unchanged | still right | still wrong |
| --- | --- | --- | --- | --- | --- | --- | --- |
| phase_8.1 | 15 | 6 → 6 | 0 | **0** | 15 | 6 | 9 |
| phase_8.3 | 9 | 8 → 8 | 0 | **0** | 9 | 8 | 1 |
| phase_8.4 | 17 | 16 → 16 | 0 | **0** | 17 | 16 | 1 |
| phase_8.5 | 60 | 54 → **57** | 3 | **0** | 57 | 54 | 3 |
| phase_8.6 `independent_v2` | 99 | 84 → **98** | 14 | **0** | 85 | 84 | 1 |
| phase_8.8 capability | 80 | 41 → **79** | 38 | **0** | 42 | 41 | 1 |
| **total** | **280** | 209 → **264** | **55** | **0** | 225 | 209 | 16 |

**`broken = 0`. The phase's release condition is met.**

The three frozen replay sets are byte-identical to Phase 8.7: same fixed list (empty),
same still-wrong list, same still-right counts. Phase 8.5's relation recall is back
at 1.0 after an intermediate version of the advice layer lost TQ-08.

Phase 8.6's independent benchmark improved on Phase 8.7 by two cases, and both were
false positives Phase 8.7's report listed as still open:

```
IV-072  Custodians hold assets on behalf of the fund.        -> []  was investment_advice
IV-089  Assuming rates hold, income is likely to be stable.  -> []  was investment_advice
```

Re-measured after Phase 8.8, `independent_v1` (100 cases) is:

| Metric | 8.6 | 8.7 | **8.8** |
| --- | --- | --- | --- |
| correct | 84 (v2) | 96 (v2) | **98 (v2)** |
| precision | 0.7750 | 0.9474 | **1.0000** |
| recall | 0.8378 | 0.9730 | 0.9730 |
| false positives | 9 | 2 | **0** |
| speaker accuracy | 73.74% | 98.99% | 98.99% |
| relation recall | 67.50% | 87.50% | 90.00% |

One failure remains on `independent_v1`: `IV-094`, the promoter annotation conflict
Phase 8.7 recorded and deliberately did not resolve. Section 7.5.

### 6.1 Two breaks were introduced, caught, and fixed

The phase's rule is that publication stops on a break. It did, twice.

| Case | What broke it | What fixed it |
| --- | --- | --- |
| `AR-08` (8.5) | the modal layer replaced the frame finding and dropped the matcher's reporting hedge, so correctly-suppressed reported speech became a kept prediction | amendments now preserve the matcher's hedge and negation |
| `IV-011` (8.6) | `Consider moving your capital into the equity fund.` was read as a third-person subject, because the clause-initial test knew only direct directives and not a transparent verb introducing one | the clause-initial test accepts `consider`/`recommend` + gerund |

Both were found by the regression suite and not by anything else. Neither is
mentioned in the benchmarks that motivated the capability.

---

## 7. Error analysis

Every failure is classified into one of the five kinds the phase names, from the
trace rather than from the symptom, so a reader can check each classification
against the evidence strings the pipeline produced.

| Kind | Count |
| --- | --- |
| `annotation_issue` | 1 |
| `lexical_gap` | 0 |
| `attribution_error` | 0 |
| `intent_ambiguity` | 0 |
| `decision_policy_issue` | 0 |
| unclassified | **0** |
| **failures** | **1 of 80 (1.2%)** |

### 7.1 The one failure

```
83-ATT-01  Analysts say the sector is volatile this year. Buy this stock before the quarter ends.
expected ['investment_advice']   got ['investment_advice', 'unverified_information']
kind     annotation_issue / label-omits-category
```

The label names one category and the pipeline produces two. The second is the
attributed first sentence: `Analysts say …` is carried on an unnamed collective, and
guide 7 makes that `unverified_information`.

**This is an annotation omission, and the evidence is that the semantic baseline
also produces it.** `semantic_evaluator_v2`, which knows nothing about Phase 8.8,
returns `unverified_information` for this text too. Two independent layers find a
category the label does not name, which is a finding about the label.

The case is a Phase 8.3 replay case, so the omission predates this phase and is
unchanged by it: it is `still_wrong` in the phase 8.3 row of section 6, exactly as it
was under Phase 8.7. The label was not edited to make it pass, because the phase
forbids changing expected results.

### 7.2 What the zeroes mean, and do not

`lexical_gap` is 0 on this benchmark, and that is a statement about 80 sentences
whose author knew what the capability detects. It is not a statement that the
lexical gaps are closed. The same is true of `attribution_error` at 0: the
attribution layer is unchanged by this phase, and its 0 here reflects a benchmark
whose quoted-advice group was written with the source lexicon in view.

The `phase_8.1` set is the counterweight, and it is still at 9 wrong of 15 — those
are adversarial sentences written to defeat a keyword evaluator, and neither of this
phase's capabilities touches them.

---

## 8. Isolation check

The phase forbids touching `multimodal_creator/`, `runtime/`, `production/`,
`workflow/`, `security/`, `artifact/`, the `xiaolin_finance` plugin and any frozen
benchmark content.

```
$ git status --porcelain
 M blank/workspace/risk_evaluation/v3/adapters/intent_pattern.py
 M blank/workspace/risk_evaluation/v3/decision.py
 M blank/workspace/risk_evaluation/v3/model.py
 M blank/workspace/risk_evaluation/v3/pipeline.py
 M blank/workspace/risk_evaluation/v3_repair/regression_report_v3_repair.json
 M blank/workspace/tests/risk_evaluation_v3_repair/test_regression_and_freeze.py
 M blank/workspace/tests/risk_evaluation_v3_validation/test_evaluation_and_errors.py
?? blank/workspace/docs/INDEPENDENT_ANNOTATION_PROTOCOL_V2.md
?? blank/workspace/risk_evaluation/v3_1/
?? blank/workspace/tests/risk_evaluation_v3_1/
```

`multimodal_creator/`, `runtime/`, `production/`, `workflows/`, `security/`,
`artifact/`, `plugins/`, `schemas/`, `distillation_core/` and `core/` appear
**nowhere** in the diff. Untracked directories under `multimodal_creator/`
(`observation/`, `pattern/`) belong to the concurrent Track B workstream and were
not staged by this phase; `tests/risk_evaluation_v3_1/test_benchmark_and_governance.py`
asserts by AST that nothing in `v3_1` imports a production, runtime, workflow,
artifact or multimodal module.

### 8.1 `risk_evaluation/v3`: exactly four files

| File | Lines changed | Why |
| --- | --- | --- |
| `model.py` | +44 | three fields on `IntentEvidence`, two on `RiskClaim`; `certainty` validated against the taxonomy |
| `adapters/intent_pattern.py` | +35/−5 | runs the layers, amends or vetoes, exposes the ablation switch |
| `decision.py` | +95/−3 | the declined-boundary channel and its comment |
| `pipeline.py` | +23 | passes the boundary verdicts and capability verdicts onto the claim |

`patterns.py`, `benchmark/`, `replay.py` and `morphology.py` are untouched. The
`evaluator_hash` is unchanged, which is a checkable statement of that.

### 8.2 Frozen content untouched

| Artifact | Check |
| --- | --- |
| Phase 8.6 labels (`v3_validation/cases.py`) | `benchmark_hash` `1bf9c9bd…` in both freezes |
| Phase 8.5 benchmark | `relation_recall` 1.0, `broken` 0, report regenerated only |
| Phase 8.1/8.3/8.4 replay sets | identical fixed, broken and still-wrong lists |
| Phase 8.7 repair freeze | still verifies MATCH |
| failure samples | none deleted; counts are 15/9/17/60/99/80 before and after |
| expected results | no benchmark label edited; the only test expectations changed are metric pins, each recording its predecessor |

### 8.3 Benchmark governance

`risk_evaluation/v3_1/audit.py`, 16 historical sources, four checks. Status
**PASS**: 0 blocking, 32 disclosed.

Group C is a declared regression set, so the audit distinguishes overlap from
contamination:

| Finding | Blocks? |
| --- | --- |
| an authored case appearing in any earlier set | **yes** |
| a group C case whose text appears in no set its declared phase publishes | **yes** |
| a group C case overlapping the frozen sets | no — disclosed, with source |
| two authored cases with the same text | **yes** |
| a development-set overlap | **yes** |
| a missing or unknown label field | **yes** |

The third row is disclosed rather than blocked, and the reason is measured: Phase
8.4's guarantee benchmark reuses wordings Phase 8.1 recorded as failures, and Phase
8.5 reuses Phase 8.3's, so copying a case faithfully imports a near-duplicate of
another. Blocking on that would fail this phase for redundancy it did not create
and cannot remove without editing frozen material.

**The audit caught a real contamination, and it is recorded rather than deleted.**
`MP-A2-08` was written as `Perhaps the fund will outperform its benchmark.` — which
is `IV-098` verbatim, one of the cases the new modal layer had been developed
against. Measuring the capability on it would have been exactly the arrangement
Phase 8.6 exists to expose. The finding is kept in `PRE_PUBLICATION_FINDINGS`, in
`audit_report_v3_1.json`, and in a test:

```
original_text      Perhaps the fund will outperform its benchmark.
replacement_text   Perhaps the share price will double this year.
resolution         rewritten before publication
```

The case was rewritten rather than deleted, because deleting it would have removed
the evidence that the audit works. The suite asserts both that the finding is
recorded and that the case now in the benchmark is the replacement.

---

## 9. Git commit

Commit subject: `feat: add risk evaluation v3.1 modal prediction and advice detection`

```
<phase 8.8 commit>  feat: add risk evaluation v3.1 modal prediction and advice detection
472d0d8             feat: add Phase M2 multimodal signal extraction prototype
8b627c8             fix: repair the three risk evaluation defects Phase 8.6 confirmed
```

The Phase 8.8 commit is the tip of `main` after this phase; its hash is not
reproduced here because writing a hash into a file that the same commit contains
makes the document wrong the moment it is recorded.

Contents: 32 files staged explicitly — the four `risk_evaluation/v3` edits, the
`v3_1` package and its 10 artifacts, 169 tests in `tests/risk_evaluation_v3_1/`, the
protocol document, this report, and the regenerated Phase 8.7 regression report.
Untracked files belonging to the concurrent Track B workstream were left unstaged.

Tests at the parent commit: 2092. After: **2261**. New tests: **169**, none removed,
none skipped. Full suite: **2261 pass, 0 failures**.

---

## 10. What this does not say

Phase 8.8 extends measured risk detection capability under frozen evaluation
constraints. It does not say any of the following, and none of them may be inferred
from the numbers above:

- **Risk detection is not solved.** On `independent_v1`, one case is still wrong and
  four relations are still missed; the adversarial set is 9 wrong of 15.
- **This is not production-safe.** The component is offline, experimental, and
  imported by no production module. An isolation test enforces that.
- **The real-world accuracy is not known.** The benchmark is synthetic and was
  written by the author of the capability. The only set that ever moved the numbers
  by being unseen was Phase 8.6's, and it moved them down by 22 and 32 points.
- **This is not deployable.** No production, runtime, workflow, artifact, security
  or plugin file was read or written by this phase.
- **There is no inter-annotator agreement figure**, and none may be quoted.
  `docs/INDEPENDENT_ANNOTATION_PROTOCOL_V2.md` says what would have to happen first.

Status: **PASS WITH ISSUES**. Both capabilities work, no historical regression was
introduced, the inherited evaluator, taxonomy, decision policy, Phase 8.6 benchmark
and configuration hashes are all unchanged, and the one failing case is an
annotation omission in a frozen Phase 8.3 label that this phase is forbidden to
edit.
