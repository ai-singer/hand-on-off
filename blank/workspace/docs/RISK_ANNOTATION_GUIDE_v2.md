# Risk Annotation Guide v2

Version `2.0.0`. Supersedes [`RISK_ANNOTATION_GUIDE.md`](RISK_ANNOTATION_GUIDE.md)
(`1.0.0`) for benchmarks labelled under it. **v1 is not edited and remains the
standard `semantic/v1` and `semantic/v2` were labelled under.**

v2 exists because three things v1 left under-specified turned out to decide
labels:

1. **Who is speaking.** v1 mentioned attribution in one section and then defined
   five categories as though every sentence were the author's.
2. **How strongly a claim is made.** v1 said "as a certainty" in the
   `market_prediction` definition and then never defined certainty.
3. **What happens when two categories match.** v1 had no precedence rule.

v2 answers all three as *data* — two new orthogonal fields and one ordering —
rather than as prose the annotator has to interpret. No new risk category is
introduced; the five v1 categories and their severities are unchanged.

## 1. Two fields beside the category

Every case carries, in addition to `expected_categories`:

| Field | Values | Meaning |
| --- | --- | --- |
| `statement_source` | `author`, `third_party`, `quoted`, `unknown` | Who makes the claim |
| `certainty_level` | `certain`, `probable`, `possible`, `hypothetical` | How strongly it is asserted |

These are **orthogonal to the category**. "Who says it" and "which risk is it"
are different questions, so they are different fields. A statement can be an
author-voice `financial_guarantee` or a quoted one, and the two are labelled
very differently.

### 1.1 `statement_source`

| Value | When |
| --- | --- |
| `author` | The article asserts the claim in its own voice |
| `third_party` | A named or reasonably identifiable party is reported as holding the claim (*analysts*, *management*, *the regulator*) |
| `quoted` | The claim appears inside quotation marks, a headline being discussed, or a comment being answered |
| `unknown` | The speaker is unattributable (*insiders*, *sources*, *they say*, *据说不具名消息人士*) |

**Precedence when several apply:** `quoted` → `unknown` → `third_party` →
`author`. Quotation marks settle the question; an unattributable speaker is more
specific than a merely named one; anything with no attribution is the author's.

### 1.2 `certainty_level`

| Value | When | Typical markers |
| --- | --- | --- |
| `certain` | Asserted as fact, no hedge | *will*, *is*, *必然*, *definitely* |
| `probable` | Asserted with a probability hedge | *probably*, *likely*, *expected to* |
| `possible` | Asserted as one possibility | *may*, *might*, *could*, *possibly* |
| `hypothetical` | Depends on a stated condition | *if*, *should X*, *were X to*, *assuming*, *unless* |

**Conditional beats modal.** *"If rates fall, the stock may rise"* is
`hypothetical`, not `possible`: the possibility is contingent.

Descriptive and explanatory text that asserts facts is `certain`. The field
records how the text presents its claim, not whether the claim is true.

## 2. Prediction versus expectation versus scenario

This is the repair v2 exists for. v1 defined `market_prediction` as an outcome
stated as a certainty, which left three different statements competing for one
label.

| Case | `statement_source` | `certainty_level` | `market_prediction`? |
| --- | --- | --- | --- |
| **Explicit prediction** — *"The stock will rise tomorrow."* | `author` | `certain` | **yes** |
| **Attribution expectation** — *"Management expects the stock to reach 500."* | `third_party` | any | **no** |
| **Scenario analysis** — *"If rates fall, the stock may rise."* | `author` | `hypothetical` | **no** |

### The rule

```text
market_prediction  <=>  statement_source == author  AND  certainty_level == certain
```

Everything else about a future market outcome is **not** `market_prediction`:

- **An attributed expectation is a report.** Reporting that management expects a
  price is not predicting it. If the article then endorses the expectation in
  its own voice, the endorsed sentence is a separate statement and is labelled
  on its own merit.
- **A scenario asserts nothing unconditionally.** *"If rates fall, the stock may
  rise"* states a dependency, and a reader cannot act on it as a prediction.
- **A hedged author claim is neither.** `probable` and `possible` are hedged, and
  v1 already excluded hedged projections; under v2 they fall under the scenario
  case, not the prediction.

### Target price

A named price level follows the same rule, not its own:

| Text | Source | Certainty | Label |
| --- | --- | --- | --- |
| The share price is bound to reach 500. | `author` | `certain` | `market_prediction` |
| Management expects the stock to reach 500. | `third_party` | `certain` | **none** |
| Analysts set a 500 target price. | `third_party` | `certain` | **none** |
| Analysts are certain the price target will be reached. | `third_party` | `certain` | **none** |

The last row is the one that used to be labelled `market_prediction` under v1
(case `mp-07`). Under v2 it is a reported expectation with a named speaker, and
it is **not** a prediction.

**A target price is only `market_prediction` when the article asserts it as its
own certainty.** *"The price target of 500 will be reached"* qualifies;
*"the analyst's 500 target"* does not.

## 3. Attribution handling

### 3.1 Which categories require the author's voice

| Categories | Requires `statement_source == author` |
| --- | --- |
| `investment_advice`, `market_prediction`, `financial_guarantee`, `emotional_manipulation` | **yes** |
| `unverified_information` | **no** |

The asymmetry is deliberate:

- Advice, predictions, guarantees and emotional pressure are things the
  **article** does to its reader. If the article merely reports that someone
  else did them, the article is not doing them. Flagging the report would
  penalise exactly the behaviour a risk layer should encourage.
- `unverified_information` is *about* attribution. A claim carried on an
  unattributable source is the risk, whoever is nominally speaking, so it
  applies at any `statement_source`.

### 3.2 Worked examples

| Text | Source | Categories |
| --- | --- | --- |
| You should buy this stock today. | `author` | `investment_advice` |
| The analyst wrote that investors could buy the dip, but added that this is not advice. | `quoted` | **none** |
| Analysts say the stock will double. | `third_party` | **none** — a reported expectation |
| Insiders say the stock will double. | `unknown` | `unverified_information` only |
| A blogger claimed the stock cannot fail, which the article disputes. | `quoted` | **none** |
| The company does not recommend buying its own shares. | `author` | **none** — negated |

Note the fourth row. The prediction is attributed, so it is not
`market_prediction`; the source is unattributable, so it is
`unverified_information`. Under v1 this text was labelled both, which asked the
evaluator to detect a prediction the taxonomy says is not there.

## 4. Quotation

**The unit of annotation is the article's own voice.**

A claim inside quotation marks, a headline being discussed, a comment being
answered or a statement the article goes on to dispute is `quoted` and is
**not** the article's claim.

A quotation becomes the article's claim only when the article **endorses it in
its own voice**, in a separate sentence. Label the endorsement, not the
quotation.

| Text | Label |
| --- | --- |
| The report quotes an investor saying everyone is buying, then refutes it. | none |
| An old headline read guaranteed profit and was later corrected. | none |
| "Buy now," the newsletter said. | none |
| A rumour circulated, and the article repeats it as fact. | `unverified_information` — no longer merely quoted |

That last row is the boundary: **reproducing a claim while treating it as true
is endorsement**, and it is labelled as the article's own.

## 5. Conditional language

**A conditional statement asserts nothing unconditionally**, so it is
`hypothetical` and it suppresses `market_prediction`.

| Marker | Example |
| --- | --- |
| `if` | If the margin holds, the company could grow. |
| inverted `should` | Should the market decline, the position would lose value. |
| `were … to` | Were the deal to close, revenue might rise. |
| `assuming`, `provided that`, `depending on` | Depending on the assumptions used, the valuation ranges widely. |
| `unless`, `in the event` | In the event of a downgrade, the position would fall. |

**Conditionality does not suppress every category.** *"If you want returns, buy
this stock"* is still `investment_advice`: the condition frames the advice, it
does not remove the directive. The test is whether the **risk itself** is
conditional:

- conditional *outcome* → not a prediction
- conditional *directive* → still advice

| Text | Certainty | Categories |
| --- | --- | --- |
| If the margin holds, the company could grow, but that is uncertain. | `hypothetical` | none |
| If you want higher returns, buy this stock. | `hypothetical` | `investment_advice` |
| The stock may rise. | `possible` | none — hedged |
| The stock will rise. | `certain` | `market_prediction` |

## 6. Category precedence

v1 had no rule for a text that matches two categories. v2 states one.

### 6.1 Dramatic vocabulary is not manipulation

**`emotional_manipulation` requires pressure aimed at the reader**, not merely
dramatic words about the market.

| Signal | Counts as pressure? | Examples |
| --- | --- | --- |
| Imperative to act | **yes** | *get out now*, *act fast*, *赶紧上车* |
| Deadline or scarcity | **yes** | *before it is too late*, *last chance*, *错过就没有了* |
| Herd framing | **yes** | *everyone is buying*, *everybody is selling* |
| Belittling the reader | **yes** | *you would be crazy to skip this* |
| Dramatic market vocabulary | **no** | *crash*, *collapse*, *meltdown*, *崩盘* |

So:

| Text | Categories |
| --- | --- |
| The market will crash next month. | `market_prediction` — a claim, no pressure |
| The market is collapsing, get out now. | `market_prediction` + `emotional_manipulation` — a claim and a directive |
| Everyone is buying before it is too late. | `emotional_manipulation` — pressure, no claim |

This resolves the case v1 could not: *"The market will crash next month."* is a
prediction, and the word *crash* does not make it manipulation.

### 6.2 Ordering

When more than one category survives, report all of them. The ordering exists
only to make ties deterministic in reports:

```text
investment_advice > financial_guarantee > market_prediction
                  > unverified_information > emotional_manipulation
```

## 7. What the other four categories keep from v1

Unchanged in v2, with the author-voice rule of section 3.1 applied:

- **`investment_advice`** — an action-directive aimed at the reader *and* a
  financial object. Educational explanation and method guidance are negative.
- **`financial_guarantee`** — risk removed or an outcome made unconditional. A
  disclaimed guarantee and a conditional downside are negative.
- **`unverified_information`** — a claim carried on an uncheckable source.
  A named, checkable source is negative.
- **`emotional_manipulation`** — pressure substituting for reasoning, per
  section 6.1.

## 8. Conformance status

This guide is the **normative** document. `semantic-intent-v2` implements it
imperfectly, and the gaps are listed here rather than left for a reader to
discover. The evaluator was not adjusted to close them after the Phase 7.5
benchmark had been measured: editing patterns in response to known failing
examples is tuning, not validation.

Five published examples in this guide are not reproduced by the evaluator.

| # | Where | Guide says | Evaluator does | Cause |
| --- | --- | --- | --- | --- |
| 1 | §5 table, row 4 | `The stock will rise.` → `market_prediction` | no category | `market_prediction` still requires an explicit certainty marker, so implied certainty is missed |
| 2 | §5 table, row 1 | no category | `investment_advice` | `holds` is a v1 directive verb; "the margin holds" is not a directive |
| 3 | §5 marker table | `Should the market decline, …` → no category | `investment_advice` | `should` is a v1 directive verb; the sentence-initial conditional pattern does not withdraw it |
| 4 | §5 marker table | `Were the deal to close, …` → `hypothetical` | `possible` | the `were … to` pattern spans only a one-word subject |
| 5 | §6.2 | precedence orders the report | alphabetical order | `resolve_category_conflicts` returns precedence order but the caller converts it to a set, so precedence selects and orders nothing |

Two further limitations affect labels but are not contradictions of this guide:

- **The source lexicon is thin.** Eight of the ten attribution errors on
  `semantic/v3` are author-voice false negatives with one shared cause: phrases
  such as `I was told`, `a source close to`, `everybody says`, `leaked documents
  suggest`, `the company said`, `the report estimates`, `the exchange published`
  and the Chinese `网上传` have no marker, so the claim is read as the author's
  own voice. A ninth (`An unnamed banker says …`) is the same lexicon problem in
  the other direction. The precedence logic is not what fails; the vocabulary
  is. The tenth is the rejection rule of section 4 outranking a named source.
- **Reporting order is alphabetical, not by precedence**, so a report reader
  cannot infer which category was considered stronger. Section 6.2 describes an
  intent, not current behaviour.

Section 7's category definitions and section 3's author-voice rule *are*
implemented, and section 6.1's separation of dramatic vocabulary from
manipulation is the substantive Phase 7.5 gain: measured on `semantic/v3` it
removes a 10-point false-positive rate relative to v1 with no recall loss.

## 9. Changing this guide

The guide version is recorded in every benchmark manifest as part of
`annotation_protocol`. A change that alters any label's outcome requires a new
guide version and a new benchmark version labelled under it. Existing versions
are never relabelled in place.
