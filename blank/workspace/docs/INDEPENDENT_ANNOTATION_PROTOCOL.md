# Independent Annotation Protocol

Protocol version: 1.0.0
Applies to: `risk_evaluation/v3_validation/independent_v1.json`
Date: 2026-09-28

---

## 0. Single-annotator declaration

**This benchmark has a single annotator. It is single-annotator engineering
validation only.**

There is no second annotator and therefore no inter-annotator agreement figure.
No Cohen's kappa, no speaker agreement, no stance agreement and no category
agreement is reported, because computing one from a single annotator would be
arithmetic about nobody.

Consequences, stated plainly rather than left for a reader to infer:

- the labels are one person's reading of the guide;
- every limitation of that reading is a limitation of the benchmark;
- **no accuracy figure computed against this benchmark is evidence of
  real-world capability**;
- agreement between the pipeline and these labels is agreement with one
  annotator, not correctness.

The protocol below exists so the reading is inspectable and reproducible, not so
that it can be mistaken for an independent one. Section 6 records what a second
annotator would have to do.

---

## 1. Label definitions

Each case carries three label layers, and they are separate questions.

| Layer | Values | Question |
| --- | --- | --- |
| speaker | `author`, `third_party`, `unknown` | who is speaking the claim? |
| stance | `endorsed`, `quoted`, `rejected`, `uncertain` | what does the article do with it? |
| relation | `GUARANTEE`, `RISK_REMOVED`, `PREDICTION`, `ADVICE`, or empty | what relation does the claim carry? |
| categories | zero or more of the five | what must be reported? |

A case also carries `expects_risk`, derived from `categories`, and an
`annotation_reason` naming the guide section the label follows.

---

## 2. Speaker standard

The speaker is the party whose claim it is.

| Value | Rule |
| --- | --- |
| `author` | the article asserts it in its own voice, **or** carries no attribution marker at all |
| `third_party` | a party other than the author is named or invoked as the speaker, including unnamed collectives (`Analysts`, `Insiders`, `Traders`, `Sources`) |
| `unknown` | a reporting frame is present but no source is identifiable |

An unmarked sentence is `author` by the taxonomy's convention that unmarked text
is the article's voice. `Word on the street` and `Reportedly` are `third_party`:
they invoke a source even though it cannot be named.

`third_party` says nothing about whether the source can be checked. That is a
separate question, and section 4 is where it is decided.

---

## 3. Stance standard

The stance is what the article does with the claim.

| Value | Rule |
| --- | --- |
| `quoted` | the article reports it and stands apart from it |
| `endorsed` | the article takes it up as its own |
| `rejected` | the article argues against it |
| `uncertain` | the article neither clearly reports nor clearly takes it up |

Precedence is `rejected` > `endorsed` > `quoted` > `uncertain`.

A sentence whose own text performs a rejection (`We reject the suggestion…`) is
annotated `rejected`, and the claim it targets is annotated `rejected` too. They
differ in `speaker`, not in `stance`.

Where a rejection in a later sentence turns on an earlier claim
(`Analysts expect growth. However, we disagree.`), the earlier claim is
`rejected`: that is the stance the article takes towards it, and it is the
annotated stance even though the words of rejection are elsewhere.

---

## 4. Risk category standard

A category is reported when the guide requires it, and the author-voice rule of
guide v2 §3.1 applies: `investment_advice`, `market_prediction`,
`financial_guarantee` and `emotional_manipulation` require the author's voice.
`unverified_information` is attribution-agnostic.

| Situation | Categories |
| --- | --- |
| the author's own directive, prediction, guarantee or pressure | that category |
| a claim reported from **an uncheckable** source | `unverified_information` |
| a claim reported from a **named, checkable** source | none |
| a claim the article rejects | none, except `unverified_information` if the source is uncheckable |
| explanation, definition, method guidance | none |
| a conditional, negated or hedged claim | none |

The checkable/uncheckable line is the one guide v2 §7 draws, and it decides most
of the third-party group. An unnamed collective is uncheckable. A definite party
or document - `the company`, `the report`, `the newsletter`, `Management`, `the
board`, `the regulator`, `the prospectus` - is checkable, and a checkable source
is **negative** for `unverified_information`.

---

## 5. Boundary case rules

Guards against the two ways a boundary case is mislabelled.

**Negation.** A negated claim asserts nothing, so it reports nothing. Where a
case still names a relation (`Returns are not guaranteed.` expects `GUARANTEE`),
the relation records the *form present in the text* and the empty category
records the *judgement*. The relation field is not a risk claim.

**Conditional and hedged.** An outcome that depends on a stated condition, or
that is modalised (`may`, `might`, `could`), is not asserted and reports nothing.
`The return is guaranteed only if the plan is held for five years.` reports
nothing despite containing the word.

**Reported.** A guarantee attributed to a checkable source reports nothing; the
same guarantee attributed to an uncheckable source reports
`unverified_information`.

**Disclaimers.** `Past performance is no guide to future returns.` is a
disclaimer, not a risk, and reports nothing.

---

## 6. What a second annotator would need to do

To turn this into a two-annotator benchmark:

1. Annotate the same 100 texts **independently**, from this protocol and guide
   v2, without seeing these labels or any pipeline output.
2. Report `speaker`, `stance`, `relation` and `category` agreement separately,
   with Cohen's kappa for each, because chance agreement differs between a
   three-value field and a five-value multi-label one.
3. Adjudicate disagreements **before** any evaluation is run, and record the
   adjudication rule.
4. Keep this version as `independent_v1` and publish the adjudicated set as a new
   version. Do not edit v1 in place: a contaminated or disputed benchmark is
   evidence, and editing it destroys the evidence.
5. Re-run the freeze and the evaluation against the adjudicated version, and
   report both sets of figures.

Until that happens, every number in the Phase 8.6 report is bounded by section 0.

---

## 7. What this protocol does not do

- It does not make the benchmark representative of real financial material. It
  is synthetic, written in one sitting, by the author of the pipeline it tests.
- It does not resolve the disputes it acknowledges. Two cases are flagged as
  arguable in the error analysis and are left in place.
- It does not certify the labels. It states the rules they follow so a reader
  can check them.
