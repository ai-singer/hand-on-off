# Independent Annotation Protocol v2

Supersedes: `docs/INDEPENDENT_ANNOTATION_PROTOCOL.md` (v1, Phase 8.6)
Applies to: `capability_v3_1/v1` (Phase 8.8), `independent_v1/v1` (Phase 8.6)
Status: **no second annotator has annotated anything in this repository**

---

## 0. What this document is, and what it is not

It is a procedure. It defines how an annotation task is set up, how labels are
decided, how disagreements are resolved and how they are adjudicated. It is
written so that a second annotator could execute it without talking to the author.

It is **not** a record of agreement. No second annotator has been engaged. Every
label in `independent_v1`, `independent_v2` and `capability_v3_1` was written by
one annotator - the repository's author - and the v3.1 capability was written by
that same person as well.

That is the central problem this protocol exists to describe rather than to paper
over, and it is worth stating with the number that makes it concrete. On Phase
8.5's own benchmark, written by the pipeline's author, the architecture scored
speaker accuracy 96.8% and relation recall 100%. On `independent_v1`, whose cases
were new but whose *annotator* was the same person, the same architecture scored
74.0% and 67.5%. Changing the cases moved the numbers by 22 and 32 points;
changing the annotator has never been tried.

So: **no agreement figure, no kappa, and no inter-annotator statistic appears
anywhere in this repository, and none may be quoted from this document.** Section
7 says what would have to happen before one could be.

---

## 1. Roles

| Role | Who | May do | May not do |
| --- | --- | --- | --- |
| **Author** | wrote the capability | write the task, the guide, the sampling frame | annotate any case in the sample |
| **Annotator A** | one person | label independently | see Annotator B's labels |
| **Annotator B** | a different person | label independently | see Annotator A's labels |
| **Adjudicator** | a third person, or the author when no third exists | resolve a disagreement | annotate a case they will adjudicate |
| **Auditor** | anyone | run `risk_evaluation/v3_1/audit.py` | change a label to make the audit pass |

One person may hold two roles only where the table allows it, and never Annotator A
and Annotator B.

---

## 2. Annotation process

### 2.1 What the annotator receives

Exactly a file of records with two fields:

```json
{"id": "AN-0001", "text": "The share index will fall next quarter."}
```

`risk_evaluation/v3_1/benchmark/cases.py::blind_records()` produces this shape and
`risk_evaluation/v3_validation/cases.py::blind_records()` produces it for the 8.6
set. Nothing else is sent: no expected categories, no relation, no certainty, no
speaker, no stance, no note, no group, and no count of how many cases expect a
risk. A label that can be inferred from the payload is not an annotation.

The task must also be accompanied by:

- `docs/RISK_ANNOTATION_GUIDE_v2.md`, unmodified;
- this protocol;
- the label schema in section 3, with the allowed values listed.

Nothing else. In particular the annotator must not receive the pipeline's
predictions, the error analysis, or the previous annotator's output.

### 2.2 What the annotator returns

One record per case:

```json
{
  "id": "AN-0001",
  "speaker": "author",
  "stance": "endorsed",
  "certainty": "certain",
  "relation": "PREDICTION",
  "categories": ["market_prediction"],
  "basis": "guide 2",
  "reason": "the article asserts a future market outcome as a fact"
}
```

`basis` names the guide section the label comes from, and `reason` is at most two
sentences. A label without a `basis` is returned unopened: the guide is the
standard, and a label that cannot cite it is a preference.

### 2.3 Order of operations

The order is part of the method and not a convenience:

1. The author freezes the benchmark **before** any annotator sees it
   (`risk_evaluation/v3_1/freeze.py`), and records the hash.
2. Annotators A and B label the frozen file, independently, with no channel
   between them.
3. Only when both files are complete and hashed are they compared.
4. Disagreements go to adjudication per section 4.
5. The adjudicated set becomes the benchmark. The pre-adjudication labels are kept
   as an artifact; they are the evidence for any agreement claim, and deleting them
   would destroy it.
6. The benchmark is cleaned of contamination per section 6.

Freezing before annotation is what makes "the labels were not fitted to the result"
checkable: if the hash recorded at step 1 differs from the hash of the labelled
file, the file changed after annotation began.

### 2.4 Recording the annotator

Every label record carries `annotator` and `annotated_at`. An unlabelled record
with no name attached is not an annotation.

---

## 3. Label guideline

The normative document is `docs/RISK_ANNOTATION_GUIDE_v2.md`. This section restates
only what an annotator must have open while working, and every rule cites its
section so the two cannot drift.

### 3.1 Fields and allowed values

| Field | Values | Guide |
| --- | --- | --- |
| `speaker` | `author`, `third_party`, `unknown` | 3.1, 4 |
| `stance` | `endorsed`, `quoted`, `rejected`, `uncertain` | 4 |
| `certainty` | `certain`, `probable`, `possible`, `hypothetical` | 1.2 |
| `relation` | `GUARANTEE`, `RISK_REMOVED`, `PREDICTION`, `ADVICE`, or none | 7 |
| `categories` | any of the five, or none | 7 |

Precedence when several speakers apply: `quoted` → `unknown` → `third_party` →
`author` (guide 1.1).

### 3.2 The four rules that decide most cases

**Certainty is the weakest carrier, not the verb.** `The market will probably crash
next month.` contains `will`, which is `certain` alone, and `probably`, which is
`probable`. The statement is `probable`. A construction can carry strength with no
modal verb at all: `There is a chance the shares will recover.` is `possible`
(guide 1.2).

**Conditional beats modal.** `If rates fall, the stock may rise.` is
`hypothetical`, not `possible`: the possibility is contingent (guide 1.2, 5).

**`market_prediction` requires author and `certain`, both.** Everything else about a
future market outcome is not it - an attributed expectation is a report, a
conditional asserts nothing unconditionally, and a hedged author claim is a
scenario. This single rule settles the whole of Phase 8.8's group A (guide 2).

**Advice needs a directive aimed at the reader *and* a financial object.**
Educational explanation and method guidance are negative. `You should hold this
stock.` is advice; `Holding diversified assets reduces risk.` is not; neither is
`Investors should hold a diversified portfolio` (guide 7). A conditional *directive*
is still advice: `If you want higher returns, buy this stock.` (guide 5).

### 3.3 Where the annotator must not decide

Two questions are not the annotator's:

- **Whether the article endorses a quotation.** Label the speaker and stance from
  guide 4 and stop; the pipeline's decision policy decides what follows. Annotating
  a consequence rather than a reading is the most common way a label becomes
  unfalsifiable.
- **Whether the wording is one the pipeline handles.** If a sentence is advice, it
  is advice whether or not any frame can see it. A label that anticipated the
  implementation would make the implementation unfalsifiable.

### 3.4 What to do with a sentence the guide does not settle

Write `uncertain_label` in `reason`, give the best reading, and flag the record.
Flagged records are the input to section 5, not a failure. A guide that settled
every sentence would not need annotators.

---

## 4. Disagreement resolution and adjudication

### 4.1 What counts as a disagreement

A disagreement is any difference in any field between Annotator A and Annotator B
for the same `id`. Field-level, not record-level: two annotators who agree on the
category and differ on `certainty` have a disagreement about certainty, and
reporting it as agreement on the record would hide it.

### 4.2 Resolution before adjudication

The two annotators may resolve a disagreement themselves, under three conditions:

1. **Neither shows the other their other labels.** The discussion is about the
   sentence and the guide.
2. **The resolution cites a guide section.** "We agreed" is not a resolution.
3. **Both resolutions are recorded**: the original pair of labels, what was said,
   and the agreed label.

A disagreement resolved this way is still a disagreement for the purpose of any
agreement statistic. It is reported in both numbers: the raw rate and the
post-discussion rate.

### 4.3 Adjudication

A disagreement that survives resolution goes to an adjudicator, who:

1. reads the sentence, the guide, and both labels;
2. rules for one label, for the other, or for a third reading;
3. records which guide section the ruling rests on and why the other reading fails.

The adjudicator may not annotate new cases in the same sample, and may not consult
the pipeline.

### 4.4 What is recorded

| Artifact | Content | Kept |
| --- | --- | --- |
| `labels_a.json`, `labels_b.json` | raw, per annotator, hashed | permanently |
| `disagreements.json` | per field, both labels, resolution path | permanently |
| `adjudication.json` | the rulings and their guide citations | permanently |
| the benchmark | the adjudicated labels | permanently |

The pre-adjudication files are never deleted and never edited. An agreement figure
whose inputs have been overwritten is not evidence.

### 4.5 Reporting

Report, per field: the count of cases, the count of raw agreements, the raw rate,
the post-discussion rate, and the adjudicated rate. Report them separately per
group. Do not report a single pooled figure: Phase 8.8's group A is 30 `certainty`
decisions and group B is 30 `imperative` decisions, and one number over both would
be a number about neither.

If the sample is too small to support a statistic, say so and report counts. Thirty
cases per group supports counts and does not support a kappa.

---

## 5. Guide-gap escalation

When a disagreement turns on a rule the guide does not state:

1. The adjudicator writes the case up as a guide gap: the sentence, the two
   readings, and which rule would separate them.
2. The gap is recorded in the next phase's report, whether or not the guide is
   revised.
3. If the guide is revised, the revision is a new guide version and every earlier
   label that the revision changes is re-examined and reported, not silently
   updated.

Phase 8.7 found a live instance of this and left it open rather than legislating:
`A promoter claimed the fund cannot lose money.` (`IV-094`) is annotated
`unverified_information` with the reason "indefinite promoter is uncheckable", and
`The article quotes a promoter saying do not miss this opportunity.`
(Phase 8.3's control `83-CTL-04`) is annotated as no risk. The two cannot both be
honoured by a source lexicon. Resolving it needs a guide rule about definite versus
indefinite role nouns, and until there is one the disagreement is reported.

---

## 6. Contamination control

The audit is `risk_evaluation/v3_1/audit.py`. It is run on the frozen benchmark and
its report is published whether it passes or fails.

| Check | Blocks? |
| --- | --- |
| an authored case appearing in any earlier set | **yes** |
| a regression case whose text appears in no set its declared phase publishes | **yes** |
| a regression case overlapping the frozen sets | no - disclosed with source |
| a development-set overlap | **yes** |
| a case missing a label field or naming an unknown value | **yes** |

A FAIL is published as a FAIL. The contaminated case is **not** deleted and the
audit is **not** recomputed on a smaller set; Phase 8.6 did that only by publishing
the clean subset *alongside* the failing one.

Fixing an authored case that duplicates an earlier one is allowed **before
publication** and only with the finding recorded. Phase 8.8 did exactly that:
`MP-A2-08` was written as `Perhaps the fund will outperform its benchmark.`, which
is `IV-098` verbatim - a sentence the new capability had been developed against.
The audit flagged it as blocking, the case was rewritten, and the original text, the
replacement and the finding are kept in `PRE_PUBLICATION_FINDINGS` and in
`audit_report_v3_1.json`. Deleting the case instead would have removed the evidence
that the audit works.

---

## 7. What would have to happen before an agreement figure may be quoted

1. Two annotators who are not the author, and not each other.
2. The frozen benchmark, hashed before either sees it.
3. Both label sets hashed and retained.
4. Disagreements resolved and adjudicated under sections 4.2 to 4.4.
5. The per-field, per-group figures computed from the retained raw labels.
6. The pipeline's scores recomputed on the adjudicated labels **and** reported
   against the original labels, so the reader can see how much of the score is
   annotation.

Until all six have happened, the honest description of every label in this
repository is: **single-annotator engineering validation only**. That phrase is in
the artifacts themselves - `independent_v1`, `independent_v2` and
`capability_v3_1` each carry it in their provenance block - and it is there so that a
reader who never opens this document still sees it.

---

## 8. Conformance status

| Requirement | Status |
| --- | --- |
| procedure defined | **yes** |
| label guideline with guide citations | **yes** |
| disagreement resolution defined | **yes** |
| adjudication defined | **yes** |
| agreement figure fabricated | **no, and none is quoted** |
| two annotators engaged | **no** |
| protocol executed | **no** |

Phase 8.8 was not required to engage a second annotator. It was required not to
pretend it had, and it does not.
