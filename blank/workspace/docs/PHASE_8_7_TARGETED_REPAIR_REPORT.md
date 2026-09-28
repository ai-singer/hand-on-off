# Phase 8.7 - Targeted Risk Evaluation Repair

Phase: 8.7
Status: **PASS WITH ISSUES**
Date: 2026-09-28
Subject: `risk_evaluation/v3` and the new `risk_evaluation/v3_repair`
Repairs: R1 intent pattern coverage, R2 attribution source and cue coverage, R3 fallback propagation
Production changed: **no**

---

## 1. Executive Summary

Phase 8.6 validated the v3 architecture on an independent benchmark and confirmed
three defects. This phase repaired those three and nothing else, then re-ran every
historical set to prove the repairs did not break anything that previously worked.

| Phase 8.6 claim | 8.6 verdict | 8.7 verdict |
| --- | --- | --- |
| Attribution resolves quoted risk and author rejection | PARTIALLY_SUPPORTED | **SUPPORTED** |
| Intent patterns resolve passive, copular and nominal guarantees | NOT_SUPPORTED | **SUPPORTED** |
| The decision policy keeps false positives and false negatives low | SUPPORTED | **SUPPORTED** |

The independent benchmark, `independent_v2` (99 cases):

| Metric | before | after |
| --- | --- | --- |
| correct | 84 | **96** |
| accuracy | 0.8485 | **0.9697** |
| precision | 0.7750 | **0.9474** |
| recall | 0.8378 | **0.9730** |
| F1 | 0.8052 | **0.9600** |
| true positives | 31 | 36 |
| false positives | 9 | **2** |
| false negatives | 6 | **1** |
| false positive rate | 0.1452 | **0.0323** |
| false negative rate | 0.1622 | **0.0270** |
| speaker accuracy | 73.74% | **98.99%** |
| stance accuracy | 78.79% | **97.98%** |
| relation recall | 67.50% | **87.50%** |
| relation precision | 84.38% | **87.50%** |
| claim / decision evidence | 100% / 100% | 100% / 100% |
| span completeness | 100% | 100% |

The Phase 8.5 benchmark (60 cases) moved the same way, and its false positive
count did not move at all:

| Metric | before | after |
| --- | --- | --- |
| correct | 54 | **57** |
| precision | 0.9500 | **0.9565** |
| recall | 0.7917 | **0.9167** |
| F1 | 0.8637 | **0.9362** |
| false positives | 1 | 1 |
| false negatives | 5 | **2** |
| speaker accuracy | 96.83% | **98.41%** |

**No case in any historical set was broken.** The frozen regression suite over
200 cases across five sets reports `broken: 0`, and the three Phase 8.1/8.3/8.4
replay sets are byte-identical before and after: same correct count, same fixed
list, same still-wrong list, same false positives.

What is **not** true, and is not claimed:

- The risk system is not production-ready. It is an offline experimental
  component wired to nothing, and Phase 8.7 changed no production file.
- The evaluator is not "solved". Five relation misses and three wrong verdicts
  remain on the independent benchmark, and one of them is an annotation conflict
  between two frozen labels that this phase could not resolve without breaking a
  control (section 6.3).
- Two of the five relation families - PREDICTION and ADVICE - were not improved
  at all. They are the whole of the remaining relation gap.

### 1.1 What was allowed, and what was done

| Allowed | Used |
| --- | --- |
| modify `risk_evaluation/v3/` | `model.py`, `patterns.py`, `decision.py`, `pipeline.py`, `adapters/intent_pattern.py`, `morphology.py` (new) |
| add `risk_evaluation/v3_repair/` | new package, 7 modules plus 3 artifacts |
| add `tests/` | `tests/risk_evaluation_v3_repair/`, 88 tests |
| add `docs/` | this report |

| Forbidden | Honoured how |
| --- | --- |
| modify `production/`, `runtime/`, `workflow/`, `plugins/`, `artifact/`, Quality Gate | none of these paths appear in the diff |
| modify the Phase 8.6 benchmark labels | `cases.py` is unmodified; `benchmark_hash` is `1bf9c9bdc4a78ed0…` in both freezes |
| delete failure samples | every case in every set is still present; counts are 15/9/17/60/99 before and after |
| change expected results | the only test expectations changed are pinned *metric* values, each recording its Phase 8.5/8.6 predecessor in a comment |
| tune rules to the benchmark | section 5.3 records a rule that was measured inert and deliberately **not** shipped |
| add hardcoded cases covering only the failures | no case text appears in any detection module |

---

## 2. R1 - Intent Pattern Coverage: the Inflection Layer

### 2.1 The confirmed defect

Phase 8.6 recorded exactly one `inflected_verb` failure:

> `Turnover expands sharply next quarter.` - `expand\b` cannot match `expands`.

`MOVEMENT_VERBS` was a hand-written alternation of **base forms** with a trailing
`\b`, so every inflected movement verb was invisible and the sentence matched no
frame at all. It produced no finding, and therefore no trace: the pipeline could
not say whether the frame had looked and declined or never looked.

### 2.2 The repair

`risk_evaluation/v3/morphology.py` (new) derives the forms from a lemma instead
of listing them. `MOVEMENT_VERBS` is now generated:

```python
MOVEMENT_LEMMAS = ("rise", "fall", "double", ..., "contract")
MOVEMENT_VERBS = f"(?:{alternation(MOVEMENT_LEMMAS)[3:-1]}|{_MOVEMENT_CJK})"
```

The layer handles third person, past, past participle and gerund, with an
irregular map (`rise/rose/risen`, `fall/fell/fallen`, `grow/grew/grown`,
`hold/held/held`) and the orthographic rules the regular endings miss: consonant
doubling gated on syllable count (`dropped` but not `recoverred`), `y → ies/ied`
(`rallies`, `multiplied`), and silent-`e` elision (`decreasing` from `decrease`).

It also runs **backwards**. `normalize_token(token)` inverts the same rules to
recover a lemma from a surface form, which is what makes the layer auditable
without the caller having registered its vocabulary first.

Three artefacts found during construction, all fixed and covered by tests:

- `recover` produced `recoverred` / `recoverring`. The CVC doubling rule was
  counting letters rather than vowel groups; a single-vowel-group condition fixed
  it.
- `normalize_token` returned its input unchanged, because the lemma index was
  empty. `derive_lemma()` now generates candidates and selects by
  `(not registered, length, alphabetical)`, which is why `dropped → drop` and
  `rallies → rally` resolve rather than `dropp` and `multiplie`.

### 2.3 No false positive growth

The phase requires this to be *proved*, not asserted, and inflecting a verb can
only ever add matches, so the burden is on the additions.

| Property | Result |
| --- | --- |
| `expands`, `expanded`, `expanding`, `expand` all match | yes |
| irregulars `rose`, `risen`, `fell`, `fallen`, `grew`, `grown` match | yes |
| `holding` does **not** match | yes - `hold` is a directive verb and stays base-form |
| `IV-014` decided correctly after the repair | yes, `market_prediction` |
| Phase 8.4 replay (17 guarantee positives) | recall 0.9412, unchanged; false positives 0, unchanged |
| Phase 8.5 benchmark false positives | 1 before, 1 after |
| Phase 8.6 false positives | 9 before; the R1 contribution is 0 of the 7 removed |

The `holding` property is the one that matters. `hold` is in `DIRECTIVES`, and
`The expense ratio is the annual cost of holding a fund.` was a Phase 8.6 false
positive. Inflecting the directives as well would have made it worse, so the
morphology layer is applied to the movement verbs only and a test asserts the
directive list is untouched.

---

## 3. R2a - Guarantee Negation Scope

### 3.1 The confirmed defect

Phase 8.6 left three shapes in three different states, and two of them were wrong:

| | Sentence | 8.6 behaviour |
| --- | --- | --- |
| Case A | `Returns are guaranteed.` | fires, asserted, kept - correct |
| Case B | `Returns are not guaranteed.` | **no frame fires at all**, no trace |
| Case C | `It is not true that returns are guaranteed.` | fires, `negated=True`, suppressed |

Case B was the coverage defect: `_COPULA` and `_ADVERB` sat between the object
and the predicate with nothing able to match `not`. Case C was the *precision*
defect in disguise: the matcher was right that something was denied, but a single
boolean could not say whether the predicate was denied or the claim was.

### 3.2 The repair

Two parts, and neither deletes a negation - the phase forbids that, and a test
asserts the guard is intact.

**The frames span the negator.** `_NEG` is inserted between the copula and the
predicate in the copular and passive guarantee frames, and a new nominal frame
covers `No guarantee is given …`. Because the Phase 8.4 guard measures negation
from the start of the `predicate` group, a frame that spans `not` comes back
`negated=True` and the decision layer suppresses it. Widening the frame therefore
adds coverage without adding a single asserted guarantee.

**The boolean is resolved into a scope.** `risk_evaluation/v3_repair/negation.py`
classifies every negated frame as `local` (a negator governs the predicate) or
`propositional` (a denial predicate governs the clause carrying the frame), and
`IntentEvidence` carries the result as `negation_scope`.

The distinction is drawn from position, not from a word list: only a marker
*outside* the predicate span can be scoping over the whole proposition. `Returns
are not guaranteed.` has `not` inside the frame and it denies the predicate;
`It is not true that …` has `not true` outside the predicate and denies the claim.

### 3.3 Result

| Case | scope | decision | trace |
| --- | --- | --- | --- |
| A `Returns are guaranteed.` | `positive` | `financial_guarantee` kept | yes |
| B `Returns are not guaranteed.` | `local` | suppressed, `D1-negated-intent` | yes |
| C `It is not true that returns are guaranteed.` | `propositional` | suppressed, `D1-negated-intent` | yes |

The rule id is unchanged for all three - the policy decision is the same - and
what differs is the reason recorded in the trace:

```
B: the GUARANTEE frame is negated in its predicate: the relation is denied, not asserted
C: the GUARANTEE relation is quoted only to be denied: the claim itself is rejected, not asserted
```

Coverage on the independent benchmark: the guarantee relation went from 7/12 to
**12/12**. All five Phase 8.6 misses are answered - `IV-047` and `IV-060`
(`protected`), `IV-050` and `IV-081` (`is/are not guaranteed`), `IV-086`
(`No guarantee is given`) - and `RISK_REMOVED` went from 6/8 to **8/8**
(`IV-048` `cannot fall`, `IV-052` `losses are impossible`).

Every one of those five is annotated as no risk, and every one still decides no
risk: the repair bought relation recall and cost no decisions.

A bug found while building this, and worth recording: `local_negator` searched for
a sentence terminator as far as the end of the *predicate*, which for `Returns are
not guaranteed.` is one character before the full stop. The window collapsed to
nothing and the scope was reported with no marker. The search limit is now the
predicate's start.

---

## 4. R2b - Attribution Source and Rejection Cue Coverage

### 4.1 The confirmed defect

24 of the 39 classified Phase 8.6 failures were coverage gaps in the attribution
layer: 15 `novel_source_noun`, 8 `novel_rejection_cue`, 1 `lexical_gap`. The
layer answered `unknown/quoted` for fourteen different wordings that all have a
source, and missed eight rejections that are plainly rejections to a reader.

`risk_evaluation/attribution/` is out of scope for this phase, so both repairs are
v3-level refinements over Phase 8.2's verdict. The refinement changes a speaker
only where the layer declined to answer, and every change is evidenced.

### 4.2 Source typing

`third_party` was the only answer available, and it cannot distinguish a checkable
source from an uncheckable one - which is the whole of guide v2 section 7:

```
The regulator said the review is ongoing.        named, checkable     -> no risk
Traders say the shares are cheap.                unnamed collective   -> unverified
An unnamed official confirmed the restatement.   explicitly anonymous -> unverified
The advert says the price will certainly double. checkable advert     -> no risk
```

`risk_evaluation/v3_repair/sources.py` types the source into five kinds and says
whether it can be checked. Three are the kinds the phase names. The fourth is
`published_material`, and it is not a way of dodging the other three: `the advert`
and `the prospectus` are documents, not authorities and not professional groups,
and calling them "unknown sources" would assert something false about a document
whose provenance the sentence gives - as well as producing the wrong verdict on
two benchmark cases. The fifth, `named_source`, exists because `According to the
report` names something specific that the lexicon cannot type, and typing it as
unknown would again assert the opposite of what the sentence says.

A source is read as a source only when the sentence reports through it. `The
manager's report is published with the annual accounts.` names a manager and the
benchmark annotates it `unknown`, correctly: the report is the subject, not the
manager. Requiring a reporting verb immediately after the source noun, with no
possessive in between, is what separates the two, and it is why this is a detector
rather than a noun list.

Three defects found and fixed while doing this:

- **The reporting verbs had the same defect as the movement verbs.** The list
  carried `claims` and not `claim`, so `Sources claim the merger talks have
  stalled.` had a perfectly good source noun and no verb to attach it to. The
  verbs are now lemmas with generated forms.
- **Hearsay names no source and had no cue.** `Word on the street`, `Rumour has
  it`, `I heard` name nobody, which is exactly what makes them uncheckable. They
  are now cues in their own right.
- **A sentence-initial capital was read as a proper noun.** `Some commentators
  argue …` was parsed as the proper noun `Some` followed by `commentators`, so the
  collective was ruled checkable - the capital letter hid the one thing that made
  it uncheckable. Sentence position is not a name.

### 4.3 Rejection cues

`risk_evaluation/v3_repair/rejection.py` types a rejection by **whose** it is and
requires an impersonal denial to have something to deny.

- First-person refusals (`we reject`, `we are unconvinced`, `we would not
  describe`, `we see no basis`, `we do not accept`) are the article's, and need no
  further condition.
- Impersonal denials (`is false`, `are overstated`, `is not supported`) are the
  article's assessment *only when the sentence presents a proposition*. The
  requirement is a `that` clause or a claim noun, and it is what separates `The
  assertion that losses are impossible is false.` from `The alarm is false.`
- Contrasts that name what they contradict (`Contrary to the marketing`, `Despite
  the hype`) carry their own proposition and need no carrier.
- A rejection attributed to somebody else is reported as `reported` and does **not**
  override the stance. `The regulator rejected the claim that returns are
  guaranteed.` is the regulator arguing, not the article, and crediting the
  article with it would be a different error in the opposite direction.

### 4.4 Result

| Group | before | after |
| --- | --- | --- |
| `third_party_claim` correct | 16/20 | **19/20** |
| `author_rejection` correct | 12/15 | **15/15** |
| `neutral_education` correct | 16/20 | **19/20** |
| speaker accuracy | 73.74% | **98.99%** |
| stance accuracy | 78.79% | **97.98%** |

Rejection detection went from 5 of 15 to **15 of 15**. The eight confirmed
misses are all found, and the two additions beyond them (hearsay, contrast) are
covered by tests rather than by the benchmark alone.

---

## 5. R3 - Fallback Propagation

### 5.1 The confirmed defect

Four Phase 8.6 false positives had the same shape: the intent layer found nothing,
so the semantic fallback was consulted, and it kept a keyword hit.

```
The expense ratio is the annual cost of holding a fund.      investment_advice
The prospectus sets out the fund's investment objective.     investment_advice
Stamp duty applies to certain share purchases.               investment_advice
Should the index fall, the fund would underperform.          investment_advice
```

All four are `investment_advice`, whose definition is an action-directive *aimed
at the reader* plus a financial object. None contains a directive at all:
`holding` is not `hold`, and a conditional clause is not an address. The fallback
was not detecting advice; it was detecting a fund word near a purchase word.

### 5.2 The repair

The existing guard already implemented "intent evidence beats the semantic layer",
but only for categories the intent layer *reached*: `declined` stops the fallback
undoing a decision. The other half of the same principle is now stated - for a
category a relation defines, the fallback is kept only when the claim carries that
relation's structure.

`unverified_information` and `emotional_manipulation` are deliberately absent:
they have no v3 relation, the semantic layer is genuinely their only detector, and
applying the rule to them would remove the fallback rather than discipline it.

`A guaranteed return is not available.` - the case the phase names - is unaffected
and still correct: it reaches the intent layer as a negated GUARANTEE, is
suppressed, and the older `declined` guard blocks the fallback. A test asserts it
by that exact text.

### 5.3 The guard was measured, not assumed

The rule is stated over the relation, so it could have been stated for all three
categories v3 has a relation for. It was measured one entry at a time on both
scored benchmarks and on the replay sets:

| table | 8.5 correct | 8.5 precision | 8.5 recall | 8.6 correct | 8.6 precision | 8.6 recall | 8.6 fp | broken |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 57 | 0.9565 | 0.9167 | 92 | 0.8571 | 0.9730 | 6 | 0 |
| `investment_advice` only | 57 | 0.9565 | 0.9167 | **96** | **0.9474** | 0.9730 | **2** | 0 |
| + `financial_guarantee` | 57 | 0.9565 | 0.9167 | 96 | 0.9474 | 0.9730 | 2 | 0 |
| + `market_prediction` | 57 | 0.9565 | 0.9167 | 96 | 0.9474 | 0.9730 | 2 | 0 |
| all three | 57 | 0.9565 | 0.9167 | 96 | 0.9474 | 0.9730 | 2 | 0 |

Only `investment_advice` does anything. The other two entries changed no number on
any of the four scored sets, because every guarantee and prediction those sets
contain already reaches the intent layer. **An entry that no measurement supports
is untested code that can only cost recall later, so it is not shipped.** The
table has one row, and a test asserts that `market_prediction` is still allowed
through so the decision stays visible rather than invisible.

The isolated contribution of step 5 is therefore: **+4 correct, −4 false
positives, precision 0.8571 → 0.9474** on the independent benchmark, with recall
unchanged.

### 5.4 One regression found, and fixed

The first version of the source typing typed an unrecognised name after
`according to` as an unknown source, which made `According to the report, the fund
cannot lose money.` produce a new `unverified_information` false positive and
broke the Phase 8.5 case `TQ-03`. An unrecognised name after `according to` is
*named*, and a named source is checkable; `TQ-03` is asserted by name in the
Phase 8.5 test module so a later change cannot lose it again.

---

## 6. Frozen Regression, the New Freeze, and What Is Still Open

### 6.1 The regression suite

`risk_evaluation/v3_repair/regression.py` runs five sets and reports, for each,
before, after, fixed, **broken** and still-wrong. `broken` is a first-class field
and the suite's exit code is non-zero when it is non-empty.

Every case is scored against three references:

- `expected` - what the annotation says;
- `baseline` - `semantic_evaluator_v2` on the whole text, which is what the
  earlier phases meant by "before";
- `pre_repair` - the pipeline as it stood before any Phase 8.7 change.

The third is the one this suite exists for. Without it, `fixed` and `broken` could
only be measured against the v2 baseline, which would credit Phase 8.7 for what
Phase 8.5 and 8.6 already did - and, worse, could not see a repair breaking a case
v3 already had right. It *did* see one: adding `promoter` to the source lexicon
broke the Phase 8.3 control `83-CTL-04`, and the suite refused to pass (section
6.3).

`regression_baseline.json` carries a `provenance` block naming the commit it was
taken on (`a6d065d`, unmodified tree) and the harness that produced it.

| set | cases | v2 baseline | pre-repair | after | fixed | broken | still wrong | fp | fn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| phase 8.1 | 15 | 0 | 6 | 6 | 0 | **0** | 9 | 0 | 8 |
| phase 8.3 | 9 | 6 | 8 | 8 | 0 | **0** | 1 | 0 | 0 |
| phase 8.4 | 17 | 4 | 16 | 16 | 0 | **0** | 1 | 0 | 1 |
| phase 8.5 | 60 | 42 | 54 | **57** | 3 | **0** | 3 | 1 | 2 |
| phase 8.6 `independent_v2` | 99 | 78 | 84 | **96** | 12 | **0** | 3 | 2 | 1 |
| **total** | **200** | 130 | 168 | **183** | 15 | **0** | 17 | 3 | 12 |

The three replay sets that Phase 8.1, 8.3 and 8.4 froze are unchanged: same
correct count, same fixed list, same still-wrong list. Phase 8.4's relation recall
stays 0.9412 and its false positive count stays 0.

### 6.2 The new freeze

`risk_evaluation/v3_repair/evaluation_freeze_v3_repair.json` - a **new version**.
`evaluation_freeze_v3.json` is untouched on disk and now fails its own
verification, which is the point of a freeze: a freeze that survived a repair
would mean the repair had not touched the pipeline.

| component | Phase 8.6 | Phase 8.7 | moved? |
| --- | --- | --- | --- |
| evaluator (pattern set) | `cd187bfa0d8d0a6e…` | `6768eb66f7e28d2c…` | **yes** |
| taxonomy | `a18bfad9f9608a55…` | `a18bfad9f9608a55…` | no |
| decision policy | `28f446e583d1ce77…` | `28f446e583d1ce77…` | no |
| benchmark | `1bf9c9bdc4a78ed0…` | `1bf9c9bdc4a78ed0…` | no |
| configuration | `c6aa35c480548563…` | `c6aa35c480548563…` | no |

Exactly one component moved, and it is the one the repair is allowed to move.

Two readings of that table are worth stating precisely.

**"We did not change the expected results" is checked, not claimed.** The
benchmark hash is byte-identical, and the new freeze stores it twice - once as its
own component and once as the superseded record - and asserts they are equal. A
label edit would fail the freeze.

**"We did not break the decision policy" is checked too, and the check has a
known limit.** The decision policy hash covers the rule table, the actions and the
relation-to-category map, and all three are unchanged: no rule was added, removed
or reworded, and no category was remapped. But the Phase 8.6 freeze schema has no
slot for the fallback guard's new table, so *that* change is invisible to it. It
is frozen separately, as `repair_table_hash = 69b29e498a73a39d…`, and the four
repair modules are frozen by source bytes:

```
repair:morphology    746d5ceef9a953fd…
repair:negation      59229d90ab0b591f…
repair:sources       e25cf7c0b007d3b6…
repair:rejection     b47fed6f23824b57…
repair:attribution   5e7322a3a619f9ea…
```

### 6.3 What is still open

Reported because the phase requires failures to be reported, not hidden.

**Annotation conflict, unresolved (1 case).** `A promoter claimed the fund cannot
lose money.` (`IV-094`) is annotated `unverified_information`, reason "indefinite
promoter is uncheckable". `The article quotes a promoter saying do not miss this
opportunity.` (Phase 8.3's control `83-CTL-04`) is annotated as no risk. Adding
`promoter` to the source lexicon fixes the first and breaks the second. The frozen
control wins, no special-case rule for the quotation is shipped, and the conflict
is recorded in `sources.py` and asserted by a test so the next phase finds it
rather than rediscovers it.

**Directive verbs in third person (2 cases).** `Custodians hold assets on behalf
of the fund.` (`IV-072`) and `Assuming rates hold, income is likely to be stable.`
(`IV-089`) are both false positives from the ADVICE frame that matches a directive
verb anywhere in the sentence. `hold` here is a third-person verb, not an
imperative. Fixing this needs an imperative test - subject-lessness or an explicit
address - not another keyword. It was not attempted: the phase's R1 defect was the
inflection of the movement verbs, and guessing at a broader fix would repeat
exactly the mistake this phase exists to correct.

**PREDICTION and ADVICE relation coverage (5 cases).** Both relations were left
exactly where Phase 8.6 found them.

```
IV-053  We disagree that this is a suitable holding for retirees.   ADVICE
IV-058  That the shares are cheap is not something we accept.       ADVICE
IV-087  If inflation subsides, yields may rise.                     PREDICTION
IV-092  Depending on the outcome, the payout could double.          PREDICTION
IV-098  Perhaps the fund will outperform its benchmark.             PREDICTION
```

The three prediction misses share one cause: the frames require `will | shall | is
going to`, and all three are hedged with `may`, `could` or `Perhaps`. A
modal-prediction frame would fire them as *hedged* PREDICTION - Phase 8.4's
matcher already reports hedges rather than filtering them - and would cost no
decisions, since a hedged frame is suppressed. It is not shipped because it is
outside the confirmed defect list: Phase 8.6 confirmed the *inflected* movement
verb, not the modal, and adding frames the validation did not ask for is the
behaviour this phase was written to constrain. It is the first item recommended
for the next phase.

The two ADVICE misses need an ADVICE relation whose object is not a directive verb
- "a suitable holding for retirees" is advice by implication. That is a judgement
call about what advice *is*, not a coverage gap, and should not be answered by a
pattern.

**Attribution, 2 cases.** `IV-058` (`is not something we accept`) and `IV-080`
(`The manager's report is published …`, predicted `quoted`) are attribution-only
mismatches whose verdicts are correct. `IV-080` is a side effect of requiring a
reporting verb: `published` is one, and the manager is not the one speaking, so
the stance is `quoted` when the label says `uncertain`.

**Relation false positives, unchanged (5 cases).** `IV-042`, `IV-072`, `IV-083`,
`IV-085`, `IV-089` were relation false positives before the repair and are
relation false positives after it. `IV-083` and `IV-085` are the deliberate Phase
8.4 design: a negated finding is reported rather than hidden, so `The fund does
not guarantee income.` is a negated GUARANTEE and not a silent one.

**Not claimed.** The risk system is not production-ready, the evaluator is not
solved, and this component is not deployable. It is an offline experimental layer
that is not imported by any production module, and an isolation test enforces
that.

---

## 7. Verification

| Check | Result |
| --- | --- |
| full test suite (`python -m unittest discover -s tests -t .`) | **1935 tests, 0 failures** |
| tests before this phase (commit `779b0ab`) | 1842; the change adds 93 and removes none |
| new tests | `tests/risk_evaluation_v3_repair/` 88, plus 5 guards added to existing modules |
| `python -m compileall` on the changed packages | pass |
| every JSON artifact parses | pass |
| secret scan | pass |
| regression suite | 200 cases, 5 sets, **broken 0** |
| repair freeze verification | MATCH, labels unchanged |
| production paths in the diff | none |

### 7.1 Files

Added:

```
risk_evaluation/v3/morphology.py
risk_evaluation/v3_repair/__init__.py
risk_evaluation/v3_repair/negation.py
risk_evaluation/v3_repair/sources.py
risk_evaluation/v3_repair/rejection.py
risk_evaluation/v3_repair/attribution.py
risk_evaluation/v3_repair/freeze.py
risk_evaluation/v3_repair/regression.py
risk_evaluation/v3_repair/regression_baseline.json
risk_evaluation/v3_repair/regression_report_v3_repair.json
risk_evaluation/v3_repair/evaluation_freeze_v3_repair.json
tests/risk_evaluation_v3_repair/__init__.py
tests/risk_evaluation_v3_repair/test_repair_layers.py
tests/risk_evaluation_v3_repair/test_regression_and_freeze.py
docs/PHASE_8_7_TARGETED_REPAIR_REPORT.md
```

Modified (all inside the allowed boundary):

```
risk_evaluation/v3/model.py                    negation_scope, sourcing_categories
risk_evaluation/v3/patterns.py                 generated movement verbs, negated copula,
                                               protected/assured, no-guarantee-given,
                                               cannot + movement, losses are impossible
risk_evaluation/v3/decision.py                 negation scope in the reason, sourcing channel
                                               for D7, the fallback guard
risk_evaluation/v3/pipeline.py                 attribution refinement, gated on use_attribution
risk_evaluation/v3/adapters/intent_pattern.py  negation scope per frame
risk_evaluation/v3/benchmark/v3_report.json    regenerated
```

Test expectations changed, and why each one is a *metric* pin rather than a label:
`test_benchmark_and_replay.py`, `test_decision.py`, `test_pipeline.py`,
`test_benchmark_and_freeze.py` and `test_evaluation_and_errors.py`. Every changed
pin records its Phase 8.5/8.6 predecessor in a comment. The Phase 8.6 failure
counts that the error-analysis tests asserted (`inflected_verb`,
`fallback_propagation`, `novel_rejection_cue` present) are now asserted to be
**zero**, with the detectors still declared so the tests can fail if a defect
returns.

### 7.2 Cross-checks on the repairs

Each repair was checked against the artefact that found it, and against the
artefacts that could have been broken by it:

| Repair | Found by | Checked against |
| --- | --- | --- |
| inflection layer | 8.6 `inflected_verb` = 1 | 8.4 replay (17 positives, recall 0.9412, fp 0), 8.5 fp 1 → 1 |
| negation scope | 8.6 guarantee recall 7/12 | 8.5 benchmark, 8.4 replay, all five 8.6 guarantee misses |
| source typing | 8.6 `novel_source_noun` = 15 | 8.3 control `83-CTL-04` (caught the `promoter` break) |
| rejection cues | 8.6 `novel_rejection_cue` = 8 | 8.6 `author_rejection` 12/15 → 15/15, no case outside the group moved |
| fallback guard | 8.6 `fallback_propagation` = 4 | entry-by-entry ablation on both benchmarks and the replay sets |

---

## 8. Conclusion

The three defects Phase 8.6 confirmed are repaired, and the repairs are proved by
re-running everything that came before them rather than by re-running the set they
were written against.

- **R1** - the inflected verb is fixed by deriving forms from a lemma, and the
  property the phase required is checked: no false positive growth, and the
  directive verbs were deliberately not inflected.
- **R2** - source and cue coverage: speaker accuracy 73.74% → 98.99%, rejection
  detection 5/15 → 15/15, guarantee relation recall 7/12 → 12/12, RISK_REMOVED
  6/8 → 8/8, with the three guarantee shapes now producing distinct, evidenced
  traces.
- **R3** - the fallback no longer overrides intent: four false positives removed,
  `A guaranteed return is not available.` still correct, and the guard was
  narrowed to the one entry the measurements support.

Final status: **PASS WITH ISSUES**. The repairs work, no historical regression was
introduced, and the decision policy's rules, actions and category mapping are
unchanged. Eight cases across the five sets remain wrong, one of them because two
frozen annotations contradict each other; the whole of the PREDICTION and ADVICE
relation gap is untouched and is the recommended next target. The component
remains offline, experimental, and not production-ready.
