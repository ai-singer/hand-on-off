# Phase 8.2 - Attribution Layer Prototype Report

Phase: 8.2
Status: **PASS WITH ISSUES**
Date: 2026-09-27
Package: `risk_evaluation/attribution/`
Connected to production: **no**

---

## 1. Where the problem came from

Phase 8.1 built an adversarial framework and pointed it at
`semantic-intent-v2`. One finding was not a vocabulary gap but a structural one.

`analyze_attribution` in `semantic_evaluator_v2` classifies **the whole text**.
An attribution anywhere in a passage sets one `statement_source` for all of it,
and every category that requires the author's voice is then withdrawn from every
sentence. Three recorded failures came from this, all the same shape:

| Failure | Text | Result in Phase 8.1 |
| --- | --- | --- |
| `ADV-F014` | Economists forecast slower growth in Europe. **This fund cannot lose money.** | `statement_source=third_party`, `financial_guarantee` suppressed, nothing reported |
| `ADV-F013` | Analysts say the sector is volatile this year. **Buy this stock before the quarter ends.** | `statement_source=unknown`, `investment_advice` suppressed |
| `ADV-F015` | Regulators published the revised disclosure rules. **Do not miss this opportunity.** | `statement_source=third_party`, `emotional_manipulation` suppressed |

The bypass is one sentence long: prefix any risky statement with an unrelated
attribution and it disappears. The economy forecast covers *European growth*; it
says nothing about the fund in the next sentence.

Two further cases from the same family passed, and Phase 8.1 recorded that they
passed **for the wrong reason**. `ADV-ATT-02` survived only because
`The company said` is not in v2's attribution lexicon at all, so no withdrawal
happened. Two defects cancelled. A pass produced by a defect is not a capability.

Phase 8.1 could say clearly *what* was wrong and could not say how to fix it,
because the missing thing was not a word list. It was a question the evaluator
had no way to ask.

---

## 2. Why attribution is needed

Phase 7.5's `statement_source` has four values — `author`, `third_party`,
`quoted`, `unknown` — and they conflate two different questions:

- **who is speaking?**
- **what does the author do with what was said?**

`Analysts expect the stock to rise` and `Analysts expect the stock to rise, and
we agree` both produce `third_party` under that field, although the second is the
article's own view. A reported claim and an endorsed claim are not the same
thing, and a rule that cannot tell them apart has only two options: treat every
report as the article's, or treat every report as somebody else's. v2 chose the
second, and Phase 8.1 showed the cost.

The fix is not a better word list. It is separating the two questions:

| | |
| --- | --- |
| `speaker` | `author` \| `third_party` \| `unknown` |
| `stance` | `endorsed` \| `quoted` \| `rejected` \| `uncertain` |

With both, `is_authorial` becomes a real question with a real answer, and it can
be asked **per claim** rather than per text. `Analysts expect growth. However, we
disagree.` is two claims: the first is the analysts' and rejected, the second is
the author's.

Note that `quoted` moves out of the speaker axis entirely. "Quoted" was never a
kind of speaker; it is a kind of stance. That single move is what makes the
model able to express `speaker=author, stance=rejected` — the author rejecting
something — which the four-value field could not.

---

## 3. Architecture

```
text
 |
 v  ClaimParser           sentence terminators, contrastive connectives
claim segments
 |
 v  SpeakerDetector       positional precedence: first marker names the subject
speaker per segment
 |
 v  StanceDetector        rejected > endorsed > quoted > uncertain
stance per segment
 |
 v  backward rejection    a contrastive lead turns on the claim before it
 |
 v  repairs               author-voice reporting, rejection-implies-author
 |
 v  AttributionResult     claims + summary
 |
 v  to_statement_source   bridge to taxonomy v2's vocabulary
```

| File | Responsibility |
| --- | --- |
| `__init__.py` | lazy re-exports (PEP 562, as elsewhere in the package) |
| `model.py` | `Claim`, `AttributionResult`, speakers, stances, `summarise` |
| `evidence.py` | `EvidenceMark`, `EvidenceLog` |
| `claim_parser.py` | `ClaimParser`, `ClaimSegment`, boundary rules |
| `stance_detector.py` | `StanceDetector`, `StanceVerdict`, marker tables |
| `analyzer.py` | `SpeakerDetector`, `AttributionAnalyzer`, `analyze`, the v2 bridge |
| `evaluation.py` | the 30-case annotation set, metrics, coverage probes |
| `annotation_report.json` | the metrics artifact |

Two deviations from the brief's directory listing, both stated rather than
hidden:

- **Speaker inference has no module of its own.** The brief lists
  `claim_parser`, `stance_detector` and `analyzer` and asks for speaker
  inference; it is what the analyzer does between the other two, so
  `SpeakerDetector` lives in `analyzer.py`.
- **`evaluation.py` is an addition.** The brief requires a 30-case annotation
  set and three accuracy metrics but lists no file for them. This follows the
  repository's existing convention, where `risk_evaluation/benchmark.py` holds
  both the cases and the runner.

Three design decisions worth stating:

**The parser returns segments, not `Claim` objects.** The brief says the parser
outputs `List[Claim]`, but a `Claim` requires a speaker and a stance, and those
are later stages. Building one inside the parser would collapse the pipeline the
phase asks for. `analyzer.analyze()` is what returns claims; the brief's output
contract, `{claims: [], summary: {}}`, is met there.

**Precedence is positional and stated.** In `Analysts say X, and we agree` the
analysts speak; in `We believe analysts are wrong` the author does. The first
marker names the subject of the main clause, so it wins; ties go to
`third_party`, because a named outside party is a stronger signal than a bare
first person. This is a heuristic, and it is written down as one.

**An unmarked claim is the author's by default, and the layer says so.** Most
financial prose contains no `we believe`. The taxonomy treats unmarked text as
the author's voice, so `is_authorial` does too — but the claim records
`is_default_voice` and carries absence evidence, so a reader can tell *no
attribution is present* from *the author was identified*. Collapsing those two
would recreate the original problem in a new form.

---

## 4. Data model

```json
{
  "id": "claim-001",
  "text": "Analysts expect the stock to rise",
  "speaker": "third_party",
  "stance": "quoted",
  "confidence": 0.75,
  "evidence": ["analysts", "expect"]
}
```

The six documented fields are present exactly as specified, plus `index`,
`is_authorial`, `spans`, `rules` and `detail`. Evidence is a list of strings as
the brief requires; `detail` carries the structured form with spans and rule ids.

**Evidence is mandatory and enforced structurally.** `Claim.__post_init__` raises
`AttributionError` if `evidence` is empty, so acceptance criterion 4 cannot be
violated by a future caller who forgets. A claim can only be built with a
speaker, a stance and a reason for both.

Negative determinations carry `rule:` tags rather than markers, because "no
speaker marker was found" is itself a finding:

```
text     : Costs were flat over the period.
speaker  : unknown    evidence ["rule:speaker.no-marker"]
stance   : uncertain  evidence ["rule:stance.no-marker"]
```

Without this, the fallback cases would be the only ones with no evidence, which
is exactly backwards: a default is the determination most in need of a stated
basis.

`AttributionResult.as_dict()` returns `{claims, summary}` as specified. The
summary counts speakers and stances and lists the claim ids each conclusion
covers (`authorial_claims`, `attributed_claims`, `rejected_claims`).

---

## 5. Test results

| | |
| --- | --- |
| Attribution suite (`tests/attribution_layer/`) | **208 tests, all passing** (requirement: 40) |
| Whole repository | **1102 tests, all passing** (was 894) |
| `compileall` | PASS |
| JSON validity | 77/77 PASS |
| Secret scan (workspace + repository root) | PASS |
| Both recorded evaluation freezes | MATCH (unchanged) |
| Production isolation | no module in `runtime`, `workflows`, `plugins`, `production`, `core`, `artifact`, `security` mentions `risk_evaluation` |
| `semantic_evaluator_v2.py` / `taxonomy_v2.py` modified | **no** (`git status` shows only two new directories) |
| Existing benchmark labels modified | **no** |

Coverage of the brief's test requirements:

| Requirement | Tests |
| --- | --- |
| A. Speaker (`Analysts said…`, `We believe…`, no subject) | `test_speaker.py`, 11 |
| B. Stance (quoted, endorsed, rejected, uncertain) | `test_stance.py`, 18 |
| C. Multiple claims (`Experts predict growth. However, we disagree.`) | `test_stance.py`, `test_claim_parser.py` (28) |
| D. Phase 8.1 failure replay (>= 5 cases) | `test_failure_replay.py`, 23 — replays all 9 |
| Evidence on every determination | `test_model_and_evidence.py` (47), `test_analyzer.py` (30) |
| Metrics and report | `test_metrics.py`, 39 |
| Isolation | `test_isolation.py`, 12 |

---

## 6. Failure case analysis

### 6.1 The 30-case annotation set

| Metric | Result |
| --- | --- |
| claim split accuracy | **100.0%** (30/30) |
| speaker accuracy | **100.0%** (35/35 aligned claims) |
| stance accuracy | **100.0%** (35/35 aligned claims) |
| speaker and stance both correct | **100.0%** (35/35) |

Per speaker: author 13/13, third_party 18/18, unknown 4/4.
Per stance: endorsed 11/11, quoted 10/10, rejected 10/10, uncertain 4/4.

**This number must be read with the disclosure below, and it is not evidence
that the layer works.**

### 6.2 Disclosure: one rule was added after the first measurement

The first run scored **speaker accuracy 88.6% (31/35)**. All four errors had one
cause: a claim whose own text performs a rejection but which carries no
first-person marker.

```
Analysts expect a rebound. But evidence shows otherwise.
  claim-002  speaker=unknown  stance=rejected  is_authorial=False
```

`unknown` plus `rejected` was **marked non-authorial**, which would have a
future evaluator treat the article's own counter-argument as somebody else's
claim and suppress it. That is the Phase 8.1 failure mode reappearing in a new
place, and it is a real defect rather than a labelling quibble, so one rule was
added:

> Only the article's own voice can reject a claim inside the article.

The rule is deliberately narrow — it applies only when no speaker marker was
found, so `Analysts dispute the rebound.` keeps `speaker=third_party` and the
rejection stays the analysts'. After it: 88.6% → 100%.

The ordering is disclosed because it matters. A rule added after seeing which
cases fail is a rule fitted to those cases, and the 100% figure is therefore
partly circular. No other rule was changed in response to the metric.

### 6.3 Coverage probe: the boundary, measured separately

A stress set of 12 cases was written **after** the rules, covering attribution
shapes the marker tables have no phrase for. It is reported separately and never
folded into the 30-case figure. It is not a held-out set, and its purpose is to
show where the boundary is.

| Metric | Result |
| --- | --- |
| claim split accuracy | **91.7%** (11/12) |
| speaker accuracy | **80.0%** (12/15) |
| stance accuracy | **86.7%** (13/15) |

| Case | Text | Expected | Got | Cause |
| --- | --- | --- | --- | --- |
| `PR-001` | Some say the rally is over. | `third_party/quoted` | `unknown/quoted` | `some say` is not in the speaker table |
| `PR-002` | It is widely believed that rates will fall. | `third_party/quoted` | `unknown/uncertain` | passive attribution has no agent |
| `PR-003` | There is a view that the fund is overpriced. | `third_party/quoted` | `unknown/uncertain` | nominalised attribution |
| `PR-006` | Experts predict growth; we are not so sure. | 2 claims | 1 claim | `;` is not a boundary rule |

What the probe shows is a clean split. Attribution phrased the way the table
expects works, including both Chinese cases (`据分析师称…`, `我们认为…`), the
rejection cases, and `We agree with analysts that the risk is contained.` What
fails is **attribution with no agent to match on**: unnamed plural speakers,
passive voice, and nominalisation. Those are 3 of the 4 failures, and they are
the same defect v2 has — Phase 7.5 found it as eight of ten attribution errors.

### 6.4 Phase 8.1 replay

All 9 `attribution_confusion` cases were reloaded from the published
`semantic/adversarial/v1` benchmark and the committed failure repository and
re-analysed. **The risk verdict was not expected to change, and did not:**
`semantic_evaluator_v2` is untouched.

| Case | Phase 8.1 | New layer |
| --- | --- | --- |
| `ADV-ATT-01` | whole text `unknown`, advice suppressed | 2 claims: third_party/quoted + **authorial** directive |
| `ADV-ATT-03` | whole text `third_party`, guarantee suppressed | 2 claims: third_party/quoted + **authorial** guarantee |
| `ADV-ATT-05` | whole text `third_party`, pressure suppressed | 2 claims: third_party/quoted + **authorial** pressure |
| `ADV-ATT-02` | passed by accident | 2 claims, second authorial — does not rely on the lexicon gap |
| `ADV-ATT-04` | passed | 2 claims; second correctly **stays attributed** |

For the three recorded misses, `authorial_text()` now returns exactly the
sentence the article is making and excludes the borrowed attribution:

```
ADV-ATT-03  authorial_text() = "This fund cannot lose money."
```

A future evaluator could run its category rules over that string instead of the
whole paragraph, and the Phase 8.1 bypass would be closed without touching the
evaluator.

The controls are the more important half of this result. All four remain
non-authorial, with empty `authorial_text()`. `ADV-ATT-04` deliberately stays
attributed: its target is `unverified_information`, which guide v2 reports
whatever the voice, so producing an authorial claim there would be
over-correction — the same class of error as the original defect.

---

## 7. Limitations

1. **The 100% figure is not an achievement.** The annotation set is 30 cases,
   synthetic, and written by the same author as the rules. One rule was fitted
   to four of its cases after the first measurement. The coverage probe is the
   more informative number.
2. **Attribution without an agent fails.** Passive voice, nominalisation and
   unnamed plural speakers have no marker to match, and there is no
   morphological analysis to fall back on. Three of four probe failures.
3. **Splitting is punctuation-deep.** `;`, `:` and participial clauses are not
   boundaries. `PR-006` is one claim where there are two. Nested quotation is
   also unhandled: a rejection inside quotation marks is read as the author's.
4. **`third_party` includes unnamed collectives.** `Sources say` and
   `some say`-style phrasing is a third party here, whereas v2 treats an
   uncheckable source as `unknown`. The bridge maps it accordingly, but the two
   layers disagree on the boundary and that disagreement is unresolved.
5. **Stance is decided by cue phrases, so disagreement is only seen when it is
   phrased as one of the listed cues.** `we remain unconvinced` is not in the
   table; `we are not convinced` is.
6. **Positional speaker precedence is a heuristic.** It resolves the cases in
   the annotation set and has no grammatical basis. Subordinate clauses will
   break it.
7. **Confidence is a marker-count function, not a calibrated probability.** The
   numbers (0.6, 0.65, 0.75, 0.8) encode how many markers matched and nothing
   else. Treating them as probabilities would be a mistake.
8. **Single sentence only, in practice.** The parser handles a paragraph, and
   rejection is projected backwards exactly one claim. Longer-range structure —
   a thesis stated in the opening and rejected in the conclusion — is out of
   scope.
9. **No production connection, no runtime connection, no Quality Gate.** This is
   a prototype by design, and nothing consumes its output.

---

## 8. How this would connect to the Risk Evaluator

Nothing was wired up, and the phase forbids it. The intended connection is
narrow and testable, and the pieces already exist:

```python
result    = attribution.analyze(text)          # claims with speaker and stance
authorial = attribution.authorial_text(result) # only what the article asserts
```

A future `semantic-intent-v3` would run its category rules over `authorial`
rather than over the whole text, and use `to_statement_source(claim)` per claim
instead of one `statement_source` per text. That is a change to the evaluator,
which Phase 8.2 has no mandate to make, and it is the only change that would
close the Phase 8.1 bypass.

What that connection needs before it is safe, in order:

1. **Agentless attribution** (limitation 2). The largest gap, and the same one
   v2 has. Without it, a rewording of `Sources say` defeats the layer.
2. **A real corpus and independent annotation.** 30 synthetic cases written by
   the rules' author cannot support a claim about generalisation. The coverage
   probe makes the shortfall visible, not small.
3. **A held-out set written before the rules**, which this phase cannot produce
   retroactively.
4. **Longer-range structure** (limitation 8) before the layer is trusted on
   multi-paragraph material.
5. **Re-running Phase 8.1's adversarial discovery against a v3 that consumes
   this layer**, which is the only way to find out whether the fix works or
   merely moves the failure.

Feeding the layer back into the evaluator without those steps would replace a
known defect with an unmeasured one.

---

## 9. What this phase does not claim

- It does not claim risk capability improved. No risk verdict changed, and the
  evaluator, taxonomy, benchmarks, Quality Gate and runtime are untouched.
- It does not claim production readiness. The layer is offline, unconnected, and
  has never seen real material.
- It does not claim the evaluator is fixed. It supplies the structure a fix
  would need; the fix is a later phase's work.
- It does not claim 100% attribution accuracy. That number is circular by
  construction and is disclosed as such.
- It does not claim the layer generalises. Its measured boundary is 80% speaker
  accuracy on text phrased differently from its rules.
