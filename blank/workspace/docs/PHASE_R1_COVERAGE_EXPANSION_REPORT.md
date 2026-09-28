# Phase R1 — Risk Coverage Expansion Report

**Architecture: PASS / Measurement: PASS / Governance: PASS / Capability: NEED IMPROVEMENT / Production: NOT READY**

## What this phase did

Phase R1 built a repeatable Risk Coverage Expansion Framework: a way to run the
frozen evaluator over a labelled set, explain every failure with evidence, turn
the explanations into candidates, and queue those candidates for a human. It did
not modify the evaluator, the taxonomy, the decision policy, any benchmark label,
or any runtime, production, workflow or plugin file. It introduces no LLM, no
network call and no production integration.

The framework's own numbers below are measurements of the *existing* evaluator,
unchanged:

| metric | value |
|---|---|
| precision | 0.9062 |
| recall | 0.1758 |
| F1 | 0.2945 |
| accuracy | 0.4949 |

## The five questions

### 1. What is the largest coverage gap right now?

The largest single gap is LEXICAL_GAP at 69 of 151 failures (45.7%), followed by ANNOTATION_CONFLICT 24, FRAME_GAP 19, STANCE_GAP 11. Read together with the generator's verdicts, the shape of the gap is lexical before it is structural: the evaluator's frames are frequently examined and declined, and the words its lexicons accept are narrower than the guide's categories.

### 2. Which failures can generate a candidate automatically?

100 of 151 failures carry a failure type this framework treats as auto-generatable (MORPHOLOGY_GAP, SYNONYM_GAP, FRAME_GAP, LEXICAL_GAP), and the generator produced 62 cases across 10 declared templates. 'Auto-generatable' means a candidate can be *built* mechanically from a declared axis. It does not mean the candidate is correct or that it may be applied — no candidate from this phase has been applied to anything.

### 3. Which failures require a human decision?

51 of 151 failures are typed for human judgement (ANNOTATION_CONFLICT, TAXONOMY_CONFLICT, UNKNOWN, ATTRIBUTION_GAP, STANCE_GAP). Two of the five taxonomy categories — `unverified_information` and `emotional_manipulation` — have no v3 relation at all, which the evaluator's own decision layer states outright; for those, a vocabulary proposal is not merely unwise but unexpressible, and 25 candidates in the queue are structural for exactly that reason.

### 4. Is it worth modifying the evaluator in the next phase?

Not yet, and the order matters. Two conditions are outstanding before touching the evaluator: a benchmark that did not exist when the candidates were made, and a decision policy that can absorb a wider lexicon without widening what counts as a finding. Adding words first would raise recall against the set the words were derived from, which measures nothing. The framework's own output argues for patience: most failures are lexical, but the ones that are not include a structural suppression path that no word list reaches.

### 5. Which risks remain barred from production?

All five categories remain barred from production, for three separate reasons. Precision on the independent set is 0.9062 with recall 0.1758, so the evaluator is silent on most risk-bearing text. `emotional_manipulation` has no v3 relation, so its detection rests entirely on a fallback. And every candidate in this phase is unscored: applying one would change behaviour with no measurement behind it. Production readiness is not claimable from any artifact in this phase, and the status remains Production: NOT READY.

## Independent corroboration

Phase 8.9 classified these same 151 failures with its own classifier. The two
distributions were produced independently — different vocabulary, different
evidence — so the points where they agree are a check on both:

| quantity | Phase 8.9 | Phase R1 | reading |
|---|---|---|---|
| cases whose text names no evaluator lexicon entity | not measured | 106 | Phase 8.9's largest class was lexical_gap at 106; this count was reached from the lexicon alone and lands on the same number |
| false positives | 3 | 3 | the evaluator's own metric and this framework's per-case outcome agree |
| annotation and taxonomy conflicts | 33 | 32 | the split differs because the types differ, but the totals are close enough that neither classifier is inventing disagreements |
| exact-set failures | 151 | 151 | identical, which is the precondition for the rest to mean anything |

The comparison is not a validation of the candidates. It says the framework
measures the same thing Phase 8.9 measured; it says nothing about whether any
proposed repair would work.

## Failure distribution, for reference

| failure type | cases | mean confidence |
|---|---|---|
| LEXICAL_GAP | 69 | 0.600 |
| ANNOTATION_CONFLICT | 24 | 1.000 |
| FRAME_GAP | 19 | 1.000 |
| STANCE_GAP | 11 | 0.600 |
| MORPHOLOGY_GAP | 9 | 1.000 |
| TAXONOMY_CONFLICT | 8 | 1.000 |
| UNKNOWN | 6 | 0.667 |
| SYNONYM_GAP | 3 | 1.000 |
| ATTRIBUTION_GAP | 2 | 1.000 |

## Not fixed

| item | state | why it is not fixed |
|---|---|---|
| Evaluator recall on the independent set (0.1758) | unchanged, by design | this phase measures and diagnoses; applying a candidate is a later phase's decision and requires a benchmark that did not exist when the candidate was proposed |
| `emotional_manipulation` has no v3 relation | reported, not repaired | repairing it means adding a relation to the frozen pattern set, which is both forbidden here and wrong to attempt without a labelled set for that category alone |
| `unverified_information` reaches the output only through a fallback | reported, not repaired | the same reason; the evaluator's decision layer documents the fallback as deliberate, and overriding a documented decision is not a coverage fix |
| Structural suppressions that no word list reaches | reported as FRAME_GAP | the capability layer declined these cases on structure, so a wider lexicon cannot recover them; they need a frame or a policy change, which this phase is not permitted to make |
| 3 cases with no adjudicated label | reported as UNKNOWN | a repair needs a defined target; proposing vocabulary for an unsettled label would be guessing at what to fix |

## What this phase does not claim

- It does not claim any accuracy improvement. No evaluator behaviour changed,
  so no metric moved; the framework's contribution is diagnosis.
- It does not claim production readiness, in whole or in part.
- It does not claim that its candidates are correct. They are proposals with
  declared reasoning, addressed to a human.
- It does not claim the failure taxonomy is complete. Unexplained failures are
  reported as UNKNOWN rather than forced into a type.
