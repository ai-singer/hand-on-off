# Risk Evaluation Framework

Phase 7.1. A designed, replaceable layer for judging finance content risk, so
risk detection can move from "does this text contain a known word" to "what is
this content trying to do".

```text
Risk Taxonomy          what the risks are            risk_evaluation/taxonomy.py
      |
      v
RiskIntentEvaluator    how risks are detected        risk_evaluation/evaluator.py
      |
      v
RiskEvaluationResult   what was judged, serializable risk_evaluation/model.py
      |
      v
risk_constraints       existing artifact shape       unchanged
      |
      v
Quality Gate           existing decision             unchanged
```

**Status honesty:** this phase builds the framework and measures the current
capability boundary. It does **not** claim risk detection is solved. The only
evaluator that exists today is the existing keyword rules wrapped read-only,
and its measured detection of unenumerated wording is **0%** (section 6).

## 1. Risk Taxonomy

Five categories. Each states what the risk is, the intent behind it, the
evidence a claim in that category would need, and the framework's default
severity and action.

| Category | Intent | Evidence required | Severity | Default action |
| --- | --- | --- | --- | --- |
| `investment_advice` | Induce the reader to act on the market | disclaimer, evidence, uncertainty | `block` | `block` |
| `market_prediction` | Replace the reader's uncertainty with the writer's certainty | source, data, time_range | `warning` | `require_evidence` |
| `financial_guarantee` | Remove the reader's perception of risk | basis, counter_evidence, uncertainty | `block` | `block` |
| `unverified_information` | Borrow authority the writer cannot demonstrate | source, verification | `warning` | `require_evidence` |
| `emotional_manipulation` | Substitute emotional pressure for explanation | neutral_restatement | `warning` | `downrank` |

### Definitions and examples

**`investment_advice`** — content that directs the reader to take a specific
investment action, or that recommends a security, product or position.
Examples: *buy*, *sell*, *invest*, *should purchase*.

**`market_prediction`** — content that states a future market outcome as a
certainty rather than as a conditional or hedged projection.
Examples: *definitely rise*, *guaranteed growth*, *certain target price*.

**`financial_guarantee`** — content that promises a return, asserts a loss is
impossible, or removes risk from a financial decision.
Examples: *risk free*, *guaranteed profit*, *cannot fail*.

**`unverified_information`** — content that circulates a claim without a
reliable, checkable source, including rumour and anonymous attribution.
Examples: *insider information*, *rumor*, *anonymous source*.

**`emotional_manipulation`** — content that bypasses reasoning through panic,
urgency or exaggeration instead of evidence.
Examples: *panic*, *everyone is buying*, *you will miss out*.

### Why the taxonomy is finer than the current evaluator

The taxonomy separates `financial_guarantee` from `investment_advice`, and
names `emotional_manipulation` explicitly. The current keyword evaluator cannot
make the first distinction: it folds guarantee wording into its
`investment_advice` category.

Each category therefore declares `evaluator_categories` — the categories the
current evaluator can emit that belong to it — so the gap is recorded data:

| Taxonomy category | Current evaluator categories |
| --- | --- |
| `investment_advice` | `investment_advice` |
| `financial_guarantee` | `investment_advice` ← shared, ambiguous |
| `market_prediction` | `market_prediction` |
| `unverified_information` | `unverified_fact` |
| `emotional_manipulation` | `emotional_language` |

## 2. Evaluation Contract

`RiskEvaluationResult` is the one output shape every evaluator produces.

| Field | Meaning |
| --- | --- |
| `category` | Primary taxonomy category |
| `intent` | The intent from the taxonomy |
| `confidence` | How confident the evaluator is in *that category*, within [0, 1] |
| `evidence_required` | Evidence the category requires |
| `severity` | `info` / `warning` / `block` |
| `action` | `downrank` / `require_evidence` / `require_review` / `block` |
| `evaluator` | Which evaluator produced it |
| `detail` | Human-readable reason, including any reported ambiguity |
| `source_ids` | Sources the judgement applies to |
| `candidates` | Every taxonomy category the evidence is consistent with |

`as_dict()` / `from_dict()` round-trip through JSON, so results can be persisted
and reviewed without depending on the evaluator that produced them.

### Ambiguity is data, not a coin flip

`candidates` exists because a keyword match often cannot decide between
categories. A guarantee phrased with an advice keyword is reported as
`category="investment_advice"` with `candidates=("investment_advice",
"financial_guarantee")` and a confidence of 0.5 — the match is certain, the
category is not. Resolving it silently would overstate what was actually
determined.

## 3. Intent Layer

```python
class RiskIntentEvaluator(Protocol):
    name: str
    def evaluate_text(self, text, *, source_ids=()) -> tuple[RiskEvaluationResult, ...]: ...
    def evaluate_artifact(self, artifact) -> tuple[RiskEvaluationResult, ...]: ...
```

Any implementation that satisfies the protocol is usable: the framework does
not care whether risk intent comes from keywords, semantics or a model.

| Evaluator | Status |
| --- | --- |
| `KeywordRiskEvaluator` (`keyword-xiaolin-finance-v1`) | **Exists.** Wraps the current xiaolin_finance rules read-only. |
| `SemanticRiskEvaluator` (`semantic-intent-v0`) | **Prototype exists** (Phase 7.2). Composes surface signals into intent patterns; reads no rule file. Not wired into production. |
| Model-backed evaluator | Not implemented. Would additionally have to document network use, timeout and failure behaviour. |

`KeywordRiskEvaluator` adds, removes and reweights **no** keyword. It runs the
plugin exactly as production does and translates the resulting risk
constraints into framework results, so what gets measured is the real current
behaviour.

## 4. Evidence Requirement

A risk judgement is not only "does this look risky" but "does the claim carry
the evidence its category requires".

`assess_evidence(category, source_ids=..., artifact=...)` reports each
requirement as:

- **satisfied** — the artifact demonstrates it;
- **unsatisfied** — the artifact should demonstrate it and does not;
- **unknown** — the artifact cannot express it at all.

The distinction matters. Only `source` is derivable from the artifact today
(the risk names the sources it applies to). Every other requirement —
`data`, `time_range`, `disclaimer`, `uncertainty`, `basis`, `counter_evidence`,
`verification`, `neutral_restatement` — is `unknown`, because the artifact
carries no field for it.

Treating `unknown` as satisfied would overstate what the content proves;
treating it as unsatisfied would overstate what the framework checks. Neither
is done.

## 5. Relationship to the Quality Gate

The gate is **not modified**. The designed connection is a projection:

```text
RiskEvaluationResult.to_risk_constraint()
        |
        v
{"rule_id", "category", "severity", "action", "message", "source_ids"}
        |
        v
artifact.risk_constraints        (existing shape, unchanged)
        |
        v
Quality Gate                     (existing logic, unchanged)
```

Resulting behaviour, by severity:

| Severity | Effect on the existing gate | Generation |
| --- | --- | --- |
| `block` | gate returns `review_required` | never invoked |
| `warning` | rubric penalty applies; content may still require review | invoked only if the gate passes |
| `info` | recorded only | no gate effect |

Per category, that means `investment_advice` and `financial_guarantee` block,
while `market_prediction`, `unverified_information` and
`emotional_manipulation` require evidence or down-ranking.

Because the projection reuses the existing constraint shape, swapping the
evaluator changes *how constraints are produced* without changing the artifact
schema, the gate or the workflow.

## 6. Current Capability Boundary

Phase 7.2 expanded the benchmark to 50 cases (10 keyword, 10 safe, 20
paraphrase, 10 adversarial) and added a second evaluator. Measured with
`python -m risk_evaluation.benchmark`:

```text
                        keyword-xiaolin-finance-v1   semantic-intent-v0
keyword recall                100%                        100%
paraphrase recall               5%                         95%   <- capability boundary
false positive rate             0%                          0%
adversarial accuracy           40%                         90%
```

The keyword mechanism is exact on enumerated wording and catches almost none of
the unenumerated phrasing. The semantic prototype closes most of that gap on
this benchmark, but the benchmark and evaluator were written together, so the
gain is in-sample. Full evidence, failure cases and the overfitting disclosure
are in [`PHASE_7_2_SEMANTIC_RISK_EVALUATOR_REPORT.md`](PHASE_7_2_SEMANTIC_RISK_EVALUATOR_REPORT.md).

## 7. Limits of this design

- The framework is **not wired into production**. Nothing calls it; the plugin
  still produces risk constraints directly. Section 5 is a design, not an
  integration — verified by test in Phase 7.2.
- Only `source` evidence is checkable. The evidence layer mostly reports
  `unknown`, which is honest but not yet useful for gating.
- The taxonomy is hand-written and uncalibrated against real material.
- The semantic evaluator is a **prototype**: an explainable rule system that
  composes surface signals. Its measured improvement is in-sample, two
  benchmark cases still fail, and no independent corpus has been used to
  confirm generalisation.
