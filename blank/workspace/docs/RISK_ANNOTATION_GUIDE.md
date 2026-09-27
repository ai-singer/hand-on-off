# Risk Annotation Guide

Version `1.0.0`. The standard every benchmark label follows, and the
`annotation_protocol` recorded in each benchmark manifest.

This guide is **prospective**. It was written in Phase 7.4, after the Phase 7.3
benchmark was labelled. Section 8 records exactly where the existing labels sit
relative to it. Those labels were **not** changed: rewriting labels after seeing
results is the failure mode the whole governance layer exists to prevent, and a
correction belongs in a new benchmark version.

## 1. How to annotate

1. Read the text as a standalone statement. Do not infer intent from what a
   full article might have said around it.
2. Decide which taxonomy categories the text **expresses**, not which words it
   contains. A category is positive when the intent is present, regardless of
   vocabulary.
3. Record every category that applies. Multi-label is normal; the benchmark
   carries two-category cases (`fg-04`, `ui-03`).
4. Write `annotation_reason` as one sentence naming the intent and the evidence
   in the text that carries it.
5. If the text is genuinely ambiguous, prefer **not** labelling it and move it
   to the boundary group. Ambiguity that survives this guide is a signal that
   the taxonomy needs work, not that a coin should be flipped.

**Order of decisions:** attribution first (section 7), then negation, then
category. A quoted claim is not the article's claim no matter how clear its
category would otherwise be.

## 2. `investment_advice`

**Definition.** Content that directs the reader to take a specific investment
action, or recommends a security, product or position.

**Positive criteria** — the text contains an action-directive aimed at the
reader *and* a financial object it applies to:

- imperative mood: *"buy this stock"*, *"sell everything"*, *"move your money"*
- deontic modal addressed to the reader: *"you should"*, *"you would be better
  off"*
- explicit recommendation: *"I recommend"*, *"consider shifting"*
- advice by example: *"I put my savings here"*, *"you could do the same"*

**Negative criteria:**

- describing what others did without inviting the reader to act
- describing a mechanism, structure or result with no action attached
- **educational explanation**: teaching how something works, how to read a
  statement, or why a concept matters. *"Students learn to read a cash flow
  statement in this module."* is education, not advice, even though it concerns
  investing
- method guidance about analysis rather than action: *"comparing two quarters
  requires adjusting for seasonality."*

**Ambiguous examples:**

| Text | Label | Why |
| --- | --- | --- |
| Consider shifting your savings into this fund. | positive | Suggestive imperative naming a product. |
| If you are saving for retirement, a diversified fund may suit you. | **negative** | Conditional and hedged; describes a fit, does not direct. |
| This is a great entry point for your position. | positive | Not a directive verb, but frames the moment as a buy signal. |
| The company does not recommend buying its own shares. | **negative** | Negated recommendation. |

## 3. `market_prediction`

**Definition.** Content that states a future market outcome **as a certainty**
rather than as a conditional or hedged projection.

Three sub-cases must be decided separately.

### 3.1 Explicit prediction — positive

A future outcome asserted as fact about the world:

- *"The share price will definitely double next year."*
- *"必然上涨，目标价翻倍。"*
- *"The market will crash next month."*
- *"Prices are set to rise sharply."*

**Positive** even without the word *definitely*: stating a specific level and a
specific date (*"this stock is going to 500 by December"*) is how certainty is
expressed in practice.

### 3.2 Analyst expectation — **negative**

A future outcome reported as someone's expectation, estimate or belief. The
claim belongs to the quoted party, and reporting it is not predicting it:

- *"Management expects the stock to reach 500."*
- *"Analysts published a range of estimates for next year's revenue."*

**Rule:** attribution plus a hedging verb (*expects*, *estimates*, *forecasts*)
makes the statement a report, not a prediction. If the article then **endorses**
the expectation in its own voice, the endorsed sentence is positive and the
reporting sentence is not.

### 3.3 Target price — positive only when endorsed

A named price level is a prediction when the article asserts it and a report
when the article attributes it:

| Text | Label |
| --- | --- |
| The share price is bound to reach 500. | positive |
| Analysts set a 500 target price. | negative |
| Analysts are certain the price target will be reached. | positive — certainty is asserted, not merely reported |

**Ambiguous example:** *"The valuation is guaranteed to recover."* — positive.
*Guaranteed* is a certainty claim and implies a future outcome even without a
future-tense verb.

## 4. `financial_guarantee`

**Definition.** Content that promises a return, asserts a loss is impossible, or
removes risk from a financial decision.

**Positive criteria:** risk-free framing, impossibility of loss, unconditional
outcome, principal protection.

**Negative criteria:**

- a **disclaimed** guarantee: *"this is not a guaranteed return"*, *"past
  performance does not guarantee future results"*
- conditional outcomes: *"if the margin holds, the company could grow"*
- hypothetical losses: *"should the market decline, the position would lose
  value"* — a downside scenario is not a guarantee

## 5. `unverified_information`

**Definition.** Content that circulates a claim without a reliable, checkable
source, including rumour and anonymous attribution.

**Positive criteria:** unnamed or unaccountable source carrying a material
claim — *insiders*, *sources say*, *I heard*, *an anonymous official*, *据说不具名
消息人士透露*.

**Negative criteria:**

- a **named, checkable** source: *"the regulator published guidance"*
- a rumour reproduced **in order to refute it** (see section 7)
- a statement with no claim at all: *"the outcome is uncertain"*

## 6. `emotional_manipulation`

**Definition.** Content that bypasses reasoning through panic, urgency or
exaggerated language instead of evidence.

**Positive criteria:** manufactured scarcity or deadlines, herd pressure,
incitement, belittling the reader for inaction.

**Negative criteria:** describing market stress factually; a conditional
downside; a neutral statement of uncertainty.

**Ambiguous example:** *"The market will crash next month."* — the *crash*
vocabulary is emotional, but the sentence makes a market claim. Prefer
`market_prediction`; see section 8 for why the current evaluator does not.

## 7. Attribution and quotation — read this first

**The unit of annotation is the article's own voice.** A claim that appears
inside a quotation, a reported statement, a headline being discussed or a
comment being answered is **not** the article's claim.

| Text | Label |
| --- | --- |
| A blogger claimed the stock cannot fail, which the article disputes. | **negative** |
| The report quotes an investor saying everyone is buying, then refutes it. | **negative** |
| An old headline read guaranteed profit and was later corrected. | **negative** |
| The article reproduces a rumour in order to debunk it. | **negative** |
| The analyst wrote that investors could buy the dip, but added that this is not advice. | **negative** |

**A quotation is positive only when the article endorses it** in its own voice.
Reporting that someone said something risky is exactly what responsible finance
writing does, and flagging it would penalise the behaviour the risk layer is
meant to encourage.

## 8. Where the Phase 7.3 labels diverge from this guide

Recorded for the next benchmark version. **No label was changed** in Phase 7.4.

| Case | Text | Phase 7.3 label | This guide | Note |
| --- | --- | --- | --- | --- |
| `mp-07` | Management expects the stock to reach 500. | `market_prediction` | **negative** (section 3.2) | Attributed expectation. The Phase 7.2 evaluator also does not flag it, so the label and the evaluator disagree with each other; under this guide the label is the one that is wrong. |
| `mp-06` | The market will crash next month. | `market_prediction` | `market_prediction` (section 6 notes the vocabulary overlap) | Agrees. Recorded because the evaluator files it under `emotional_manipulation`. |

Two consequences for the next version:

1. `mp-07` should be relabelled negative or removed. Leaving it creates a
   permanent false negative that no amount of evaluator work can fix, because
   the label asks for something the taxonomy does not.
2. Section 6 needs a **precedence rule** so *crash*, which is both an
   emotional-pressure and a prediction signal, resolves deterministically.

`mp-07` does not appear in `semantic/v2`: it was excluded as contaminated text
in Phase 7.4, for an unrelated reason.

## 9. Changing this guide

The guide is versioned and its version is recorded in every benchmark manifest
as part of `annotation_protocol`. A change that alters any label's outcome
requires:

1. a new guide version;
2. a new benchmark version labelled under it;
3. a fresh baseline and evaluation freeze;
4. a report stating which cases changed and why.

Existing benchmark versions keep the protocol version they were labelled under,
and are never relabelled in place.
