# Phase M2 — Multimodal Signal Extraction Prototype

**Status: PASS**
**Correct description of what this achieves:**
> *M2 validates the extraction and representation pipeline using controlled observations.*

This phase builds a working prototype that turns **declared structural descriptions**
into M1-valid multimodal artifacts. It does not understand real images, has not
discovered any viral template, has no perceptual capability, and is not deployed
anywhere. See §6 for the explicit list of non-claims.

---

## 1. Implementation scope

Phase M1 defined the contract and left six open questions. M2 answers four of
them with running code:

| M1 open question | M2 answer | Evidence |
| --- | --- | --- |
| #1 Who produces observations? | Three non-perceptual producers: hand annotation, mock extraction, and a mixture | `multimodal_creator/extraction/` |
| #2 (implicit) How is layout expressed? | Region roles + normalized boxes + layer order, validated at construction | `visual_sample.py` |
| #3 When are two visual templates similar? | A four-dimension, fully decomposable structural similarity contract | `multimodal_creator/similarity/` |
| #4 What does "recurring" mean? | Deterministic average-linkage clustering with recorded evidence | `multimodal_creator/clustering/` |

Delivered:

1. **Observation Producer** — `VisualSample` → M1 `StructuralObservation`, supporting
   layout (region boxes, layer order), visual (colour family, composition),
   asset (subject role), and cross-modal (text/visual region relationship).
2. **Template Similarity** — explainable structural similarity over geometry,
   structure, style, and asset, returning a 0.0–1.0 score with per-dimension
   decomposition and machine-readable difference codes.
3. **Template Discovery** — clusters visual families from multiple samples,
   recording cluster evidence, the similarity threshold, and member ids.
   No cluster is ever specified by hand.
4. **Artifact Integration** — Observation → Pattern Extraction → Artifact, producing
   `visual_patterns`, `layout_patterns`, and `cross_modal_patterns` while
   preserving the M1 universal/plugin boundary.
5. **Prototype Benchmark** — 30 synthetic cases in three groups of ten.

Explicitly out of scope, and not attempted: production system, model training,
deployment, content generation, real image input.

---

## 2. New files

| File | Lines | Purpose |
| --- | --- | --- |
| `multimodal_creator/extraction/__init__.py` | 62 | Extraction surface |
| `multimodal_creator/extraction/visual_sample.py` | 368 | Declarative sample, region/subject/typography specs, provenance |
| `multimodal_creator/extraction/mock_vision_extractor.py` | 239 | Deterministic sample → observation |
| `multimodal_creator/extraction/cross_modal_candidates.py` | 328 | Geometry-derived text/visual relations |
| `multimodal_creator/extraction/observation_producer.py` | 270 | Producer, batch, annotation path |
| `multimodal_creator/similarity/__init__.py` | 55 | Similarity surface |
| `multimodal_creator/similarity/similarity_contract.py` | 733 | The four-dimension similarity contract |
| `multimodal_creator/clustering/__init__.py` | 47 | Clustering surface |
| `multimodal_creator/clustering/template_discovery.py` | 408 | Agglomerative discovery with evidence |
| `multimodal_creator/benchmark/__init__.py` | 35 | Benchmark surface |
| `multimodal_creator/benchmark/cases.py` | 764 | 30 synthetic cases |
| `multimodal_creator/benchmark/runner.py` | 334 | Benchmark harness and label-agreement scoring |
| `multimodal_creator/integration.py` | 262 | Observation → Pattern → Artifact |
| `docs/PHASE_M2_MULTIMODAL_EXTRACTION_REPORT.md` | this file | Phase report |
| `tests/multimodal_extraction/test_observation_and_geometry.py` | 458 | 62 tests |
| `tests/multimodal_extraction/test_similarity_and_clustering.py` | 421 | 54 tests |
| `tests/multimodal_extraction/test_integration_and_benchmark.py` | 319 | 41 tests |

**Exactly one existing file was modified**: `multimodal_creator/__init__.py`, to
export the new M2 surface (`integrate_samples`, `ArtifactIntegration`, and the
integration version). No file under `risk_evaluation/`, `runtime/`,
`production/`, `workflows/`, `security/`, `artifact/`, `evaluation/`, or
`plugins/xiaolin_finance/` was touched, no test file was modified, and no artifact
schema was changed. Verified with `git diff --name-only HEAD`.

---

## 3. Prototype architecture

```
   VisualSample  (declared structure: boxes, layer order, colour family,
        │          subject role, type scale, provenance)
        │
        ├── MockVisionExtractor ──────▶ StructuralObservation   (M1 type)
        │      derives evidence kinds, multi-role set, alignment
        │
        └── candidates_from_sample ───▶ CrossModalCandidate[]
               geometry-derived text↔visual relation
        │
        ▼
   ObservationBatch  ──────────────────────────────┐
        │                                          │
        ▼                                          ▼
   similarity_matrix                     build_multimodal_artifact
   (4 dimensions, decomposable)          (M1 builder, layer=universal)
        │                                          │
        ▼                                          │
   discover_templates                              │
   (average linkage, threshold, evidence)          │
        │                                          │
        └──────────────► integrate_samples ◄───────┘
                              │
                              ▼
                    M1-valid multimodal artifact
                    + TemplateDiscovery (beside, not inside)
```

### 3.1 Observation production is deliberately blind

`MockVisionExtractor` is named "mock" because it performs no perception. It is a
pure function from a declared sample to an M1 observation:

| Declared fact | Evidence kind it justifies |
| --- | --- |
| region boxes | `region_layout`, `region_geometry` |
| more than one layer order | `dominance_order` |
| declared layout class | `reading_order` |
| image/chart subject present | `subject_salience` |
| `chart` region or chart class | `chart_encoding` |
| palette relation | `color_distribution`, `palette_relation` |
| text style | `type_placement`, `type_scale_relation` |
| non-default negative space | `negative_space_ratio` |
| declared alignment | `alignment_relation` |
| video frame | `temporal_rhythm` |

`ocr_text` is never emitted, and there is no code path that could emit it. A test
asserts that no module in the package imports `PIL`, `cv2`, `pytesseract`,
`numpy`, `torch`, `requests`, or `urllib`, and that the extraction package
contains no `open(`, `urlopen`, or socket use. The anti-OCR boundary holds
**architecturally**, not by a check someone could forget.

### 3.2 Cross-modal relations come from geometry, not text

`geometric_relation` classifies a text box against a visual box as `left_of`,
`right_of`, `above`, `below`, `overlaps`, `contains`, `contained_by`,
`same_band`, or `diagonal` using normalized boxes and layer order. That spatial
fact maps to a semantic relation (`labels`, `illustrates`, `reinforces`) through a
**fixed, published table**. A caller may override it by *declaring* a relation
explicitly, and the candidate then records `declared=True`.

So a reader can always tell measurement from interpretation. The prototype never
infers meaning from text content, because it has no text content.

The anchor is chosen by role-weighted area, not raw area. A full-frame
`background` box has the largest area of anything in a sample, so ranking by area
alone would make every relation read "contained_by the background" — true but
useless. `subject`, `chart`, and `data_table` are weighted 4×, `background` 0.25×.

### 3.3 Similarity is a contract, not an embedding

**This is not a visual embedding.** No learned representation, no vector space,
no nearest-neighbour index, no pixel access. It is a transparent weighted
comparison:

| Dimension | Weight | Compares |
| --- | --- | --- |
| `geometry` | 0.35 | Region position (area-weighted), size, layer order — matched **by role**, not index |
| `structure` | 0.30 | Layout graph (Jaccard over region-pair relations), template class, alignment, density |
| `style` | 0.20 | Colour family, palette relation, contrast role, type scale and hierarchy depth |
| `asset` | 0.15 | Subject class, salience, placement |

Layout carries 65% because a template is fundamentally a spatial arrangement.
Asset carries the least because creators swap subjects far more readily than
layouts.

Every result is **decomposable and contestable**: `score` equals the sum of the
weighted dimension contributions (asserted by a test), each dimension reports its
raw score and sub-details, and `difference_codes` names every disagreement
(`layout_template_class_mismatch`, `region_geometry_differs`, …). `explain()`
renders the whole thing for a human.

Two design decisions worth recording:

- **Position and size are scored separately**, and position error is weighted by
  the area a role occupies. A title that moves across the canvas changes a layout
  far more than resizing a caption, and the score says so.
- **"Not declared" is not "differs".** A field absent on one side scores neutrally
  (0.5) rather than as a mismatch, so a sample is not punished for omitting
  typography.

Provenance is a first-class input. `cross_provenance` mode marks same-creator
pairs **non-comparable** rather than returning a misleadingly high score — one
creator repeating themselves is not evidence of a shared template.

### 3.4 Discovery is deterministic and evidence-carrying

Average-linkage agglomerative clustering, chosen specifically because single
linkage chains: with single linkage, A~B and B~C merges A and C even when they
are nothing alike, manufacturing templates out of coincidences.

Properties that are tested, not asserted:

- **Never hardcoded.** `discover_templates` takes samples and a threshold. A test
  greps its source to confirm the words `same_family` and `expected_` never appear
  in it — the labels cannot leak in.
- **Deterministic.** Ties break on cluster identifier, so reversing the input
  order produces identical cluster ids.
- **Content-addressed ids.** A cluster id is `family-` plus its sorted member ids,
  so an id cannot drift while its members stay the same.
- **Evidence-carrying.** Each cluster records the threshold, mean and minimum
  internal similarity, creator count, dominant layout class, layout-class
  agreement, and every merge step with the pairs that justified it.

The threshold is `0.90`, calibrated from the benchmark: the same-template
population scores ≥ 0.976 under geometry jitter, the different-layout population
scores ≤ 0.83, so 0.90 sits in a wide empty band. It is exposed and overridable,
and it is explicitly *not* a universal constant.

### 3.5 Integration keeps the boundaries

`integrate_samples` runs extraction → discovery → artifact and holds three
invariants, each with a test:

- **Universal/plugin.** Every structural record is emitted with
  `layer="universal"`, `origin="common"`. A plugin's contribution is confined to
  `creator_extension`. A plugin binding naming a non-existent family is rejected;
  a plugin's free-form domain vocabulary is stored but **inert** — a record using
  a plugin-invented region role is still rejected.
- **Anti-OCR.** Cross-modal relations come from geometry, so cross-modal records
  carry structural evidence by construction.
- **Additive.** The base text core is never rewritten; the result still validates
  against the unmodified baseline schema via the M1 projection proof.

Discovery results live **on the result object, not inside the artifact**. The M1
schema declares `additionalProperties: false` and the brief forbids editing it, so
a sidecar key inside the artifact would either violate the contract or force a
schema edit. Keeping it beside the artifact preserves both and keeps the artifact
a pure M1 document.

---

## 4. Benchmark result

`multimodal_creator/benchmark/` — 30 synthetic cases, three groups of ten.

### Group 1: layout (10 cases) — 10/10

Ten layouts spanning the closed template-class vocabulary
(`image_left_text_right`, `image_top_text_bottom`, `three_card`,
`full_bleed_overlay`, `single_column`, `two_column`, `list_stack`, plus chart,
cover, and data-table compositions). Each asserts the extracted layout class, the
region-role multiset, text/visual region counts, the cross-modal anchor role, and
required roles and evidence kinds.

### Group 2: template similarity (10 cases) — 10/10

Five same-family pairs (identical, mild jitter, colour-only change, subject-only
change, three-card variant) and four different-family pairs, plus one honest
near-miss: two samples declaring the same layout class with **mirrored geometry**.
That case is expected to score below threshold and to emit
`region_role_absent_on_right` — a declared-class agreement must not be allowed to
hide a geometric disagreement. Each case also asserts the score is exactly the sum
of its weighted contributions.

### Group 3: cross-modal alignment (10 cases) — 10/10

Ten text/visual geometries asserting the derived geometric relation, the semantic
relation, the anchor role, and whether the relation was declared or derived:
`left_of`, `below`, `above`, `contained_by` (overlay), caption-below-chart,
label-beside-image, title-above-table, text-right-of-image, corner-label-on-bleed,
and one author-declared `contrasts` where geometry says adjacency.

### Discovery: recovers the labeled groupings without seeing the labels

Discovery runs over all 40 samples in the suite at once, then the labels are used
**afterwards** to score it:

| Metric | Result |
| --- | --- |
| Same-family pairs grouped together | 5 / 5 |
| Different-family pairs wrongly merged | **0** |
| Label agreement | **1.000** |

Ten clusters emerged: four marked `recurring` (≥ 3 members), six pairs. The four
recurring families were recovered with 3–9 members drawn from 3–9 distinct
creators, dominant layout classes `image_left_text_right`,
`image_top_text_bottom`, and `three_card`, and minimum internal similarity 0.905.

**What this does and does not mean.** It means the extraction, similarity, and
clustering algorithms behave as specified on controlled structural input. It says
**nothing** about performance on real posts, because the benchmark contains no
real posts — the "templates" it recovered are families the fixtures were designed
to contain. This is a protocol test, not an accuracy result.

---

## 5. Test results

**157 new tests, all passing** (62 + 54 + 41). Full suite: 2092 tests, OK.

| Required coverage area | Representative tests |
| --- | --- |
| 1. Observation schema valid | 15 (`ObservationSchemaTests`) |
| 2. Geometry normalisation | 20 (`RegionGeometryTests`, `VisualSampleValidationTests`) |
| 3. Similarity deterministic | 6 (`SimilarityDeterminismTests`) |
| 4. Similar templates cluster together | 6 (`SimilarTemplateTests`, `TemplateDiscoveryTests`) |
| 5. Different templates separate | 8 (`DifferentTemplateTests`, discovery separation) |
| 6. Cross-modal requires both anchors | 10 (`CrossModalCandidateTests`) |
| 7. No OCR degeneration | 7 (`AntiOcrRegressionTests`, `AntiOcrIntegrationTests`) |
| 8. No plugin override of universal structure | 7 (`LayerBoundaryTests`) |
| Integration, provenance, benchmark, contract shape | the remainder |

The eight required areas are all covered; the counts above name the classes that
target each area, and several classes contribute to more than one.

Notable assertions beyond the required list:

- A score equals the sum of its weighted contributions (`test_score_is_decomposable_into_contributions`).
- Comparison is symmetric and matrices are order-independent.
- Reversing region declaration order does not change the score.
- `discover_templates`' own source is checked to prove labels cannot leak in.
- No perception or network import exists anywhere in the package.
- The integrated artifact carries no key outside the M1 schema.
- The text core projection validates against the unmodified baseline schema.

---

## 6. Explicit non-claims

Stated plainly, because overclaiming is this phase's main risk:

- ✗ **Has not understood a real image.** No image was ever read. Every input was a
  structural declaration written by a fixture or a human annotator.
- ✗ **Has not discovered a viral template (爆款模板).** The families found are
  families the synthetic fixtures were built to contain. No real post was seen.
- ✗ **Has not reached visual capability.** There is no perception. The word "mock"
  in `MockVisionExtractor` is load-bearing.
- ✗ **Cannot generate viral content.** No generation of any kind exists in M2.
- ✗ **Not deployed to 小龙虾.** Nothing was deployed anywhere.
- ✗ **Not a production system.** Single-process, in-memory, no persistence, no
  concurrency, no service surface.
- ✗ **Similarity is not a visual embedding.** It is explainable structural
  comparison over closed vocabularies.
- ✗ **Threshold 0.90 is not calibrated on real data.** It is calibrated on 30
  synthetic cases and must be re-derived before any real use.

---

## 7. Known limitations

1. **The threshold is synthetic-calibrated.** 0.90 separates the fixture
   populations with a wide margin; it has no claim on real material. Re-deriving
   it requires real samples — which M2 deliberately did not obtain.
2. **Similarity is O(n²) and in-memory.** `similarity_matrix` computes every pair.
   At 1,000 samples that is ~500k comparisons held in a dict. A production path
   needs blocking or an index, and this prototype has neither.
3. **Vocabulary is coarse and human-authored.** `COLOR_FAMILIES` has twelve
   members, `SUBJECT_SALIENCE` four. Two genuinely different colour systems can
   land in `mixed` together. The coarseness buys explainability and costs
   resolution; that trade was made deliberately and should be revisited with real
   data.
4. **Position similarity is a linear L1 penalty.** A region moved 0.3 scores 0.7
   regardless of direction or whether it crossed a meaningful boundary (e.g. the
   frame midline). A perceptual metric would score a boundary crossing as more
   significant.
5. **No notion of template evolution.** Clusters are static. There is no way to
   express that family B is a 2025 variant of family A, or that a template drifted
   over time.
6. **Clusters can still chain through near-identical members.** Average linkage
   mitigates single-linkage chaining but does not eliminate transitivity: a chain
   of each-to-next-similar members can still merge two distant ends. The
   `min_similarity` evidence field exposes this after the fact, but the algorithm
   does not prevent it.
7. **`display_density` and `sequence_role` are barely exercised.** Video and
   multi-page structure are representable and tested for construction, but no case
   exercises a realistic multi-page rhythm.
8. **Discovery output is not yet consumable by the M1 artifact.** It sits beside
   the artifact (see §3.5) because the schema is sealed. Making it first-class
   requires a schema version bump and a migration decision that M2 was not
   authorised to make.
9. **`similarity_to_centroid` is a misnomer retained for report compatibility.**
   It is computed as mean pairwise similarity to the other members. There is no
   geometric centroid, because this is not an embedding space; the field name
   should be corrected in the next phase.
10. **No integration with `DistillationEngine`.** The prototype is proven
    *compatible* with the M1 artifact contract, not *connected* to the live
    pipeline. Wiring it in requires touching `distillation_core/`, which the
    current isolation rules reserve.

---

## 8. Suggested next steps (Phase M3)

1. **Decide the schema path.** Either bump to `multimodal_artifact.schema.json`
   v2 with a `template_discovery` family, or keep discovery as a sidecar and
   formalise that as the contract. This is the blocking decision for everything
   downstream.
2. **Connect to the engine, or explicitly keep the prototype standalone.** If
   connecting, the isolation boundary needs revisiting; `DistillationEngine.distill`
   currently validates against the baseline schema only.
3. **Replace the mock producer with a real observer behind the same interface.**
   `StructuralObservation` is already the seam: a real region detector emits the
   same type, and every similarity, clustering, and integration test keeps working
   unchanged. That is the payoff of M1's contract-first approach and it should be
   cashed in here.
4. **Calibrate the threshold on real samples** once a real observer exists, and
   report the score distribution rather than a single number.
5. **Address clustering scalability** before sample counts grow: blocking by
   dominant layout class would cut the pair count sharply.
6. **Exercise multi-page and video rhythm** with a dedicated case group, since
   `page_sequence_pattern` currently has construction coverage but no behavioural
   coverage.
7. **Rename `similarity_to_centroid`** and consider exposing the dimension weights
   as a configurable profile so a domain can re-weight without forking the contract.
