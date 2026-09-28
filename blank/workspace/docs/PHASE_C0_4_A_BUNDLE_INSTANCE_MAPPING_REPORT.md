# PHASE_C0_4_A_BUNDLE_INSTANCE_MAPPING_REPORT.md

**Phase C0.4-A — Skill Bundle → Creator Instance Mapping Layer**

C0.2 projects a Creator Instance from assets. C0.3 composes a Skill Bundle from the
same assets. Nothing connected them::

```text
    SkillBundle
         |
         v   creator_mapping          ← this phase
         |
    creator_instance artifact
```

This phase is a **configuration bridge and nothing else.**

---

## 1. Mapping architecture

```text
creator_mapping/
    rules.py        the mapping contract: skill type → module, one RULE_* per field
    resolver.py     selection → skill → asset, through the C0.2 asset registry
    mapper.py       the derivation, plus bundle_instance_diff()
    provenance.py   one FieldMapping per field: skill, asset, version, rule
    validation.py   four layers
    errors.py       MappingError + 5 subtypes
```

Two ideas hold the layer together, and both are enforced rather than documented:

**1. A skill never copies a field.** A skill carries a capability name and an asset
reference — not content. Every instance field is *derived* from the resolved asset,
and every derivation cites the rule that performed it. A mapper that copied
`skill.capabilities` into the instance would be inventing content, so there is no
code path that reads a skill's own fields into an instance.

**2. An absent capability is declared, never enabled.** Generation and publishing
are unimplemented in this repository, so mapping emits them disabled with a
machine-readable reason, and `validation` **rejects** an instance that claims
otherwise. This is the same principle C0.1, C0.2 and C0.3 each enforce.

### 1.1 The bridge reads the layers, and changes none of them

The resolver holds two registries: the C0.3 **skill registry** to turn a bundle's
*selections* back into skills, and the C0.2 **asset registry** to read what those
skills are bound to. The mapping layer declares no asset path of its own — a test
asserts the package contains no asset-location literal.

---

## 2. Bundle → Instance flow

```text
SkillBundle { selections, extras, request }
      |
      |  1. RESOLVE   BundleAssetResolver
      |       for each selection: skill registry → skill → provenance.source_ref
      |       → asset registry → document   (unavailable ⇒ a declared absence,
      |                                       not an error)
      v
BundleAssets { ResolvedAsset[asset_id] }
      |
      |  2. ROUTE     SKILL_MODULE_RULES
      |       identity     → identity
      |       domain       → identity + source
      |       source       → source
      |       distillation → text_rules + visual_rules
      |       review       → risk_policy
      |       generation   → generation
      |       publishing   → publishing
      v
      |  3. DERIVE     one FieldRule per target field
      |       mode=asset         read the resolved asset, derive the value
      |       mode=structural    creator id, domain, platform, language, review flags
      |       mode=capability    routing declaration; enabled only if the asset is
      |       mode=not_available emit a marked declaration of absence
      |       mode=unavailable   no place in the document; recorded in provenance
      |
      |       The asset a field reads is selected by its OWN declared asset type,
      |       not by the module: text_rules must not read the visual asset, even
      |       though both skills share the `distillation` type.
      v
      |  4. DECLARE     capability honesty
      |       generation.enabled = false, reason = generation_capability_not_available
      |       publishing.enabled = false, reason = publishing_capability_not_available
      v
      |  5. RECORD      MappingProvenanceBuilder
      |       one {skill_id, asset_id, version, rule_id, mode} per field
      v
creator_instance artifact  →  validate → creator_contract.validate()
      |                                   → mapping validation (4 layers)
      v
bundle_instance_diff(bundle, instance) → unmapped skills / lost assets /
                                          capability changes / incomplete provenance
```

---

## 3. Field mapping table

Every target field, its rule id, its mode, and the asset it derives from. Rule ids
are cited verbatim in each field's provenance record.

### identity ← `identity` + `domain` skills

| Rule | Field | Mode | Source |
| --- | --- | --- | --- |
| `RULE_IDENTITY_001` | `creator_id` | structural | the request |
| `RULE_IDENTITY_002` | `name` | structural | derived from `creator_id` |
| `RULE_IDENTITY_003` | `domain` | structural | the request, validated |
| `RULE_IDENTITY_004` | `persona` | asset | domain skill → value-rule sections |
| `RULE_IDENTITY_005` | `audience` | not_available | `audience_model_not_available` |
| `RULE_IDENTITY_006` | `tone` | asset | distillation skill |
| `RULE_IDENTITY_007` | `platform` | structural | the request, validated |
| `RULE_IDENTITY_008` | `language` | structural | derived from the platform |

### source ← `domain` + `source` skills

| Rule | Field | Mode | Source |
| --- | --- | --- | --- |
| `RULE_SOURCE_001` | `keywords` | asset | domain skill → value rules (43 keywords) |
| `RULE_SOURCE_002` | `data_sources` | asset | two-layer declaration |
| `RULE_SOURCE_003` | `collection_rules` | not_available | `collection_rules_not_available` |
| `RULE_SOURCE_004` | `reference_creators` | not_available | `reference_creator_not_available` |

### text_rules ← `distillation` + `review` skills

| Rule | Field | Mode | Source |
| --- | --- | --- | --- |
| `RULE_TEXT_001` | `title_formula` | asset | structure template sections |
| `RULE_TEXT_002` | `structure` | asset | `text_structure_templates` |
| `RULE_TEXT_003` | `tone` | asset | distillation skill |
| `RULE_TEXT_004` | `length` | asset | platform-aware structural bounds |
| `RULE_TEXT_005` | `knowledge_boundary` | asset | review rubric questions |

### visual_rules ← `distillation` skill (**reference only**)

| Rule | Field | Mode | Source |
| --- | --- | --- | --- |
| `RULE_VISUAL_001` | `profile_id` | asset | `visual_profile_m5` |
| `RULE_VISUAL_002` | `profile_version` | asset | `visual_profile_m5` |
| `RULE_VISUAL_003` | `visual_language` | asset | M5 identity section |
| `RULE_VISUAL_004` | `attention_strategy` | asset | M5 attention section |
| `RULE_VISUAL_005` | `composition` | asset | M5 composition section |
| `RULE_VISUAL_006` | `hierarchy` | asset | M5 hierarchy section |
| `RULE_VISUAL_007` | `constraints` | asset | M5 constraints section |
| `RULE_VISUAL_008` | `provenance` | asset | M5's own provenance, carried through |

**No prompt, model reference, or image data is derivable here** — the M5 profile
cannot carry them, so the mapping cannot introduce them.

### risk_policy ← `review` skill

| Rule | Field | Mode | Source |
| --- | --- | --- | --- |
| `RULE_RISK_001` | `risk_categories` | asset | `risk_policy_reference` (4 categories) |
| `RULE_RISK_002` | `review_rules` | asset | rubric pass score + severities |
| `RULE_RISK_003` | `blocked_patterns` | asset | filter rules (37 patterns) |
| `RULE_RISK_004` | `evidence_requirement` | asset | rubric checks |
| `RULE_RISK_005` | `review_required` | structural | `true` |
| `RULE_RISK_006` | `source` | structural | `risk_evaluation` |
| `RULE_RISK_007` | `runtime_connected` | structural | **`false`** |
| `RULE_RISK_008` | `enabled` | capability | true when the asset resolved |

### generation / publishing ← `generation` / `publishing` skills

| Rule | Field | Mode | Value |
| --- | --- | --- | --- |
| `RULE_GEN_001` | `adapter_ref` | capability | `deployment.generation_adapter` |
| `RULE_GEN_002` | `input` | capability | the six runtime inputs |
| `RULE_GEN_003` | `output_format` | capability | `content_plan` |
| `RULE_GEN_004` | `quality_gate` | capability | requires `PASS` |
| `RULE_GEN_005` | `enabled` | capability | **`false`** (no adapter ships) |
| `RULE_GEN_006` | `reason` | capability | `generation_capability_not_available` |
| `RULE_PUB_001` | `platform` | capability | from the request |
| `RULE_PUB_002` | `image_requirement` | capability | platform-aware aspect ratio |
| `RULE_PUB_003` | `api` | capability | adapter + idempotency key |
| `RULE_PUB_004` | `schedule` | capability | `manual` |
| `RULE_PUB_005` | `requires_human_approval` | capability | `true` |
| `RULE_PUB_006` | `enabled` | capability | **`false`** (no publisher exists) |
| `RULE_PUB_007` | `reason` | capability | `publishing_capability_not_available` |

**47 field rules** in total.

---

## 4. Capability status

| Capability | Skill status | Asset status | `enabled` | Reason |
| --- | --- | --- | --- | --- |
| `identity` | available | available | — | — |
| `source` | declared | **unavailable** | — | keywords still derived from the domain asset; `collection_rules` and `reference_creators` declared absent |
| `text_rules` | available | available | — | — |
| `visual_rules` | available | available | — | — |
| `risk_policy` | available | available | **true** | a real policy asset backs it |
| `generation` | **declared** | **unavailable** | **false** | `generation_capability_not_available` |
| `publishing` | **declared** | **unavailable** | **false** | `publishing_capability_not_available` |

### 4.1 What "declared absent" looks like

The contract seals different fields differently, so a declaration takes the shape
the field requires. In every case a marker is present, so nothing can be mistaken
for mapped content:

| Field shape | Declaration |
| --- | --- |
| scalar string (`audience`) | `"not_available:audience_model_not_available"` |
| sealed object (`collection_rules`) | `min_notes: 0`, `rate_limit_seconds: 0`, `dedupe_by: "not_available:…"` |
| sealed array (`reference_creators`) | one entry whose `verification_method` is the marker |
| sealed object with all-inner-required (`persona`, `visual_rules.*`) | structurally valid template with the marker inside a required value |
| free object (`risk_policy` fields) | `{"not_available": true, "reason": "…"}` |

Validation accepts exactly these three declaration families and rejects anything
else, including a plausible-looking value that is not marked.

### 4.2 Partial bundles

A bundle composed for a domain with no skills still maps. The sports bundle has no
identity or domain skill, so `identity.persona` and every `visual_rules` field are
declared absent, and the instance validates. **A gap is reported, never filled.**

---

## 5. Provenance design

Each of the 47 fields carries exactly the four links the brief requires:

```json
"visual_rules.profile_id": {
  "field": "visual_rules.profile_id",
  "skill_id": "visual-style-distillation",
  "asset_id": "visual_profile_m5",
  "version": "1.0.0",
  "rule_id": "RULE_VISUAL_001",
  "mode": "asset"
}
```

### 5.1 Where it lives

The C0.1 provenance block is **sealed** to its declared keys, and so is every module
document. The contract does, however, declare one open object —
`provenance.field_provenance` — and the mapping layer stores everything there:

```json
"provenance": {
  "field_provenance": {
    "fields":  { "<module>.<path>": { skill_id, asset_id, version, rule_id, mode } },
    "modules": { "<module>": { has_available_source, asset_id, asset_status, … } },
    "rule_count": 47
  },
  "generated_by": "creator_mapping.mapper c0.4-a bundle=<id> rules=47"
}
```

No contract change was needed, and the mapping identity is carried in `generated_by`
because the provenance block has no other open field. When an instance is written to
disk, `provenance.json` receives the full audit report alongside it.

### 5.2 Truthful attribution

A module may be fed by more than one skill. `identity.persona` and `source.keywords`
are derived from the **domain** skill's value rules, while `identity.creator_id` is
structural — so provenance names the domain skill for the first two and the persona
skill for the third, even though both bind the same asset. Crediting one skill for
another's content would make the audit trail worse than useless.

---

## 6. Test result

```text
tests/creator_mapping_layer/
    test_rules.py                     38 tests
    test_mapping.py                   57 tests
    test_field_mapping.py             66 tests
    test_honesty.py                   26 tests
    test_provenance.py                41 tests
    test_validation_and_isolation.py  28 tests
                                     ─────────
                                     256 tests, OK
```

Target was ≥150; delivered **256**.

### 6.1 Required coverage

| Required area | Tests | Result |
| --- | --- | --- |
| **Mapping** — complete finance bundle, partial bundle, unavailable skill | 57 | **pass** |
| **Field mapping** — identity, visual, text, risk, generation, publishing | 66 | **pass** |
| **Honesty** — unavailable generation rejected, unavailable publishing rejected | 26, incl. every false-enable path | **pass** |
| **Provenance** — missing source rejected | 41, incl. each required key removed in turn | **pass** |
| **Regression** — C0.1 205, C0.2 340, C0.3 308 | all three re-run | **pass** |
| **Isolation** — frozen directories unmodified | 28, incl. AST analysis and SHA256 sweeps | **pass** |

### 6.2 Regression confirmation

```text
creator_contract_layer     Ran 205 tests  OK
creator_projection_layer   Ran 340 tests  OK (skipped=1)
creator_skill_layer        Ran 308 tests  OK
```

### 6.3 Isolation verification

| Check | Result |
| --- | --- |
| `creator_mapping` imports from `runtime`, `production`, `risk_evaluation`, `multimodal_creator`, `distillation_core`, `workflows`, `plugins`, `artifact` | **none** (AST analysis, not grep) |
| The seven frozen directories change during mapping or validation | **no** (SHA256 tree comparison) |
| Asset-location literals inside the package | **none** — the C0.2 registry owns them |
| Absolute paths inside the package | **none** |
| Reason codes agree across C0.2, C0.3 and C0.4-A | **asserted by test** |
| Contract version and generation inputs agree with C0.1 / C0.2 | **asserted by test** |

### 6.4 Six real defects found by the tests, and fixed

1. **`module_types` was a set of tuples, not strings.** `required_asset_type`
   returns a *preference tuple*, so intersecting it with the set of present asset
   types never matched — every module was wrongly treated as having no source. Only a
   test asserting that keywords *are* derived from an available asset caught it.
2. **Provenance could cite the wrong asset type.** When a preferred asset was absent,
   the fallback attributed the field to another asset that merely shared its skill
   type — an unavailable visual field credited to the text asset. The fallback now
   refuses to substitute across asset types.
3. **Item 2's fix was initially bypassed**, because the rule's mode had already been
   rewritten to `not_available`, so the asset-type lookup was skipped. The lookup is
   now keyed off whether a derivation exists for the field, not off the current mode.
4. **Declared absences were validated from the mapping's build-time record**, not
   from the instance. A field could be replaced with ordinary content after mapping
   and still validate. Absences are now derived from the instance's own provenance.
5. **`source.collection_rules` and `reference_creators` are sealed**, so an extra
   `not_available` key was rejected by the schema. The declaration moved into the
   required values.
6. **`SkillRegistry` defines `__len__`**, so an *empty* registry is falsy and the
   test helper's `registry or default` idiom silently substituted a populated one —
   making a rejection test pass vacuously. Fixed with an explicit `None` check.

A seventh finding was **not** a defect: a module may legitimately be fed by several
skills, and the first "one asset per module" design was wrong rather than the code.

---

## 7. Remaining blockers

| # | Blocker | Severity | Impact |
| --- | --- | --- | --- |
| B1 | **Nothing loads an instance** | High | `runtime.bootstrap` still reads `config/runtime/default.json`; the mapped artifact has no consumer. |
| B2 | **No sports or tech persona** | High | Only finance maps a complete bundle. Sports and tech produce declared gaps. |
| B3 | **Source, generation, publishing unimplemented** | High | Three of seven modules map to declared capabilities. |
| B4 | **No Lobster integration** | High | Bundles cannot be shared or uploaded. Out of scope by instruction. |
| B5 | **`risk_policy.action` has no consumer** | Medium | The gate reads only `severity == "block"`; three of four categories are inert there. |
| B6 | **Visual corpus is synthetic** | Medium | `visual_rules` references a profile derived from 40/40 synthetic samples. |
| B7 | **No instance diff between two mappings** | Medium | `bundle_instance_diff` compares a bundle to its own instance; comparing two *instances* over time is not yet possible. |
| B8 | **`identity.tone` and `text_rules.tone` derive from different things** | Low | One is a string from the distillation skill, the other an object. Correct today, but the name collision invites future error. |
| B9 | **Mapping is not re-runnable against a changed bundle** | Low | A changed bundle produces a new instance with no delta report against the old one. |

---

## 8. Recommended next phase (C0.4-B)

### C0.4-B — Instance loading *(recommended)*

Teach the runtime to load a Creator Instance and derive its plugin, skill and
workflow selection from it, instead of reading `config/runtime/default.json`
directly. **This is the first point at which C0.2, C0.3 and C0.4-A output has a
consumer**, and until it exists the whole ladder is an unexercised artifact format.

Two properties make it the right next step: it needs no capability that does not
exist, and it is testable offline with the same fixtures the previous three phases
already use.

### Alternatives, and why they are second

| Candidate | Assessment |
| --- | --- |
| **C0.4-C author the missing skills** | Valuable but content work, not architecture. It would let sports and tech map completely, but changes nothing about the bridge. |
| **C0.4-D skill bundle packaging** | Useful for distribution, which cannot happen without Lobster. Premature. |
| **C0.4-E multi-version registry** | Only needed once a shared library exists. |
| **Instance-to-instance diff** | Closes blocker B7 and is cheap, but has no consumer either. |

**Recommended scope: C0.4-B alone.** The ladder now has five passing layers
(C0.1 contract, C0.2 projection, C0.3 skill factory, C0.4-A mapping) and no
runtime consumer for any of them. Adding a sixth producer before building the first
consumer would repeat the pattern this programme exists to avoid.

---

## 9. Deliverables

### 9.1 `creator_mapping/` package

```text
creator_mapping/
    __init__.py      public surface
    errors.py        MappingError + 5 subtypes
    rules.py         the 47 field rules and the skill→module routing
    resolver.py      BundleAssetResolver, BundleAssets, ResolvedAsset
    mapper.py        map_bundle_to_instance, write_mapped_instance,
                     bundle_instance_diff, the derivation table
    provenance.py    FieldMapping, MappingProvenanceBuilder
    validation.py    four validation layers
```

### 9.2 Tests

`tests/creator_mapping_layer/` — 6 files, 256 tests.

---

## 10. Compliance statement

| Constraint | Status |
| --- | --- |
| Do not modify `runtime/` | **No changes** |
| Do not modify `production/` | **No changes** |
| Do not modify `workflows/` | **No changes** |
| Do not modify `risk_evaluation/` | **No changes** |
| Do not modify `multimodal_creator/` | **No changes** |
| Do not modify `distillation_core/` | **No changes** |
| Do not modify `plugins/` | **No changes** |
| Do not integrate the Lobster API | **Not integrated** |
| Do not upload to the Shared Skill Library | **Nothing uploaded** |
| Do not create a real Agent | **No agent created** |
| Only connect the configuration layer | `creator_mapping/` + tests + this report |

`creator_contract`, `creator_projection` and `creator_skill` were **read** and not
modified. `core` is imported only for its existing schema validator, as C0.2 does.

---

## 11. Commit

```
feat: add skill bundle instance mapping layer
```

Not pushed.
