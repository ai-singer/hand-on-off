# Phase 8.4 - Risk Intent Core Repair: Relational Intent Patterns

Phase: 8.4
Status: **PASS WITH ISSUES**
Date: 2026-09-27
Package: `risk_evaluation/intent_patterns/`
Benchmark: `intent_pattern/v1`, 42 cases
Production changed: **no**

---

## 1. Where the problem came from

Phase 8.1 built an adversarial framework and found that `financial_guarantee` —
a `block`-severity category — is invisible in its most ordinary English form:

| Text | Detected before this phase |
| --- | --- |
| This is a guaranteed return. | yes |
| **This return is guaranteed.** | **no** |
| **Returns are guaranteed.** | **no** |
| **We guarantee this return.** | **no** |

Phase 8.3 measured the consequence. On its 60-case experiment dataset the
guarantee blind spot was the single largest error shared by *both* arms: `A-02`
and `D-06` were missed by the baseline and by the attribution-aware experiment
alike. Fixing it was the top recommendation of that report, with the warning
that it would change the baseline and therefore needed its own measurement.

This is that measurement.

The old rule for the category is

```
risk_negation  ->  \bguaranteed\s+(?:return|returns|profit|profits|
                                     gain|gains|income|outcome)\b
```

`guaranteed` matched only when it **precedes** the noun it modifies. Three other
English realisations of the same relation were invisible.

---

## 2. What the old mechanism could not express

The limitation is not a missing word and not a missing synonym. It is that the
rule encodes a **fixed word order**, and the relation it is trying to detect is
realised in at least five orders:

| Realisation | Example | Old rule |
| --- | --- | --- |
| attributive | This is a **guaranteed return**. | matched |
| copular | This return **is guaranteed**. | missed |
| passive | Your returns **are guaranteed by the scheme**. | missed |
| active | We **guarantee** this return. | missed |
| nominal | The fund offers **a guarantee of** returns. | missed |

Two further problems follow from the same cause.

**Negation has nowhere to live.** `Returns are not guaranteed.` and
`Returns are guaranteed.` differ by one token, and a substring rule cannot
express "the same frame, negated" — it can only add another pattern that
happens to exclude it. Without that, correcting the miss risks turning every
negated guarantee into a false positive.

**A rule that declines and a rule that never ran are indistinguishable.**
`Returns cannot be guaranteed.` and `The company reports its results in March.`
both produce no match, and the old output says nothing about which happened.
One is a rule working, the other is a rule not applying, and a report that
merges them cannot tell a repair from a silent failure.

Adding synonyms would not have fixed any of this. Adding `guaranteed` to more
places would have widened the miss surface, not narrowed it.

---

## 3. The new pattern design

```
EntityType   what the relation is about       RETURN, CAPITAL, VALUE, OUTCOME, GUARANTOR
Relation     what is asserted about it        GUARANTEE, RISK_REMOVED
Frame        how it is realised in syntax     active, passive, copular,
                                              attributive, nominal
```

| Module | Responsibility |
| --- | --- |
| `model.py` | `EntityType`, `EntityLexicon`, `Frame`, `Relation`, `IntentPattern`, match types |
| `matcher.py` | `RelationMatcher`, negation, hedging, sentence spans |
| `financial_guarantee.py` | the entity types, the two relations, the pattern set |
| `evaluation.py` | the benchmark, the old/new comparison, the attribution combination |

### 3.1 `IntentPattern`

The six documented fields:

```json
{
  "id": "financial-guarantee-relational-v1",
  "category": "financial_guarantee",
  "required_entities": ["RETURN", "CAPITAL", "VALUE", "OUTCOME"],
  "relations": ["GUARANTEE", "RISK_REMOVED"],
  "confidence": 0.8,
  "evidence": "Guide v2 section 7: the category is risk removed ..."
}
```

### 3.2 Frames, and the relation they carry

The `GUARANTEE` relation has six frames. `object + be + guaranteed by X` is the
passive; without the agent it is copular. That distinction is not decoration: it
is why `Your returns are guaranteed by the scheme.` reports one frame rather
than two.

```python
Frame(ATTRIBUTIVE, r"\bguaranteed\s+(?P<object>{OBJECT})\b", ...)
Frame(PASSIVE,     r"\b(?P<object>{OBJECT}){FILLER}\s+{COPULA}\s+{ADVERB}"
                   r"(?P<predicate>guaranteed)\s+by\s+(?P<agent>...)", ...)
Frame(COPULAR,     r"\b(?P<object>{OBJECT}){FILLER}\s+{COPULA}\s+{ADVERB}"
                   r"(?P<predicate>guaranteed)\b", ...)
Frame(ACTIVE,      r"\b(?P<subject>{GUARANTORS})\s+...(?P<predicate>guarantee(?:s|d)?)\s+"
                   r"(?P<object>{OBJECT})\b", ...)
Frame(NOMINAL,     r"\b(?:a|the|its|our|their)\s+(?P<predicate>guarantee)\s+"
                   r"(?:of|on|for|over|that)\s+(?P<object>{OBJECT})\b", ...)
```

Matching binds roles, so a match reports *who promised what* rather than a
substring offset. `{FILLER}` is bounded to four words, which is what lets
`The value of your investment is guaranteed.` match without letting the frame
span unrelated clauses.

### 3.3 Negation and hedging are properties of a match

`FrameMatch` carries `negated` and `hedge` rather than being filtered away.
`PatternMatch` therefore reports three states:

| State | Meaning |
| --- | --- |
| `fired` | an asserted, unhedged frame was found |
| `scanned` | a frame matched, but it is negated or hedged |
| silent | no frame matched at all |

This is what makes `Returns cannot be guaranteed.` an *evidenced negative*
rather than an absence, and it is the distinction section 2 said the old
mechanism had no way to express.

### 3.4 `RISK_REMOVED` exists for parity, not for coverage

The phase targets one blind spot. The second relation carries the rest of what
the old rule matched — `risk-free`, `no risk`, `cannot lose`, `never falls` —
so the new layer is a **superset** of the old one. Without it, a change in
recall could equally be caused by dropped coverage, and the comparison would
prove nothing. `PG-16` and `PG-17` exist to check it.

### 3.5 Scope

Only `financial_guarantee` is implemented, as the phase requires. The pattern
layer is not an evaluator: it is not in `regression.EVALUATORS`, is not a
registered benchmark version, and is imported by nothing outside its own
package and tests.

---

## 4. Benchmark

`intent_pattern/v1`, 42 cases, exported to `benchmark_v1.json`.

| Group | Cases | Required | Meaning |
| --- | --- | --- | --- |
| positive | 17 | 15 | an author-voice guarantee; the pattern must fire |
| negative | 15 | 15 | no guarantee relation; the pattern must not fire |
| boundary | 10 | 10 | guarantee vocabulary that is conditional, reported or uncertain |

Form coverage is recorded per case and asserted by a test:
`copular 5`, `active 3`, `nominal 3`, `passive 2`, `attributive 2`,
`risk_removed 2`; negatives split `negation 8`, `discussion 4`, `education 3`;
boundary split `quoted 6`, `hypothetical 3`, `uncertain 1`.

**Boundary cases are not negative cases, and they are not scored as either.**
The pattern layer finds a relation; deciding whether a *reported* or
*conditional* guarantee is the article's guarantee is the attribution layer's
job. Scoring boundary as an error would penalise the layer for a question it
does not ask; scoring it as a success would hide a real cost. It is reported
separately, and section 5.3 measures what adding attribution does to it.

The benchmark is **not registered in the benchmark registry**. Phase 8.4's
permitted additions are this package, tests, `benchmarks/` as files, and docs;
adding a version to the registry is a governance act on shared code that this
phase was not asked to perform. `intent_pattern/v1` is versioned in the package
and exported alongside it.

---

## 5. Old versus new

### 5.1 Headline, relation view (17 positive, 15 negative)

| Measure | Old (`semantic-intent-v2`) | New pattern layer |
| --- | --- | --- |
| recall | 0.2353 (4/17) | **0.9412 (16/17)** |
| false positives | 1 | **0** |
| false negatives | 13 | **1** |

**Miss reduction: 12 of 13 (92.3%).**

13 cases fixed, **0 broken**. The fixed set is `PG-03` … `PG-14` and `NG-07`.

The category view — boundary cases counted as benign — produces identical
numbers, because hedging is built into the matcher rather than bolted on: the
pattern layer fires on **none** of the ten boundary cases.

### 5.2 By realisation

| Form | Cases | Old | New |
| --- | --- | --- | --- |
| attributive | 2 | 2 | 2 |
| copular | 5 | **0** | **5** |
| active | 3 | **0** | **3** |
| passive | 2 | **0** | **2** |
| nominal | 3 | **0** | 2 |
| risk_removed (parity) | 2 | 2 | 2 |

The old rule handled exactly the two attributive cases and the two parity cases.
Every other positive except one is new.

### 5.3 With the attribution layer (Phase 8.3's 60 cases)

| Stack | Correct | Misses |
| --- | --- | --- |
| baseline `semantic-intent-v2` | 39 | 9 |
| + attribution layer (Phase 8.3) | 53 | 2 |
| + attribution **and** pattern layer | **55** | **0** |

The pattern layer changes exactly two cases, `A-02` and `D-06` — the two
guarantee blind-spot cases Phase 8.3 identified as unfixable by attribution
alone. It breaks nothing.

One composition detail is worth recording because getting it wrong is easy.
The pattern layer's findings must pass **through** the Phase 8.3 decision policy,
not be added to the merged result afterwards. Adding them afterwards broke two
cases: `We disagree with the view that this fund cannot lose money.` is
`author/rejected`, the pattern layer correctly finds the guarantee relation in
it, and R3 is what stops that becoming the article's risk. Bypassing the policy
put the false positive straight back. The combination now runs
`decide_claim` over baseline detections and pattern detections together.

---

## 6. Failure case analysis

### 6.1 One positive still missed

| Case | Text | Old | New |
| --- | --- | --- | --- |
| `PG-15` | Returns are a guarantee on this product. | miss | **miss** |

The nominal frames cover `a guarantee of/on/for OBJECT`, where the object
follows the preposition. `PG-15` puts the object *before* the copula —
`OBJECT are a guarantee on X` — which is a different construction the frame set
does not have. It is left in the benchmark and reported rather than reworded:
deleting an inconvenient case after seeing it fail is the same act as adding a
convenient one.

### 6.2 Two regressions the benchmark caught during the build

Both are cases where **repairing the blind spot broke something the old
evaluator got right**. They are the reason the negative group exists.

**`PG-17` — `This fund cannot lose money.`** The old evaluator caught this.
The first version of the new matcher did not: the frame `cannot lose` carries
its own negator, and the negation guard read that `cannot` as a modifier and
suppressed the match. Fixed by marking such frames `self_negating`, so the
negation window is measured from the start of the match rather than from the
predicate. `It is not true that the fund cannot lose money.` is still correctly
rejected, so the fix did not disable negation.

**`C-01` / `C-03` — rejected guarantees.** Adding pattern findings to the merged
result after the decision policy reintroduced false positives the attribution
layer had already removed (§5.3). Fixed by routing both sources through
`decide_claim`.

Both were caught by tests that exist to check the new layer does not damage the
old one. Neither would have been visible from the recall figure alone, which
went up in both cases.

### 6.3 A bug in the negation guard, found by a benchmark case

`Returns cannot be guaranteed.` fired in the first version. The negator sits
*inside* the frame, between the object and the copula, and the guard only looked
before the start of the match. Fixed by anchoring the negation window at the
predicate. `NG-04` is in the benchmark for exactly this.

### 6.4 A double-counted frame

`Your returns are guaranteed by the scheme.` reported itself as both `copular`
and `passive`, because a copular match starts at the same position as the
passive that contains it. The skip check compared whole spans, which never
match. Fixed by comparing start positions, so one relation is one frame.

---

## 7. Limitations

1. **One category, one language pair.** Only `financial_guarantee` is
   implemented, and the non-English coverage is a list of Chinese phrases rather
   than frames. The architecture generalises; this instance does not.
2. **The benchmark was written by the pattern author.** 42 synthetic cases,
   authored alongside the frames they test. Section 6.1 shows the boundary is
   real, but a dataset written by someone else would find more of it.
3. **`PG-15` is a known miss**, and the nominal construction it tests
   (`OBJECT are a guarantee on X`) is not merely absent from the frames — it was
   never considered until the case failed.
4. **`{FILLER}` is bounded at four words.** `The value of the units held in your
   investment account is guaranteed.` will not match. The bound is a
   precision/recall trade-off with no measurement behind it beyond this dataset.
5. **Hedging is a marker list, not an analysis.** `You may be interested to
   know: returns are guaranteed.` is treated as hedged because of `may`, and a
   conditional whose `if` clause is in the previous sentence is treated as
   asserted. Both directions are wrong and neither is measured.
6. **Negation is a window, not a scope.** `It is not the case that the fund
   underperformed; returns are guaranteed.` is negated because `not` is within
   30 characters. No case in the benchmark covers it.
7. **The pattern layer is not an evaluator.** It reports whether a relation is
   present, not whether the text is risky. The combination in §5.3 is the
   honest use, and that combination lives in an experiment module, not in the
   evaluator.
8. **No production connection, no runtime, no Quality Gate.** Nothing imports
   the package outside its own tests, and `semantic_evaluator_v2` is untouched.

---

## 8. Next steps

**This is a prototype that works, and it should not be merged as it stands.**

What it establishes:

- the guarantee blind spot is a **word-order** defect, not a vocabulary defect,
  and a relation-level rule closes it: recall 0.2353 → 0.9412 with **zero**
  broken cases and zero new false positives;
- negation and hedging can be modelled as properties of a match, which is what
  makes a repair distinguishable from a silent failure;
- composed correctly with Phase 8.3's attribution layer, the three-stack result
  is 55/60 correct with **no misses and no regressions** — and the composition
  only works if pattern findings pass through the decision policy.

What must happen before this becomes `semantic-intent-v3`, in order:

1. **A fresh, independently annotated benchmark.** The current one cannot
   support a generalisation claim, and the report's own §6.1 shows where it is
   thin. Phase 8.3's recommendation — a real-material corpus — is still
   outstanding and this phase does not address it.
2. **Extend the frames to the remaining categories**, one at a time, each with
   its own benchmark version. The five risk categories are not alike:
   `unverified_information` is about sourcing and `emotional_manipulation` is
   about pressure, and neither is a simple relation between an entity and a
   predicate.
3. **Replace the hedging marker list with something defensible.** Limitation 5
   is the largest remaining source of silent error, and it is not fixable by
   adding markers.
4. **Measure the `{FILLER}` bound** rather than assuming four words is right.
5. **Re-run Phase 8.1's adversarial discovery against any v3 that consumes
   this**, which is the only way to find out whether the repair holds or merely
   moves the miss somewhere else.

The concrete recommendation is to lift `financial_guarantee`'s relation model
into a v3 evaluator **together with** the Phase 8.3 attribution layer, as one
change with one fresh measurement — not to merge either prototype on its own.

---

## 9. What this phase does not claim

- It does not claim production safety has improved. Nothing in the production
  path changed; the plugin still produces the runtime's risk constraints.
- It does not claim the risk capability is solved. One category is covered, one
  case is still missed, and section 7 lists eight open limits.
- It does not claim overall risk ability improved. Recall improved **on one
  category, measured on a synthetic benchmark written by the pattern's author**.
  No other category was touched.
- It does not claim the benchmark is independent or representative.
- It does not claim it is shippable. It is not registered, not imported by
  production, and not a replacement for any evaluator.

---

## 10. Verification

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests` | **1389 passed, 0 failed** (was 1256) |
| Phase 8.4 suite (`tests/intent_patterns_tests/`) | 133 passed (requirement: 50) |
| `python -m compileall` | PASS |
| JSON validity (all workspace JSON) | 82/82 PASS |
| Secret scan (workspace + repository root) | PASS |
| Both recorded evaluation freezes | MATCH (unchanged) |
| `benchmark_registry.verify_all()` | all True; registry keys unchanged |
| `semantic_evaluator_v2.py` / `taxonomy_v2.py` modified | **no** |
| Existing benchmark labels modified | **no** |
| Production / runtime / plugin files modified | **no** — `git status` shows only two new directories |
| `regression.EVALUATORS` | unchanged (`keyword`, `semantic`) |

Test coverage of the phase's requirements:

| Requirement | Tests |
| --- | --- |
| pattern schema | `test_pattern_schema.py`, 35 |
| active / passive / negation / quoted | `test_matcher.py`, 31 |
| benchmark and old/new comparison | `test_benchmark.py`, 53 |
| regression and production isolation | `test_isolation.py`, 14 |
