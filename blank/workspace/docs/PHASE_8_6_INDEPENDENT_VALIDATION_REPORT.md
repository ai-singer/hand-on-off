# Phase 8.6 - Independent Risk Evaluation v3 Validation

Phase: 8.6
Status: **PASS WITH ISSUES**
Date: 2026-09-28
Subject: `risk_evaluation/v3` (Phase 8.5), frozen and unmodified
Benchmark: `independent_v1` / `v1` (100 cases) and `independent_v2` (99, clean subset)
Production changed: **no**

---

## 1. Executive Summary

Phase 8.5 claimed its architecture improved risk evaluation. This phase asked
whether that holds on data that took no part in its development, and the answer
is **partly**.

| Claim from Phase 8.5 | Verdict on independent data |
| --- | --- |
| Attribution resolves quoted risk and author rejection | **PARTIALLY_SUPPORTED** |
| Intent patterns resolve passive, copular and nominal guarantees | **NOT_SUPPORTED** |
| The decision policy keeps false positives and false negatives low | **SUPPORTED** |

The headline numbers fell, and by a lot:

| Metric | Phase 8.5 (own benchmark) | Phase 8.6 (independent) | Change |
| --- | --- | --- | --- |
| speaker accuracy | 96.8% | **74.0%** | −22.8 |
| stance accuracy | 95.2% | **79.0%** | −16.2 |
| relation recall | 100.0% | **67.5%** | −32.5 |
| decision precision | 0.9500 | **0.7750** | −0.175 |
| decision recall | 0.7917 | **0.8378** | +0.046 |
| decision F1 | 0.8637 | **0.8052** | −0.059 |
| decision accuracy | 0.9000 | **0.8500** | −0.050 |
| false positives | 1 | **9** | +8 |
| false negatives | 5 | **6** | +1 |

**This is the result the phase exists to produce.** Phase 8.5's figures were
measured on a benchmark written by the same author as the pipeline, and 22.8
points of speaker accuracy and 32.5 points of relation recall did not survive
contact with sentences the layers had not seen.

What survived, and matters:

- **the decision policy still works.** Precision 0.7750, recall 0.8378, FPR
  14.3%, FNR 16.2% - against a baseline of 0.7500 / 0.7297 on the same cases. v3
  is still better than the evaluator it extends, and the false-positive and
  false-negative rates stay in single figures as proportions of the negative and
  positive sets.
- **the trace is intact.** 100% of claims, 100% of decisions and 100% of spans
  carry evidence, exactly as in Phase 8.5.
- **the guard rails held.** Neutral education scored 16/20 rather than collapsing,
  and no case in the benchmark was made worse by the pipeline relative to the
  baseline in the groups the architecture was built for.

Three defects were found that the development benchmark could not see, and one of
them is a plain bug:

1. **Inflected movement verbs are invisible.** `Turnover expands sharply next
   quarter.` is a prediction by the guide; the frames list `expand` and the word
   boundary after it does not match `expands`.
2. **`is not guaranteed` breaks the copular frame.** Three cases of a negated
   copular guarantee match no frame at all, because the frame cannot span the
   intervening `not`.
3. **The sourcing lexicon is the dominant single cause.** 15 of 39 classified
   failures are a reporting frame whose source noun the attribution layer does
   not know: `traders`, `a person familiar with the matter`, `market chatter`,
   `the custodian`, `the trustee`, `the exchange`, `the prospectus`, `the advert`.

Nothing was repaired. The phase forbids adjusting a rule in response to a
result, and the freeze below is what makes that checkable rather than promised.

---

## 2. Dataset Construction

`independent_v1`, 100 cases, written for this phase.

| Group | Cases | Target | Decided correctly |
| --- | --- | --- | --- |
| author endorsed risk | 25 | 25 | 24/25 |
| third party claim | 20 | 20 | 17/20 |
| author rejection | 15 | 15 | 12/15 |
| neutral education | 20 | 20 | 16/20 |
| ambiguous boundary | 20 | 20 | 16/20 |

All five categories are covered: `unverified_information` 17,
`financial_guarantee` 6, `investment_advice` 5, `market_prediction` 5,
`emotional_manipulation` 4. Relation coverage: `PREDICTION` 13, `GUARANTEE` 12,
`RISK_REMOVED` 8, `ADVICE` 7.

Every case carries `id`, `text`, `labels` (speaker, stance, relation, categories)
and `annotation_reason`. Labels were written from `RISK_ANNOTATION_GUIDE_v2.md`
and the protocol in section 3; the pipeline was not consulted while labelling.

**No case is reused from Phase 8.1, 8.2, 8.3, 8.4 or 8.5**, and section 4 checks
that mechanically rather than taking it on trust.

One label was corrected **before the measurement**, and is recorded because the
distinction matters: `IV-017` (`Word on the street is that the board will
resign.`) was first marked `author/endorsed`, which is wrong under the protocol -
hearsay names a source even when it cannot be named. It was corrected to
`third_party/quoted` while drafting, before any prediction existed. No label was
changed after the run.

---

## 3. Annotation Protocol

`docs/INDEPENDENT_ANNOTATION_PROTOCOL.md` records the label definitions, the
speaker and stance standards, the category standard including the
checkable/uncheckable line, and the boundary-case rules for negation,
conditionals, reported speech and disclaimers.

### 3.1 Single annotator, declared

**This benchmark has one annotator. It is single-annotator engineering
validation only.**

There is no second annotator, so no inter-annotator agreement is reported. No
Cohen's kappa, no speaker agreement, no stance agreement, no category agreement.
Computing any of them from one annotator would be arithmetic about nobody.

The consequence is stated at the top of the protocol and repeated here because
it bounds everything below: **no accuracy figure in this report is evidence of
real-world capability.** Agreement with these labels is agreement with one
reader of the guide.

Section 6 of the protocol records exactly what a second annotator would have to
do, including that disagreements must be adjudicated **before** any evaluation
runs and that v1 must not be edited in place.

---

## 4. Audit Result

`risk_evaluation/v3_validation/audit.py`, four checks against 13 sources read
from the artifacts the earlier phases published.

```
benchmark      : independent_v1
cases          : 100
dataset hash   : 1bf9c9bdc4a78ed0
sources checked: 13
status         : FAIL
findings       : 1
  exact_overlap          1
affected cases : 1
```

**The benchmark FAILS its own audit.**

`IV-037` (`According to the prospectus, charges are capped.`) appears verbatim in
Phase 8.3's experiment dataset. The audit found it; nothing removed it.

| Check | Result |
| --- | --- |
| exact overlap with an earlier benchmark | **1 finding** |
| near duplicates within the benchmark | 0 |
| near duplicates against earlier benchmarks | 0 |
| development-set overlap | 0 |
| label completeness | 0 |

The phase forbids deleting a contaminated case and recomputing, so `IV-037`
stays in v1 and v1 stays `FAIL`. The decontaminated subset is published **beside**
it as `independent_v2` (99 cases, hash `363be619efa62234`), which passes with
zero findings - the same response Phase 7.4 applied to `semantic/v1`.

The effect on the metrics is nil: v1 and v2 score identically to four decimal
places on every decision measure, because the contaminated case was decided
correctly in both.

---

## 5. Freeze Information

`evaluation_freeze_v3.json`, taken **before** the evaluation ran.

| Component | Hash |
| --- | --- |
| evaluator hash (v3 pattern set) | `cd187bfa0d8d0a6e…` |
| taxonomy hash | `a18bfad9f9608a55…` |
| decision policy hash | `28f446e583d1ce77…` |
| benchmark hash | `1bf9c9bdc4a78ed0…` |
| configuration hash | `c6aa35c480548563…` |
| timestamp | `2026-09-28T01:36:25Z` |

Verification after the run: **MATCH**, with no mismatches.

The taxonomy hash equals the value recorded in Phase 7.5's freeze
(`a18bfad9f9608a55`), which is the check that the taxonomy genuinely never moved
across four phases. `risk_evaluation/v3` is untouched: `git status` shows only
new directories, and the freeze verification would have failed if any hashed
component had changed.

Two tests make the ordering itself checkable rather than asserted: one asserts
the freeze file's mtime precedes the prediction artifact's, and one asserts the
frozen benchmark hash still matches the dataset on disk - so a label edited after
the run would be caught.

---

## 6. Evaluation Result

Blind: `predict()` takes only `id` and `text` and cannot reach a label. A test
confirms that passing a `categories` field alongside `text` does not change the
prediction. Predictions were written first; scoring ran afterwards against the
labels.

### 6.1 Attribution

| Metric | Result |
| --- | --- |
| claim split accuracy | **100.0%** (100/100) |
| speaker accuracy | **74.0%** (74/100) |
| stance accuracy | **79.0%** (79/100) |

### 6.2 Intent

| Metric | Result |
| --- | --- |
| relation recall | **67.5%** (27/40) |
| relation precision | **84.4%** (27/32) |

| Relation | Recall |
| --- | --- |
| GUARANTEE | 58.3% (7/12) |
| RISK_REMOVED | 75.0% (6/8) |
| PREDICTION | 69.2% (9/13) |
| ADVICE | 71.4% (5/7) |

### 6.3 Decision

| Metric | v3 | Baseline |
| --- | --- | --- |
| precision | **0.7750** | 0.7500 |
| recall | **0.8378** | 0.7297 |
| F1 | **0.8052** | 0.7397 |
| accuracy | **0.8500** | 0.7900 |
| false positive rate | **0.1429** | 0.1429 |
| false negative rate | **0.1622** | 0.2703 |
| tp / fp / fn / tn | 31 / 9 / 6 / 54 | 27 / 9 / 10 / 54 |

v3 is ahead of the baseline on precision, recall, F1 and accuracy, and level on
the false positive rate. The gain is smaller than Phase 8.5 reported and it is
real.

### 6.4 Trace

| Metric | Result |
| --- | --- |
| claims with evidence / total claims | **100/100** |
| decisions with evidence / total decisions | **40/40** |
| span completeness | **100/100** |

The trace contract survives independent data completely. Every claim carries
evidence, every decision carries evidence, and every claim keeps a span.

---

## 7. Comparison With Phase 8.5

The three claims, verified one at a time on the independent benchmark, with a
sub-claim judged at 75% or above.

### 7.1 Claim 1 - attribution resolves quoted risk and rejection: PARTIALLY_SUPPORTED

| Sub-claim | Result | Verdict |
| --- | --- | --- |
| quoted third-party claims decided correctly | 17/20 (85.0%) | SUPPORTED |
| author rejections decided correctly | 12/15 (80.0%) | SUPPORTED |
| speaker accuracy on aligned claims | 74/100 (74.0%) | PARTIALLY_SUPPORTED |
| stance accuracy on aligned claims | 79/100 (79.0%) | SUPPORTED |

The two specific claims Phase 8.5 made **do** hold: quoted risk is handled at
85% and rejection at 80%, both above the threshold. What does not hold is the
underlying accuracy - the speaker is right three times in four, and the failures
are not spread evenly. They cluster on reporting frames whose source noun is
outside the marker table.

Phase 8.5 reported speaker accuracy of 96.8% on its own benchmark. On this one it
is 74.0%. The gap is the measure of how much of that figure came from the
vocabulary the layer was built against.

### 7.2 Claim 2 - passive, copular and nominal guarantees: NOT_SUPPORTED

| Sub-claim | Result | Verdict |
| --- | --- | --- |
| copular guarantee | 4/5 (80.0%) | SUPPORTED |
| nominal guarantee | 1/1 (100.0%) | SUPPORTED |
| attributive guarantee | 3/3 (100.0%) | SUPPORTED |
| active guarantee | 3/4 (75.0%) | SUPPORTED |
| **guarantee text no frame matched** | **0/7 (0.0%)** | **NOT_SUPPORTED** |
| per-relation recall | 27/40 (67.5%) | PARTIALLY_SUPPORTED |

This is the most important result in the report, and it is more interesting than
a single number.

**Every guarantee form Phase 8.5 named does hold**, at 75-100%, on the cases
where the matcher found the relation at all. The claim fails on a group Phase
8.5 never measured: **seven cases the guide calls a guarantee where the matcher
matched no frame whatsoever.** A form that is handled cannot rescue a form that
is never reached.

The seven, and why each matched nothing:

| Case | Text | Cause |
| --- | --- | --- |
| IV-047 | We are unconvinced that capital is protected here. | `protected` - the label asserts GUARANTEE by meaning; no guarantee vocabulary is present |
| IV-050 | Contrary to the marketing, the return is not guaranteed. | **`is not guaranteed` breaks the copular frame** |
| IV-060 | There is no evidence for the claim that capital is protected. | `protected` again |
| IV-081 | Returns are not guaranteed under any circumstances. | **`are not guaranteed` again** |
| IV-048 | The idea that the fund cannot fall is not supported. | `cannot fall` - RISK_REMOVED lists `cannot fail`, `cannot lose`, not `cannot fall` |
| IV-052 | The assertion that losses are impossible is false. | `losses are impossible` - the frame expects `impossible to lose` |
| IV-086 | No guarantee is given regarding distributions. | `No guarantee is given` - the nominal frame expects `a guarantee of/on/for OBJECT` |

Three of the seven are the same defect: **a negated copular guarantee has no
frame**, because the template cannot span the `not` between the copula and the
participle. The other four are phrasings the frame set does not know.

### 7.3 Claim 3 - low false positives and false negatives: SUPPORTED

| Sub-claim | Result | Verdict |
| --- | --- | --- |
| false positive rate | 14.29% | SUPPORTED |
| false negative rate | 16.22% | SUPPORTED |
| precision | 77.50% | SUPPORTED |
| recall | 83.78% | SUPPORTED |

The decision policy survives. Both rates stay under 20%, precision and recall are
both above 75%, and the layer is ahead of the baseline it extends on three of the
four measures.

It is worth being precise about what this does **not** say. Phase 8.5 reported 1
false positive and 5 false negatives on 60 cases; here it is 9 and 6 on 100. The
*rates* hold because the benchmark is bigger and its negative set is larger, not
because the pipeline behaves the same.

---

## 8. Error Analysis

Every failure is classified and explained; none is reported as a number alone.
The classifier records **which stage** failed as the primary category and **why**
as a mechanism, because those are different questions.

### 8.1 Summary

| | Count |
| --- | --- |
| cases | 100 |
| classified failures | **39** (39.0%) |
| — of which the verdict was wrong | **15** (15.0%) |
| — of which only the labels were wrong | 24 |

A wrong speaker that did not change the verdict is still a failure and is
recorded as one. The 15.0% is the decision error rate; the 39.0% counts every
case where any layer was wrong.

| Primary category | Count |
| --- | --- |
| attribution error | 31 |
| intent detection error | 3 |
| decision policy error | 5 |

| Mechanism | Count |
| --- | --- |
| novel source noun | 15 |
| novel rejection cue | 8 |
| fallback propagation | 4 |
| inflected verb | 1 |
| lexical gap | 1 |

| Cross-cutting view | Count |
| --- | --- |
| unknown language pattern | **23** |

The phase names five error categories. Two of them are better expressed as
cross-cutting views than as exclusive buckets, and the report shows all five
rather than forcing cases into a shape they do not fit. **Annotation ambiguity is
0**: the eight labels that the detector flags as arguable all sit on cases that
were decided correctly, so no decision error rests on a disputed label. **Unknown
language pattern is 23**: the layer not knowing the wording caused 23 of the 39
failures, across three different stages.

### 8.2 Attribution errors (31) - the dominant cause

Fifteen are a **reporting frame whose source noun is not in the lexicon**:

```
IV-045  The exchange said trading was orderly.
        annotated third_party/quoted, predicted unknown/quoted
IV-044  The trustee published the annual statement.
        annotated third_party/quoted, predicted unknown/quoted
IV-033  Traders say the shares are cheap.
        annotated third_party/quoted, predicted unknown/quoted
```

The attribution layer knows `analysts`, `experts`, `insiders`, `sources`,
`the company`, `the board`, `the report`, `the newsletter`. It does not know
`traders`, `a person familiar with the matter`, `market chatter`, `the custodian`,
`the trustee`, `the exchange`, `the regulator` (singular), `the prospectus`,
`the advert`, `the marketing material`. Every one of those is an ordinary way to
attribute a claim in financial writing.

Eight are a **rejection phrased outside the cue list**:

```
IV-046  We reject the suggestion that returns are guaranteed.
        annotated author/rejected, predicted unknown/uncertain
        -> the guarantee is read as the article's own, and flagged
IV-051  We see no basis for the view that the price will triple.
        annotated author/rejected, predicted unknown/uncertain
        -> the prediction is read as the article's own, and flagged
```

The cue list contains `we disagree`, `we doubt`, `we are not convinced`,
`dispute`, `refute`, `debunk`. It does not contain `we reject`, `we are
unconvinced`, `is not supported`, `we see no basis`, `is false`, `are
overstated`, `we do not accept`, `we would not describe`. Each of the eight is a
first-person rejection the layer reads as an endorsement, and each therefore
becomes a false positive.

Two of the eight cascaded into decision errors (`IV-046`, `IV-051`, `IV-055`),
which is why the rejection group scores 12/15.

Three are a **stance the layer does not treat as reported** - `Reportedly the
fund has changed its mandate.`, `Word on the street is that the audit is late.`,
`Rumour has it the chief executive is leaving.` - all annotated `third_party/
quoted` and all predicted `uncertain`. The source is recognised; the reporting
frame is not.

One is a marker firing where it should not: `IV-080`
(`The manager's report is published with the annual accounts.`) is predicted
`quoted` because `published` is a reporting verb, on a sentence that reports
nothing.

### 8.3 Intent detection errors (3)

```
IV-014  Turnover expands sharply next quarter.
        expected market_prediction, predicted []
        mechanism: inflected_verb - `expands` appears but the frames list only `expand`
```

This is a plain bug rather than a coverage gap. `MOVEMENT_VERBS` lists
`expand|rise|grow|climb|double|…` in base form only, and each is followed by
`\b`, so `expands`, `grows`, `rises`, `doubles`, `climbed` and `expanding` can
never match. The development benchmark contained only base forms, which is
exactly why Phase 8.5 reported 100% relation recall.

The same `\b`-after-base-form shape affects `IV-095` and any inflected movement
verb in unseen text. Two further cases are lexical gaps: `cannot fall` and
`losses are impossible` are risk removals the frame set does not express.

### 8.4 Decision policy errors (5) - fallback propagation

```
IV-062  The expense ratio is the annual cost of holding a fund.
        expected no risk, predicted investment_advice
        mechanism: fallback_propagation - the semantic fallback reproduced the
                   baseline's verdict on this text
```

Four of the five are the same shape, and it is worth stating precisely because
it is not the policy's own fault. The intent layer was **silent** on these texts
- there is no directive and no guarantee to find - so the semantic fallback ran,
and the baseline called them `investment_advice`:

| Case | Text | What the baseline saw |
| --- | --- | --- |
| IV-062 | The expense ratio is the annual cost of holding a fund. | `holding` read as the directive verb `hold` |
| IV-071 | The prospectus sets out the fund's investment objective. | the same |
| IV-072 | Custodians hold assets on behalf of the fund. | the same |
| IV-075 | Stamp duty applies to certain share purchases. | the same |

`hold` is a directive verb and also an ordinary transitive verb. The fallback
inherits the evaluator's false positives into neutral text, and the architecture
has no mechanism to reject them: a fallback layer is only as good as the layer it
falls back to.

The fifth is `IV-089`, the same `hold`-as-directive defect inside a conditional.

### 8.5 Annotation ambiguity - 0 decision errors, 8 arguable labels

No decision error rests on a disputed label. Eight labels are flagged by the
detector as arguable, and all eight sit on correctly decided cases:

| Case | Text | Why the label is a reading |
| --- | --- | --- |
| IV-047 | We are unconvinced that capital is protected here. | labelled `GUARANTEE`, but the text contains no guarantee vocabulary |
| IV-048 | The idea that the fund cannot fall is not supported. | labelled `RISK_REMOVED`, but `cannot fall` is not one of its markers |
| IV-050 | Contrary to the marketing, the return is not guaranteed. | `GUARANTEE` appears only under a negation |
| IV-052 | The assertion that losses are impossible is false. | labelled `RISK_REMOVED` by meaning |
| IV-059 | We would not describe this as a safe bet. | labelled `RISK_REMOVED`; the article is refusing the framing |
| IV-060 | There is no evidence for the claim that capital is protected. | as IV-047 |
| IV-081 | Returns are not guaranteed under any circumstances. | as IV-050 |
| IV-086 | No guarantee is given regarding distributions. | as IV-050 |

This is a limitation of the labels, not of the pipeline, and it is the honest
cost of a single annotator writing a relation field by meaning where the text
carries a different form. The detector deliberately checks only the two relations
whose form is a closed list: `PREDICTION` and `ADVICE` are realised too variously
for a checklist, and an earlier version that tried flagged a correct label
(`Turnover expands sharply next quarter.`) as ambiguous, which is worse than not
checking.

---

## 9. Limitations

1. **Single annotator, synthetic, self-authored.** The benchmark was written by
   the same person who wrote the pipeline, in one sitting, from the guide. It is
   *independent of the pipeline's development*, which is what the phase asked
   for, and it is **not independent of its author**. Every figure here is bounded
   by that.
2. **The audit fails.** `independent_v1` contains one reused sentence. `v2`
   passes, and the reader should prefer it, but v1 is the version the freeze and
   the headline figures name.
3. **The failures are one failure, mostly.** 23 of 39 come from the layer not
   knowing the wording. This is not 23 independent problems; it is a lexicon and
   a frame set that were fitted to a narrow sample.
4. **No kappa, no adjudication, no second opinion.** Section 6 of the protocol
   says what would be needed and none of it exists.
5. **The absolute numbers are not capability claims.** 85% decision accuracy on
   100 synthetic sentences says nothing about real financial material, and the
   phase forbids saying otherwise.
6. **Two layers cannot be told apart here.** The attribution and intent layers
   share their lexical weakness, so a case that fails may fail at either and the
   classifier's primary category is a judgement about where to lay it.
7. **The fallback is unguarded.** Four false positives are the baseline's,
   carried through unchanged, and nothing in the architecture filters them.
8. **Latency is unmeasured**, and the audit itself is slow - the full test suite
   went from 23 to 58 seconds, almost all of it the 100 × 13 overlap comparisons.
9. **The classifier is a heuristic.** It leaves nothing unclassified here, but
   its mechanism detectors are pattern matches on the text and would not
   necessarily generalise.

---

## 10. Recommendation

**Do not proceed to production integration. Do proceed to a targeted repair
phase, in this order.**

The architecture's *shape* survived: the decision policy holds, the trace holds
completely, and v3 beats the baseline on precision, recall, F1 and accuracy on
data it had never seen. What did not survive is the vocabulary, and the phase's
own headline claim about guarantee forms failed on a group it had never measured.

Priorities, highest value first:

1. **Fix the inflected-verb bug.** It is a defect, not a design choice. One word
   boundary is the difference between `expand` and `expands`. This is the only
   item on this list that is unambiguously a bug, and it is the cheapest.
2. **Make the copular frame span a negator.** Three of the seven unmatched
   guarantee cases are `is not guaranteed`. A frame that cannot match the negated
   form of the relation it exists to detect cannot be audit-checked against
   negation handling at all.
3. **Widen the attribution lexicon and cue list.** `traders`, `custodian`,
   `trustee`, `exchange`, `prospectus`, `advert`, `marketing material` and
   `we reject` / `we are unconvinced` / `is not supported` are ordinary financial
   vocabulary, and they account for 23 of 39 failures.
4. **Guard the fallback.** A category the intent layer was silent on is being
   taken from an evaluator whose false positives were already measured. Either
   suppress fallback categories that the baseline's own precision makes doubtful,
   or accept them explicitly as inherited risk.
5. **Then re-run this exact validation**, against `independent_v2` and a **new**
   independent set written after the repair, with the freeze taken before the
   run. A repair validated on the set that motivated it is not validated.
6. **Get a second annotator before any further capability claim.** The protocol
   already specifies what that requires. Until it happens, this is engineering
   validation and nothing more.

The one thing not to do is to treat the drop from Phase 8.5's numbers as a
regression. It is not: Phase 8.5's numbers were measured on material the
architecture was built against, and this phase measured the difference. The
architecture did not get worse; the measurement got honest.

---

## 11. Verification and Status

| Check | Result |
| --- | --- |
| Independent benchmark created | 100 cases, 5 groups, 5 categories |
| No benchmark contamination | **FAIL** for v1 (1 exact overlap), PASS for v2 (99 cases) |
| Pipeline frozen before evaluation | yes; freeze file mtime precedes the predictions |
| Freeze verified after evaluation | **MATCH**, no mismatches |
| Blind evaluation completed | yes; predictions from `id` and `text` only |
| Metrics reproducible | yes; re-running reproduces every figure |
| Error analysis completed | 39 failures classified and explained |
| Production untouched | yes; `git status` shows only new directories |
| `risk_evaluation/v3` modified | **no** — frozen by hash, verified after |
| Historical benchmark labels modified | **no** |
| `python -m unittest discover -s tests` | **1750 passed, 0 failed** (was 1632) |
| Phase 8.6 suite | 118 passed |
| `compileall` / JSON / secret scan | PASS / 93 of 93 / PASS |
| Lazy exports | 53, all resolving |

| Requirement | Tests |
| --- | --- |
| benchmark, audit, freeze | `test_benchmark_and_freeze.py`, 62 |
| blind evaluation, metrics, claims, errors | `test_evaluation_and_errors.py`, 56 |

### What this phase does not claim

- It does not claim the risk system is production-ready.
- It does not claim the evaluator is solved; six cases are missed at the decision
  level and 39 layers were wrong somewhere.
- It does not claim the accuracy figures represent real-world capability. The
  benchmark is synthetic, single-annotated and self-authored.
- It does not claim v3 can be deployed, to the Creator Agent or anywhere else.
  It is not wired in, and this phase connected nothing.
