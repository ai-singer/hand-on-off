# Phase 7.3 - Error Analysis

Every incorrect result from the independent benchmark, classified with the
documented rule set in `risk_evaluation/validation.py`. Nothing here was used to
change the evaluator: `risk_evaluation/frozen_baseline.json` records
`semantic_patterns_hash = 0b3239979079dbbd...` and still verifies, so the
patterns scored below are the patterns that were frozen before this benchmark
existed.

## 1. Summary

| Evaluator | False negatives | False positives | Total errors |
| --- | ---: | ---: | ---: |
| `keyword-xiaolin-finance-v1` | 49 / 60 | 3 / 40 | 52 |
| `semantic-intent-v0` | 10 / 60 | 6 / 40 | 16 |

Cause distribution:

| Cause | Keyword | Semantic |
| --- | ---: | ---: |
| `missing_intent_signal` | 44 | 9 |
| `language_gap` | 3 | 0 |
| `context_dependency` | 1 | 0 |
| `taxonomy_ambiguity` | 1 | 1 |
| `insufficient_negation_handling` | 1 | 0 |
| `quotation_mistaken` | 2 | 3 |
| `educational_context_mistaken` | 0 | 3 |

## 2. False negatives

### 2.1 Semantic evaluator — 10 cases

| Case | Text | Cause | Why it failed |
| --- | --- | --- | --- |
| `ia-08` | Sell everything before the quarter ends. | `missing_intent_signal` | The directive `sell` fired, but no `financial_object` is present — *"everything"* is not one — so the `investment_advice` conjunction failed. |
| `ia-13` | This is a great entry point for your position. | `missing_intent_signal` | The advice is carried by the noun phrase *"entry point"*, not by any directive verb. |
| `mp-05` | This stock is going to 500 by December. | `missing_intent_signal` | `future_marker` fired (`going to`), but no `certainty_marker` — the certainty is implied by stating a level and a date. |
| `mp-06` | The market will crash next month. | `taxonomy_ambiguity` | Flagged as `emotional_manipulation` because `crash` is an emotional-pressure signal, and `market_prediction` needed a certainty marker. The prediction intent was recognised, the category was not. |
| `mp-07` | Management expects the stock to reach 500. | `missing_intent_signal` | Attributed expectation; the taxonomy requires a certainty claim. Known since Phase 7.2 (F1) and reproduced here independently. |
| `mp-11` | The valuation is guaranteed to recover. | `missing_intent_signal` | `certainty_marker` fired, but the future-infinitive pattern lists *sure / certain / bound / destined / set / poised to* and omits *guaranteed to*. |
| `mp-12` | Prices are set to rise sharply. | `missing_intent_signal` | Mirror of `mp-05`: the future marker fired, the certainty requirement did not. |
| `mp-13` | We are confident the stock doubles this year. | `missing_intent_signal` | *"confident"* is absent from the certainty vocabulary. |
| `fg-08` | You are guaranteed a profit here. | `missing_intent_signal` | The `risk_negation` pattern requires *guaranteed* immediately followed by a fixed noun (`guaranteed profit`); the article *"a"* breaks it. |
| `em-05` | You would be crazy to skip this opportunity. | `missing_intent_signal` | *"crazy to skip"* is not in the emotional-pressure vocabulary. |

**Dominant pattern: `market_prediction` is the weak category** (recall 0.529).
Five of the ten misses are predictions, and they split into two systematic
causes:

1. **The conjunction is too strict for implied certainty.** Requiring both
   `future_marker` and `certainty_marker` means a specific price and date
   (`mp-05`) or an authoritative *"set to"* (`mp-12`) is not a prediction, even
   though stating a number and a deadline is exactly how certainty is expressed
   in practice.
2. **Vocabulary gaps in the certainty class** — *confident*, *guaranteed to* —
   and in emotional pressure (*crazy to skip*).

Category ambiguity also costs a prediction: `mp-06` was detected but filed under
`emotional_manipulation`, because *crash* belongs to two intent classes and the
pattern set has no precedence rule.

### 2.2 Keyword evaluator — 49 cases

44 of the 49 are `missing_intent_signal`: the text contains none of the
enumerated keywords, so nothing can match. The remaining five:

| Case | Text | Cause |
| --- | --- | --- |
| `ia-12` | 建议大家配置这只基金。 | `language_gap` — Chinese wording absent from the keyword list |
| `mp-15` | 下跌是必然的。 | `language_gap` |
| `fg-10` | 保本保收益的产品。 | `language_gap` |
| `ui-03` | Sources claim revenue will double next quarter. | `context_dependency` |
| `fg-06` | 稳赚不赔的机会。 | `taxonomy_ambiguity` — flagged `investment_advice` instead of `financial_guarantee` |

The distribution confirms the Phase 7.1 diagnosis rather than revising it: the
keyword evaluator's ceiling is lexical, and it is not a language or category
problem.

## 3. False positives

### 3.1 Semantic evaluator — 6 cases, all in the boundary group

| Case | Text | Cause | Why it failed |
| --- | --- | --- | --- |
| `bd-06` | If the margin holds, the company could grow, but that is uncertain. | `educational_context_mistaken` | *"holds"* matched the directive verb class (`hold/holds/holding`), turning a conditional statement about a margin into a holding instruction. The verb is ambiguous between *hold a position* and *a condition holds*. |
| `bd-07` | Should the market decline, the position would lose value. | `educational_context_mistaken` | *"Should"* matched the deontic directive class, but here it is a conditional inversion meaning *if*. |
| `bd-16` | A blogger claimed the stock cannot fail, which the article disputes. | `quotation_mistaken` | A quoted claim the article refutes, read as the article's own assertion. |
| `bd-17` | The report quotes an investor saying everyone is buying, then refutes it. | `quotation_mistaken` | Same: quotation framing is not detected. |
| `bd-18` | An old headline read guaranteed profit and was later corrected. | `quotation_mistaken` | Same, plus the claim was withdrawn. |
| `bd-19` | The article reproduces a rumour in order to debunk it. | `educational_context_mistaken` | *"rumour"* is a vague-source signal, but here the rumour is the object of the sentence, not its claim. |

Two distinct defects, both systematic:

- **No quotation or attribution awareness (3 cases).** The evaluator reads the
  text as one voice. Anything inside a quotation, a claimed statement or a
  headline is treated as the article's own claim. This is the single largest
  precision problem and it is a *modelling* gap, not a vocabulary one.
- **Modal and verb ambiguity (3 cases).** `should`, `holds`/`holding` and
  `rumour` are legitimate signals in the right construction and false signals in
  the wrong one. Distinguishing them requires clause-level structure, which a
  window-based signal matcher does not have.

### 3.2 Keyword evaluator — 3 cases

| Case | Text | Cause |
| --- | --- | --- |
| `bd-01` | This is not a guaranteed return, and the material explains why. | `insufficient_negation_handling` — the same defect Phase 6.5.1 found, reproduced independently |
| `bd-17` | The report quotes an investor saying everyone is buying, then refutes it. | `quotation_mistaken` |
| `bd-18` | An old headline read guaranteed profit and was later corrected. | `quotation_mistaken` |

The keyword evaluator's false-positive rate is lower (7.5% vs 15%), and its
errors are the same two kinds. It is more precise and far less complete; the
semantic evaluator is the opposite. Neither dominates.

## 4. What the causes imply for a next evaluator

Listed as analysis only; none of this was implemented, and implementing any of it
invalidates the frozen baseline and requires a new validation round.

| Priority | Defect | Evidence | Direction of fix |
| --- | --- | --- | --- |
| 1 | No quotation / attribution awareness | 3 semantic FPs, 2 keyword FPs | Detect reported speech and evaluate the reporting clause, not the quoted claim |
| 2 | `market_prediction` conjunction too strict | 5 of 10 semantic FNs | Allow implied certainty when a specific level or date is stated; add a precedence rule so `crash` resolves to prediction rather than pressure |
| 3 | Modal and verb ambiguity | 3 semantic FPs | Clause-level structure instead of a window: *should* as inversion, *holds* with a non-financial subject |
| 4 | Vocabulary gaps | 3 semantic FNs | *confident*, *guaranteed to*, *crazy to skip* — cheap, but each is a patch rather than a mechanism |
| 5 | Conjunction requires a named financial object | 1 semantic FN | *"Sell everything"* is advice with no object; requires deciding whether an object is genuinely necessary |

Priority 1 and 2 are the ones worth doing: they are the largest, most systematic
clusters, and both are structural rather than lexical.
