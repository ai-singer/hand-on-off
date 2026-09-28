# C0_EXISTING_ASSET_MAPPING.md

**Phase 1 — Existing capability → contract field mapping**

Purpose: before defining any contract, establish where each instance field's content
can actually come from today, and how strong that source is.

Legend for **Source strength**: **REAL** = working code producing a validated
artifact · **PROSE** = documented procedure or Markdown rules, not executable ·
**ABSENT** = no implementation and no data.

---

## 1. The mapping table

| Capability | Current source | What it actually produces today | Strength | Future field |
| --- | --- | --- | --- | --- |
| **Persona** | `nuwa-skill` (`huashu-nuwa`, 451-line procedure) | A generated persona `SKILL.md` — proven by `tim-mediastorm-perspective` (118 lines, 5 mental models, self-declares *"Generated with Nuwa Skill"*) | **PROSE** (procedure) + **REAL** (proven output) | `identity.json` |
| **Source** | `xhs-collection-strategy` + `xhs-scraper-skill/scripts/scrape_two_stage.py` | Two API stages (`/user_posted`, `/feed`) writing 3 JSON files; creator discovery is prose with the mandatory verification call **unimplemented** | **PROSE** (discovery) + **PARTIAL** (collection, defects D1–D10) | `source.json` |
| **Text style** | `plugins/xiaolin_finance/rules/*.json` + `mediastorm-text-generation/SKILL.md` | 5 value rules, 4 filter rules, 1 structure template, 1 rubric (**REAL**, JSON-as-data); a 250-line voice rule set (**PROSE**) | **REAL** (taxonomy) + **PROSE** (voice) | `text_rules.json` |
| **Visual style** | `multimodal_creator/` M5 → `VisualCreatorProfile` → `factory_config()` | A flattened profile: `visual_profile` envelope, `identity`, `composition`, `attention`, `hierarchy`, `constraints`, `provenance`; **8 real emitted profiles** in `docs/m5/profiles/` | **REAL** (code + artifacts) but **synthetic corpus** (40/40 `synthetic_rendered`) | `visual_rules.json` |
| **Risk** | Two disjoint systems: `plugins/xiaolin_finance/rules/filter_rules.json` → `evaluation/` gate (**wired**), and `risk_evaluation/` (288 files, **unwired**) | 4 categories (1 `block`, 3 `warning`), severity/action/keywords; the gate reads **only** `severity == "block"` | **REAL** (live gate) + **UNWIRED** (deep evaluator) | `risk_policy.json` |
| **Generation** | `workflows/content_distillation_pipeline/generation_interface.py` + `production/generation_input.py` | A 24-line `GenerationRequest` contract, a read-only projection, and a **stub** handoff returning JSON. **No adapter ships.** | **ABSENT** (no generator) | `generation.json` |
| **Publish** | `github-repo-manager/SKILL.md` (manual `curl` recipes) | Prose GitHub Contents API operations against one hardcoded repo; zero `cms`/`idempot`/`retry` anywhere | **ABSENT** (no implementation) | `publishing.json` |
| **Provenance** | M5 `FieldProvenance` (`multimodal_creator/profile/model.py`) + nuwa `Research cutoff` + source register | Per-rule source phase + artifact id + confidence; `tim-mediastorm-perspective:12,106-118` | **REAL** (for visual) | `provenance.json` |

Task-supplied shorthand, resolved:

| Brief's label | Actual system | Correction |
| --- | --- | --- |
| `collector` | `xhs-collection-strategy` + `xhs-scraper-skill` | Exists, but **defective** (D1–D10) — not a working collector |
| `M5` | `multimodal_creator/profile/` | Correct: real code and real artifacts |
| `risk evaluator` | `evaluation/` gate **and** `risk_evaluation/` | Two systems; only the gate is wired |
| `runtime` | `workflows/.../generation_interface.py` + `production/generation_input.py` | Correct location, but generation is a **contract only** |
| `CMS` | **nothing** | **Does not exist** — no CMS, no publisher, no interface |

---

## 2. Coverage of the eight contract modules

| Contract module | Real source available? | Notes |
| --- | --- | --- |
| `identity.json` | **Partial** | Persona distillation works (proven output) but the **template** has no persona slot; `platform`, `audience`, and `tone` have **no model anywhere**. |
| `source.json` | **Partial** | Collection code exists but is broken and credential-gated; discovery is prose; `candidate_registry.json` and the verification call are absent. |
| `text_rules.json` | **Yes** | Rule taxonomy is already JSON-as-data — the model to imitate. Voice guidance is prose. |
| `visual_rules.json` | **Yes** | M5 emits a real, flattened, provenance-carrying profile. Must be referenced, **never** re-specified. |
| `risk_policy.json` | **Yes** | 4 categories + keywords are real config. `action` is declared but unread by the gate. |
| `generation.json` | **Contract only** | The interface exists; the adapter does not. The contract must therefore declare a **routing reference**, not a model. |
| `publishing.json` | **No** | Nothing to project. Must be declared as a **target** with an explicit idempotency key. |
| `provenance.json` | **Partial** | M5 has real per-field provenance; other modules have none today. |

---

## 3. What the mapping dictates for the contract design

Five design constraints follow directly from the table above:

1. **`visual_rules` must be a reference, not a copy.** M5 already emits a
   flattened, provenance-complete profile, and its schema forbids `prompt`,
   `model`, `image`, `publish`, `endpoint`, `api_key`, and `webhook`. Re-specifying
   visual content in the instance would duplicate M5 and break that guarantee.
2. **`generation` and `publishing` declare routing, not behaviour.** Both sources
   are absent, so the honest contract shape is `adapter_ref` + parameters. A
   contract that embedded a model call would freeze a decision nothing supports.
3. **`risk_policy` must be required to be non-empty.** The live gate only reads
   `severity == "block"`, so an empty policy would silently disable all risk
   control. The contract must refuse it.
4. **`identity` must carry `mode`.** The nuwa *template* mandates a roleplay
   section (`角色扮演规则`) while the *deployed* Tim instance omits it and writes
   third person. Both are legitimate; the contract must force the choice to be
   recorded rather than inferred.
5. **`provenance` must be mandatory for every module.** Today only M5 tracks
   provenance. Without a contract-level requirement, every other module's origin
   would be unknowable — which is precisely how the template and the instance
   toolchain drifted apart in the first place.

---

## 4. Absent assets the contract must not pretend exist

| Absent | Consequence for the contract |
| --- | --- |
| Reference-creator discovery implementation | `source.reference_creators` must require `identity_verified: true`, so an unverified `user_id` cannot be configured |
| Publisher / CMS | `publishing` is a target declaration; `requires_human_approval` defaults to `true` |
| Generation adapter | `generation.enabled` defaults to `false`; only the routing reference is required |
| Platform and audience models | `platform` is a closed enum; `audience` is declared free text — its absence is recorded, not hidden |
| `agent_config/` (named, never created) | The contract **is** the realisation of that missing directory |

## 5. Files inspected in Phase 1

`blank/workspace/{IDENTITY.md,SOUL.md,USER.md,AGENTS.md,pyproject.toml}` ·
`config/runtime/{default.json,loader.py}` ·
`plugins/xiaolin_finance/{plugin.json,plugin.py,README.md,rules/value_rules.json,rules/filter_rules.json,rules/structure_templates.json,evaluation/rubric.json}` ·
`distillation_core/{engine,classifier,extractor}.py` ·
`evaluation/{evaluator.py,quality_gate_controller.py}` ·
`workflows/content_distillation_pipeline/{generation_interface.py,pipeline.py}` ·
`production/generation_input.py` · `schemas/unified_distillation_artifact.json` ·
`multimodal_creator/profile/{__init__,model,schema,serialization,validation}.py` ·
`multimodal_creator/grammar/constraints.py` · `docs/m5/{profiles/visual_profile.yaml,example_factory_config.json}` ·
`risk_evaluation/evaluator.py` · `runtime/bootstrap.py` ·
`old/.openclaw/skills/nuwa-skill/SKILL.md` + `references/{extraction-framework,skill-template}.md` ·
`old/.openclaw/skills/tim-mediastorm-perspective/SKILL.md` ·
`old/.openclaw/skills/mediastorm-text-generation/SKILL.md` ·
`old/.openclaw/skills/mediastorm-visual-prompt/SKILL.md` ·
`old/.openclaw/skills/xhs-collection-strategy/SKILL.md` ·
`old/.openclaw/skills/xhs-scraper-skill/{SKILL.md,package.json,scripts/scrape_two_stage.py}` ·
`old/.openclaw/skills/github-repo-manager/SKILL.md` · `new/skills.tar.gz` (member listing).
