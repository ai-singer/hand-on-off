# Creator Production Readiness Report

Phase 6.5.1 — Creator Production Loop Validation.

```text
Final Status: PASS WITH ISSUES
```

```text
Source -> Distill -> Evaluate -> Artifact -> Generate Contract -> Production Ready Output
                                                                    ^ closed, with a measured
                                                                      risk-recall gap
```

The loop runs end to end on all four source kinds. The blocking issue is not
the loop: it is that the Creator plugin's risk boundary catches **none** of the
prohibited statements phrased in wording its rules do not enumerate (section 7).

Scope note: this phase added documentation, validation tooling and tests only.
No universal distillation logic, runtime bootstrap, artifact schema, plugin
contract, Lobster workflow, or `xiaolin_finance` risk rule was modified. No
content was generated.

## 1. Production Loop Architecture

Full model and per-stage layer ownership: [`CREATOR_PRODUCTION_LOOP.md`](CREATOR_PRODUCTION_LOOP.md).

```text
Raw Material -> Source Adapter -> RawSource            [Runtime / Universal contract]
   -> Universal Distillation                            [Universal]
   -> Creator Plugin Enhancement                        [Creator Specific]
   -> Artifact Validation                               [Universal + Creator Specific]
   -> Quality Evaluation                                [Universal + Creator Specific]
   -> Generation Contract                               [Runtime]
   -> Content Production                                [Runtime, injected adapter]
```

Nine stages, three layers, one loop. The four properties that make it one loop
rather than parallel pipelines — one input contract, one distillation run, one
artifact, one gate — were each verified in section 3.

## 2. Source Adapter Validation

All four adapter kinds were exercised (Step 2 Test A–D):

| # | Adapter kind | Contract value used | RawSource valid | Artifact produced | Sections |
| --- | --- | --- | --- | --- | ---: |
| A | business analysis text | `document` | yes | yes | 9 |
| B | structured financial metrics | `data` | yes | yes | 9 |
| C | video summary | `video` | yes | yes | 9 |
| D | image / OCR description | `image` | yes | yes | 9 |

**One contract deviation, recorded rather than worked around:** the task calls
kind A `text`, but the `RawSource` contract has exactly four values —
`video`, `document`, `data`, `image`. There is no `text`. Text material maps to
`document`, and the contract **rejects** `source_type="text"` with
`InvalidSourceError`. Coercing it would have hidden a real contract boundary.

No adapter kind takes a separate distillation path: the kind is data on one
envelope, consumed by one engine.

## 3. Distillation Evidence

**Uniform structure across kinds** — distilling each adapter kind separately
produces the same nine sections and the same artifact version:

```text
document   sections=9 identical_structure=True
data       sections=9 identical_structure=True
video      sections=9 identical_structure=True
image      sections=9 identical_structure=True
```

**All four common families populate from mixed kinds** — one source per
distillation role, deliberately mixing adapter kinds (document / video / data /
image):

```text
topic_candidate   : 5 entries   (1 common + 4 from the plugin)
content_template  : 1 entry
knowledge_unit    : 1 entry
style_pattern     : 1 entry
referenced ids    : all four source ids, each in exactly one family
```

`knowledge_unit` items carry `evidence_refs` with both `source_id` and
`source_type`, so provenance survives the universal layer.

## 4. Plugin Enhancement Evidence

`xiaolin_finance@1.2.0` adds a domain extension without rewriting common output:

| Check | Result |
| --- | --- |
| `domain_extension` present and non-empty | yes |
| All five distilled sections present | yes |
| At least one section matched on finance material | yes — `business_mechanism`, `financial_structure`, `misconception_analysis` |
| `plugin_identity` names the plugin | yes |
| `source_classification` populated from real references | yes |
| `content_template` / `knowledge_unit` / `style_pattern` identical to a domain-free run | yes, byte-identical |
| `topic_candidate` only appended to | yes, common entries unchanged and first |

## 5. Evaluation Evidence

Evaluation behaves as a production gate, not a display layer.

| Case | Input | Domain score | Risks | Gate status | Generation adapter |
| --- | --- | ---: | --- | --- | ---: |
| 1 — high quality finance explanation | mechanism + income statement + growth ratio | 0.88 | none | **pass** | **invoked 1×** |
| 2 — prohibited content | "This is a guaranteed buy at the current price." | 0.20 | `investment_advice` (block) | **review_required** | **invoked 0×** |

Case 1 also builds a generation handoff (`ready_for_generation`). Case 2's
handoff attempt is rejected, so there is no path from a blocked artifact to
content production.

## 6. Generation Contract Evidence

`GenerationRequest`
(`workflows/content_distillation_pipeline/generation_interface.py`) remains the
single generation contract. `production/generation_input.py` adds a **derived,
never-persisted projection** that answers "can this artifact be consumed?" —
it defines no new artifact format and runs no distillation.

| Addressed input | Projected from | Resolved |
| --- | --- | --- |
| `topic` | `topic_candidate` | yes |
| `structure` | `content_template` | yes |
| `knowledge` | `knowledge_unit` | yes |
| `style` | `style_pattern` | yes |
| `domain_context` | `domain_extension` | yes |
| `constraints` | `risk_constraints` | yes |

Evidence:

- every addressed input resolves and the projection reports `complete`;
- each projected value **is** the artifact section (identity check), so the
  projection cannot drift from the artifact it came from;
- an empty `risk_constraints` is a **valid** production state ("no risks"), not
  an incomplete input — `INPUTS_ALLOWING_EMPTY` documents that, together with
  `domain_context` for plugin-less instances;
- a `GenerationRequest` carries the artifact by reference and consumption does
  not mutate it;
- full-loop run over four mixed-kind sources: gate `pass`, generation inputs
  `complete`, adapter invoked exactly once.

## 7. Known Limitations

### 7.1 Risk Recall Baseline — the blocking issue

**Stated baseline from the preceding phase: Risk Recall Baseline = 25%.**
No Phase 6.4 artifact exists in this repository, so that number cannot be
reproduced here. It is recorded as given, and this phase measured the baseline
independently rather than restating it.

Measurement (`python -m production.risk_recall`, 20 prohibited probes + 5 clean
probes, all synthetic):

```text
prohibited probes      : 11/20  (recall 55%)
  keyword probes       : 11/11  (recall 100%)
  paraphrase probes    :  0/9   (recall 0%)   <- the real risk baseline
clean probes flagged   :  1/5   (false positive rate 20%)

per category:
  investment_advice    2/5
  market_prediction    2/5
  emotional_language   3/5
  unverified_fact      4/5
```

**Read the split, not the blended number.** The blended 55% is an artifact of
probe composition — it counts probes that happen to contain a literal rule
keyword. The number that describes real risk is **paraphrase recall: 0 of 9**.

- **The matching mechanism works**: every probe containing a rule keyword was
  caught (11/11).
- **The semantic gap is total**: when the same prohibited intent is expressed in
  words the rules never enumerate, **nothing is caught**. Examples of missed
  statements: *"You should buy this stock today."*,
  *"I recommend adding this company to your portfolio."*,
  *"Analysts are certain the price target will be reached."*,
  *"The market will crash next month."*, *"Word on the street is that revenue is
  fake."*
- This is a **false-negative** failure, the dangerous direction: prohibited
  content reaches the gate unflagged, and a clean-looking artifact can proceed.

The stated 25% sits between the measured 55% (blended) and 0% (paraphrase). All
three cannot be compared directly because recall depends entirely on the probe
set; the probe set, its composition and the split are published so the number is
reproducible rather than asserted.

### 7.2 False positives push legitimate material into review

```text
flagged but clean: "This is not a guaranteed return, and the material explains why."
```

Substring matching ignores negation, so a sentence that explicitly disclaims a
guarantee is blocked. Direction is conservative, but it costs reviewer time and
is the mirror image of 7.1.

### 7.3 Other limitations

| ID | Limitation | Impact |
| --- | --- | --- |
| L-01 | Rule set is keyword based with no semantic understanding | Cannot detect implication, irony, or unenumerated phrasing (7.1) |
| L-02 | Never calibrated against real material | Precision and recall on real content are unknown; every phase so far forbade collecting material |
| L-03 | Bilingual coverage only (English / Chinese) | Other languages are not designed for |
| L-04 | `domain_context` and `constraints` may be empty | Deliberate; a plugin-less instance or a clean artifact is valid, and downstream must handle both |
| L-05 | The template ships no generation adapter | Content production is instance-owned; this phase validated the contract, not an adapter |
| L-06 | Source Adapter implementations are instance-owned | The template validates the `RawSource` contract and one adapter kind per source type, not real ingestion |
| L-07 | Plugin version namespace is not unified with the template | Carried over from Phase 5.4 VER-1 |

### 7.4 What this phase does not claim

- It does **not** claim the risk boundary is production safe. Section 7.1 shows
  it is not, for anything beyond enumerated wording.
- It does **not** claim real content quality. No real material was collected and
  no content was generated; quality was validated on synthetic fixtures only.

## 8. Validation Summary

| Check | Command | Result |
| --- | --- | --- |
| Unit tests | `python -m unittest discover -s tests -v` | **PASS** — Ran **122** tests, OK (104 before, 18 new) |
| Compile | `python -m compileall .` | **PASS** — exit 0 |
| JSON | all `*.json` | **PASS** — 23/23 |
| Secret scan | workspace and repository root | **PASS** — 0 findings both scopes |
| Risk recall | `python -m production.risk_recall` | measured; see 7.1 |

New tests `tests/creator_production_loop/` (18):

| Group | Count | Covers |
| --- | ---: | --- |
| Source adapter | 5 | four adapter kinds + the missing `text` contract value |
| Distillation uniformity | 2 | identical structure across kinds; all four families from mixed kinds |
| Plugin enhancement | 2 | domain extension present; common families never rewritten |
| Evaluation loop | 2 | Case 1 pass + handoff; Case 2 gated with zero adapter calls |
| Generation contract | 3 | all inputs resolve; projection is derived; request carries artifact unchanged |
| Production readiness | 4 | full loop; probe set intact; enumerated wording always caught; baseline matches this report |

The final group **pins the measured baseline to this document**, so if the rules
improve the test fails and this report must be updated in the same change.

## 9. Recommendation

```text
Loop          : production ready
Risk boundary : NOT production ready (paraphrase recall 0%)
```

1. Do not rely on the risk boundary for unenumerated phrasing. Until it changes,
   prohibited-content detection is effectively limited to wording already in
   `rules/filter_rules.json`.
2. Treat the plugin as an **assistive** risk signal on the current loop, not as
   the sole control; keep human review between `review_required` and publication.
3. Priority order for closing the gap, cheapest first: broaden rule coverage
   against a curated adversarial corpus → add negation/stem handling → introduce
   a separately injected semantic evaluator with a documented timeout and error
   contract (never inside the core).
4. Re-run `python -m production.risk_recall` after any rule change, and update
   section 7.1 and the pinned test together.
