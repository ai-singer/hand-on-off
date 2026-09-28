# PHASE_C0_1_CREATOR_INSTANCE_CONTRACT_REPORT.md

**Phase C0.1 — Creator Instance Contract Definition**

Scope: define and freeze *what one Creator Agent instance is made of*. This phase
does **not** build a Factory, generate a creator, or touch the runtime.

---

## 1. Instance Architecture

```text
                        creator_request
                              │
                              │  domain, platform, style, creator_ref ...
                              ▼
        ┌───────────────────────────────────────────────────────────┐
        │              CREATOR INSTANCE CONTRACT  (C0.1)             │
        │                                                           │
        │   creator_instance/<creator_id>/                           │
        │       identity.json        source.json                     │
        │       text_rules.json      visual_rules.json                │
        │       risk_policy.json     generation.json                  │
        │       publishing.json      provenance.json                  │
        │       creator_instance.json   (aggregate)                   │
        │                                                           │
        │   schemas/creator_instance.schema.json   ← the frozen shape │
        │   creator_contract/validation.py         ← the three checks │
        └───────────────────────────────────────────────────────────┘
                              │
                              │  an instance is READ, never executed
                              ▼
        ┌───────────────────────────────────────────────────────────┐
        │                        RUNTIME  (unchanged)                │
        │  runtime.bootstrap → DistillationEngine → QualityGate       │
        │                     → injected generation / publishing      │
        │                                                           │
        │  instance declares adapter_ref; the runtime supplies it     │
        └───────────────────────────────────────────────────────────┘
```

**The one-line rule: an instance is configuration, never runtime.** It may
*reference* an engine, an adapter, or an M5 profile; it may never *contain* code,
a model call, a crawler, or a publisher.

### 1.1 Placement chosen for this phase

| Artifact | Path | Why |
| --- | --- | --- |
| Contract package | `creator_contract/` | New top-level package; imports nothing from the runtime and is imported by nothing in it |
| Contract schema | `schemas/creator_instance.schema.json` | Joins the existing `schemas/` convention (the task's `creator_contract/creator_instance.schema.json` alternative would have duplicated the convention) |
| Tests | `tests/creator_contract_layer/` | **Renamed** from `tests/creator_contract/` — see §5.3 |
| Reports | `docs/` | Joins 58 existing phase reports |

---

## 2. Schema design

`schemas/creator_instance.schema.json` — sealed at the root
(`additionalProperties: false`), 9 required top-level keys, expressed strictly in
the project's dependency-free schema subset (`type` / `enum` / `required` /
`properties` / `additionalProperties` / `items` / `minItems`). **No `$ref`,
`allOf`, `oneOf`, or `if`/`then`** — the project validator cannot express them, and
a test asserts their absence.

### 2.1 Module responsibilities

| Module | Responsibility | Key rules enforced |
| --- | --- | --- |
| `identity.json` | Who the creator is | `creator_id`, `name`, closed `domain` enum (`finance`/`sports`/`tech`/`general`), `platform` enum, `language` enum, `audience`, `tone`; `persona.mode` is a **required choice** between `reasoning_model` and `roleplay_persona`; 1+ mental models each with `mechanism`/`evidence`/`apply_when`/`failure_condition`; 1+ heuristics; 1+ honest boundaries |
| `source.json` | What material feeds it | 1+ `reference_creators` each requiring **`identity_verified: true`**; `data_sources` carrying the dual-layer `layer` enum (`discovery`/`evidence`); `collection_rules` (`min_notes`, `material_tiers` S/A/B/C, `rate_limit_seconds`, `dedupe_by`); 1+ weighted `keywords` |
| `text_rules.json` | How text is produced | `title_formula` (1+), `structure.template_id` + 1+ sections, `tone` (voice/certainty/avoid), `length` bounds, 1+ `knowledge_boundary` |
| `visual_rules.json` | **A reference to M5** | `profile_id`, `profile_version`, `visual_language`, `attention_strategy`, `composition` (preferred/forbidden layout), `hierarchy`, `constraints` (must_have/avoid), `provenance`. **No prompt, no model, no image — by shape and by content check** |
| `risk_policy.json` | What must not be produced and who decides | 1+ `risk_categories` (severity `info`/`warning`/`block`, action `downrank`/`require_evidence`/`require_review`/`block`), 1+ `review_rules` (`pass`/`require_review`/`block`), 1+ `blocked_patterns` each referencing a declared category, `evidence_requirement` |
| `generation.json` | **Routing only** | `adapter_ref` (required), `input` from the closed six-value set matching `production/generation_input.py`, `output_format`, `quality_gate.required_decision` **pinned to `PASS`**, `enabled` (defaults `false`) |
| `publishing.json` | **A target only** | `platform` enum, `image_requirement` (aspect ratio enum, min width, title-safe-area ratio), `api.adapter_ref` + **`idempotency_key` (required)** + `retry_policy`, `schedule.mode` enum, `requires_human_approval` |
| `provenance.json` | Where every module came from | All seven modules required to carry a record; `generated_by`; `template_contract` metadata when projected |

### 2.2 Two deliberate asymmetries

1. **`generation` and `publishing` declare references, not behaviour.** Both
   capabilities are absent from the template, so a contract that embedded a model
   or a publish call would freeze a decision nothing supports. Idempotency is made
   *mandatory* precisely because no publisher exists to supply it — the reference
   task's own analysis found zero `idempot` matches anywhere in either system.
2. **`visual_rules` carries vocabulary but no prompt.** The source of truth stays
   `multimodal_creator.profile`; the contract's visual block mirrors
   `factory_config()`'s own keys (`visual_profile` / `attention` / `hierarchy` /
   `composition` / `constraints` / `provenance`) so the two cannot drift.

---

## 3. Existing capability mapping (summary)

Full table in `docs/C0_EXISTING_ASSET_MAPPING.md`. Condensed:

| Capability | Current source | Strength | Contract field |
| --- | --- | --- | --- |
| Persona | `nuwa-skill` (451-line procedure) | PROSE + proven output | `identity.json` |
| Source | `xhs-collection-strategy` + `scrape_two_stage.py` | PROSE + PARTIAL (defects D1–D10) | `source.json` |
| Text style | `plugins/xiaolin_finance/rules/*.json` + `mediastorm-text-generation` | **REAL** + PROSE | `text_rules.json` |
| Visual style | `multimodal_creator/` M5 → `factory_config()` | **REAL**, synthetic corpus | `visual_rules.json` |
| Risk | `evaluation/` gate (wired) + `risk_evaluation/` (unwired) | **REAL** + UNWIRED | `risk_policy.json` |
| Generation | `generation_interface.py` + `production/generation_input.py` | **ABSENT** (contract only) | `generation.json` |
| Publish | `github-repo-manager` (manual curl) | **ABSENT** | `publishing.json` |
| Provenance | M5 `FieldProvenance` + nuwa `Research cutoff` | **REAL** (visual only) | `provenance.json` |

---

## 4. Validation result

Three independent checks, each separately reportable:

| Check | Implementation | What it enforces |
| --- | --- | --- |
| **Schema** | `validate_schema()` → project validator + the new schema | Field completeness, types, closed enums, sealed objects |
| **Dependency** | `validate_dependencies()` | Cross-module references resolve: creator id non-blank, unique model ids, **`identity_verified` must be true**, an **`evidence`-layer data source must exist**, every blocked pattern references a declared category, visual profile id/version non-blank, gate requires `PASS`, **idempotency key non-blank** |
| **Isolation** | `validate_isolation()` → `assert_no_runtime_code` + `assert_visual_rules_reference_only` + `assert_risk_policy_not_empty` | No code keys (18 named), no code/HTTP-client substrings (19 patterns), no runtime-module references (6 modules); no prompt/model/image keys (39 named) or prompt phrases (9) in `visual_rules`; risk policy non-empty |

`validate()` runs all three and returns an `IsolationReport`
(`status`, `contract_version`, `modules_present`, `provenance_modules`, `checks`).

### 4.1 A real validation result on real content

The blank template projects cleanly:

```text
projection validate: PASS  {schema: PASS, dependencies: PASS, isolation: PASS}
  creator_id : creator-agent-template
  counts     : mental_models=5  decision_heuristics=5  keywords=43
               data_sources=1   risk_categories=4       blocked_patterns=37
               structure_sections=5
  sources_read: 6
```

Two findings surfaced by validation while building this phase, both genuine:

1. The schema rejected an undeclared `provenance.generated_by` — the contract
   refusing an undocumented field, as designed. The field was then declared.
2. The isolation check initially flagged the phrase `"projected from the
   template"` as code. A bare `"from "` pattern matches ordinary English; it was
   removed, because `"import "` already covers `from x import y`. A test now pins
   that ordinary prose is **not** flagged — a check with false positives is a
   check people switch off.

### 4.2 Projection is read-only with respect to the template

`project_blank_template()` reads six files and writes nothing. Two tests assert
the template's full file list is byte-identical before and after projection
(including `write_projected_instance`, which writes only to the caller's
`out_root`).

---

## 5. Test result

```text
tests.creator_contract_layer.test_schema        44 tests   OK
tests.creator_contract_layer.test_validation    57 tests   OK
tests.creator_contract_layer.test_projection    62 tests   OK
tests.creator_contract_layer.test_negative      42 tests   OK
                                                ─────────
                                                205 tests  OK   (0.43 s)
```

Target was ≥80 (20 per class); delivered **205** — schema 44, validation 57,
projection 62, negative 42.

### 5.1 The four mandated negative cases

| Required rejection | Test | Result |
| --- | --- | --- |
| Instance contains code (`python:`) | `Negative1InstanceContainsCodeTests` — 12 tests, incl. the literal `python:` key, nesting depth, and `def`/`import` in strings | **rejected** |
| Visual contains a generation prompt (`prompt: create image`) | `Negative2VisualContainsGenerationPromptTests` — 14 tests, incl. `prompt`, `system_prompt`, `negative_prompt`, diffusion settings, image data, and prompt phrases under innocent keys | **rejected** |
| Risk rules empty | `Negative3EmptyRiskPolicyTests` — 7 tests, incl. the literal empty `risk_rules: {}` | **rejected** |
| No provenance | `Negative4NoProvenanceTests` — 6 tests, incl. each of the seven modules removed in turn | **rejected** |

Plus `NegativeCrossCuttingTests` (4) confirming combined defects are still
rejected and that a valid instance **is not** rejected — so the negative suite
does not pass for the wrong reason.

### 5.2 Policy tuples are tested, not decorative

`test_every_isolation_forbidden_key_is_actually_rejected` iterates all 18
isolation keys, `test_visual_rules_may_not_carry_any_prompt_key` iterates all 39
prompt keys, and `test_runtime_module_reference_is_caught` iterates all 6 runtime
modules — each asserting the entry actually bites. A denylist nobody verifies is
a comment.

### 5.3 One defect found by the project's own guard, and fixed

The first full-suite run failed with:

```text
FAIL: test_test_packages_do_not_shadow_workspace_packages
AssertionError: Lists differ: ['creator_contract'] != []
```

`python -m unittest discover -s tests` puts `tests/` at `sys.path[0]`, so
`tests/creator_contract/` **shadowed the real top-level `creator_contract`
package** — every `from creator_contract import ...` inside the tests resolved to
the test package, producing 4 collection errors. The project already guards this
hazard (that test exists precisely because `runtime/` had the same problem) and
its convention is `tests/runtime_bootstrap/` for the `runtime/` package. The
directory was renamed to **`tests/creator_contract_layer/`**, matching the
convention, and all 205 tests then passed.

### 5.4 Isolation of the new layer

```
creator_contract imports: json, dataclasses, pathlib, typing, copy
                          + core.errors, core.schema_validation
                          + its own modules
forbidden runtime modules imported: NONE
```

Verified by grep: no import of `runtime`, `production`, `risk_evaluation`,
`workflows`, `multimodal_creator`, or `distillation_core`.

### 5.5 Files added

| File | Lines | Purpose |
| --- | --- | --- |
| `creator_contract/__init__.py` | 130 | Public surface |
| `creator_contract/errors.py` | 40 | `CreatorContractError` (+3 subtypes) extending `ArtifactValidationError` |
| `creator_contract/artifacts.py` | 330 | Eight-module layout, path helpers, canonical JSON, dependency-free emitter/parser |
| `creator_contract/validation.py` | 640 | Schema / dependency / isolation checks, `IsolationReport` |
| `creator_contract/authoring.py` | 300 | Builders; M5-faithful visual defaults |
| `creator_contract/template_projection.py` | 470 | Blank template → contract projection |
| `schemas/creator_instance.schema.json` | 330 | The frozen shape |
| `tests/creator_contract_layer/test_schema.py` | 230 | 44 tests |
| `tests/creator_contract_layer/test_validation.py` | 390 | 57 tests |
| `tests/creator_contract_layer/test_projection.py` | 400 | 62 tests |
| `tests/creator_contract_layer/test_negative.py` | 290 | 42 tests |
| `docs/C0_EXISTING_ASSET_MAPPING.md` | — | Phase 1 mapping |
| `docs/PHASE_C0_1_CREATOR_INSTANCE_CONTRACT_REPORT.md` | — | This report |
| `pyproject.toml` | +1 line | Added `creator_contract` to the packages list |

---

## 6. Factory readiness

# **PARTIAL**

Precisely: **the contract is READY; the Factory is NOT READY.**

| Aspect | Status | Reasoning |
| --- | --- | --- |
| Instance *format* frozen | **READY** | Eight modules, one sealed schema, enum-closed, provenance-mandatory |
| Instance *validation* | **READY** | 205 tests; three checks; policies tested to bite |
| Template → contract *projection* | **READY** | The real blank template projects and validates; projection is read-only |
| Persona generation → `identity.json` | **PARTIAL** | nuwa produces personas, but as Markdown prose; no converter to the contract exists |
| Acquisition → `source.json` | **PARTIAL** | Collection code exists but has defects D1–D10 and the mandatory `user_id` verification is unimplemented |
| Visual → `visual_rules.json` | **PARTIAL** | M5 emits a real profile; the corpus is 40/40 synthetic and M5 is not wired to the engine |
| Risk → `risk_policy.json` | **PARTIAL** | 4 categories real; `action` is unread by the gate; the 288-file evaluator is unwired |
| Generation → `generation.json` | **NOT READY** | No adapter exists; the contract can only declare a routing reference |
| Publishing → `publishing.json` | **NOT READY** | No publisher, no CMS, no idempotency implementation anywhere |
| Runtime *loading* of an instance | **NOT READY** | `runtime.bootstrap` reads `config/runtime/default.json`, not this contract; wiring is explicitly out of scope for C0.1 |

**Why not READY outright:** five of eight modules can only be *declared* today,
because the capabilities behind them are absent or defective. The contract is
honest about that — `generation.enabled` defaults to `false`,
`publishing.requires_human_approval` defaults to `true`, and projection records
each gap in its notes rather than defaulting silently.

---

## 7. Remaining gaps

### 7.1 Blocking the Factory

| # | Gap | Consequence |
| --- | --- | --- |
| G1 | **No Markdown → contract converter** | nuwa emits `SKILL.md` prose; `identity.json` needs structure. Without a converter every instance's identity is hand-written — the same manual bottleneck Phase 5 identified as Step 9. |
| G2 | **Runtime cannot load an instance** | `runtime.bootstrap` is unchanged by design this phase, so nothing consumes the contract yet. This is the next integration point, not a defect of C0.1. |
| G3 | **Discovery automation absent** | `xhs-collection-strategy` describes a 6-step creator-discovery procedure with **no implementation**, and the mandatory `/user/otherinfo` verification call is missing from the only script (defect D8). |
| G4 | **Generation is a declaration only** | `generation.enabled = false`; no adapter ships on either side. |

### 7.2 Quality gaps

| # | Gap |
| --- | --- |
| G5 | **Visual corpus is 100% synthetic** (40/40 `synthetic_rendered`) — no real creator post has ever been examined, so `visual_rules` describes synthetic templates |
| G6 | **`risk_policy.action` has no consumer** — the gate reads only `severity == "block"`, so three of four finance rules are inert at the gate |
| G7 | **The deep risk evaluator is unwired** — `risk_evaluation/` is imported only by its own tests, and its baseline `KeywordRiskEvaluator` loads the production plugin, so it cannot act as an independent check |
| G8 | **Acquisition defects D1–D10** — no pagination, import-time `xhshow` patch, hardcoded Linux paths, absent `meta.json` producer, absent `normalize.py` |
| G9 | **No evaluation feedback into identity** — nothing yet feeds measured performance back into `identity.json` or `text_rules.json` |

### 7.3 Deliberately deferred

| # | Deferred | Reason |
| --- | --- | --- |
| D1 | Factory / instance generation | Forbidden this phase |
| D2 | Runtime, production, risk-evaluator, visual-distillation changes | Forbidden this phase |
| D3 | Publishing integration | Forbidden this phase |
| D4 | YAML emission | Canonical JSON chosen: JSON is a strict subset of YAML 1.2, dependency-free, and byte-deterministic. A flattened emitter/parser is provided for readers needing that form |
| D5 | Version migration tooling | A single contract version (`1.0.0`) exists; migration is premature |

---

## 8. Compliance statement

| Constraint | Status |
| --- | --- |
| ❌ Create a Creator Factory | **Not done.** No generator, no scaffolding, no instance produced. |
| ❌ Auto-generate a new creator | **Not done.** The only instance-shaped output is a *projection of the existing template*, written only to a caller-supplied path (tests use `TemporaryDirectory`). |
| ❌ Modify runtime | **Not done.** Zero changes under `runtime/`. |
| ❌ Modify production | **Not done.** Zero changes under `production/`. |
| ❌ Modify risk evaluator | **Not done.** Zero changes under `risk_evaluation/` or `evaluation/`. |
| ❌ Modify visual distillation | **Not done.** Zero changes under `multimodal_creator/`. |
| ❌ Touch the publishing system | **Not done.** `publishing.json` is a declaration only; no integration. |
| ✅ Add contract layer | `creator_contract/` (6 modules) |
| ✅ Add schema | `schemas/creator_instance.schema.json` |
| ✅ Add validation | `creator_contract/validation.py` + 205 tests |

One file outside the contract layer was touched: **`pyproject.toml`, one line**,
adding `creator_contract` to `[tool.setuptools] packages` so the package is
installable. This is packaging metadata, not runtime, production, risk, or visual
code.

Also unchanged: the blank template's own configuration. Projection proved
read-only by test.

---

## 9. The contract in one page

```text
creator_instance/<creator_id>/
├── identity.json      who        ← nuwa_skill (PROSE today)
├── source.json        what feeds ← xhs_collection_strategy (PARTIAL)
├── text_rules.json    how text   ← value_rules + structure_templates (REAL)
├── visual_rules.json  how it looks ← M5_profile (REAL, REFERENCE ONLY)
├── risk_policy.json   what not   ← filter_rules + risk_evaluation (REAL, partially wired)
├── generation.json    routing    ← runtime_generation_contract (DECLARED)
├── publishing.json    target     ← deployment_publishing_target (DECLARED)
└── provenance.json    where from ← mandatory for all seven

Rules that cannot be broken:
  · an instance is configuration, never runtime
  · visual_rules references M5 and carries no prompt
  · risk_policy may not be empty
  · every module records its provenance
  · generation may only run after the gate returns PASS
  · publishing declares an idempotency key
```
