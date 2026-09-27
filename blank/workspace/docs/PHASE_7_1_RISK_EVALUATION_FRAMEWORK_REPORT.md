# Phase 7.1 - Risk Evaluation Framework Report

```text
Final Status: PASS WITH ISSUES
```

The framework is built, measured and tested. It does **not** claim risk
detection is solved: the only evaluator that exists wraps the current keyword
rules, and its detection of unenumerated wording is **0%**.

Scope compliance: `xiaolin_finance` rules and keywords, the quality gate, the
artifact schema, the runtime bootstrap and the workflow were **not modified**.
No external model was introduced. No existing behaviour changed.

## 1. 当前问题分析

Phase 6.5.1 measured the plugin's risk boundary:

| Metric | Value |
| --- | --- |
| Detection of enumerated wording | 100% (11/11) |
| Detection of unenumerated wording | **0%** (0/9) |
| False positive rate on clean text | 20% (1/5) |

The failure is in the **false-negative** direction, which is the dangerous one:
prohibited content phrased outside the keyword list reaches the gate unflagged.

```text
detected   : "Buy now for a guaranteed return."
not detected: "You should buy this stock today."
not detected: "The price will definitely rise."      ("will definitely" matched; the
                                                      paraphrase above did not)
not detected: "This opportunity cannot fail."
```

Root cause: risk is modelled as a *lexical property of text* rather than as an
*intent expressed by text*. A keyword list can only recognise the phrasings
someone already wrote down.

The design response is not a bigger keyword list. It is to separate:

- **what a risk is** — a taxonomy of intents, with evidence expectations;
- **how it is detected** — a replaceable evaluator behind one interface.

so that a semantic evaluator can be added later without touching the taxonomy,
the result contract, the artifact schema or the gate.

## 2. Risk Taxonomy

Five categories, each with definition, intent, evidence requirement, severity
and default action. Full text in
[`RISK_EVALUATION_FRAMEWORK.md`](RISK_EVALUATION_FRAMEWORK.md).

| Category | Intent | Evidence required | Severity | Action |
| --- | --- | --- | --- | --- |
| `investment_advice` | Induce the reader to act on the market | disclaimer, evidence, uncertainty | `block` | `block` |
| `market_prediction` | Replace uncertainty with the writer's certainty | source, data, time_range | `warning` | `require_evidence` |
| `financial_guarantee` | Remove the reader's perception of risk | basis, counter_evidence, uncertainty | `block` | `block` |
| `unverified_information` | Borrow authority the writer cannot demonstrate | source, verification | `warning` | `require_evidence` |
| `emotional_manipulation` | Substitute emotional pressure for explanation | neutral_restatement | `warning` | `downrank` |

The taxonomy covers all four categories the phase required, plus
`emotional_manipulation`, which the current evaluator already detects and which
would otherwise have no home in the taxonomy.

### Design finding: the taxonomy is finer than the evaluator

The taxonomy separates `financial_guarantee` from `investment_advice`; the
current evaluator cannot. This is recorded as data rather than hidden: each
category declares the evaluator categories that map to it, and
`financial_guarantee` shares `investment_advice` with `investment_advice`.
Evaluating a guarantee therefore yields `candidates=("investment_advice",
"financial_guarantee")` and a confidence of 0.5.

## 3. Evaluation Contract

`RiskEvaluationResult` — one serializable shape for every evaluator:

```text
category, intent, confidence, evidence_required, severity, action,
evaluator, detail, source_ids, candidates
```

Design decisions worth recording:

- **`confidence` states category confidence, not match confidence.** A keyword
  match is deterministic, so the interesting uncertainty is *which category* it
  means. With N candidate categories the evaluator reports `1/N`.
- **`candidates` makes ambiguity explicit.** Silently picking one category would
  overstate what was determined.
- **Round-trippable.** `as_dict()` / `from_dict()` survive `json.dumps` →
  `json.loads`, so results can be stored and reviewed independently of the
  evaluator that produced them.
- **Validation at construction.** Unknown severity or action, out-of-range
  confidence and empty category/intent raise immediately.

## 4. Intent Layer 设计

```python
class RiskIntentEvaluator(Protocol):
    name: str
    def evaluate_text(self, text, *, source_ids=()) -> tuple[RiskEvaluationResult, ...]: ...
    def evaluate_artifact(self, artifact) -> tuple[RiskEvaluationResult, ...]: ...
```

| Evaluator | Status | Notes |
| --- | --- | --- |
| `KeywordRiskEvaluator` | Implemented | Wraps `plugins.xiaolin_finance` read-only; adds/removes/reweights no keyword |
| Semantic evaluator | Not implemented | Interface only; a test double proves the protocol accepts it |
| Model-backed evaluator | Not implemented | Would also have to document network use, timeout and failure behaviour |

`evaluate_artifact` exists alongside `evaluate_text` so an existing artifact can
be re-judged without re-distilling it. Backward compatibility is handled: an
artifact written before Phase 6.2 has no `risk_constraints[].category`, and the
evaluator resolves it from the rule id instead of failing.

## 5. Evidence Requirement

`assess_evidence()` reports each requirement as **satisfied**,
**unsatisfied**, or **unknown**.

| Evidence | Derivable from the artifact today? |
| --- | --- |
| `source` | **yes** — the risk names its sources |
| `verification`, `data`, `time_range`, `disclaimer`, `evidence`, `uncertainty`, `basis`, `counter_evidence`, `neutral_restatement` | **no — reported as `unknown`** |

This is the honest result and also the main gap: the framework can state what a
claim would need, but the artifact cannot yet prove it. `unknown` is
deliberately distinct from `unsatisfied` — one means "not expressed", the other
means "expressed and missing".

## 6. Benchmark 结果

> **已被 Phase 7.2 取代（保留为历史记录）。** 本节记录的是 Phase 7.1 当时的 **20 条**
> 基准（10 positive / 5 safe / 5 paraphrase）。Phase 7.2 按阶段要求把基准扩展到
> **50 条**（10 keyword / 10 safe / 20 paraphrase / 10 adversarial），并修正了 safe 集
> 假阳性的统计口径。因此现在运行 `python -m risk_evaluation.benchmark` 得到的是 50 条
> 结果，与本节的数字不可直接比较。当前基线与对比见
> [`PHASE_7_2_SEMANTIC_RISK_EVALUATOR_REPORT.md`](PHASE_7_2_SEMANTIC_RISK_EVALUATOR_REPORT.md)。

`tests/risk_evaluation_framework/` — 20 benchmark cases (10 positive /
5 safe / 5 paraphrase) plus framework tests. Measured with
`python -m risk_evaluation.benchmark`:

```text
evaluator            : keyword-xiaolin-finance-v1
positive (enumerated): 10/10  (100%)
paraphrase (novel)   :  0/5   (0%)   <- capability boundary
safe flagged         :  0/5   (0%)

per taxonomy category:
  emotional_manipulation   2/3
  financial_guarantee      2/3
  investment_advice        3/5
  market_prediction        2/4
  unverified_information   3/3
```

Missed cases (all paraphrase):

```text
You should buy this stock today.
I recommend adding this company to your portfolio.
Analysts are certain the price target will be reached.
This opportunity cannot fail.
The market will crash next month, get out now.
```

Reading:

- The mechanism is sound: every enumerated case is detected, across both
  languages the rules cover.
- The semantics do not exist: **0 of 5** paraphrases are detected.
- This benchmark shows **0% false positives** on its safe set, which does not
  contradict Phase 6.5.1's measured 20% — a different safe set is used. Negation
  handling is still absent; a sentence disclaiming a guarantee remains flagged.

**Adding this framework did not improve detection.** The numbers are identical
to the keyword rules it wraps, because it *is* those rules. That is the point:
the boundary is now measured through a replaceable interface, so a better
evaluator can be dropped in and re-measured against the same benchmark.

## 7. 与 Quality Gate 关系

The gate was not modified. The designed connection is a projection:

```text
RiskEvaluationResult
   -> to_risk_constraint()
   -> {"rule_id", "category", "severity", "action", "message", "source_ids"}
   -> artifact.risk_constraints        (existing shape)
   -> Quality Gate                     (existing logic)
   -> generation decision
```

| Severity | Gate effect | Generation |
| --- | --- | --- |
| `block` | `review_required` | never invoked |
| `warning` | rubric penalty; content may still need review | only if the gate passes |
| `info` | recorded only | no effect |

Because the projection emits the constraint shape the gate already consumes,
swapping evaluators changes how constraints are produced and nothing else.

**This is a design, not an integration.** Nothing in production calls the
framework today.

## 8. Known Limitations

| ID | Limitation | Impact |
| --- | --- | --- |
| L-01 | **Paraphrase detection is 0%** | Risk intent expressed outside the keyword list is not detected at all |
| L-02 | **The framework is not wired in** | Production still uses the plugin's keyword rules directly; this layer changes no runtime behaviour |
| L-03 | Only `source` evidence is checkable | The evidence layer reports `unknown` for 9 of 10 requirements |
| L-04 | `financial_guarantee` and `investment_advice` are indistinguishable | Reported as a 2-candidate ambiguity with confidence 0.5, not resolved |
| L-05 | Taxonomy is hand-written and uncalibrated | Category boundaries have never been tested against real material |
| L-06 | No semantic or model evaluator exists | The replaceability is proven by a test double, not by a working alternative |
| L-07 | Negation is still unhandled | A sentence disclaiming a guarantee is flagged as a guarantee |
| L-08 | Benchmark is synthetic and small | 20 cases can show the mechanism works; they cannot estimate real-world precision |
| L-09 | Bilingual only | Rules and probes cover English and Chinese; other languages are not designed for |

### What this phase does not claim

- It does **not** claim risk detection is solved, improved, or production safe.
  Detection capability is unchanged from Phase 6.5.1.
- It does **not** claim the taxonomy is complete or correct — it is a designed
  starting point that a future evaluator can be measured against.
- It does **not** claim the evidence layer enforces anything. It reports.

## 9. Validation

| Check | Command | Result |
| --- | --- | --- |
| Unit tests | `python -m unittest discover -s tests -v` | **PASS** — Ran **160** tests, OK (122 before, 38 new) |
| Compile | `python -m compileall .` | **PASS** — exit 0 |
| JSON | all `*.json` | **PASS** — 23/23 |
| Secret scan | workspace and repository root | **PASS** — 0 findings both scopes |
| Benchmark | `python -m risk_evaluation.benchmark` | measured; see section 6 |

New tests `tests/risk_evaluation_framework/` (38):

| Group | Count | Covers |
| --- | ---: | --- |
| Model and taxonomy | 11 | result round-trip and validation, constraint projection, severity effects; taxonomy completeness, policy, evaluator mapping |
| Evaluator | 11 | protocol conformance, replaceability by a different implementation, detection, ambiguity reporting, empty input, artifact evaluation, pre-6.2 artifacts, unknown rule id, serialization |
| Evidence | 8 | requirements follow the taxonomy, descriptions, `source` satisfied/unsatisfied, non-derivable reported as unknown, serialization |
| Benchmark | 8 | 10/5/5 composition, unique ids, well-formed expectations, measured rates, per-category counts, serialization |

The benchmark group **pins the measured rates to this report**, so if the rules
or evaluator change, the test fails and this document must be updated in the
same change.

### Test package naming

The test package is `tests/risk_evaluation_framework/`, not
`tests/risk_evaluation/` as the phase suggested. `tests/risk_evaluation/` would
shadow the workspace-level `risk_evaluation` package under
`unittest discover -s tests`, which puts `tests/` at `sys.path[0]`. The
existing guard test `test_test_packages_do_not_shadow_workspace_packages`
caught this immediately — the third time this hazard has appeared in this
project, and the first time the guard prevented it instead of a failure being
diagnosed afterwards.

## 10. Recommendation

1. Treat this as a **capability framework**, not a capability. Nothing improves
   until a second evaluator exists.
2. Next evaluator, cheapest first: (a) negation and stem handling inside the
   keyword evaluator; (b) a curated adversarial corpus to replace the 20-case
   benchmark; (c) a semantic evaluator behind the existing protocol, measured
   against the same benchmark with no rule changes.
3. Keep the benchmark and the taxonomy as the acceptance surface: any new
   evaluator must be scored on the same 20 cases, and section 6 updated.
4. Do not wire the framework into production until an evaluator beats the
   current numbers — wiring in a wrapper that reproduces keyword behaviour adds
   surface without adding capability.
