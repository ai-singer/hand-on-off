# Multimodal Creator Distillation Contract

**Phase M1 — protocol construction only.**
Status: contract defined, schema added, 92 tests passing.

> **Scope statement.** This document and the code beside it establish a
> *protocol*. They do **not** implement visual distillation. No image or video
> was generated, no model was trained, no external asset was fetched, and no
> image was ever read by this track. Nothing here may be described as "visual
> distillation is implemented", "viral templates were discovered", or "image
> patterns are understood". M1 builds the vocabulary, the storage surface, the
> classification rules, and the checks that a later phase must satisfy.

---

## 1. The problem this contract solves

The framework already has a Universal Distillation Framework with four text
signals (`topic_candidate`, `content_template`, `knowledge_unit`,
`style_pattern`) and four source types (`document`, `data`, `video`, `image`).

Images and videos are currently consumed **as text**: their pixels are
flattened into a string, and only the string survives into the artifact. That
works for *what a post says* and cannot express *what a post looks like*.

Given 100 top-performing posts that share one background, one title zone, one
card layout, one colour system, and one image rhythm, the present artifact
cannot store a single one of those regularities. The failure is not missing
perception — it is a missing **vocabulary and storage surface**.

Phase M1 fixes only that: it defines what visual distillation should discover,
how it enters the artifact, which layer owns which part, and how text and
vision are related.

---

## 2. Question 1 — What should visual distillation discover?

Five families of **structure**, never text.

### 2.1 Visual signals (`visual_patterns`)

| Signal | What it captures | Typical structural fields |
| --- | --- | --- |
| `visual_template` | A recurring visual family | `regions[]`, `alignment`, `structural_recurrence` |
| `layout_pattern` | Spatial structure | `template_class`, `region_grid`, `reading_order` |
| `composition_pattern` | Subject / text / negative-space relations | `density`, `negative_space_ratio`, `subject_salience`, `dominance_order` |
| `color_pattern` | Colour system | `palette_relation`, `contrast_role` |
| `typography_pattern` | Type scale and text hierarchy | `type_scale_relation`, `hierarchy_levels`, `alignment` |

### 2.2 Asset signals (`asset_patterns`)

| Signal | What it captures |
| --- | --- |
| `subject_pattern` | Subject type (`subject_class`) |
| `image_asset_pattern` | How image assets recur and are placed (`asset_reuse`, `aspect_band`, `placement`) |
| `chart_pattern` | Chart visual structure (`chart_class`) |
| `cover_pattern` | Cover structure (`cover_role`) |

### 2.3 Cross-modal signals (`cross_modal_patterns`)

| Signal | What it captures |
| --- | --- |
| `text_visual_alignment` | How a text signal relates to a visual structure |
| `hook_visual_alignment` | How the opening hook relates to its visual |
| `page_sequence_pattern` | Multi-page visual rhythm |

### 2.4 The structural foundation: regions and geometry

Every visual claim rests on **regions** — normalized boxes in a 0..1 frame,
each with a role from a closed universal vocabulary (`background`, `header`,
`title`, `subtitle`, `body`, `caption`, `label`, `subject`, `logo`,
`watermark`, `footer`, `chart`, `data_table`, `annotation`) and a
`layer_order`.

This is the substrate that makes the anti-OCR rule enforceable. A still image
and a video frame are described by the *same* geometry vocabulary; a video
merely adds `temporal_rhythm` and sequence roles. Structure is expressed as
space and relation, not as words.

### 2.5 Constraint 1 — visual distillation must not degrade into OCR

The forbidden degenerate pipeline is:

```
image → OCR text → text distillation          ✗ NOT visual distillation
```

The contract makes this a **hard, testable boundary** in three ways:

1. `ocr_text` is classified as **non-structural evidence**. It may accompany
   structural evidence as a label channel, but a record whose entire evidence
   set is `ocr_text` is rejected (`assert_no_ocr_substitution`).
2. Any record carrying a structural field (`regions`, `region_grid`,
   `reading_order`, `alignment`, `density`, `palette_relation`,
   `type_scale_relation`) must also report at least one structural evidence
   kind.
3. Text extracted from an image or video must be tagged
   `text_is_transcribed=True`. `SourceStructure` **refuses to construct** when
   an image or video declares a textual modality without that flag, so
   transcription can never masquerade as visual observation.

Structural evidence kinds: `region_layout`, `region_geometry`,
`dominance_order`, `color_distribution`, `palette_relation`,
`type_scale_relation`, `type_placement`, `reading_order`,
`negative_space_ratio`, `alignment_relation`, `page_rhythm`,
`temporal_rhythm`, `subject_salience`, `chart_encoding`.

---

## 3. Question 2 — How does this enter the Artifact?

Via the new optional schema `schemas/multimodal_artifact.schema.json`, which
adds six fields to the existing nine and **removes none**:

| Added field | Role |
| --- | --- |
| `multimodal_envelope` | Declares contract version, which source carries which roles and modalities, geometry units, and the motif policy |
| `visual_patterns` | B1–B5 visual signals |
| `layout_patterns` | Spatial structure, first class |
| `asset_patterns` | C1–C4 asset signals |
| `cross_modal_patterns` | D1–D3 cross-modal signals |
| `creator_extension` | Plugin domain interpretation |

### 3.1 Why the baseline schema could not simply be extended

`schemas/unified_distillation_artifact.json` declares
`additionalProperties: false`. It is **sealed**: it cannot accept new fields
without being edited, and editing it is forbidden by the Phase M1 isolation
rules. This is a genuine architectural constraint, not a stylistic choice, so
the contract states compatibility precisely rather than loosely:

> **Compatibility claim.** A multimodal artifact, *projected onto the baseline's
> own declared field set*, validates against the **unmodified** baseline schema.
> The projection is derived from the baseline schema at runtime
> (`project_text_core`), not hardcoded, so it cannot drift.

Consequences that follow, and are all tested:

- The nine baseline fields keep identical names, types, and required status.
- Only three new families are required when a run claims
  `visual_capability="observed"` (`visual_patterns`, `layout_patterns`,
  `asset_patterns`). `cross_modal_patterns` is deliberately **not** required: a
  single image with no textual companion has nothing to align against, and
  demanding a cross-modal record there would be a false claim.
- A text-only artifact validates against the new schema unchanged, because
  every added field is optional.

### 3.2 Two states, and why the distinction matters

`multimodal_envelope.visual_capability` has exactly two values:

- **`contract_only`** — the extension surface exists and validates, but **no
  visual structure is claimed**. This is what Phase M1 ships.
- **`observed`** — the run claims observed visual structure, which requires the
  three visual families to be populated.

This single field is what prevents Phase M1 from being mistaken for a
capability. The shipped default is `contract_only`.

### 3.3 The builder cannot invent structure

`build_multimodal_artifact` emits a record for a signal **only if the
observation actually supplies the field that signal requires**
(`SIGNAL_REQUIREMENTS`). A bare background region cannot justify a
`subject_pattern`, `chart_pattern`, or `cover_pattern`; those records are
skipped rather than defaulted. Emitting a placeholder class would be claiming a
visual regularity that was never observed — the exact failure mode this
contract exists to prevent.

---

## 4. Question 3 — Universal layer vs Creator plugin

The split is by **authority over vocabulary**, and it is enforced in code.

| Layer | Owns | Examples |
| --- | --- | --- |
| **Universal** | The *structure vocabulary*: what a region is, what a layout template is, which evidence counts, what a pattern is called | `REGION_ROLES`, `LAYOUT_TEMPLATE_CLASSES`, `STRUCTURAL_EVIDENCE`, `SIGNAL_BINDING` |
| **Creator plugin** | *Domain interpretation*: what a structural pattern means for this audience, and what deserves attention | "a guidance-cut bar chart carries the load-bearing claim" |

Every structural record carries `layer: "universal"` and an `origin` of
`common` or `framework`. A record originating from a plugin is **rejected**
(`assert_universal_layer_shape`).

### 4.1 Constraint 2 — not all visual information may live in the plugin

A Creator plugin may **not** redefine what `layout_pattern` means. It may not
extend the region-role vocabulary, the layout template classes, or the evidence
kinds. Concretely:

- `assert_creator_extension_is_interpretive` rejects a `pattern_binding` that
  names a family outside the four real families, or that omits a
  `domain_meaning`.
- A plugin extension must acknowledge the universal vocabulary it cannot
  redefine, via `creator_extension.may_not_redefine`.
- **A plugin's domain vocabulary is free-form but inert.** A plugin can store
  `{"region_role": ["earnings_banner"]}`, yet a *record* using
  `role: "earnings_banner"` is still rejected, because the universal region
  vocabulary did not change. This is tested
  (`test_plugin_cannot_add_a_region_role`): the plugin got its vocabulary, and
  the structure contract is untouched.

The boundary in one line: **plugins say what structure means; the universal
layer says what structure is.**

---

## 5. Question 4 — How are text and visual related?

Through `cross_modal_patterns`, which by construction carry **both** anchors:

```json
{
  "cross_modal_type": "text_visual_alignment",
  "relation": "reinforces",
  "text_anchor": { "text_signal": "topic_candidate", "text_role": "title",
                   "excerpt": "3 mistakes investors make" },
  "visual_anchor": { "family": "layout_patterns", "pattern_id": "...",
                     "evidence_kinds": ["region_layout", "dominance_order"] },
  "source_ids": ["img-1"]
}
```

A cross-modal record that has only a text anchor, or only a visual anchor, is
rejected. This is the mechanism that keeps "text and visual are not confused" a
two-way, testable boundary rather than a naming convention.

`relation` is drawn from a closed vocabulary: `reinforces`, `contrasts`,
`illustrates`, `labels`, `duplicates`, `replaces`, `sequences`, `unrelated`.

### 5.1 The worked example from the brief

> Title: `"3 mistakes investors make"` → red warning ground, three-card
> structure, left-image-right-text layout.

This becomes one visual observation supplying regions and a layout class, plus
two cross-modal records:

| Anchor | Value |
| --- | --- |
| Text | `topic_candidate`, role `title`, excerpt `"3 mistakes investors make"` |
| Visual | `layout_patterns` → `template_class: "three_card"`, `region_grid`, `reading_order` |
| Composition | `composition_pattern` → `density`, `dominance_order`, `negative_space_ratio` |
| Colour | `color_pattern` → `palette_relation`, `contrast_role` (the warning ground) |
| Relation | `reinforces` — the text names a mistake count; the three-card grid enumerates it |

The colour and layout facts are stored as **structure**. The string
`"3 mistakes investors make"` is stored as a text signal. Neither is derived
from the other, and `text_signals_are_not_visual` asserts in both directions
that no text field appears in a visual family and no visual field appears in a
text signal.

---

## 6. Multi-page rhythm

`page_sequence_pattern` records an ordered list of
`{page_index, sequence_role, layout_template, reading_anchor,
display_density}`, with `sequence_role` from `opener`, `build`, `turn`,
`proof`, `summary`, `cta`, `interstitial`.

Rhythm is therefore expressed as an ordered sequence of **structural**
positions, not as prose about the pages. `display_density` is a coarse ordinal
(`sparse` / `balanced` / `dense`) rather than a numeric ratio, because the
contract stores relationships, not measurements.

---

## 7. Source classification

See `docs/MULTIMODAL_SOURCE_CLASSIFICATION.md`. In short: a source carries a
**set** of roles, never one label, and each role must be backed by a declared
modality. A single earnings screenshot can be a `knowledge_source`,
`visual_style_source`, `layout_source`, and `typography_source` at once.

---

## 8. What Phase M1 did NOT do

Stated plainly, because premature claims are the main risk of this phase:

- ✗ No image generation, video generation, or asset synthesis.
- ✗ No pixel reading, computer vision, or model training. Nothing in
  `multimodal_creator/` opens an image file.
- ✗ No external fetching or scraping.
- ✗ No claim that any viral template has been discovered. The system has never
  seen a real 爆款 post.
- ✗ No claim that images are understood.
- ✗ No production readiness and no 小龙虾 deployment.
- ✗ No modification to `risk_evaluation/`, `runtime/`, `production/`,
  `workflow/`/`workflows/`, `security/`, `artifact/`, the semantic evaluator,
  `taxonomy/`, the benchmark registry, regression or freeze files, or the
  `xiaolin_finance` plugin.

What M1 *did* produce is a contract that a later phase can be checked against:
a vocabulary, a storage surface, a classification rule set, and 92 tests that
fail loudly when those boundaries are crossed.

---

## 9. Open questions carried into Phase M2

1. **Observation production is unbuilt.** `StructuralObservation` records are
   caller-supplied. Who produces them — a deterministic region detector, a
   vision model, a human annotator — and how are they validated against each
   other? M1 deliberately fixes only the *shape* of an observation.
2. **Recurrence counting is per-observation.** `recurrence` and
   `structural_recurrence` are integers a caller supplies. The aggregate
   question — "these 100 posts share one layout" — needs a clustering step that
   M1 does not define.
3. **Similarity is undefined.** Nothing in M1 says when two `layout_patterns`
   are *the same* pattern. A cross-batch identity rule is required before
   "template" means anything at scale.
4. **`contrast_role` and `hierarchy_levels` are declared but barely exercised.**
   They are in the schema for completeness; their structural semantics need
   definition alongside real observations.
5. **No interoperability with the live engine.** `DistillationEngine` still
   calls the baseline schema. Wiring `multimodal_creator` in requires touching
   `distillation_core/`, which the current isolation rules reserve. The two
   validation paths are proven compatible, not yet connected.
6. **Video temporal structure is coarse.** `temporal_rhythm` is a single
   evidence kind; shot boundaries, pacing curves, and motion structure are not
   modelled.
