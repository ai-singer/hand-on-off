# Phase 8.3 - Attribution Aware Risk Evaluation Experiment

Phase: 8.3
Status: **PASS WITH ISSUES**
Date: 2026-09-27
Baseline: `semantic-intent-v2` (`semantic_evaluator_v2`)
Experiment: `attribution-aware-experiment` (`risk_evaluation/attribution_experiment/`)
Dataset: `attribution_experiment/v1`, 60 cases
Production changed: **no**

---

## 1. Purpose of the experiment

Phase 8.1 found a structural defect; Phase 8.2 built a layer that could describe
it. Phase 8.3 asks whether that layer actually helps, and refuses to accept a
plausible answer.

The defect is one sentence long. `semantic_evaluator_v2` decides attribution once
for a whole text, so an unrelated attribution anywhere in a passage withdraws
every author-voice category in it:

```
Economists forecast slower growth in Europe. This fund cannot lose money.
baseline: []          <- the guarantee in the second sentence is gone
```

The experiment tests four questions:

| # | Question | Where it is measured |
| --- | --- | --- |
| 1 | citation misjudgement | group B, third_party_citation |
| 2 | author-rejection misjudgement | group C, author_rejection |
| 3 | third-party attribution | groups B and C together |
| 4 | claim-level risk localisation | group D, mixed_claim |

Groups A (author risk) and E (no-risk education) are the controls: A checks that
the experiment does not lose the article's own risk, E checks that it does not
start flagging neutral text. A change that improves B, C and D while damaging A
or E is not an improvement.

---

## 2. Baseline

`semantic_evaluator_v2`, called once per text, unmodified.

```
baseline = SemanticRiskEvaluatorV2().evaluate_text(text)
```

The baseline is **not wrapped, not subclassed in the experiment's own path, and
not modified**. `tests/attribution_experiment_tests/test_baseline_unchanged.py`
pins its output on ten texts recorded before the experiment was written, re-runs
the baseline after evaluating all 60 cases, and asserts the two are identical.
It also checks that the experiment does not appear in `regression.EVALUATORS`,
in the benchmark registry, or anywhere in the production import graph.

The baseline's weakness on this dataset is stark and worth stating before any
comparison:

| Group | Baseline correct |
| --- | --- |
| A author_risk | 14/15 |
| B third_party_citation | 6/10 |
| C author_rejection | 4/10 |
| D mixed_claim | **0/10** |
| E no_risk_education | 15/15 |

The baseline gets **none** of the ten mixed-claim cases right. Every one of them
contains a borrowed attribution in the first sentence, and that is enough to
suppress whatever the second sentence says.

---

## 3. Experimental evaluator

```
text
  |
  v  AttributionAnalyzer            claims with speaker and stance (Phase 8.2)
claims
  |
  v  semantic_evaluator_v2          called once per claim, unmodified
claim-level detections
  |
  v  decision policy                R1 raises, R2 and R3 suppress
AttributionAwareResult              claims, claim_results, final_decision, evidence
```

`AttributionAwareResult` carries the four specified fields:

| Field | Content |
| --- | --- |
| `claims` | the attribution layer's claims |
| `claim_results` | what the baseline returned for each claim text |
| `final_decision` | the merged, deduplicated result |
| `evidence` | evaluator, policy, claim count, baseline categories, dropped categories, suppression count |

The `baseline` result is carried on the same object, so both verdicts are always
available and the comparison never re-runs anything.

### 3.1 The decision rules

The phase's three rules are implemented as named predicates rather than as
conditions buried in a merge:

| Rule | Meaning | Implementation |
| --- | --- | --- |
| R1 | only `speaker=author` AND `stance=endorsed` raises the risk weight | `raises_risk_weight` |
| R2 | `speaker=third_party` AND `stance=quoted` must not become author risk | `is_third_party_quotation` |
| R3 | `speaker=author` AND `stance=rejected` must not be risk | `is_author_rejection` |

**One exception, from the taxonomy rather than the experiment.** `taxonomy_v2`
declares `unverified_information` attribution-agnostic: reporting an uncheckable
source is a risk whatever the voice. Dropping it would have been an experiment
artefact that scores well and means nothing, so it survives R2 and R3 and the
rule is recorded as `R4-attribution-agnostic` in the evidence.

**R1 has two possible readings and both are measured.** R2 and R3 say what must
*not* be risk; R1 says what is *elevated*. A claim covered by none of them is
left with the baseline's verdict under the default `strict-rules` policy.
The alternative, `authorial-filter`, suppresses every non-authorial claim. They
are not equivalent:

| Policy | Reading |
| --- | --- |
| `strict-rules` (default) | suppress only what R2 and R3 name |
| `authorial-filter` | suppress anything that is not the article's own voice |

Both are reported in section 5.

### 3.2 Two mechanisms, not one

The fixes come from two different places, and conflating them would misdescribe
the result:

- **Suppression (groups B and C).** The claim is a citation or a rejection, so
  R2 or R3 drops a category the baseline reported. This removes false positives.
- **Claim isolation (group D).** The borrowed sentence is neutral, so nothing is
  suppressed. The gain is that the author's sentence is evaluated *on its own*,
  and the category rules see `This fund cannot lose money.` instead of the whole
  paragraph. The decision records `R6-baseline-verdict` for that claim, not a
  suppression rule. This removes false negatives.

A test pins the distinction so a later change cannot quietly attribute the group
D gains to suppression.

---

## 4. Dataset

`attribution_experiment/v1`, 60 cases, exported to `dataset_v1.json`.

| Group | Name | Cases | Required | Expectation |
| --- | --- | --- | --- | --- |
| A | author_risk | 15 | 15 | the article's own risky claim |
| B | third_party_citation | 10 | 10 | no author-voice category |
| C | author_rejection | 10 | 10 | no author-voice category |
| D | mixed_claim | 10 | 10 | the author's category |
| E | no_risk_education | 15 | 15 | nothing |

Expectations come from annotation guide v2, not from either evaluator:

- an author-voice category in a borrowed sentence is not expected;
- a rejected claim is not the article's claim;
- an uncheckable source is `unverified_information` whatever the voice;
- a conditional or hedged statement is not a prediction.

The dataset is **not registered as a benchmark**. Phase 8.3's permitted changes
are the experiment package, tests and docs; adding a version to the benchmark
registry is a governance act that touches shared code and was not asked for.
Version `v1` is recorded in the package and exported alongside it.

### 4.1 The Phase 8.1 replay set

Twelve cases (§5 requires at least ten): the nine published
`attribution_confusion` cases from `semantic/adversarial/v1` — five attacks and
four controls — plus three fresh cases of the same shape authored here.

The published family has only nine cases, so the minimum of ten could not be met
from it alone. The three additions are marked `origin="phase-8.3"`; they are the
only replay cases the layer had not been measured against before. This is stated
because it matters: two of the three came out fixed, and a reviewer is entitled
to discount them.

---

## 5. Metrics

The phase says not to look only at F1, so the four required measures come first.

### 5.1 Headline, strict-rules policy, 60 cases

| Measure | Baseline | Experiment | Change |
| --- | --- | --- | --- |
| false positives | 10 | 3 | **-7** |
| false negatives | 9 | 2 | **-7** |
| true positives | 18 | 25 | +7 |
| true negatives | 23 | 30 | +7 |
| categories exactly right | 39 | 53 | +14 |
| **attribution errors** | 20 | 6 | **-14** |

**Attribution-related error reduction: 70.0%** (14 of 20 errors on groups B, C
and D removed).

**Decision difference cases: 16** — 14 fixed, 0 broken, 2 different.

F1, reported last because the phase asks for it last: macro F1 0.6546 → 0.9091.
The F1 move is real, but it is the least informative number here: the F1 gain and
the FP/FN gains are not independent, and F1 alone would hide that the experiment
never once made a case worse.

Note that errors are counted on **exact category match** while the FP/FN deltas
are counted on **whether anything was flagged**, which is what a gate would act
on. A case expecting `unverified_information` that is flagged
`financial_guarantee` counts as flagged but wrong. Both bases are reported
because a binary flag hides the interesting failures.

### 5.2 Per group

| Group | Baseline | Experiment | FP | FN |
| --- | --- | --- | --- | --- |
| A author_risk | 14/15 | 14/15 | 0 → 0 | 1 → 1 |
| B third_party_citation | 6/10 | **9/10** | 4 → 1 | 0 → 0 |
| C author_rejection | 4/10 | **8/10** | 6 → 2 | 0 → 0 |
| D mixed_claim | **0/10** | **7/10** | 0 → 0 | 8 → 1 |
| E no_risk_education | 15/15 | 15/15 | 0 → 0 | 0 → 0 |

The controls behave exactly as they must: A is unchanged and E is untouched. No
group got worse.

### 5.3 Phase 8.1 replay, 12 cases

| Measure | Baseline | Experiment |
| --- | --- | --- |
| false positives | 0 | 0 |
| false negatives | 5 | **0** |
| categories exactly right | 6 | 11 |
| attribution errors | 6 | **1** |

Attribution error reduction **83.3%**. Fixed: `ATT-03`, `ATT-05`, `NEW-01`,
`NEW-02`, `NEW-03`. Broken: none. Different: `ATT-01` (see section 7.3).

`ATT-02` — the case Phase 8.1 recorded as passing *by accident*, because
`The company said` is not in v2's attribution lexicon — is unchanged and now
passes structurally: the borrowed sentence is its own claim and the author's
prediction is evaluated separately.

### 5.4 Policy sensitivity

| Policy | FP | FN | exact | broken |
| --- | --- | --- | --- | --- |
| `strict-rules` | 10 → 3 | 9 → 2 | 39 → 53 | 0 |
| `authorial-filter` | 10 → **2** | 9 → 2 | 39 → **54** | 0 |

The broader reading fixes one more case (`B-04`, where the speaker is `unknown`
rather than `third_party`) and breaks nothing. The choice between them is a
policy decision, not a measurement, which is why both are published.

---

## 6. Improvements

### 6.1 The Phase 8.1 defect, closed (7 cases)

```
D-01  Economists forecast slower growth in Europe. This fund cannot lose money.
      baseline   []                        (false negative)
      experiment ['financial_guarantee']   (fixed)
      claim-001  third_party/quoted  detected=[]                    nothing to drop
      claim-002  author              detected=['financial_guarantee']  kept
```

The mechanism is worth restating: nothing was suppressed here. The borrowed
sentence carries no risk of its own, and the fix is that the author's sentence is
no longer evaluated as part of a paragraph that starts with somebody else's
attribution. `D-01`, `D-02`, `D-04`, `D-05`, `D-07`, `D-08`, `D-09` are all
fixed this way, and the group goes from 0/10 to 7/10.

### 6.2 Citations stop being the article's guarantee (3 cases)

```
B-03  According to the report, the fund cannot lose money.
      baseline   ['financial_guarantee']   (false positive)
      experiment []                        (fixed)
      claim-001  third_party/quoted  detected=['financial_guarantee']
                 dropped by R2-third-party-quoted
```

`B-02` (`The company said …`) and `B-06` (`The report states …`) are fixed the
same way. `B-06` is worth noting: the baseline read `The report states the stock
will certainly double.` as the author's own prediction, because `the report` is
not in v2's source vocabulary, and the attribution layer recognises it.

### 6.3 Rejections stop being the article's risk (4 cases)

```
C-01  We disagree with the view that this fund cannot lose money.
      baseline   ['financial_guarantee']   (false positive)
      experiment []                        (fixed)
      claim-001  author/rejected  dropped by R3-author-rejected
```

`C-02` (`We disagree with the claim that the stock will certainly double.`),
`C-03` (`We doubt the fund cannot lose money.`) and `C-07` (the `;`-joined
advert quote) are fixed the same way. The baseline flagged a guarantee in a
sentence whose entire purpose is to argue against it.

### 6.4 The controls did not move

Group E stays at 15/15 and group A at 14/15. The experiment fixed fourteen cases
without flagging a single piece of neutral text and without losing a single
author risk. On this dataset, the four attribution questions were answered
without a recall cost.

---

## 7. Regressions

### 7.1 No case was broken

**Zero.** Across 60 cases and both policies, there is no case the baseline got
right and the experiment got wrong. That is the strongest single statement in
this report, and section 8 explains why it should not be read as a guarantee.

### 7.2 Seven errors remain, and none of them is a regression

| Case | Text | Expected | Both report | Cause |
| --- | --- | --- | --- | --- |
| `A-02` | This return is guaranteed. | `financial_guarantee` | `[]` | Phase 8.1 blind spot: `guaranteed` matches only as a prenominal adjective |
| `D-06` | Commentators said the quarter was mixed. This return is guaranteed. | `financial_guarantee` | `[]` | same blind spot |
| `B-04` | A broker told clients the fund cannot lose money. | `[]` | `financial_guarantee` | `a broker` is not in the attribution layer's source table |
| `C-08` | This article rejects the idea that the fund cannot lose money. | `[]` | `financial_guarantee` | `this article rejects` is not an author marker and `rejects` is not a rejection cue |
| `C-09` | The claim that the stock will certainly double is incorrect. | `[]` | `market_prediction` | `is incorrect` is not in the rejection cue list |
| `D-03`, `D-10` | (see 7.3) | `['investment_advice']` | two categories | annotation dispute, not an error |

Two of the seven are the `guaranteed` blind spot that Phase 8.1 found and Phase
8.3 was not permitted to fix — it is an evaluator defect, not an attribution one,
and it affects both evaluators identically. Three are coverage gaps in the
Phase 8.2 attribution layer's marker tables. Two are annotation disputes.

### 7.3 Two annotation disputes, reported rather than edited

```
D-03  Analysts say the sector is volatile this year. Buy this stock before the quarter ends.
      expected   ['investment_advice']
      experiment ['investment_advice', 'unverified_information']
```

The experiment kept `unverified_information` from the first claim, because
`Analysts say` is an unnamed collective and `taxonomy_v2` reports that category
whatever the voice. **On a reading of guide v2, the experiment is right and the
annotation is incomplete.** The same applies to `D-10` and to replay case
`ATT-01`.

The annotations were **not** changed after the run. Editing them would have
improved the headline: `categories exactly right` would rise from 53 to 55, and
the two cases would move from `different` to `fixed`, making it 16 fixed and 18
decision differences. That number is available to any reader who prefers it, and
the dataset stays as it was measured. Changing an expectation after seeing which
way a case fell is the same act as changing it to flatter the result, whichever
direction it happens to point.

---

## 8. Limitations

1. **Zero broken cases is a result about 60 synthetic cases, not a property of
   the method.** The dataset was written by the same author as the decision
   rules, and the shapes in group D are the shapes the attribution layer was
   built to handle. A dataset written by someone else would find the boundary,
   and the boundary is visible already: three of the seven remaining errors are
   marker-table gaps.
2. **The dataset's expectations are not independent.** They come from the same
   reading of guide v2 that produced the attribution layer's rules. Two of them
   are demonstrably incomplete (7.3).
3. **The evaluator defect is untouched.** The most consequential finding of
   Phase 8.1 — `This return is guaranteed.` is invisible — is still open, and it
   is shared by both arms of this experiment. The comparison is silent about it.
4. **Per-claim evaluation loses context.** A claim is now evaluated as a
   standalone string. Anaphora (`The fund … It cannot lose money.`), tables,
   bullet lists and multi-sentence claims will behave differently, and none of
   them is in the dataset.
5. **The attribution layer's own accuracy bounds this result.** Phase 8.2
   measured 80% speaker accuracy on text phrased differently from its rules.
   Every attribution error it makes can become a decision error here, in either
   direction. `B-04` is exactly that.
6. **The strict policy is the literal reading of R1, and it may be the wrong
   one.** The two readings differ by one case here; on a larger corpus they
   could differ more, and the experiment cannot tell you which to adopt.
7. **No confidence calibration.** R1 records that the weight was raised; it does
   not change any confidence value. The experiment does not test whether
   authorial claims should score higher, only whether non-authorial ones should
   score at all.
8. **Not connected to anything.** No runtime, no Quality Gate, no production
   path. The production risk constraints still come from the plugin, unchanged.

---

## 9. Whether to proceed

**Yes, to a v3 evaluator design — but not by merging this code, and not yet on
this evidence.**

What the experiment establishes:

- the Phase 8.1 defect is **fixable**, and the fix is small: evaluate per claim
  rather than per text, and suppress on attribution rather than on the presence
  of any attribution;
- the fix costs nothing measurable on the controls in this dataset: no author
  risk lost, no neutral text flagged, no case broken under either policy;
- the false-positive and false-negative reductions are equal (-7 each), so the
  change is not trading one error type for the other;
- 83.3% of the Phase 8.1 replay errors are removed, including all three recorded
  failures.

What it does **not** establish, and what a next phase must address first:

1. **A non-synthetic corpus.** 60 cases written by the rules' author cannot
   support a claim about behaviour on real material. This is the same limitation
   Phase 8.2 carried and it has not been resolved by adding more synthetic cases.
2. **The `guaranteed` blind spot.** It is the single largest shared error and it
   is orthogonal to attribution. Fixing it would change the baseline, so it has
   to be done either before or as part of a v3, with a fresh measurement.
3. **Independent annotation.** The two disputed expectations show what happens
   without it.
4. **A rejection of the two policies.** Pick one, with a reason, on evidence
   that can distinguish them.

The concrete next step I would recommend is a `semantic-intent-v3` that consumes
the attribution layer's `authorial_text()` and `to_statement_source()`, measured
against a fresh benchmark version with independent annotation and a real-material
subset — **not** a merge of `AttributionAwareEvaluator` as it stands, whose
all-or-nothing suppression and `unknown`-speaker handling are prototype choices
rather than settled design.

---

## 10. What this phase does not claim

- It does not claim risk capability has improved in production. Nothing in the
  production path changed, and `semantic_evaluator_v2` is byte-identical.
- It does not claim the evaluator has been replaced. The experiment is a separate
  offline package, is not in `regression.EVALUATORS`, is not a registered
  benchmark, and is imported by nothing outside its tests.
- It does not claim the result generalises. It is 60 synthetic cases.
- It does not claim the experiment is safe to ship. It was never asked to be, and
  section 8 lists eight reasons it could not be.
- It does not claim zero regressions in general. It claims zero regressions on
  this dataset, which is a weaker and more accurate statement.

---

## 11. Verification

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests` | **1256 passed, 0 failed** (was 1102) |
| Phase 8.3 suite (`tests/attribution_experiment_tests/`) | 154 passed (requirement: 50) |
| `python -m compileall` | PASS |
| JSON validity (all workspace JSON) | PASS |
| Secret scan (workspace + repository root) | PASS |
| Both recorded evaluation freezes | MATCH (unchanged) |
| `benchmark_registry.verify_all()` | all True |
| `semantic_evaluator_v2.py` / `taxonomy_v2.py` modified | **no** |
| Existing benchmark labels modified | **no** |
| Production/runtime/plugin files modified | **no** — `git status` shows only new paths |
| `regression.EVALUATORS` | unchanged (`keyword`, `semantic`) |

Test coverage of the phase's requirements:

| Requirement | Tests |
| --- | --- |
| baseline unchanged | `test_baseline_unchanged.py`, 12 |
| attribution extraction | `test_dataset.py` (33), via groups A–E |
| decision merge | `test_decision.py`, 27 |
| failure replay | `test_comparison.py` `ReplayTests` |
| control cases | `test_comparison.py` `GroupBreakdownTests`, `test_dataset.py` |
| evaluator contract and policies | `test_evaluator.py`, 31 |
| metrics and differences | `test_comparison.py`, 51 |
