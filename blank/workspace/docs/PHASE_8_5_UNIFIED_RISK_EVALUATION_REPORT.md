# Phase 8.5 - Unified Risk Evaluation Architecture

Phase: 8.5
Status: **PASS WITH ISSUES**
Date: 2026-09-27
Package: `risk_evaluation/v3/`
Benchmark: `risk_evaluation_v3/v1`, 60 composition cases
Production changed: **no**

---

## 1. Architecture

An experimental composition of three layers built in Phases 8.2 to 8.4, behind
one interface.

```
                     Raw text
                        |
      claim extraction  |  Phase 8.2 ClaimParser
                        v
                      Claims
                        |
   attribution analysis |  Phase 8.2 AttributionAnalyzer
                        v
                 Speaker + Stance
                        |
  intent analysis       |  Phase 8.4 RelationMatcher, four relations
                        v
          Relation + Entity + Frame
                        |
  semantic fallback     |  semantic_evaluator_v2, only where intent was silent
                        v
                    Categories
                        |
  decision policy       |  explicit, ordered, evidenced
                        v
        Risk evaluation result + full trace
```

| Module | Responsibility |
| --- | --- |
| `model.py` | `RiskClaim`, `ClaimInput`, `IntentEvidence`, `RiskDecision`, `ClaimTrace`, `RiskEvaluationResult` |
| `patterns.py` | the four relations over six entity types, reusing Phase 8.4's model classes |
| `adapters/` | `attribution.py`, `intent_pattern.py`, `semantic.py` - uniform `evaluate(claim)` |
| `decision.py` | the ordered rule table, including the phase's three cases |
| `pipeline.py` | `RiskEvaluationPipeline.evaluate(text)` |
| `benchmark/` | 60 composition cases and the four metric families |
| `replay.py` | the Phase 8.1 / 8.3 / 8.4 failure replay |

### 1.1 Three constraints enforced in code, not promised in prose

**Every claim has evidence.** `RiskClaim.__post_init__` raises if `evidence` is
empty. A claim whose speaker and stance cannot be evidenced is not one this
pipeline is allowed to report.

**No decision without evidence.** `RiskDecision.__post_init__` raises if its
evidence is empty, so "why was this flagged?" always has an answer naming the
rule and the finding it acted on.

**The span survives.** `source_span` is kept on every claim, so a final category
traces back to the characters that produced it. Returning only categories is
what made the Phase 8.1 defect hard to see: the verdict was there and the reason
was not.

### 1.2 The adapters convert protocols and nothing else

Each adapter wraps one existing implementation through a uniform
`evaluate(claim)` interface. None of them holds detection logic: the attribution
adapter delegates to `risk_evaluation.attribution`, the intent adapter to
`risk_evaluation.intent_patterns`, the semantic adapter to
`semantic_evaluator_v2`. A test asserts the adapters contain no signal patterns,
no intent patterns and no entity lexicon of their own.

Two details are worth recording.

**Attribution runs on the source text, not the claim.** Stance is not a
per-sentence question: `Analysts expect growth. However, we disagree.` labels the
first claim `rejected` because of a connective in the second. Results are cached
per source text, so n claims cost one analysis.

**The semantic evaluator is a fallback.** It is consulted for a claim only when
the intent layer asserted no relation there. Running it unconditionally would
make this v2 with extra steps and would hide whether the new layers contribute
anything. The stage records which of the two situations occurred.

### 1.3 Relations and entities

| Relation | Category | Realisations |
| --- | --- | --- |
| `GUARANTEE` | `financial_guarantee` | attributive, passive, copular, active, nominal |
| `RISK_REMOVED` | `financial_guarantee` | risk-free, no risk, cannot lose, never falls |
| `PREDICTION` | `market_prediction` | will + movement, certain to + movement, horizon, reported expectation |
| `ADVICE` | `investment_advice` | imperative, modal directive, implicit, directive verb |

`unverified_information` and `emotional_manipulation` are deliberately absent.
Sourcing and reader pressure are not relations between an entity and a
predicate, and inventing frames for them would be pattern-fitting. They come
from the fallback, which is what the fallback is for.

The entity set is the phase's four - RETURN, CAPITAL, VALUE, OUTCOME - plus
`INSTRUMENT` and `REVENUE`, marked as extensions in `model.py`. `You should buy
this stock.` has no object among the four: a stock is not a return, a capital
amount, a value or an outcome.

---

## 2. Benchmark composition

`risk_evaluation_v3/v1`, 60 cases, exported to
`benchmark/v3_report.json`.

| Group | Cases | Required | Expectation |
| --- | --- | --- | --- |
| author endorsed risk | 15 | 15 | the article's own risk category |
| third party quoted risk | 15 | 15 | the source's category, never the article's |
| author rejection | 10 | 10 | nothing |
| neutral education | 10 | 10 | nothing |
| ambiguous | 10 | 10 | nothing |

**Labels come from the annotation guide, never from a run.** Every case carries
a `basis` string naming the guide section its label follows, and a test asserts
that no case names a pipeline result as its source. Each case also labels its
claims (speaker, stance, expected relation), so attribution accuracy and intent
recall are measured on the same cases as the decision metrics.

Two label corrections were made after the first run, both disclosed:

- **AR-04** read `[]`, contradicting Phase 8.3's C-04 - the *same sentence* -
  labelled `["unverified_information"]`. Guide v2 §7 makes unverified
  information attribution-agnostic, so C-04 was right. The correction lowers the
  v3 false-positive count by one.
- **AM-09** read `["unverified_information"]`; the marketing material is a
  checkable document, so §7 makes it negative. The correction removes one error.

The TQ group was relabelled to follow §7 strictly: an unnamed collective
("Analysts", "Experts", "Economists", "Officials", "Commentators", "a broker",
"Sources") is uncheckable and becomes unverified information; a definite party
or document ("the company", "the report", "the newsletter", "Management", "the
board", "the regulator") is checkable and becomes nothing. **Five of those
labels are cases the pipeline gets wrong**, and they were left wrong rather than
softened.

---

## 3. Attribution metrics

| Metric | Result |
| --- | --- |
| claim split accuracy | **100.0%** (60/60) |
| speaker accuracy | **96.8%** (61/63 aligned claims) |
| stance accuracy | **95.2%** (60/63 aligned claims) |

Attribution is scored only on cases whose claim count matched, and the aligned
count is always reported next to the figure.

The five errors are inherited from Phase 8.2 and are all marker-table gaps:

| Case | Text | Expected | Got | Cause |
| --- | --- | --- | --- | --- |
| TQ-04 | A broker told clients the fund cannot lose money. | third_party | unknown | `a broker` is not in the source table |
| TQ-14 | The regulator said capital is guaranteed. | third_party | unknown | `the regulator` singular is not (`regulators` is) |
| TQ-08 | The newsletter recommends buying this stock. | quoted | uncertain | `recommends` is not a reporting frame |
| NE-07 | The board meets on the second Tuesday of the month. | third_party | third_party | stance: a mentioned party is read as a speaker |
| NE-01 | A price-to-earnings ratio compares price with earnings per share. | uncertain | quoted | the `per ` quotation marker matches `per share` |

NE-01 is the most interesting: a Phase 8.2 marker intended for `per analysts`
fires on the ordinary phrase `per share`. It is a false attribution produced by
a weak marker, and it is why the stance figure is not higher.

---

## 4. Intent metrics

| Metric | Result |
| --- | --- |
| relation recall (relations) | **100.0%** (40/40) |
| relation recall (cases) | **100.0%** (40/40) |

| Relation | Found / expected |
| --- | --- |
| GUARANTEE | 11/11 |
| RISK_REMOVED | 16/16 |
| PREDICTION | 9/9 |
| ADVICE | 4/4 |

Detection and assertion are counted separately. `Analysts say the fund cannot
lose money.` contains the RISK_REMOVED relation - the layer found it - and the
policy then declines to report it as the article's. Counting only *asserted*
relations scored this metric at 37.5% for a layer that found the relation in
every case, because it was scoring the intent layer for a decision the policy
made. `CaseOutcome` now reports `found_relations` and `asserted_relations`
separately.

Getting to 100% took two genuine additions found by the misses: `the market` was
missing from the VALUE entity type, and there was no frame for a *reported*
expectation (`Management expects the share price to double.`), only for direct
assertions.

---

## 5. Decision metrics

| Metric | Baseline (`semantic-intent-v2`) | v3 |
| --- | --- | --- |
| precision | 0.6429 | **0.9500** |
| recall | 0.7500 | **0.7917** |
| F1 | 0.6923 | **0.8637** |
| accuracy | 0.7000 | **0.9000** |
| false positives | 10 | **1** |
| false negatives | 6 | **5** |

**12 cases fixed, 0 broken.** 54 of 60 cases exactly right.

| Group | Baseline | v3 | FP | FN |
| --- | --- | --- | --- | --- |
| author endorsed risk | 12/15 | **15/15** | 0 → 0 | 3 → 0 |
| third party quoted risk | 7/15 | **10/15** | 3 → 0 | 3 → 5 |
| author rejection | 4/10 | **9/10** | 6 → 1 | 0 → 0 |
| neutral education | 10/10 | 10/10 | 0 → 0 | 0 → 0 |
| ambiguous | 9/10 | **10/10** | 1 → 0 | 0 → 0 |

The controls behave: neutral education is untouched, and no group regressed on
accuracy. The group B result is an honest trade, not a uniform gain - v3 stops
flagging borrowed guarantees as the article's (FP 3 → 0) and misses five
uncheckable-source cases the baseline also missed or got wrong differently
(FN 3 → 5).

### 5.1 The six remaining errors

| Case | Text | Expected | v3 | Cause |
| --- | --- | --- | --- | --- |
| TQ-04 | A broker told clients the fund cannot lose money. | unverified_information | `[]` | sourcing lexicon |
| TQ-05 | Economists forecast the stock will certainly double. | unverified_information | `[]` | sourcing lexicon |
| TQ-06 | Officials said the fund cannot lose money. | unverified_information | `[]` | sourcing lexicon |
| TQ-07 | Commentators said the market will certainly crash. | unverified_information | `[]` | sourcing lexicon |
| TQ-13 | Experts predict the fund cannot lose money. | unverified_information | `[]` | sourcing lexicon |
| AR-07 | This article rejects the idea that the fund cannot lose money. | `[]` | `financial_guarantee` | rejection cue not in the Phase 8.2 table |

**Five of the six are one defect.** The sourcing classifier recognises
`analysts`, `insiders`, `sources` and `rumour`, and not `broker`, `economists`,
`officials`, `commentators` or `experts`. This is the "the lexicon is thin"
finding from Phase 7.5, now with a measured cost: five recall failures on the
group the pipeline was built to handle.

---

## 6. Trace completeness

| Metric | Result |
| --- | --- |
| claims across the benchmark | 63 |
| claims with evidence | **63 (100.0%)** |
| decisions without evidence | **0** |
| traces missing a span | **0** |

The phase requires 100% of claims to carry evidence, and this is produced by a
run rather than asserted in a docstring. The trace for one claim:

```json
{
  "claim": "This return is guaranteed.",
  "claim_id": "claim-001",
  "source_span": [0, 26],
  "speaker": "unknown",
  "stance": "uncertain",
  "intent": {"relation": "GUARANTEE", "entity": "RETURN"},
  "evidence": [
    "rule:speaker.no-marker",
    "rule:stance.no-marker",
    "rule:attribution.unknown/uncertain",
    "copular_guarantee_pattern",
    "rule:semantic.skipped:intent-found-GUARANTEE"
  ],
  "decision": {"category": "financial_guarantee", "action": "block"}
}
```

Every final judgement can answer the four questions the phase names: *why was it
detected* (the frame and pattern), *who said it* (speaker and stance with their
markers), *what relation* (relation, entity, frame), and *on what basis* (the
rule id and the evidence strings).

One design change came out of this. Stage timings were initially recorded in the
trace, which made two runs of the same text differ in the fourth decimal: a
trace that is not reproducible is not much of a trace. Timings are now off by
default and available through `PipelineConfig(record_timings=True)`.

---

## 7. Failure analysis

### 7.1 Historical replay

41 cases read from the artifacts the earlier phases published, with before and
after kept for each.

| Phase | Cases | Min | Before | After | Fixed | Broken | Still open |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 8.1 adversarial misses | 15 | 5 | 0 | 6 | 6 | **0** | 9 |
| 8.3 attribution failures | 9 | 5 | 6 | 8 | 2 | **0** | 1 |
| 8.4 guarantee blind spots | 17 | 5 | 4 | 16 | 12 | **0** | 1 |

**No historical failure regressed.** Evidence is complete on all 41.

The Phase 8.4 group is the clearest result: the old rule saw 4 of 17 guarantee
forms, and v3 sees 16. The Phase 8.1 group is the least: six fixed and nine
still open, all paraphrase cases (`Acquire a position in this equity`,
`Your capital is insulated from any decline`). v3 does not add synonym coverage
and does not claim to; those remain Phase 8.1's open finding.

### 7.2 Two defects the replay itself found

Both were regressions v3 introduced, and both were caught before the phase was
reported.

**Case 2 as specified broke two Phase 8.1 controls.** The phase says a quoted
third party's guarantee becomes `unverified_information`. Applied literally,
`Management expects the share price to double.` produced it - but guide v2 §7
says a *named, checkable* source is **negative** for that category. The rule is
now narrowed to sources the sourcing layer actually flags, and the pipeline
emits nothing for a checkable one. The guide is the normative document and it
wins over a loose sentence in a brief. This is reported rather than quietly
resolved because the phase text and the guide genuinely conflict.

**The fallback undid the intent layer's decision.** `A guaranteed return is not
available.` reaches the intent layer as a negated GUARANTEE, which the policy
suppresses - and then the semantic layer re-added `financial_guarantee`, putting
the false positive straight back. A category the intent layer found and the
policy declined is no longer offered to the fallback again. Two of the six
benchmark errors were this defect.

### 7.3 Two composition defects found while building

**`should` means different things for different relations.** Phase 8.4 lists it
as a hedge, which is right for a guarantee and wrong for advice: `You should buy
this stock.` *is* the advice. The decision layer now interprets the marker per
relation rather than the matcher discarding it.

**Reporting hedges are not conditional hedges.** `The company said the fund
cannot lose money.` is hedged by `said`, which is the same marker the attribution
layer used to call it quoted. Treating it as a generic hedge suppressed the
finding entirely and produced no category at all. Reported speech is now routed
to Case 2 and only conditional or modal hedging suppresses.

---

## 8. Limitations

1. **One benchmark, written by the architecture's author.** 60 synthetic cases.
   Five of its labels are cases the pipeline fails, which is the honest
   direction, but a dataset written by someone else would find more.
2. **The sourcing lexicon is the largest single defect** - five of six remaining
   errors. It is a Phase 8.2 gap that v3 inherits and exposes rather than fixes.
3. **The fallback is a fallback, not a solution.** `unverified_information` and
   `emotional_manipulation` have no relation model; without the semantic layer
   the pipeline would report neither.
4. **`REVIEW` is declared but unused.** The action exists in `ACTIONS` and is
   emitted by no rule. It is a placeholder for a severity between block and
   require-evidence that this phase did not need.
5. **No confidence calibration.** `RiskClaim.confidence` takes the maximum of the
   attribution and intent confidences, which is a convenient number rather than a
   calibrated probability.
6. **Merged decisions keep the strongest action and lose the rest.** Two claims
   raising the same category with different actions produce one decision; the
   weaker action is discarded rather than reported.
7. **Case 3's scope is a judgement call.** "A rejection does not inherit the
   rejected claim's risk" now suppresses the rejected claim's fallback categories
   too. Guide v2 does not say this explicitly; it follows from reading §3.1's
   purpose.
8. **Performance is not measured.** The pipeline runs the Phase 8.2 analyzer once
   per text (cached) and the semantic evaluator once per unsilent claim. No
   benchmark exists for latency or cost.
9. **Not connected to anything.** No runtime, no Quality Gate, no production
   path, and nothing imports this package outside its own tests.

---

## 9. What this phase does not claim

- It does not claim the risk capability is production-ready. It is an offline
  prototype on a synthetic benchmark.
- It does not claim the evaluator is solved. One category set is modelled by
  relations, two come from the fallback, and six benchmark cases are wrong.
- It does not claim it is wired into the Creator Agent. Nothing was integrated:
  `semantic_evaluator_v2`, `taxonomy_v2`, the plugin, the Quality Gate and the
  runtime are untouched, and `git status` shows only new directories.
- It does not claim the benchmark is independent. It is not.
- It does not claim the improvement generalises. It is measured on 60 synthetic
  cases written by the same author as the pipeline.

---

## 10. Verification

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests` | **1632 passed, 0 failed** (was 1389) |
| Phase 8.5 suite (`tests/risk_evaluation_v3/`) | 243 passed |
| `python -m compileall` | PASS |
| JSON validity (all workspace JSON) | 84/84 PASS |
| Secret scan (workspace + repository root) | PASS |
| Both recorded evaluation freezes | MATCH (unchanged) |
| `benchmark_registry.verify_all()` | all True; registry keys unchanged |
| `semantic_evaluator_v2.py` / `taxonomy_v2.py` modified | **no** |
| Existing benchmark labels modified | **no** |
| Production / runtime / plugin files modified | **no** — only two new directories |
| `regression.EVALUATORS` | unchanged (`keyword`, `semantic`) |
| Lazy exports | 46, all resolving, no duplicate keys |

| Requirement | Tests |
| --- | --- |
| unified data model and trace | `test_model.py`, 60 |
| adapters | `test_adapters.py`, 35 |
| decision policy and three cases | `test_decision.py`, 33 |
| pipeline, fallback, trace completeness | `test_pipeline.py`, 41 |
| benchmark and historical replay | `test_benchmark_and_replay.py`, 57 |
| production isolation and regression protection | `test_isolation.py`, 17 |

### 10.1 Acceptance criteria

| Criterion | State |
| --- | --- |
| Attribution integrated | yes — adapter, per-claim, cached |
| Intent pattern integrated | yes — adapter, four relations, 100% relation recall |
| Semantic evaluator fallback integrated | yes — consulted only where intent was silent |
| Decision trace generated | yes — 100% of claims, with spans and rule ids |
| Historical failures replayable | yes — 41 cases across three phases, 0 broken |
| Production code untouched | yes — verified by diff and by test |
