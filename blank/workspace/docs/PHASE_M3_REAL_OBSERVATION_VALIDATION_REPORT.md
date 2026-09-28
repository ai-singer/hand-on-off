# Phase M3 — Real Observation + Template Discovery Validation

**Status: PASS WITH ISSUES**

**Correct description of what this achieves:**
> *validated on a collected synthetic observation set.*

M3 replaces M2's mock observer with a **real observation adapter** that decodes
and analyses actual image bytes. The chain runs end to end:
`PNG on disk → pixel analysis → StructuralObservation → similarity → clustering →
creator visual pattern`, and it is scored against labels that were fixed before
any of that code ran.

Two findings dominate this phase and both are uncomfortable:

1. **M2's similarity threshold does not transfer.** Calibrated on synthetic
   declared structure, `0.90` loses 22–32% of true same-template pairs on real
   observations. M3 re-measured and recommends much lower.
2. **The observer's layout classifier is weak** (micro F1 ≈ 0.33). It does not
   harm template discovery, which is what M3 was asked to validate, but it is a
   real deficiency and is reported as such rather than buried.

---

## 1. Architecture

```
 sample spec ──▶ PNG on disk            (real bytes, real compression)
                     │
                     ▼
        StdlibPixelBackend               real pixel analysis, no CV library
          ├─ decode PNG (zlib/struct)
          ├─ build normalized working grid
          ├─ connected components of similar colour
          ├─ text bands by luminance ALTERNATION (never recognition)
          ├─ clip bands at neighbouring visual blocks
          ├─ charts/tables by interior grid-line structure
          └─ roles from position / size / layer / saturation / texture
                     │
                     ▼
            FrameObserver                ⟵ only depends on VisionBackend
          ├─ layout_evidence      ┐
          ├─ visual_evidence      │ four mandatory families
          ├─ asset_evidence       │
          └─ cross_modal_evidence ┘
                     │
                     ▼
          ObservationResult              M1 observation + provenance
                     │
                     ▼
        ObservationSetBuilder            reconstructs M2 VisualSample
                     │
                     ▼
   similarity ─▶ clustering ─▶ CreatorVisualPattern
   (M2, unchanged)  (M2, unchanged)   (new in M3)
```

**Nothing in M2 was modified.** Similarity, clustering, and artifact integration
consume the same M1 `StructuralObservation` as before and cannot tell that the
producer changed. That was the point of building the contract first, and M3 is
the first phase to actually cash it in: swapping a mock for real perception was
an additive change, not a rewrite.

### Backend adapter

`VisionBackend` is a four-method protocol: `detect_regions`,
`detect_visual_roles`, `detect_style_features`, `detect_text_visual_alignment`.
Three implementations ship — real pixel analysis, manual annotation, and the M2
mock descriptor — and a test asserts the observer's source contains no reference
to any concrete backend.

The protocol has **no text field**. An OCR-only backend cannot satisfy it even if
someone wrote one, because there is nowhere to put the characters.

### Anti-OCR enforcement at the pixel level

This is the phase's hardest boundary and it is enforced structurally, not by
convention:

* A text region is located by **luminance alternation** — a row of text reverses
  light/dark repeatedly; a boundary between two flat blocks steps once and stays
  there. Counting *reversals* rather than raw deltas is what keeps a coloured
  block from reading as text.
* A text region's **role** comes from position, extent, and layer: full width at
  the top is a title, full width at the bottom is an action area, narrow and low
  is a caption. An image reading "BUY NOW" produces an action area only if a band
  genuinely occupies a full-width strip at the bottom of the frame. The words are
  never read, so they cannot drive the structure.
* `ocr_text` is absent from the admissible evidence-source vocabulary, and a test
  asserts no OCR-like identifier appears anywhere in the package.
* An observation grounded only in transcription is rejected outright.

---

## 2. Observer implementation

| Component | Lines | Role |
| --- | --- | --- |
| `observation/interface.py` | 273 | `VisualSource`, `ObservationResult`, `EvidenceRecord`, `VisionBackend`, completeness rules |
| `observation/image_observer.py` | 651 | `StdlibPixelBackend` — real pixel analysis |
| `observation/frame_observer.py` | 627 | Backend output → evidence-complete observation; video sequences |
| `observation/manual_backend.py` | 184 | Manual annotation and M2 mock backends |
| `observation/observation_result.py` | 237 | Observation sets; reconstruction into M2 samples |
| `observation/pixel/png_codec.py` | 282 | Dependency-free PNG codec |
| `observation/pixel/primitives.py` | 475 | Components, text bands, colour statistics |
| `observation/calibration.py` | 391 | Four-quadrant measurement and threshold selection |
| `observation/benchmark_dataset.py` | 342 | 54 labeled cases |
| `observation/benchmark_runner.py` | 497 | End-to-end run and scoring |
| `observation/evaluation.py` | 358 | Detection / clustering / pattern metrics |
| `observation/corpus.py` | 659 | Synthetic image corpus generator |
| `pattern/distillation.py` | 345 | `CreatorVisualPattern` distillation |

The project declares `dependencies = []`, so image I/O had to be written from
scratch on `zlib` and `struct`: 8-bit RGB/RGBA, non-interlaced, all five filter
types on read with adaptive selection on write. Round-trips are verified
byte-exact by test.

**Evidence completeness.** Every observation must report all four families. A
family a backend cannot determine appears as a zero-strength record plus a
recorded warning. Layout, visual, and asset evidence must be non-zero.
Cross-modal is the one family permitted to be zero, because it describes a
*relation* and some compositions genuinely lack one — a full-bleed image whose
overlaid text falls below the detection floor has no relation to report, and
demanding one would force fabrication.

---

## 3. Dataset description

**Source: generated, not collected.** The corpus is rendered from ten structural
template specifications into real 480×720 PNGs, with grain, gradients, rounded
corners, and ragged text edges. The observer receives bytes only; it never sees a
spec. This is what makes the validation real — but it is **not** social-media
material, and no 爆款 post was collected, viewed, or measured.

- **10 templates**, structurally distinct arrangements
- **8–12 creators**, each using 2 templates, with template **reuse across
  creators** so the `different_creator_same_template` quadrant is populated
- **Repeat samples** of one template by one creator, so
  `same_creator_same_template` is populated rather than inferred
- **40 images** in the benchmark set, **54 labeled cases**

**Corpus defects found and fixed** (each was masquerading as a detector failure):

1. A template painted text **across** its own subject block, fragmenting it. A
   `validate_templates` invariant now rejects that at corpus-build time.
2. A palette had ink and ground only ~0.16 apart in luminance, making overlaid
   text genuinely unreadable.
3. Text was rendered as **solid horizontal bars** — which reads as text to a
   human but contains no per-row alternation at all, so the detector was correct
   and the corpus was wrong.
4. A loop variable named `height` shadowed the renderer's own `height`
   parameter, corrupting the y-coordinates of every region painted after it.

**Label independence.** Labels come from the generator. The dataset module
imports neither the clustering nor the similarity package (checked on the parsed
AST, not the prose). `discover_templates` is checked to read no `template_id`,
`layout_family`, `expected_`, or `same_family` identifier. In the runner,
discovery executes *before* any family label is read, and a test asserts that
ordering.

---

## 4. Similarity calibration

780 pairs over 40 real observations. M2's synthetic `0.90` is explicitly not
reused.

| Quadrant | n | mean | median | min | max |
| --- | --- | --- | --- | --- | --- |
| same_creator_same_template | 32 | 0.833 | 0.848 | 0.512 | 0.996 |
| same_creator_different_template | 48 | 0.343 | 0.352 | 0.196 | 0.612 |
| different_creator_same_template | 53 | 0.799 | 0.788 | 0.484 | 0.998 |
| different_creator_different_template | 647 | 0.385 | 0.377 | 0.182 | 0.844 |

**The classes overlap.** Same-template minimum 0.484 vs different-template
maximum 0.844 — a gap of **−0.360**. Youden's J selects **0.646**
(precision 0.854, recall 0.965, F1 0.906).

An independent threshold sweep against the benchmark's family labels shows why
the choice matters:

| Threshold | pairwise P | pairwise R | F1 | false merges | missed pairs |
| --- | --- | --- | --- | --- | --- |
| 0.646 (calibrated) | 0.759 | 1.000 | **0.863** | 27 | 0 |
| 0.84 | 1.000 | 0.761 | 0.864 | **0** | 16 |
| 0.90 (M2 synthetic) | 1.000 | 0.676 | 0.806 | 0 | **12** |

At M2's `0.90`, **one in three same-template pairs is missed**. Every false merge
in the corpus involves a pair that also appears as a true match elsewhere, so
both failure modes are visible at once.

**A structural contributor, documented not patched.** M2's similarity contract
scores an *undeclared* comparable field as neutral (0.5) rather than as
agreement. When `text_style` is absent on both sides — common for real
observations — an otherwise identical pair tops out at **0.955, not 1.0**.
Observations that cannot evidence typography therefore have a lower attainable
ceiling, which compresses the positive class downward and is one reason the
synthetic threshold transfers poorly. M3 is forbidden from changing the M2
contract, so this is pinned by a test and recorded here instead.

---

## 5. Clustering results

Average-linkage agglomeration over real observations, threshold 0.646,
`provenance_agnostic`:

| Metric | Value |
| --- | --- |
| Pairwise precision | **0.759** |
| Pairwise recall | **1.000** |
| Pairwise F1 | **0.863** |
| true positives / false positives | 85 / 27 |
| true negatives / false negatives | 668 / 0 |
| Clusters | 8 (6 recurring) over 40 samples |

Recall is perfect: no same-template pair was split. The cost is 27 false merges.
At threshold 0.84 the trade inverts to precision 1.000 / recall 0.761.

Benchmark cases by group:

| Group | Passed |
| --- | --- |
| same-template detection | **12 / 12** |
| different-template separation | **12 / 12** |
| negative cases (same creator, different template) | **10 / 10** |
| sequence consistency | 6 / 8 |
| creator pattern extraction | 3 / 12 |
| **Total** | **43 / 54** |

The two groups M3 was chartered to validate — grouping the same and separating
the different — are perfect. The two that fail are downstream of the weak layout
classifier and of full-bleed text detection, both discussed in §7.

---

## 6. Pattern distillation evidence

Patterns are abstracted **strategy**, not material. A `CreatorVisualPattern`
carries:

```
pattern_id, cluster_id, support, cohesion, confidence, creator_ids
layout_strategy : ["headline_top", "subject_center", "cta_bottom"]
hierarchy       : ["attention_entry", "information_block", "action_area"]
style_pattern   : ["high_contrast", "large_typography"]
region_recipe   : [{role, band, presence, mean_area}, ...]
evidence        : {threshold, min_similarity, layout_class_agreement, ...}
```

A test asserts the serialised pattern contains no `.png`, `.jpg`, `base64`,
`pixels`, `asset_reference`, `bitmap`, or `path`. Traits are abstract labels
(`high_contrast`), never values (never a colour triple). The abstraction is an
aggregate across members, so only agreed-on traits survive — a trait in one
member and absent from the rest does not enter the pattern.

| Pattern metric | Value |
| --- | --- |
| Patterns distilled | 8 |
| Ground-truth groups recovered | 8 / 10 |
| Purity (mean dominant-template share) | **0.912** |
| Coverage | 1.000 |

**This is automated agreement, not human agreement.** No human rater scored
these outputs; the evaluator says so in its own JSON output
(`measurement_note`) rather than letting "agreement" imply validation it does
not have.

---

## 7. Failure analysis

### 7.1 Layout classification is weak (micro F1 ≈ 0.33)

Per family:

| Family | P | R | F1 |
| --- | --- | --- | --- |
| image_left_text_right | **1.000** | **1.000** | **1.000** |
| single_column | 0.667 | 0.250 | 0.364 |
| list_stack | 0.286 | 1.000 | 0.444 |
| image_top_text_bottom | 0.000 | 0.000 | 0.000 |
| three_card / two_column / full_bleed_overlay / mixed_irregular | 0.000 | 0.000 | 0.000 |

Two distinct causes:

* **`list_stack` over-predicts.** It is the terminal fallback for text-heavy
  frames, so every layout whose geometry is not recognised lands there. The
  class is being used as a dustbin rather than as a prediction.
* **Full-bleed layouts collapse.** T04 and T06 place text over a full-bleed
  block. The text is genuinely not detectable at working-grid resolution, so the
  observation degenerates to a bare subject and every such sample looks alike.
  That is an honest detection limit, not a bug — but it means `full_bleed_overlay`
  cannot currently be evidenced.

Note that `image_left_text_right` — the one family the detector can evidence from
clean geometry — scores perfectly. The mechanism works; the vocabulary is too
ambitious for the available evidence.

**Impact is bounded.** `layout_template_class` is one of four inputs to M2's
structure dimension, weighted 0.25 within it, so 7.5% of total similarity.
Clustering reaches F1 0.863 and pattern purity 0.912 *despite* it. But pattern
extraction (3/12) reads layout strategy directly, so it inherits the weakness in
full.

### 7.2 Four benchmark cases fail for a documented contract reason

`sequence-04-T04` fails because its frames report no cross-modal evidence: the
overlaid text is not detectable, so no text/visual relation exists. The observer
records a warning and accepts the gap; the case then flags the incomplete
observation. This is the completeness rule working as designed — an unsupported
claim is rejected rather than fabricated — but it does surface as a case failure.

### 7.3 Sequence consistency (6/8)

Two sequences observe inconsistently across frames. Same root cause: within-family
jitter moves a sample across a decision boundary in the layout classifier, so
frames of one sequence receive different layout classes. Clustering is unbothered
(the frames still group together), but the observation is not stable.

### 7.4 Observation cost

Rendering and analysis take ~140 s for 40 images at 480×720. The bottleneck is
the pure-Python flood fill and box downscale. Fine for a validation corpus,
unusable at scale — see §9.

---

## 8. Limitations

1. **The corpus is synthetic.** Ten generated templates, no real social-media
   material. Every number here describes pipeline behaviour on controlled input.
   No 爆款 pattern was discovered because no 爆款 material was examined.
2. **Ten templates is a small vocabulary.** The overlap in §4 may narrow or widen
   substantially with real design diversity.
3. **The threshold is calibrated on 780 pairs from 40 images.** It is a measured
   value, not a universal constant, and must be re-derived on any new corpus.
4. **Classes overlap, so no threshold is correct.** At 0.646 precision is 0.759;
   at 0.84 recall is 0.761. The operator must choose which error hurts more, and
   M3 does not make that choice for them.
5. **Layout classification F1 ≈ 0.33** (§7.1). Report it; do not ship it as a
   classifier.
6. **Full-bleed overlaid text is not detected** at working-grid resolution.
7. **No temporal model.** Video is a sequence of independently observed frames
   with a transition count. No shot boundaries, no pacing, no motion.
8. **No real annotation exists.** The manual backend is exercised only with
   synthetic annotations written by tests.
9. **Pattern strategy vocabulary is small** — roughly a dozen moves. It cannot
   express composition subtleties.
10. **O(n²) similarity and pure-Python pixel work** (§7.4).
11. **Not connected to the live pipeline.** `DistillationEngine` still validates
    against the baseline schema only; M3 is proven *compatible*, not *wired in*.
12. **No content generation, no deployment.** Nothing was generated and nothing
    was deployed anywhere.

---

## 9. Suggested next steps (Phase M4)

1. **Fix or narrow the layout vocabulary.** Either improve full-bleed text
   detection (higher-resolution band analysis) or reduce the claimed vocabulary to
   what the observer can actually evidence. Claiming eight classes and delivering
   one is worse than claiming two and delivering both.
2. **Replace the `list_stack` dustbin** with an explicit `mixed_irregular` or
   `undetermined` outcome, so a non-recognition is recorded as such instead of
   masquerading as a prediction.
3. **Revisit the undeclared-field penalty in the similarity contract.** §4 shows
   it compresses the positive class. This requires a contract revision, which M3
   was not authorised to make — it is the first item that needs one.
4. **Choose the operating point deliberately.** Precision-first (0.84) or
   recall-first (0.646) should be an explicit, recorded product decision.
5. **Replace the corpus with real material** under a licensing and privacy review
   that M3 was not scoped to perform. Everything downstream gets more meaningful
   at that point.
6. **Replace `StdlibPixelBackend` with a real detector behind the same protocol.**
   The seam is proven; a C-backed or model-backed implementation drops in without
   touching similarity, clustering, or distillation.
7. **Add a temporal model** so sequence consistency is a property of the observer
   rather than a hope.
8. **Wire into `DistillationEngine`** once the isolation boundary is revisited,
   and bump the artifact schema to carry discovery output first-class.

---

## 10. Explicit non-claims

- ✗ **No 爆款 regularity was discovered.** The corpus is generated; no real post
  was examined.
- ✗ **User aesthetics were not modelled.** Nothing here represents taste.
- ✗ **No production capability.** Single-process, in-memory, ~140 s per 40 images.
- ✗ **Not deployed to 小龙虾.** Nothing was deployed.
- ✗ **No content was generated.** M3 produces observations, clusters, and abstract
  strategy descriptions — never an image.
- ✗ **Not human-validated.** Pattern agreement is automated agreement against
  generator labels. No human rater was involved.
- ✗ **The similarity number is not an embedding distance.** It is explainable
  structural comparison over closed vocabularies.
- ✗ **The layout classifier is not usable.** Micro F1 ≈ 0.33.

---

## 11. Verification performed

| Check | Result |
| --- | --- |
| Full test suite | **2417 tests, OK** |
| New M3 tests | **156, all passing** |
| `python -m compileall` | exit 0, no errors |
| JSON validation (all `*.json` in workspace) | 0 invalid |
| Secret scan (new M3 sources) | 0 hits |
| Isolation | **0 tracked files modified**; all 20 new files are additions |
| `risk_evaluation/`, `runtime/`, `production/`, `workflows/`, `artifact/`, `security/`, `plugins/` | untouched |
| M1 contract, M2 similarity contract, existing artifact schemas | untouched |
| Semantic evaluator, freeze files, benchmark registry | untouched |
