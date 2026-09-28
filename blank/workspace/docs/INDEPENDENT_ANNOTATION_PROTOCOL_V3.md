# Independent Annotation Protocol v3

Supersedes: `docs/INDEPENDENT_ANNOTATION_PROTOCOL_V2.md` (Phase 8.8)
Applies to: `risk/independent/v1` (Phase 8.9)
Status: **executed, with machine annotators; no human annotator has been engaged**

---

## 0. What was actually done, in one paragraph

Phase 8.9 required an independent dataset and independent annotation. Neither a
human dataset author nor a human annotator was available, so both roles were filled
by **machine agents other than the one that wrote the evaluator's capabilities**.
The text was written by six generative agents working from a sampling frame that
contains no evaluator vocabulary; the labels were assigned by two further agents,
blind to each other and to the evaluator, following this protocol. Cohen's kappa is
computed between them and reported in section 5. This is **not human inter-annotator
agreement** and may not be quoted as such. It measures how stable this protocol is
across two independent applications of it, which is a real and useful quantity and a
different one. Sections 6 and 7 say exactly what it does and does not support.

---

## 1. Roles

| Role | Who held it in Phase 8.9 | Saw | Did not see |
| --- | --- | --- | --- |
| **Evaluator author** | the agent that wrote Phase 8.7 and 8.8 | everything | — |
| **Sampling frame author** | the evaluator author | the guide, the taxonomy | — |
| **Dataset author** | 6 generative agents | the guide, a frame descriptor | the evaluator, its tests, its benchmarks, `risk_evaluation/**` |
| **Annotator A** | 1 agent, applied in batches | the guide, this protocol, blind records | Annotator B, the evaluator, the frame's label intent |
| **Annotator B** | 1 further agent, separate calls | the same | Annotator A, the evaluator, the frame's label intent |
| **Adjudicator** | the evaluator author | both label sets | — |

No agent held two of {dataset author, Annotator A, Annotator B}. The adjudicator is
the evaluator author, which is a **conflict of interest** and is why the pre-adjudication
label sets are kept and published in full: a reader who distrusts the adjudication can
recompute everything from them.

The exact prompt given to each role is published verbatim in
`benchmarks/risk/independent/v1/manifest.json` under `generation_prompts` and
`annotation_prompts`. That is what makes "they never saw the evaluator" a claim a
reader can check rather than one they must believe.

---

## 2. Annotation process

### 2.1 What each annotator receives

A file of records with two fields and nothing else:

```json
{"id": "IND-0001", "text": "The share index will fall next quarter."}
```

No group, no expected category, no sampling descriptor, no count of how many cases
expect a risk, no evaluator output. The batch a case appears in is shuffled so that
batch composition carries no signal either.

### 2.2 What each annotator returns

One record per case, with the six fields this protocol defines plus a reason:

```json
{
  "id": "IND-0001",
  "claim": "The share index will fall next quarter.",
  "speaker": "author",
  "stance": "endorsed",
  "intent": "PREDICTION",
  "certainty": "certain",
  "severity": "warning",
  "decision": ["market_prediction"],
  "reason": "guide 2: the article asserts a future market outcome as a fact"
}
```

A record missing a field, or naming a value outside the schema in section 3, is
returned unopened. A label that cannot cite a guide section is a preference.

### 2.3 Order of operations

```
1. freeze the evaluator                      evaluation_freeze_v3_2.json
2. write the sampling frame                  no evaluator vocabulary in it
3. generate text                             dataset authors, text only
4. freeze the dataset                        dataset_hash recorded, before labels
5. annotate, A and B, blind and independent  neither sees the other
6. compare, resolve, adjudicate              raw label sets retained
7. score the frozen evaluator                no modification permitted
8. classify every failure                    proposal, not patch
```

Step 1 before step 3, and step 4 before step 5, are what make the result
unfittable: the evaluator could not be adjusted to the text, and the labels could not
be adjusted to the evaluator's output, because neither existed when the other was
fixed. Step 7 is enforced by `freeze.guard()`, which re-hashes every frozen source
and raises if one changed.

---

## 3. Label guideline

Normative document: `docs/RISK_ANNOTATION_GUIDE_v2.md`. Every rule below cites its
section so the two cannot drift. Values are exactly the taxonomy's.

### 3.1 `claim`

The span of text that asserts something, quoted verbatim, or `none` when the text
asserts nothing a risk category could attach to.

A claim is present when a reader could disagree with it. `Past performance is not a
reliable indicator of future results.` contains no claim to disagree with. `Yields
may rise.` does. **Annotate the claim, not the sentence**: a 40-word paragraph with
one directive has one claim.

### 3.2 `speaker` (guide 1.1, 4)

| Value | When |
| --- | --- |
| `author` | the article's own voice, or nothing marks it as anyone else's |
| `third_party` | attributed to a named person, body or document |
| `unknown` | unattributable: *insiders*, *sources*, *they say*, *据说* |

Precedence when several apply: `quoted` → `unknown` → `third_party` → `author`. In
this schema `quoted` is a **stance**, not a speaker, so the precedence reduces to
`unknown` → `third_party` → `author`.

### 3.3 `stance` (guide 4)

| Value | When |
| --- | --- |
| `endorsed` | the article advances the claim as its own |
| `quoted` | inside quotation marks, a headline being discussed, or a comment being answered |
| `rejected` | the article argues against it |
| `uncertain` | reported without either commitment |

A quotation becomes the article's claim only when the article endorses it in its own
voice, in a separate sentence. Reproducing a claim while treating it as true **is**
endorsement (guide 4).

### 3.4 `intent` (guide 7)

Which relation, if any, the claim carries. Exactly one per claim, and `NONE` when
the claim carries none.

| Value | Meaning |
| --- | --- |
| `GUARANTEE` | an outcome is made unconditional, or `guaranteed` / `protected` / `assured` is used |
| `RISK_REMOVED` | risk is denied without the word guarantee: *risk-free*, *cannot lose*, *never falls* |
| `PREDICTION` | a future market outcome is asserted |
| `ADVICE` | an action-directive with a financial object |
| `NONE` | a claim with no such relation |

A **negated** relation is still reported as its relation. `Returns are not
guaranteed.` carries `GUARANTEE`, and the decision layer decides what follows; a
label that recorded `NONE` there would make the negation invisible.

### 3.5 `certainty` (guide 1.2)

| Value | Markers |
| --- | --- |
| `certain` | *will*, *is*, *必然*, *definitely*, *certainly*, *bound to* |
| `probable` | *probably*, *likely*, *expected to*, *should* |
| `possible` | *may*, *might*, *could*, *possibly*, *perhaps* |
| `hypothetical` | *if*, inverted *should*, *were … to*, *assuming*, *unless* |
| `n/a` | the claim carries no certainty, as a directive does not |

**The weakest carrier wins.** `The market will probably crash.` contains `will` and
`probably` and is `probable`. **Conditional beats modal**: a conditional statement is
`hypothetical` whatever else is present (guide 1.2, 5).

### 3.6 `severity`

The highest severity among the categories in `decision`, from the taxonomy.

| Value | Categories |
| --- | --- |
| `block` | `financial_guarantee`, `investment_advice` |
| `warning` | `market_prediction`, `unverified_information`, `emotional_manipulation` |
| `none` | no category |

### 3.7 `decision` (guide 2, 3.1, 5, 6, 7)

The final label: which of the five categories the **article** is doing to its reader.
Zero or more, and reporting all that survive is required rather than picking one.

| Category | Positive when | Negative when |
| --- | --- | --- |
| `investment_advice` | an action-directive aimed at the reader **and** a financial object | educational explanation; method guidance |
| `market_prediction` | speaker `author` **and** certainty `certain` | a reported expectation; a hedged author claim; a scenario |
| `financial_guarantee` | risk removed, or an outcome made unconditional | a disclaimed guarantee; a conditional downside |
| `unverified_information` | carried on an uncheckable source | a named, checkable source |
| `emotional_manipulation` | pressure substituting for reasoning | dramatic market vocabulary alone |

Three of these turn on one rule each and the rule is the whole of the field:

```
market_prediction   <=> speaker == author AND certainty == certain
unverified_information is negative for a named, checkable source
emotional_manipulation requires pressure aimed at the reader, not drama
```

Both halves of the advice definition are required. `Holding diversified assets
reduces risk.` is education, not advice; `You should hold this stock.` is advice.

### 3.8 What the annotator must not decide

- **Whether the evaluator can see the wording.** If a sentence is advice it is
  advice whether or not any rule detects it. A label that anticipated the
  implementation makes the implementation unfalsifiable.
- **Whether the article should have said it.** The guide records what the text does,
  not whether it is wise.

---

## 4. Agreement

### 4.1 What is computed

**Cohen's kappa**, per field, from Annotator A's and Annotator B's raw labels:

```
kappa = (p_o - p_e) / (1 - p_e)
```

where `p_o` is the observed agreement and `p_e` the agreement expected by chance
from each annotator's own marginals over the same cases.

| Field | Unit of agreement | Kappa |
| --- | --- | --- |
| `speaker` | one of 3 values | one kappa |
| `stance` | one of 4 values | one kappa |
| `intent` | one of 5 values | one kappa |
| `certainty` | one of 5 values | one kappa |
| `severity` | one of 3 values | one kappa |
| `decision` | a set of up to 5 categories | **one kappa per category**, on present/absent, plus exact-set agreement as a rate |

A single pooled kappa over all fields is **not** reported. Two annotators can agree
perfectly on `severity` because both said `none` while disagreeing on `decision`, and
a pooled figure would average that into a number about neither.

### 4.2 Interpretation bands

Reported alongside every kappa, and never instead of it:

| Kappa | Band |
| --- | --- |
| < 0.00 | worse than chance |
| 0.00 – 0.20 | slight |
| 0.21 – 0.40 | fair |
| 0.41 – 0.60 | moderate |
| 0.61 – 0.80 | substantial |
| 0.81 – 1.00 | almost perfect |

The bands are Landis and Koch's and are a convention, not a result. A field at 0.55
has moderate agreement and that is all the number says.

### 4.3 Raw and adjudicated agreement are both reported

Kappa is computed on the **raw** labels, before any discussion. Agreement after
adjudication is a different and higher number and would be a misleading one to
publish alone, because adjudication is where disagreement goes to disappear.

### 4.4 What a kappa from machine annotators means

Two agents applying this protocol are two applications of one set of instructions by
one class of model. Their agreement measures:

- whether the protocol is **unambiguous enough to be applied twice**;
- which fields are **under-specified**, since those are where they differ.

It does not measure human agreement, and a high value is not evidence that a human
would agree. A field where two machines disagree is a field where a human probably
would too — that direction of inference is useful. The other direction is not.

---

## 5. Disagreement resolution and adjudication

1. **Field-level.** Any difference in any field for the same `id` is a disagreement.
   Two annotators who agree on `decision` and differ on `certainty` have a
   disagreement about certainty.
2. **No discussion between A and B.** They may not resolve anything between
   themselves: they are separate calls with no channel, and giving them one would
   destroy the independence the kappa measures.
3. **Adjudication.** Every disagreement goes to the adjudicator, who rules for one
   label or a third reading and records the guide section the ruling rests on.
4. **Retention.** `labels_a.json`, `labels_b.json`, `disagreements.json` and
   `adjudication.json` are kept, hashed and published. The benchmark carries the
   adjudicated labels; the raw ones are never overwritten.
5. **Guide gaps.** A disagreement that turns on a rule the guide does not state is
   recorded as a **taxonomy ambiguity** and reported as a proposal. It is not
   resolved by editing the guide during the run.

---

## 6. Benchmark construction

The dataset is stratified by a sampling frame fixed before generation: five
generator-facing dimensions (source type, language, sentence form, topic, and the
group the case is intended to fall in). The frame is the evaluator author's, which is
an acknowledged limit: it decides *what kinds of sentence exist*, not *what they
mean*. The labels are the annotators'.

Where the frame's intent and the annotators' consensus disagree, that is reported as
a finding rather than corrected. Correcting it would hide the one signal that says
the frame was mis-specified.

Required distribution, and how it is met:

| Group | Target | Meaning |
| --- | --- | --- |
| risk positive | 150 | the adjudicated decision is non-empty |
| safe | 75 | the adjudicated decision is empty and the frame intended no risk |
| boundary | 75 | the frame intended a hard case: hedged, quoted, negated, conditional, or a category boundary |

A case whose adjudicated label does not match its intended group is **kept and
reported**, not replaced: replacing it would make the achieved distribution look like
the intended one.

---

## 7. What this protocol does not establish

| Not established | Why |
| --- | --- |
| human inter-annotator agreement | the annotators are machine agents |
| real-world accuracy | the dataset is 300 synthetic sentences, not a corpus |
| that the sampling frame is representative | it is one author's frame over one taxonomy |
| that a high kappa implies a correct label | agreement is not accuracy; both annotators can be wrong together |
| that the evaluator generalises to real financial text | nobody has measured it on real financial text |

The honest summary of every number in the Phase 8.9 report is: **capability measured
on machine-authored text with machine-assigned labels, against a frozen evaluator.**
