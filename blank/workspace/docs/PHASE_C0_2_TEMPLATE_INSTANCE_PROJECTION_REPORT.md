# PHASE_C0_2_TEMPLATE_INSTANCE_PROJECTION_REPORT.md

**Phase C0.2 — Template → Instance Projection**

Goal: build the Projection Layer that turns existing Creator assets into a Creator
Instance conforming to the C0.1 contract.

```text
Existing Assets  ->  Projection  ->  Creator Instance Artifact
```

Not in scope, and not done: creating a creator, generating content, running an
agent, building a Factory, scheduling, publishing, model calls.

---

## 1. Which assets were successfully converted?

| Contract module | Source asset(s) | Status | Notes |
| --- | --- | --- | --- |
| `identity` | `plugin_manifest`, `runtime_config`, `text_distillation_rules` | **CONVERTED (substituted)** | The persona asset is unavailable, so the persona is projected from the template's declared value-rule sections. Recorded as `asset_substitution`, confidence 0.4. |
| `source` | `text_distillation_rules` | **CONVERTED (substituted)** | Discovery procedure unavailable; 43 weighted keywords flattened from the value rules. |
| `text_rules` | `text_structure_templates`, `evaluation_rubric` | **CONVERTED (real)** | 1 template id, 5 sections referenced by name, 9 knowledge boundaries from rubric questions. No prose generated. |
| `visual_rules` | `visual_profile_m5` | **CONVERTED (referenced)** | M5 profile referenced by id. Vocabulary and constraints only; no prompt, model, or image data. |
| `risk_policy` | `risk_policy_reference`, `evaluation_rubric` | **CONVERTED (declared)** | 4 categories, 37 blocked patterns, 3 review rules. Declared `runtime_connected: false`. |
| `generation` | `generation_capability` (unavailable) | **DECLARED ABSENT** | `enabled: false`, `reason: generation_capability_not_available` |
| `publishing` | `publishing_capability` (unavailable) | **DECLARED ABSENT** | `enabled: false`, `reason: publishing_capability_not_available` |
| `provenance` | registry | **CONVERTED (real)** | Every field of every module carries a complete record. |

### 1.1 Example projection artifact

```text
creator_instance/template_creator/
    identity.json      3,114 B      source.json        3,624 B
    text_rules.json    1,908 B      visual_rules.json  4,060 B
    risk_policy.json   4,927 B      generation.json      434 B
    publishing.json      509 B      provenance.json   17,232 B
    instance.json     37,260 B
```

Validation: `PASS {schema: PASS, dependencies: PASS, capability_declaration: PASS, isolation: PASS}`

### 1.2 Asset registry coverage

15 assets registered; **9 available, 6 unavailable** with machine-readable reasons:

| Unavailable asset | Reason |
| --- | --- |
| `nuwa_persona_skill`, `nuwa_skill_template`, `persona_perspective_skill` | `external_toolchain_not_present_in_repository` |
| `source_collection_strategy` | `external_toolchain_not_present_in_repository` |
| `generation_capability` | `generation_capability_not_available` |
| `publishing_capability` | `publishing_capability_not_available` |

No asset path is hard-coded in Python: a test iterates every registered asset and
another asserts every provenance `source_asset` is a registered id.

---

## 2. Which capabilities are still missing?

| Capability | Missing since | Consequence for projection |
| --- | --- | --- |
| **Persona distillation** (nuwa) | The toolchain lives outside this repository | `identity` is projected from the template's own config, not a distilled persona. Marked as substitution. |
| **Creator discovery** | Never implemented; the mandatory `/user/otherinfo` verification is absent from the only script | `source.reference_creators` carries a placeholder with an explicit "not-applicable" verification method. |
| **Acquisition** | Script has defects D1–D10 | `source` carries no live collection configuration beyond declared keywords. |
| **Generation** | Only a 24-line request contract exists | `generation.enabled: false` |
| **Publishing** | No publisher, CMS, or idempotency implementation anywhere | `publishing.enabled: false` |
| **Runtime loading of an instance** | Out of scope for C0.1/C0.2 | The artifact exists; nothing consumes it yet. |
| **Real visual corpus** | 40/40 samples synthetic | `visual_rules` references a profile derived from synthetic templates. |

**No capability was invented to fill a gap.** Each is either declared absent with a
reason or recorded as a substitution with lowered confidence.

---

## 3. Which fields are only declarations?

Fields that state an intent or an absence rather than carrying content, with the
confidence the projection assigns them (`capability_declaration` = 0.0,
`asset_substitution` = 0.4, real reads/references = 1.0):

| Module | Declaration-only fields | Confidence |
| --- | --- | --- |
| `generation` | `enabled`, `reason`, `adapter_ref`, `quality_gate.controller_ref` | 0.0 |
| `publishing` | `enabled`, `reason`, `api.adapter_ref`, `api.idempotency_key`, `requires_human_approval`, `schedule` | 0.0 |
| `risk_policy` | `review_required`, `source`, `runtime_connected`, `enabled` | 0.0 |
| `identity` | `audience` (*"unspecified; the template declares no audience model"*), `platform` | mixed |
| `source` | `reference_creators` (placeholder), `collection_rules`, `data_sources` | 0.4 |

Specifically:

- **`adapter_ref` values name an adapter that does not exist.** They declare which
  deployed component *would* be injected, not that one is present.
- **`publishing.api.idempotency_key` declares a key source**, because no publishing
  implementation exists to supply or consume one.
- **`risk_policy.runtime_connected: false` is enforced**: a test asserts the check
  rejects `true`, so the declaration cannot be quietly flipped.
- **`identity.audience` / `platform`** have no model anywhere in either system.

---

## 4. What still blocks the Factory?

| # | Blocker | Severity | Why it blocks |
| --- | --- | --- | --- |
| B1 | **No Markdown → contract converter for real personas** (G1 from C0.1) | High | The mapper's `markdown_projection` path is implemented and tested against a fixture, but no real persona asset is in the repository, so every projected identity is a substitution. |
| B2 | **Nothing loads an instance** | High | `runtime.bootstrap` still reads `config/runtime/default.json`. Until it reads a Creator Instance, projection produces an artifact no component consumes. |
| B3 | **Generation absent** | High | Instances declare `enabled: false`. A Factory emitting them would produce creators that cannot produce content. |
| B4 | **Publishing absent** | High | No target can be reached, and no idempotency implementation exists. |
| B5 | **Discovery and acquisition** | Medium-High | `source` is a keyword list plus a placeholder; nothing acquires material. |
| B6 | **Visual corpus is synthetic** | Medium | Every `visual_rules` profile describes generated templates, not real creator posts. |
| B7 | **`risk_policy.action` has no consumer** | Medium | The gate reads only `severity == "block"`; three of four categories are inert there. |
| B8 | **No instance-level diff or drift detection** | Low-Medium | Re-projecting after an asset change produces a new instance silently; nothing reports what changed. |
| B9 | **YAML is a form choice, not a format** | Low | Canonical JSON was chosen (a subset of YAML 1.2). A flattened emitter exists; a YAML *writer* that emits block style does not. |

**Blocking summary:** B1–B4 must be resolved before a Factory can emit instances
that do anything. B5–B9 are quality and integration gaps.

---

## 5. What does C0.3 need?

Ordered by dependency, not by ambition.

### C0.3-A — Instance loading (unblocks everything)

Teach the runtime to load a Creator Instance and derive the plugin/skill/workflow
selection from it, instead of reading `config/runtime/default.json` directly. This
is the first point at which projection output has a consumer. **Prerequisite for
evaluating any generated instance.**

### C0.3-B — Real persona ingestion

Bring a persona skill into the repository (or a reachable asset path) so the
`markdown_projection` path runs against real content. The converter, including
`Model N:` extraction and verbatim bullet preservation, is **already implemented and
tested**; only the asset is missing. Until this lands, every identity is a
substitution.

### C0.3-C — Instance diff and drift reporting

Projection is deterministic today (asserted by test). C0.3 should add a
`project → diff → report` step so an asset change produces a *reviewable* delta
rather than a silent new instance. This is what makes a Factory safe to re-run.

### C0.3-D — Generation boundary, still without a model

Define and test the adapter *contract* end to end with a recording stub (the
pattern already exists in `tests/creator_production_loop/_fixtures.py`), so that
enabling generation is a configuration change rather than a code change. **Do not
enable it in a projected instance.**

### C0.3-E — Discovery as a declared, unimplemented asset

Promote creator discovery to first-class: implement the `/user/otherinfo`
verification call (currently documented but absent), so `source.reference_creators`
can carry a genuinely verified entry instead of a placeholder.

### C0.3-F — Flattened YAML emission

Only if a downstream consumer requires block-style YAML. JSON remains canonical
meanwhile.

**Recommended C0.3 scope:** A + B + C. They are self-contained, produce a
demonstrable end-to-end path (assets → instance → loaded runtime → diffable
change), and require no capability that does not yet exist.

---

## 6. Deliverables

### 6.1 Projection package

```text
creator_projection/
    __init__.py            public surface
    assets.yaml            asset registry (15 assets)
    errors.py              ProjectionError + 5 subtypes
    yaml_subset.py         dependency-free YAML-subset reader
    asset_registry.py      validated registry access + typed reads
    markdown_parser.py     Markdown -> ordered sections, text preserved
    mapper.py              asset -> contract module mappers + orchestration
    provenance.py          field-level provenance
    validation.py          projection checks
```

### 6.2 Tests

```text
tests/creator_projection_layer/
    test_yaml_subset.py            32 tests
    test_markdown_parser.py        34 tests
    test_asset_registry.py         43 tests
    test_provenance.py             37 tests
    test_capability_declaration.py 37 tests
    test_mapper.py                 66 tests
    test_projection.py             41 tests
    test_negative.py               50 tests  (5 mandated classes)
                                  ─────────
                                  340 tests, OK
```

Target was ≥100; delivered **340**.

### 6.4 Field-level provenance volume

46 field records across the 7 sourced modules (identity 9, source 4, text_rules 5,
visual_rules 8, risk_policy 8, generation 6, publishing 6).

### 6.3 Example artifact

`creator_instance/template_creator/` — 9 files, schema-valid, isolation-clean.

---

## 7. Test result

```text
C0.2 suite (creator_projection_layer)     340 tests   OK
C0.1 suite (creator_contract_layer)       205 tests   OK   (regression)
Full repository suite                   3,571 tests   OK   (1 skipped)
```

### 7.1 The five mandated negative cases

| Required rejection | Tests | Result |
| --- | --- | --- |
| 1. `prompt` field | `Negative1PromptFieldTests` — 8 tests, incl. all 26 prompt keys and nested/content forms | **rejected** |
| 2. Generation falsely enabled | `Negative2GenerationFalselyEnabledTests` — 14 tests, incl. missing/empty/arbitrary reasons and the self-contradictory enabled+reason case | **rejected** |
| 3. Visual rules containing generation ability | `Negative3VisualGenerationTests` — 13 tests, every generation token plus no-copy assertion | **rejected** |
| 4. Modification of an original asset | `Negative4OriginalAssetModificationTests` — 6 tests, SHA256 over the whole workspace before/after projection and after writing the example | **rejected** |
| 5. Missing source | `Negative5MissingSourceTests` — 9 tests, each module removed, each required provenance key removed, and a field added without provenance | **rejected** |

Plus 5 cross-cutting tests confirming combined defects are rejected **and** that a
valid instance is not — so the negatives do not pass for the wrong reason.

### 7.2 Three real defects found by the tests, and fixed

1. **The contract permitted a false capability claim.** `write_instance` delegates
   to the contract's `validate()`, which did not check capability declarations — so
   `enabled: true` with a `reason` was accepted. Fixed by adding
   `assert_no_phantom_capability` to **C0.1's** validation, where the rule belongs
   (it is a property of a valid instance, not of how it was produced). The contract
   now has **four** checks.
2. **C0.1's own builders were then caught by the new rule**, correctly: they emitted
   `enabled: false` with no explanation. `build_generation` and
   `build_publishing` now state why they are disabled, and
   `template_projection` delegates to them so the two definitions cannot drift.
3. **`Path("/etc/passwd").is_absolute()` is `False` on Windows**, so the
   workspace-relative location guard passed a POSIX absolute path on this host.
   Replaced with a platform-independent `_looks_absolute`.

The second of these is the more interesting: the contract rule immediately
invalidated the previous phase's authoring defaults, which is exactly what a
frozen contract is for.

### 7.3 Isolation verification

| Check | Result |
| --- | --- |
| `creator_projection` imports from `runtime`/`production`/`risk_evaluation`/`multimodal_creator`/`distillation_core`/`workflows` | **none** |
| `git diff` on `runtime/`, `production/`, `workflows/`, `risk_evaluation/`, `multimodal_creator/`, `distillation_core/`, `plugins/` | **no modifications** |
| Registry uses only workspace-relative paths | enforced; absolute rejected |
| Workspace byte-identical after projection | asserted over the whole tree |

---

## 8. Compliance statement

| Constraint | Status |
| --- | --- |
| No modification of `runtime/`, `production/`, `workflow(s)/`, `risk_evaluation/`, `multimodal_creator/`, `distillation_core/`, `plugins/` | **No changes made** — verified by `git diff` and by a SHA256 sweep in tests |
| No Factory, no Scheduler, no publishing integration, no model calls | **None added** |
| No automatic article or image generation | **None** |
| No modification of existing rule content or benchmarks | **None** — rules are read only; a test asserts their bytes are unchanged |
| Absent capabilities explicitly marked | **Enforced**: `generation`/`publishing` `enabled: false` with reasons, and the contract now *rejects* a false enable |
| `creator_projection/` package added | 9 files |
| `creator_projection/assets.yaml` registry added | 15 assets |
| `markdown_parser.py` added | structure-only conversion |
| Provenance per module and per field | 46 field records across 7 modules |
| ≥100 tests | **340** |
| Example projection | `creator_instance/template_creator/` |
| Commit `feat: add creator instance projection layer`, no push | see §9 |

**One file outside the new package was changed:** `creator_contract/validation.py`
(+ `__init__.py` re-export, `authoring.py` defaults, and
`schemas/creator_instance.schema.json`), to add the capability-declaration rule and
the `reason`/`registry_version` fields the projection requires. This is the C0.1
contract layer, which C0.2 owns by dependency; it is not runtime, production, risk,
visual, or plugin code. Recorded here explicitly rather than left implicit.

---

## 9. Commit

```
feat: add creator instance projection layer
```

Not pushed.
