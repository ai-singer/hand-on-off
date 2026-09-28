# Phase 8.9 - Independent Annotation and Realistic Adversarial Validation

Phase: 8.9
Status: **PASS WITH ISSUES**
Date: 2026-09-28
Subject: `risk_evaluation/v3` + `v3_1` + `v3_repair`, **frozen and unmodified**
Dataset: `risk/independent/v1` (300 cases, hash `8ee2993aa4f9c4de…`)
Production changed: **no evaluator change made; six proposals written instead**

> Capability measured on machine-authored text with machine-assigned labels,
> against a frozen evaluator.

---

## 1. Dataset provenance

### 1.1 What was built

`risk_evaluation/benchmarks/risk/independent/v1/` — a sixth registered benchmark
version, 300 cases, built to the sampling frame in
`risk_evaluation/v3_independent/sampling_frame_v3_2.json`.

| Group | Frame quota | Cases | Labelled with a category | Labelled empty |
| --- | --- | --- | --- | --- |
| risk positive | 150 | 150 | **137** | 13 |
| safe | 75 | 75 | **1** | 74 |
| boundary | 75 | 75 | 28 | 47 |
| **total** | **300** | **300** | **166** | **134** |

Labelled categories: `unverified_information` 52, `investment_advice` 46,
`emotional_manipulation` 36, `market_prediction` 31, `financial_guarantee` 25.

The frame's quota and the achieved labels **do not match, and that is reported
rather than corrected**: 13 risk-positive slots were labelled empty and one safe
slot was labelled with a category. The labels are the annotators'; replacing a case
to make the achieved distribution look like the intended one would remove exactly
the evidence that the frame was mis-specified.

### 1.2 The sampling frame

Five crossed dimensions, fixed before generation:

| Dimension | Values |
| --- | --- |
| source type | news_report, analyst_note, forum_post, educational_article, marketing_material, regulatory_filing, social_post, earnings_summary |
| language | en (150), zh (150) |
| form | declarative_certain, declarative_hedged, imperative, interrogative, conditional, nominal, quoted, passive |
| topic | equities, bonds, funds, property, commodities, foreign_exchange, crypto, pensions, macroeconomics, corporate_earnings |
| boundary kind | 15 shapes, 5 cases each |

Assignment is by rotation rather than random sampling, so every cell the frame
declares is used and the frame is reproducible from its own declaration.

The frame **contains no evaluator vocabulary**. `tests/risk_evaluation_v3_independent/test_freeze_and_frame.py`
asserts that neither the frame nor either agent prompt contains a frame name, a
matcher class, a pattern id, an entity list, a module path or a decision-rule id.

### 1.3 Who produced what

| Role | Who | Count |
| --- | --- | --- |
| sampling frame | the evaluator's author | 1 |
| **dataset authors** | machine agents, one per batch | **30** |
| **annotators** | machine agents, blind to each other | **2** |
| **adjudicator** | a machine agent, neither annotator | **1** |

The dataset authors are **not** the evaluator's author. Each received one slot file
and the annotation guide, and nothing else from the repository. The exact prompt is
published verbatim in `manifest.json` under
`provenance.generation_prompt`, along with the annotation and guide prompts, so the
claim is checkable rather than merely asserted.

### 1.4 What this provenance does not buy

| Claim | Status |
| --- | --- |
| synthetic text | **true**, recorded in the manifest |
| independent of the evaluator's author | **true for text and labels** |
| human annotated | **false** — machine annotators throughout |
| sampled from real financial publications | **false** |
| real-world accuracy | **unknown**, and no number here estimates it |

---

## 2. Annotation protocol

`docs/INDEPENDENT_ANNOTATION_PROTOCOL_V3.md` defines six fields — `claim`,
`speaker`, `stance`, `intent`, `certainty`, `severity` — plus `decision`, and the
values are the taxonomy's own. Every rule cites its guide section, so the protocol
and the normative document cannot drift.

**Order of operations**, and the first two steps are what make the result
unfittable:

```
1. freeze the evaluator                  evaluation_freeze_v3_2.json
2. write the sampling frame              no evaluator vocabulary
3. generate text                         30 agents, text only
4. freeze the dataset                    before any label exists
5. annotate, A and B, blind              neither can see the other
6. compare, then adjudicate              raw label sets retained
7. score the frozen evaluator            modification forbidden
8. classify failures                     proposal, not patch
```

The evaluator could not be adjusted to the text, and the labels could not be
adjusted to the evaluator's output, because neither existed when the other was
fixed.

### 2.1 What the annotators could not see

Each annotator received a file of `{id, text}` records and nothing else. No group,
no frame descriptor, no expected category, and no evaluator output. The two
annotators' batches are **shuffled with different seeds**, so they do not share a
case order; the seeds are recorded in `build.ANNOTATION_SEEDS`.

### 2.2 Adjudication

155 field disagreements across 95 cases went to a third agent that was neither
annotator. It ruled on each disputed field with a guide citation:

| Resolution | Count |
| --- | --- |
| annotator A upheld | 81 |
| annotator B upheld | 60 |
| third reading, neither | 10 |
| **declined to settle** | **4** |

Three cases had an unresolved field. They are **kept in the dataset, marked
`resolved: false`, and excluded from the primary metrics**, with their case ids
published. Substituting an annotator's value would have produced a benchmark whose
labels are one annotator's wherever the other disagreed, and the disagreement rate
would have vanished from the score without vanishing from the data.

### 2.3 Published artifacts

`cases.json`, `labels.json`, `manifest.json`, and — for the protocol's retention
rule — `labels_a.json`, `labels_b.json`, `disagreements.json`, `adjudication.json`,
`adjudicated.json`. An agreement figure whose inputs have been overwritten is not
evidence.

---

## 3. Agreement statistics

Cohen's kappa, per field, on the **raw** labels before any discussion. Never one
pooled figure: two annotators can agree perfectly on `severity` because both said
`none` while disagreeing on `decision`, and a pooled number would average that into
a number about neither.

| Field | Kappa | Observed | Band |
| --- | --- | --- | --- |
| `severity` | **+0.9379** | 0.9600 | almost perfect |
| `intent` | **+0.8478** | 0.8900 | almost perfect |
| `stance` | **+0.8361** | 0.9133 | almost perfect |
| `speaker` | **+0.8301** | 0.9167 | almost perfect |
| `certainty` | **+0.8128** | 0.8767 | almost perfect |

Per category, on present/absent:

| Category | Kappa | Band |
| --- | --- | --- |
| `investment_advice` | **+0.9752** | almost perfect |
| `emotional_manipulation` | **+0.9684** | almost perfect |
| `market_prediction` | **+0.9630** | almost perfect |
| `financial_guarantee` | **+0.9419** | almost perfect |
| `unverified_information` | **+0.8375** | almost perfect |

Exact decision-set agreement: **0.9267**. Disagreements: **155** field units across
**95** of 300 cases, a rate of **0.0820** over the 1 800 field units compared.

By group, decision agreement: safe 0.9867, risk positive 0.9267, boundary 0.8667.

### 3.1 What these numbers mean, and do not

Two machine agents applying one protocol are two applications of one set of
instructions by one class of model. The kappa measures:

- whether the protocol is **unambiguous enough to be applied twice**;
- which fields are **under-specified**, since those are where they differ.

It does **not** measure human agreement, and a high value is not evidence that a
human would agree. `certainty` (+0.8128) and `speaker` (+0.8301) are the two lowest
field scores and `unverified_information` (+0.8375) the lowest category — three
places a human annotator would most plausibly diverge too, but this study cannot
show that, and does not claim it.

**No agreement figure in this report may be quoted as human inter-annotator
agreement.**

---

## 4. Evaluator metrics

The evaluator was frozen before generation and verified unchanged after evaluation:
evaluator `6768eb66…`, taxonomy `a18bfad9…`, decision policy `28f446e5…`,
benchmark `1bf9c9bd…`, configuration `c6aa35c4…` — all byte-identical to Phase 8.8,
across 36 frozen source files.

**297 cases scored** (3 excluded, section 2.2).

### 4.1 Overall

| Metric | Value |
| --- | --- |
| correct (exact category set) | 147 / 297 = **0.4949** |
| **precision** | **0.9062** |
| **recall** | **0.1758** |
| **F1** | **0.2945** |
| true positives | 29 |
| false positives | **3** |
| false negatives | **136** |
| true negatives | 129 |
| false positive rate | 0.0227 |
| false negative rate | 0.8242 |

This is the phase's headline and it is a failure of recall. The evaluator almost
never flags something that is not there — 3 false positives in 297 cases — and it
misses **136 of 165** labelled risk cases.

### 4.2 Per category

| Category | Precision | Recall | F1 | tp / fp / fn / tn |
| --- | --- | --- | --- | --- |
| `investment_advice` | **1.0000** | 0.1556 | 0.2693 | 7 / 0 / 38 / 252 |
| `unverified_information` | 0.8333 | 0.1923 | 0.3125 | 10 / 2 / 42 / 243 |
| `emotional_manipulation` | **1.0000** | 0.1714 | 0.2926 | 6 / 0 / 29 / 262 |
| `financial_guarantee` | 0.3333 | 0.0800 | 0.1290 | 2 / 4 / 23 / 268 |
| `market_prediction` | 0.5000 | 0.0323 | 0.0607 | 1 / 1 / 30 / 265 |

Three of the five categories have perfect precision on this data, which is the same
finding as section 4.1 from another angle: the evaluator's errors are almost all
omissions. `financial_guarantee` is the exception in both directions — the worst
recall *and* the only category with more than two false positives.

### 4.3 Per group

| Group | Correct | Accuracy | fp | fn |
| --- | --- | --- | --- | --- |
| safe | 72 / 74 | **0.9730** | 1 | 1 |
| boundary | 48 / 74 | 0.6486 | 2 | 22 |
| risk positive | 27 / 149 | **0.1812** | 0 | 113 |

The safe group is the one place the evaluator is reliable, and it is the place a
false positive would be most damaging. The risk-positive group is where it fails.

### 4.4 Confusion matrix

Rows are the labelled highest-precedence category, columns the predicted one;
`none` is a class. Two matrices are reported because the labels are sets — this one,
and a 2×2 per category in `metrics_v3_2.json` / `evaluation_v3_2.json`.

```
labelled \ predicted    investment  financial  market  unverified  emotional  none
investment_advice                7          1       0           2          2    33
financial_guarantee              0          0       1           1          0    19
market_prediction                0          0       1           0          0    30
unverified_information           0          3       0           7          0    35
emotional_manipulation           0          0       0           0          4    19
none                             0          1       0           2          0   129
```

The `none` column carries 136 of the 297 cases. The matrix's shape is the result:
almost everything labelled risky lands in `none`, and almost nothing lands in the
wrong risky category.

---

## 5. Error analysis

Every one of the 151 failing cases is classified into one of the five kinds the
phase names, from the trace rather than the symptom, in a declared precedence order
so the classification is reproducible. **Nothing was modified in response.**

| Kind | Count | Meaning |
| --- | --- | --- |
| `lexical_gap` | **106** | the labelled relation produced no finding at all |
| `annotation_disagreement` | 29 | the two annotators differed on this case's label |
| `semantic_gap` | 8 | a relation was found and the outcome is still wrong |
| `taxonomy_ambiguity` | 4 | the adjudicator ruled a third reading or declined |
| `attribution_error` | 4 | the speaker or stance differs from the label |

### 5.1 The failure is not a language failure

| Language | annotation_disagreement | taxonomy_ambiguity | attribution_error | lexical_gap | semantic_gap | total | accuracy |
| --- | --- | --- | --- | --- | --- | --- | --- |
| en | 14 | 2 | 3 | 51 | 8 | 66 | 0.480 |
| zh | 15 | 2 | 1 | 55 | **0** | 73 | 0.513 |

This contradicted the hypothesis the phase started with. Chinese accuracy (0.513) is
*marginally higher* than English (0.480), and the lexical gap is split 51/55. The
failure is uniform across **every** dimension the frame varies — language, form,
source type and topic all land between 0.378 and 0.622 — which is the signature of a
systematic gap rather than a vocabulary gap in one language.

### 5.2 Where it is worst, and where it is perfect

Fifteen boundary shapes, five cases each:

| Boundary shape | Correct |
| --- | --- |
| `endorsed_quotation` (guide 4) | **0 / 5** |
| `target_price_author_certain` (guide 2) | **0 / 5** |
| `pressure_without_claim` (guide 6.1) | 1 / 5 |
| `quoted_risk_unnamed_source` (guide 3.1) | 1 / 5 |
| `conditional_directive` (guide 5) | 2 / 5 |
| `author_rejection`, `dramatic_vocabulary`, `generic_disclosure`, `method_guidance`, `quoted_risk_named_source`, `reported_expectation_named` | **5 / 5 each** |

The six perfect shapes are the six the existing decision policy and source lexicon
already handle explicitly. The two zeroes are guide rules no layer implements: an
endorsed quotation becoming the article's own claim, and a price level asserted as
the author's own certainty.

### 5.3 What the three diagnostic examples show

```
IND-0021  If you are saving for retirement, put our dividend equity sleeve at the
          centre of your portfolio.
          labelled investment_advice; the ADVICE relation WAS found; category []
```

Guide 5 says a conditional *directive* is still advice. The relation is found and the
`if` marker hedges it into suppression — a **semantic gap**, not a vocabulary gap.

```
IND-0217  The Harborline Balanced Fund closed to new subscriptions on 3 March after
          net assets passed $2.4 billion, its manager said on Tuesday.
          labelled []; evaluated unverified_information
```

`its manager` is a definite, identifiable party and the label treats it as a checkable
source. The professional-group rule types a role noun as an uncheckable collective —
the same tension Phase 8.7 found between `IV-094` and the Phase 8.3 control, now
appearing independently.

```
IND-0259  Don't let anyone tell you bitcoin is a sure thing: nothing in this market
          is guaranteed, and nobody can promise you a dollar back.
          labelled []; evaluated financial_guarantee via RISK_REMOVED
```

A sentence *warning against* a guarantee was read as one. The colloquial-certainty
frame fired on `a sure thing` inside a rejection context.

### 5.4 Proposals, not patches

Six proposals are written to `risk_evaluation/v3_independent/proposals_v3_2.json`,
one per class plus a guide revision. Each names what a repair would have to do and
**what it must not break**.

| id | Class | Observed | Blocked by |
| --- | --- | --- | --- |
| P1-language-coverage | lexical_gap | 106 | the freeze |
| P2-modality-coverage | lexical_gap | 106 | the freeze |
| P3-annotation-ambiguity | annotation_disagreement | 29 | scope |
| P4-attribution-boundary | attribution_error | 4 | the freeze |
| P5-semantic-boundary | semantic_gap | 8 | the freeze |
| P6-guide-v3 | taxonomy_ambiguity | 4 | scope |

**No proposal is implemented, and `freeze.guard()` raises if one is.** A repair made
after seeing the result would make the result meaningless.

### 5.5 Coverage matrix

Full matrix in `coverage_matrix_v3_2.json`; built from each record's own `frame`
block, so a dimension is the one the dataset author was given rather than one
inferred from the text. Extreme cells:

| Dimension | Worst | Best |
| --- | --- | --- |
| language | en 0.480 | zh 0.513 |
| form | quoted 0.378 | interrogative 0.622 |
| source type | forum_post 0.378 | regulatory_filing 0.622 |
| topic | corporate_earnings 0.400 | bonds / pensions 0.600 |
| intended intent (frame's own target) | emotional_manipulation 0.133 | market_prediction 0.233 |

---

## 6. Regression

Six sets, and `broken` is counted against the pre-Phase-8.7 pipeline.

| Set | Cases | Correct | Floor | Fixed | **Broken** |
| --- | --- | --- | --- | --- | --- |
| phase 8.1 replay | 15 | 6 | 6 | 0 | **0** |
| phase 8.3 replay | 9 | 8 | 8 | 0 | **0** |
| phase 8.4 replay | 17 | 16 | 16 | 0 | **0** |
| phase 8.6 `independent_v2` | 99 | 98 | 96 | 14 | **0** |
| phase 8.8 capability | 80 | 79 | — | 38 | **0** |
| **total** | **220** | **207** | — | **52** | **0** |

Phase 8.6's `independent_v1` (100 cases): correct 99, precision 1.0000, recall 0.9730.

**Status PASS**: `broken = 0`, no floor violated, and the freeze verified by the gate.
Every set scores exactly what Phase 8.8 measured, which is what a frozen evaluator
should produce — and is checked rather than assumed, because a replay that is
identical because nothing ran is not the same as one identical because nothing
changed.

---

## 7. Limitations

**1. The annotators are machines.** Every kappa in section 3 is machine-to-machine
and may not be quoted as human inter-annotator agreement. No human has annotated
anything in this repository.

**2. The text is synthetic.** 300 sentences written by generative agents to a
published frame. Nobody has measured this evaluator on real financial text, and
section 4's numbers are not an estimate of how it would behave there.

**3. The sampling frame is the evaluator author's.** It decides *what kinds of
sentence exist*. It contains no evaluator vocabulary — checked, not asserted — but
the choice of dimensions and their values is one author's.

**4. Thirty text authors share a model family.** "Independent" here means a
different agent with a different context and a published prompt, not a different
kind of mind. Common training may make the text more uniform than real writing is.

**5. Three cases are excluded** from the primary metrics because the adjudicator
declined to settle a field. Their ids are published; including them with an
arbitrary label would not have been better.

**6. The frame quota and the achieved labels differ** (section 1.1). Reported, not
corrected.

**7. 29 failures are annotation disagreements**, so they measure the guide as much as
the evaluator. Separating them from the 106 lexical gaps is the best this phase can
do; the split is a judgement made by declared rules, not a fact.

**8. A benchmark this size cannot support a threshold.** No pass mark was set, and
none should be read out of these numbers.

**9. A pre-existing environment fragility was found while running the suite.**
`tests/runtime_bootstrap/test_lobster_integration.py` captures a subprocess's output
with the locale codec; when `PYTHONIOENCODING=utf-8` is set in the environment, the
child emits UTF-8 and the parent fails to decode it. **This is not caused by Phase
8.9** — it reproduces identically at the parent commit with no Phase 8.9 changes —
and it is outside this phase's scope, so it is reported rather than fixed. The full
suite passes (3026 tests) when the variable is not set.

**10. Nothing here says the risk system is solved, production-ready or deployable.**
The headline result is a recall of 0.176 on data the evaluator had not seen.

---

## 8. Phase 8.9 status

```
Phase 8.9 Status: PASS WITH ISSUES

dataset size    300 cases  (150 risk positive / 75 safe / 75 boundary)
                166 labelled with a category, 134 empty
                hash 8ee2993aa4f9c4de...
                risk/independent/v1, a sixth registered benchmark version

agreement       Cohen's kappa, 300 cases, two blind machine annotators
                speaker +0.8301   stance +0.8361   intent +0.8478
                certainty +0.8128  severity +0.9379
                per category: investment_advice +0.9752 ... unverified_information +0.8375
                exact decision-set agreement 0.9267, 155 disagreements over 95 cases
                NOT human inter-annotator agreement

metrics         resolved cases 297 of 300 (3 excluded, adjudicator declined)
                precision 0.9062   recall 0.1758   F1 0.2945   accuracy 0.4949
                tp/fp/fn/tn 29/3/136/129
                per category and both confusion matrices in evaluation_v3_2.json
                safe group 0.9730, boundary 0.6486, risk-positive 0.1812

errors          151 failures, every one classified, none unclassified
                lexical_gap 106, annotation_disagreement 29, semantic_gap 8,
                taxonomy_ambiguity 4, attribution_error 4
                six proposals written (P1..P6); the evaluator was NOT modified

limitations     machine annotators, synthetic text, one author's frame,
                one model family, 3 excluded cases, 29 failures measuring the guide,
                10 items listed in section 7, no threshold supported

regression      six sets, 220 cases, broken 0, floors met, freeze verified
isolation       13 files scanned, 0 forbidden imports, evaluator byte-identical
tests           3026 pass (217 new in tests/risk_evaluation_v3_independent)
evaluator       frozen before generation, verified unchanged after evaluation
commit          the Phase 8.9 commit on main; not pushed
```

**PASS WITH ISSUES**, and the issue is the point of the phase: the architecture that
scored precision 1.0000 and recall 0.9730 on the author's own benchmark scores
precision 0.9062 and **recall 0.1758** on text and labels its author did not produce.
That is not a regression — nothing broke, and the frozen evaluator behaved exactly as
Phase 8.8 measured it. It is a measurement of what the evaluator does not yet cover,
produced under the constraints the phase set, with every failure classified and every
repair left as a written proposal.
