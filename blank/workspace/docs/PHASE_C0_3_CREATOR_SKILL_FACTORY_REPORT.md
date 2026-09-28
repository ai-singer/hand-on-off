# PHASE_C0_3_CREATOR_SKILL_FACTORY_REPORT.md

**Phase C0.3 — Creator Skill Factory Architecture**

The objective changed from *Creator Instance Factory* to **Creator Skill Factory**:
classify, compose and generate the **skills** a Creator Agent is built from.

```text
"create a finance xiaohongshu creator"
              |
              v
   Creator Skill Factory   (this phase: architecture + protocol)
              |
              v
        Skill Bundle
              |
              v
   Lobster Shared Skill Library      (NOT implemented — out of scope)
              |
              v
   Creator Instance loads the bundle
              |
              v
   a runnable Creator Agent          (NOT implemented — out of scope)
```

This phase delivers **protocol, schema and builder design only**. It does not
deploy, call Lobster, upload a skill, generate content, invoke a model, or create
an agent.

---

## 1. Skill taxonomy

A skill answers exactly one question. Seven types cover the whole lifecycle:

| # | Skill type | 负责 | Question | Example | Required | Output |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `identity` | 是谁 | who is speaking | `finance-persona` | **yes** | `identity` |
| 2 | `domain` | 懂什么 | what it knows | `business-finance-analysis`, `technology-analysis` | **yes** | `domain_extension`, `value_signals` |
| 3 | `source` | 去哪里找信息 | where it finds material | `xiaohongshu-source`, `news-source` | **yes** | `raw_source_set` |
| 4 | `distillation` | 如何学习素材 | how it learns | `text-distillation`, `visual-style-distillation` | **yes** | `unified_distillation_artifact`, `visual_creator_profile` |
| 5 | `generation` | 如何生成内容 | how it produces content | `xiaohongshu-article-generation` | **yes** | `generation_request` |
| 6 | `review` | 审核 | what it must refuse | `finance-risk-review`, `evidence-review` | **yes** | `risk_constraints`, `gate_decision` |
| 7 | `publishing` | 发布 | where output goes | `xiaohongshu-publishing` | **yes** | `publishing_target` |

### 1.1 Composition skeleton

The taxonomy declares a `requires_prior` order, which is the shape of a valid
creator: **identity → domain → source → distillation → generation → review →
publishing** (with `generation` and `review` both following `distillation`, and
`publishing` following `review`).

### 1.2 How the split supports the five requirements

| Requirement | How the taxonomy delivers it |
| --- | --- |
| **Multi-domain** | Only `identity` and `domain` are domain-bound; the other five are domain-agnostic and reused verbatim. Adding a domain means adding two skills, not seven. |
| **Multi-platform** | `source` and `publishing` declare a platform; `distillation`, `review` and `generation` declare none and are shared across platforms. |
| **Multi-creator** | A different persona is a different `identity` skill; everything else is reused. |
| **Skill reuse** | Bundles share skills by reference. `text-distillation` appears in every bundle; two creators differ only where their compatibility differs. |
| **Skill version management** | Every skill carries `version` (semver) and `provenance.skill_version`, and the registry resolves `skill_id@version` exactly, refusing a version mismatch. |

---

## 2. Skill schema

`schema.build_schema()` **generates** the JSON Schema from the model's own
vocabularies rather than hand-writing it, following
`multimodal_creator.profile.schema`. A literal blob would drift from the model
silently; derivation means a vocabulary change cannot leave the two disagreeing.

Top-level required fields, exactly as the brief specifies:

```
skill_id · skill_type · version · description · capabilities · inputs ·
outputs · dependencies · compatibility · provenance · status
```

plus optional `reason`, `reusable`, `tags`.

### 2.1 Strictness and isolation are structural

- `additionalProperties: false` at every level. There is **nowhere to put** a
  prompt, a model call, or runtime code, so such a document is rejected by
  *shape* before any semantic check runs.
- The schema uses only the subset the project's dependency-free validator
  supports (`type` / `enum` / `required` / `properties` /
  `additionalProperties` / `items` / `minItems`) — no `$ref`, `allOf`, `oneOf`,
  `if`. A test asserts their absence.

### 2.2 Forbidden content, and how it is caught

| Forbidden | Layer 1: schema | Layer 2: semantic |
| --- | --- | --- |
| `prompt`, `system_prompt`, `negative_prompt`, `template_prompt` | rejected by shape | prompt *phrases* ("create image", "system prompt", "you are a", "act as a") rejected even under an innocent key |
| `model`, `model_call`, `model_id`, `model_reference`, `api_call` | rejected by shape | provider names (`openai`, `anthropic`, `gemini`, `httpx`) rejected inside any string |
| `code`, `script`, `python`, `executor`, `handler`, `callback`, `entrypoint`, `implementation`, `api_key`, `credentials`, `endpoint`, `webhook` | rejected by shape | `def `, `import `, `subprocess.`, `requests.`, `urllib`, code-shaped substrings, and references to `runtime.`, `distillation_core.`, `multimodal_creator.`, `risk_evaluation.` |
| hard-coded skill paths | — | `skills/` path literals rejected |

**A skill is a capability declaration, not executable code.** Four validation
checks enforce it: `schema`, `semantics`, `provenance`, `isolation`.

### 2.3 The check that scans values, not just keys

While testing, the isolation check failed to catch `outputs: ["runtime.engine"]`.
The cause was a real defect: the document walker yielded container values, so a
string nested inside a sequence was only ever seen as the containing list. A
dedicated string-walker now scans every string at every depth, and a test pins
that a legitimate capability name containing the word `runtime` (e.g.
`review.runtime_connected`) is **not** flagged — a check with false positives is
a check people switch off.

---

## 3. Bundle design

```json
{
  "bundle_id": "bundle-696970f4f76f7fd0",
  "request": { "domain": "finance", "platform": "xiaohongshu", "style": "education" },
  "selections": [
    { "skill_type": "identity",     "skill_id": "finance-persona",              "status": "available" },
    { "skill_type": "domain",       "skill_id": "business-finance-analysis",    "status": "available" },
    { "skill_type": "source",       "skill_id": "xiaohongshu-source",           "status": "declared"  },
    { "skill_type": "distillation", "skill_id": "text-distillation",            "status": "available" },
    { "skill_type": "generation",   "skill_id": "xiaohongshu-article-generation","status": "declared" },
    { "skill_type": "review",       "skill_id": "finance-risk-review",          "status": "available" },
    { "skill_type": "publishing",   "skill_id": "xiaohongshu-publishing",       "status": "declared"  }
  ],
  "extras": [ { "skill_id": "visual-style-distillation" } ],
  "notes": [], "alternatives": { "review": ["evidence-review"] }
}
```

### 3.1 Two structural decisions

1. **`selections` holds exactly one skill per type** — the creator's spine. The
   model rejects a duplicate type at construction, so "one skill per role" is an
   invariant, not a convention.
2. **`extras` holds additional skills of an already-satisfied type**, such as a
   visual-style distillation alongside text distillation. Keeping extras separate
   is what lets a bundle have two `distillation` skills without breaking the
   one-per-type rule, and a skill may not appear in both lists.

### 3.2 Verifiability

`SkillComposer.verify(bundle)` checks, and raises on any failure:

| Check | Meaning |
| --- | --- |
| `skills_exist` | every selected **and extra** skill id resolves in the registry, at the selected version |
| `types_unique` | no two selections share a skill type |
| `required_types` | every required type is present, **or** the gap is declared in `notes` |
| `dependencies` | `require` edges between selections are satisfied; a `conflict` edge whose partner is selected raises |
| `acyclic` | the selected subgraph has no dependency cycle |

**A bundle cannot reference a skill that does not exist** — that is the first
check, and it runs against the registry rather than trusting the bundle's own
contents. An incomplete bundle that declares no gap note is also rejected, so a
silent partial result cannot escape.

---

## 4. Composition flow

```text
CreatorRequest { domain, platform, style, declared_capabilities? }
        |
        v
for each required skill type, in taxonomy order:
        |
        +-- 1. FILTER by compatibility
        |       domain declared and not matched   -> incompatible, scored -1
        |       platform declared and not matched -> incompatible, scored -1
        |       style declared and not matched    -> incompatible, scored -1
        |       (an empty declaration is a wildcard, not a match)
        |
        +-- 2. FILTER by availability
        |       available skills win; a declared-but-unimplemented skill is used
        |       only when nothing available fits, and is marked `declared`
        |
        +-- 3. SCORE
        |       base = provenance.confidence
        |       + 0.30 domain match · + 0.30 platform match · + 0.20 style match
        |
        +-- 4. SELECT the best, record the reason and the rejected set
        |
        v
SkillBundle + reasons + rejected + unsatisfied  ->  verify()  ->  PASS/PARTIAL
```

### 4.1 Every selection states its reason

```text
identity:     finance-persona: matched domain finance; matched style education;
              confidence 0.40
domain:       business-finance-analysis: matched domain finance; confidence 1.00
source:       xiaohongshu-source: matched platform xiaohongshu; confidence 0.40
              (declared, not available: source_collection_strategy asset unavailable)
generation:   xiaohongshu-article-generation: matched platform xiaohongshu;
              confidence 0.00 (declared, not available: generation_capability_not_available)
review:       finance-risk-review: matched domain finance; confidence 1.00
publishing:   xiaohongshu-publishing: matched platform xiaohongshu;
              confidence 0.00 (declared, not available: publishing_capability_not_available)
```

The `rejected` map is emitted alongside, so a caller sees what lost and by how
much rather than only what won.

### 4.2 Composition results today

| Request | Selections | Complete? | Note |
| --- | --- | --- | --- |
| finance / xiaohongshu / education | 7 | **yes** | the full finance-xiaohongshu creator |
| finance / xiaohongshu + visual extra | 7 + 1 extra | **yes** | adds `visual-style-distillation` |
| sports / xiaohongshu | 5 | no | `identity`, `domain` unsatisfied — no sports skills exist |
| tech / bilibili | 4 | no | `identity`, `generation`, `publishing` unsatisfied |
| finance / web | 5 | no | `generation`, `publishing` unsatisfied |

A gap is reported, never filled by invention.

### 4.3 Determinism

`bundle_id` is `sha256(creator_id | domain | platform | style | type:id@version…)`
truncated to 16 hex characters, and the timestamp defaults to a fixed epoch
value. Composing the same request twice yields a byte-identical bundle, so a
re-run is diffable — which is what makes a factory safe to re-run.

---

## 5. Existing asset mapping

Every skill is bound to a **registered asset** in
`creator_projection/assets.yaml`. No skill path is hard-coded anywhere; a test
asserts every catalog `source_ref` resolves, and another asserts that no module
contains an absolute path or a skill path literal.

| Existing asset | Contract module (C0.2) | **Skill** (C0.3) | Status |
| --- | --- | --- | --- |
| `text_distillation_rules` | `identity`, `domain` | `finance-persona`, `business-finance-analysis`, `technology-analysis` | available / declared |
| `text_structure_templates` | `text_rules` | `text-distillation` | available |
| `visual_profile_m5` | `visual_rules` | **`visual-style-distillation`** | available |
| `risk_policy_reference` | `risk_policy` | `finance-risk-review` | available |
| `evaluation_rubric` | `text_rules`, `risk_policy` | `evidence-review`, `news-source` | available / declared |
| `generation_capability` (unavailable) | `generation` | `xiaohongshu-article-generation` | **declared** |
| `publishing_capability` (unavailable) | `publishing` | `xiaohongshu-publishing` | **declared** |
| `source_collection_strategy` (unavailable) | `source` | `xiaohongshu-source` | **declared** |

Direct mappings requested by the brief:

```text
M5 Visual Profile  ->  visual-style-distillation   (distillation_artifact: visual_profile_m5)
Text rules         ->  text-distillation           (template: text_structure_templates)
Risk policy        ->  finance-risk-review         (template: risk_policy_reference)
```

### 5.1 Provenance: no unsourced skill

Every skill carries `source_kind` (`template` / `distillation_artifact` /
`projection` / `manual`), `source_ref`, `skill_version`, `generated_at`, and
`confidence`. A `distillation_artifact` or `projection` source must **resolve in
the asset registry**, so a skill cannot claim to derive from something that does
not exist. Confidence is assigned by source kind (manual = 0.7, derived = 1.0),
and the three skills bound to unavailable assets carry **0.0** — an unimplemented
capability must not claim confidence it has not earned.

---

## 6. Test result

```text
tests/creator_skill_layer/
    test_schema.py                 36 tests
    test_taxonomy_and_model.py     66 tests
    test_registry.py              56 tests
    test_composition.py           59 tests
    test_provenance.py            32 tests
    test_negative.py              44 tests
    test_isolation.py             15 tests
                                 ─────────
                                 308 tests, OK
```

Target was ≥150; delivered **308**.

### 6.1 Required coverage

| Required area | Tests | Result |
| --- | --- | --- |
| **Skill schema** — valid, invalid, forbidden fields | 36, incl. 20 forbidden fields each asserted rejected | **pass** |
| **Registry** — register, resolve, missing dependency | 56, incl. duplicates, version pinning, cycles, conflicts, unregister guards | **pass** |
| **Composition** — finance, sports, mixed | 59, incl. all five scenarios in §4.2 | **pass** |
| **Provenance** — missing source rejected | 32, incl. every required key removed in turn, unregistered artifact rejected | **pass** |
| **Isolation** — runtime/production/risk/multimodal/distillation untouched | 15, incl. AST import analysis and SHA256 sweeps | **pass** |

### 6.2 Isolation verification

| Check | Result |
| --- | --- |
| `creator_skill` imports from `runtime`, `production`, `risk_evaluation`, `multimodal_creator`, `distillation_core`, `workflows`, `plugins`, `artifact`, `security` | **none** (verified by AST, not grep) |
| The six frozen directories change during registry, composition and verification operations | **no** (SHA256 tree comparison before/after) |
| Absolute paths or skill path literals in the package | **none** |
| `creator_skill` reads the projection layer | **yes** — that is the point of C0.3 |

### 6.3 Three real defects found by the tests, and fixed

1. **`_walk` did not scan strings nested in sequences**, so `outputs:
   ["runtime.engine"]` passed the isolation check. A real hole in a security-shaped
   check, found by a negative test. Fixed with a dedicated string-walker.
2. **`verify()` could not see a gap note.** `_build_bundle` was called *before*
   the partial-bundle note was appended, and `SkillBundle` is frozen — so the note
   never reached the bundle, and `verify` then refused every partial bundle.
   Order corrected; notes are now recorded before construction.
3. **`require` and `enhance` edges were treated identically** in
   `validate_dependency`, so an optional enhancement to an absent skill was
   reported as a missing dependency. `enhance` edges are now satisfied-or-skipped
   by definition; only `require` edges can be missing.

A fourth finding was **not** a defect: the dependency graph initially coupled
`source` skills to specific domain skills, which made every non-finance bundle
fail. The edges now express genuine compositional need (generation needs
distillation, publishing needs review), while the taxonomy's `requires_prior`
ordering is enforced by composition order rather than smuggled into the graph.

---

## 7. Remaining blockers

| # | Blocker | Severity | Impact on the Skill Factory |
| --- | --- | --- | --- |
| B1 | **No sports or tech persona exists** | High | A sports bundle cannot satisfy `identity`/`domain`; a tech bundle has a domain taxonomy but no persona. Only finance composes completely. |
| B2 | **Source, generation and publishing are declared, not implemented** | High | Three of seven slots in every bundle are capabilities without implementations. `allow_unavailable=False` refuses every bundle today. |
| B3 | **No Lobster Shared Skill Library integration** | High | The bundle cannot be published or shared. Explicitly out of scope for this phase. |
| B4 | **Nothing loads a bundle** | High | `runtime.bootstrap` reads `runtime/config/default.json`; no component consumes a SkillBundle. |
| B5 | **Skill packaging/versioning is single-version per id** | Medium | The registry holds one version per skill id and refuses a second. Multi-version coexistence needs a versioned key. |
| B6 | **No skill-level evaluation** | Medium | Nothing measures whether a skill *works*; provenance records where a skill came from, not whether it helps. |
| B7 | **No bundle-to-instance mapping yet** | Medium | C0.2 projects an *instance*; the path from a bundle to an instance's `plugin` is not defined. |
| B8 | **`technology-analysis` is declared, not authored** | Medium | Its taxonomy dimensions are asserted without tech-specific rules; confidence is 0.5. |
| B9 | **No schema file written to `schemas/`** | Low | The schema is generated at runtime into a temp file. Writing it to `schemas/creator_skill.schema.json` would match the project convention. |

**Blocking summary:** B1–B4 must be resolved before any generated bundle is
usable. B5–B9 are quality and integration gaps.

---

## 8. Recommended next phase (C0.4)

### C0.4-A — Bundle → Instance mapping (recommended first)

Define how a `SkillBundle` becomes a C0.2 Creator Instance. This closes the loop
the two phases opened: C0.2 projects an instance from assets, C0.3 composes skills
from those same assets, and nothing yet connects them. It is small, mechanical,
and makes the architecture demonstrable end to end.

### C0.4-B — Instance loading

Teach the runtime to load a Creator Instance and derive its selection from it.
This is the first point at which either C0.2 or C0.3 output has a consumer.

### C0.4-C — Author the missing skills

Add sports and tech personas, and promote the three declared capabilities to
available once implementations exist. Every `status: declared` is a promise the
architecture currently cannot keep.

### C0.4-D — Skill packaging format

Define the on-disk Skill Bundle artifact (`bundle.json` + skill documents) and a
validator, so a bundle can be written, diffed, and eventually uploaded. **Do not
integrate Lobster** — define the artifact only.

### C0.4-E — Multi-version skill registry

Key skills by `(skill_id, version)` so two versions can coexist, which is a
prerequisite for a shared library where different creators pin different versions.

**Recommended scope: A + D.** Both are self-contained, need no capability that
does not exist, and produce a concrete artifact. B is larger and touches the
runtime. C depends on content authoring rather than architecture.

---

## 9. Deliverables

### 9.1 `creator_skill/` package

```text
creator_skill/
    __init__.py         public surface
    errors.py           SkillError + 6 subtypes
    model.py            CreatorSkill, SkillBundle, CreatorRequest, provenance
    taxonomy.py         the seven skill types and the composition skeleton
    schema.py           JSON Schema generated from the model vocabularies
    registry.py         SkillRegistry: register, resolve, validate_dependency, list
    composition.py      SkillComposer: request -> verified bundle, with reasons
    catalog.py          the shipped 11-skill catalog
    provenance.py       source and version records
    validation.py       schema, semantics, provenance, isolation
```

### 9.2 Tests

`tests/creator_skill_layer/` — 7 files, 308 tests.

---

## 10. Compliance statement

| Constraint | Status |
| --- | --- |
| Do not modify `runtime/` | **No changes** |
| Do not modify `production/` | **No changes** |
| Do not modify `workflows/` | **No changes** |
| Do not modify `risk_evaluation/` | **No changes** |
| Do not modify `multimodal_creator/` | **No changes** |
| Do not modify `distillation_core/` (also named) | **No changes** |
| Do not modify `plugins/` (also named) | **No changes** |
| Do not integrate the Lobster API | **Not integrated** — no client, no endpoint, no call |
| Do not upload a real skill | **Nothing uploaded** |
| Do not generate content | **Nothing generated** |
| Do not call a model | **No model call** anywhere in the layer |
| Do not create a real agent | **No agent created** |
| Only protocol, schema, builder design | `creator_skill/` + tests + this report |

Verification: the six frozen directories are read-only in this phase, asserted by
SHA256 tree comparison in `test_isolation.py` under registry, composition and
verification operations.

`creator_projection` and `creator_contract` were **read** and not modified; `core`
is imported for its existing schema validator, as C0.2 also does.

---

## 11. Commit

```
feat: define creator skill factory architecture
```

Not pushed.
