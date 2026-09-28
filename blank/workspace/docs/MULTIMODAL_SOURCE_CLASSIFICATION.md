# Multimodal Source Classification

**Phase M1.** Companion to
`docs/MULTIMODAL_CREATOR_DISTILLATION_CONTRACT.md`.

This document redefines source classification for multimodal distillation. It
does **not** replace the existing text-centric classifier; it specifies the
multi-role model that a later phase must implement, and defines the vocabulary
that model uses.

---

## 1. Why the single label had to go

`distillation_core/classifier.py` returns exactly one `MaterialRole` per
source: `topic_candidate`, `content_template`, `knowledge_unit`, or
`style_pattern`.

For text that is correct and sufficient. For multimodal material it is
structurally wrong, because one artifact routinely answers several different
questions at once:

> **An earnings screenshot** contains the reported revenue figures, the visual
> treatment the creator uses for every earnings post, the card layout that
> holds those figures, and the typographic hierarchy that ranks them.

Forcing that into one label either throws away three quarters of the
information or invites an arbitrary choice. A single label is a lossy
projection of a genuinely multi-dimensional fact.

**The contract therefore uses a set of roles, not a label.**

---

## 2. The multi-role model

A source is classified along two independent axes.

### Axis 1 — Modalities declared

`textual`, `visual`, `temporal`, `structured`

Modality is what the source *is*. It is declared, not inferred.

### Axis 2 — Roles carried

`knowledge_source`, `visual_style_source`, `layout_source`,
`composition_source`, `color_source`, `typography_source`, `subject_source`,
`chart_source`, `cover_source`, `sequence_source`, `hook_source`

Role is what the source is *used for*. A source carries one or more roles.

A role is meaningful only if the matching modality was declared:

| Role group | Requires modality |
| --- | --- |
| `visual_style_source`, `layout_source`, `composition_source`, `color_source`, `typography_source`, `subject_source`, `chart_source`, `cover_source`, `sequence_source` | `visual` |
| `knowledge_source`, `hook_source` | `textual` |

The reverse direction is enforced too: declaring a `visual` modality with **no**
visual role is rejected, because a visual source that contributes nothing
visual is a classification error rather than an empty case.

### Worked example

```
source_id:  img-earnings-01
source_type: image
modalities:  {visual, textual}
roles:       {knowledge_source, visual_style_source, layout_source,
              typography_source}
text_is_transcribed: true
```

One source, four roles, two modalities. It is simultaneously evidence for a
knowledge unit, a visual family, a layout template, and a type hierarchy. No
information is discarded and no arbitrary winner is chosen.

---

## 3. Source types redefined

The four existing `SourceType` values keep their names. What changes is what
they are understood to carry.

### `image`

- Default modality: `visual`. A textual modality must be **declared
  explicitly**.
- Text inside an image is transcription by construction. `SourceStructure`
  refuses to construct an image with a `textual` modality unless
  `text_is_transcribed=True`.
- Typical roles: `visual_style_source`, `layout_source`, `composition_source`,
  `color_source`, `typography_source`, `subject_source`, `chart_source`,
  `cover_source`, plus `knowledge_source` when the image carries data.

### `video`

- Default modality: `visual`. Adds `temporal`.
- The **only** source type permitted to report `temporal_rhythm`; an image
  observation claiming it is rejected at construction.
- Adds `sequence_source` and `hook_source` roles, because a video has ordered
  structure and an opening beat that a still image does not.
- Frame geometry uses the same normalized region vocabulary as a still: only
  the temporal axis is new.

### `document`

- Default modality: `textual`. This is the one source type whose text is
  **native** rather than transcribed, which is why the transcription rule does
  not apply to it.
- A document may still be a visual source (a designed PDF page), in which case
  `visual` is declared and visual roles may be attached.
- May declare `structured` when it carries tables.

### `data`

- Default modalities: `structured` and `textual`.
- Primarily a `knowledge_source`. It may declare `visual` when it ships
  rendered charts, at which point `chart_source` becomes available.

---

## 4. Classification is not a single pass

Because roles overlap, classification cannot be a function
`source → one label`. It is:

```
source → {modalities} × {roles} → {observations} → {pattern records}
```

Each `(modality, role)` pair licenses a different family of signals:

| Role | Licenses |
| --- | --- |
| `knowledge_source` | `knowledge_unit` (text signal) |
| `visual_style_source` | `visual_template` |
| `layout_source` | `layout_pattern` |
| `composition_source` | `composition_pattern` |
| `color_source` | `color_pattern` |
| `typography_source` | `typography_pattern` |
| `subject_source` | `subject_pattern` |
| `chart_source` | `chart_pattern` |
| `cover_source` | `cover_pattern` |
| `sequence_source` | `page_sequence_pattern` |
| `hook_source` | `hook_visual_alignment` |

The role a record was derived from is recorded on the record itself (`roles` on
visual patterns), so provenance from source to signal stays traceable.

### 4.1 One observation, several signals

`StructuralObservation` is the single record type that makes image and video
multi-signal without a per-medium schema. One observation may justify several
records, and the builder fans it out across families. A single video
observation in the tests yields layout, visual, and chart records
simultaneously.

---

## 5. Adoption path from the existing classifier

The existing single-label classifier stays valid and untouched. Migration is
purely additive:

1. Read `distillation_role` (existing) as before. It remains authoritative for
   text-only sources.
2. Add `modalities` and `multimodal_roles` to source metadata. Both are
   optional; `structure_from_metadata` supplies conservative defaults.
3. `LEGACY_ROLE_SUCCESSOR` maps an old single label onto its multi-role
   successor when a caller needs the bridge:

   | Legacy label | Multi-role successor |
   | --- | --- |
   | `topic_candidate` | `knowledge_source` |
   | `content_template` | `layout_source` |
   | `knowledge_unit` | `knowledge_source` |
   | `style_pattern` | `visual_style_source` |

**The legacy map is lossy and is not the migration mechanism.** It exists only
so an old label degrades sensibly. Real multi-role classification requires
declaring the roles explicitly, because the whole point is that a source
carries several.

---

## 6. What classification does not do

- It does not read pixels. Every role is declared or derived from metadata.
- It does not decide that two sources are *the same* style. That is a
  similarity question, deferred to Phase M2.
- It does not assign confidence. Confidence lives on the pattern records, not
  on the source classification, because a source's role membership is a
  declaration rather than an inference.
- It does not change `core.models.SourceType`. The four source types keep their
  meaning; only the classification *over* them became multi-role.
