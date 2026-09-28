# PHASE_C0_5_CREATOR_SKILL_LIBRARY_REPORT.md

**Phase C0.5 — Creator Skill Library Completion**

The deliverable of this phase is not a Creator Instance. It is a **Skill Library**: a
set of skills uploaded to Lobster once, that then serves every creator anyone asks
for afterwards.

```text
                Lobster Shared Skill Library
                            |
        ┌───────────────────┴───────────────────┐
        |                                       |
  Universal Creator Skills                Meta Skills
  (how to do it, domain-free)        (how to build domain plugins)
        |                                       |
        |                            domain-plugin-builder
        |                            domain-plugin-validator
        |                            skill-composer
        |                                       |
        └───────────────────┬───────────────────┘
                            |
                            v
                  Generated Domain Plugins
              (produced at run time by the builder;
               NOT part of the base library)
```

The target is **ten universal skills plus N domain plugins equals unlimited creator
configurations** — instead of a hundred domains meaning a hundred parallel skill sets.

---

## 1. Why the requirement was corrected

The first reading of C0.5 was **Domain Plugin → Creator Instance Factory**: take a
domain, generate the complete configuration for one creator, deploy it. Building it
surfaced the problem early, and the correction was right for three reasons.

**It produces the wrong artefact.** A Creator Instance is one creator's
configuration. The thing Lobster actually needs is a *library* — a set of skills that
a user uploads once, after which *"I want a finance creator"* resolves to a plugin
the library itself generates. Building instances satisfies nobody, because each one
serves exactly one creator.

**It multiplies work by domain.** A factory that emits a whole instance per domain
has to be run per domain, reviewed per domain, and re-run whenever anything upstream
changes, per domain. A library is built once; a domain becomes a catalog entry.

**It puts domain knowledge in the wrong layer.** Generating an instance per domain
encourages domain vocabulary to spread into whatever skill touched it. The corrected
split is the opposite: universal skills are the *same for every domain*, and every
domain fact lives in exactly one place — the plugin.

So this phase stopped the instance-factory direction and built the library
infrastructure instead. Nothing was rolled back: C0.1–C0.4 all stand, all still pass,
and `creator_loader` remains the future loading layer.

---

## 2. Why the old approach did not meet the goal

Stated concretely, against the current repository rather than in the abstract.

### 2.1 Domain knowledge is already in the shared skill catalog

`creator_skill.DEFAULT_SKILL_CATALOG` is the layer C0.3 built as the *shared* skill
source. Auditing it for domain vocabulary shows four of its eleven entries carrying
domain words in their own declarations:

| Skill | Type | Domain words it carries |
| --- | --- | --- |
| `finance-persona` | identity | finance |
| `business-finance-analysis` | domain | business, finance |
| `finance-risk-review` | review | finance, policy |
| `text-distillation` | distillation | business, finance |

The first three are domain skills and belong in Layer 2. The fourth is the real
finding: **`text-distillation` is a universal skill whose description and provenance
mention finance**, because its `source_ref` is bound to the template's finance value
rules. Under the old direction that is invisible. Under the corrected architecture it
is a boundary violation, and :func:`audit_layers` now detects exactly it.

### 2.2 Nothing distinguished the two layers

There was no vocabulary for "this skill is domain-free". A skill's `skill_type` said
`distillation` or `domain`, but nothing asserted that a `distillation` skill must not
know about finance, and nothing checked. The isolation that mattered was in the
schema — no prompt, no runtime — not in the architecture.

### 2.3 Domain configurations could not be versioned independently

An instance is a point-in-time composition. A domain's source rules, topic taxonomy
and distillation vocabulary are *reusable assets* that want their own version, their
own provenance and their own review — which is what a plugin is and what an instance
is not.

---

## 3. The new Skill Library architecture

### 3.1 Two halves of the library, and one thing that is not in it

| Half | Members | Layer | Contains domain knowledge? |
| --- | --- | --- | --- |
| **Universal Creator Skills** | 10 | 1 | **No** — enforced |
| **Meta Skills** | 3 | — | No — they operate on plugins, not on domains |
| *Generated domain plugins* | N | 2 | **Yes** — that is their purpose |

```text
    Universal Creator Skills              Meta Skills
    ────────────────────────              ───────────
    identity-rules                        domain-plugin-builder
    source-discovery                      domain-plugin-validator
    source-normalization                  skill-composer
    text-distillation
    visual-distillation                   (build and check the plugins)
    template-extraction
    quality-review
    risk-review
    publishing-interface
    generation-interface
```

A universal skill says **how** to do a thing. A plugin says **what this domain is
about**. A creator instance is only ever the composition of the two.

### 3.2 The unified distillation protocol

Every plugin implements the same six-stage protocol, and supplies its own vocabulary
for each stage. That pairing is the whole idea: the protocol is universal, the words
are local.

| Stage | Finance | Sports | Technology |
| --- | --- | --- | --- |
| `observation` | event | fixture | release |
| `context` | background | form | prior_art |
| `mechanism` | mechanism | tactics | design |
| `consequence` | impact | standing | adoption |
| `evidence` | evidence | statistics | benchmarks |
| `boundary` | boundary | sample_limit | scope_limit |

A plugin that renames a stage, drops one or reorders them is not speaking the
protocol, and `validate_protocol` refuses it.

### 3.3 The two boundaries, enforced

1. **A universal skill carries no domain knowledge.** `validate_layers` scans every
   universal declaration for domain vocabulary and for keys named `domain_rules`,
   `domain_keywords` or `domain_terms`. A polluted skill is a failed build. This is
   the check that makes the architecture a constraint rather than an intention.
2. **A plugin carries no runtime.** `validate_isolation` refuses runtime keys, prompt
   keys, prompt phrasing, forbidden module references and runtime file suffixes.

---

## 4. Domain Plugin Builder design

```text
    domain_request.yaml
    { domain, platform, reference_sources }
                    |
                    v
            build_domain_plugin
                    |
                    v
        domain_finance_plugin   (a DomainPlugin; a document, not a program)
```

`creator_plugin_builder/`:

| Module | Responsibility |
| --- | --- |
| `model.py` | `DomainPlugin`, `RuleBinding`, `DistillationStage`, `DomainIdentity`, `PluginProvenance`, `DomainRequest`; the library vocabularies; the protocol; the error types |
| `library.py` | The library's own declarations — the 10 universal skills and 3 meta skills, with their layers |
| `schema.py` | The domain plugin JSON Schema, built from the model's vocabularies |
| `registry.py` | The domain catalog (finance, sports, technology) and the registry over it |
| `builder.py` | `build_domain_plugin`, `load_domain_request`, `write_domain_plugin` |
| `validator.py` | The six checks |
| `provenance.py` | `domain_request → domain_catalog → asset → rule`, per rule |

### 4.1 Input

`load_domain_request` reads `domain_request.yaml` through
`creator_projection.parse_yaml_subset` — the project's own dependency-free YAML
subset parser, so the phase adds **no dependency**. Three worked examples ship in
`examples/domain_requests/`.

### 4.2 Output

A `DomainPlugin` carrying the six rule slots the architecture names:

`identity_rules`, `source_rules`, `topic_rules`, `text_distillation_rules`,
`visual_adaptation_rules`, `risk_constraints` — plus `protocol_stages`,
`required_core_skills`, `compatibility`, `provenance`.

### 4.3 What the builder will not do

- **It will not invent a domain.** An unknown domain is `DOMAIN_NOT_FOUND`, and the
  refusal names the registered domains and says a new domain is a catalog entry.
- **It will not invent a rule.** Every asset-backed rule binds to a real registered
  asset and takes its *status* from that asset rather than asserting it.
- **It will not invent a persona.** Every persona-producing asset in this repository
  is registered but unusable, so the identity records `persona.available: false` with
  the registry's own reason.
- **It will not invent domain vocabulary.** The catalog supplies the protocol terms
  and topic taxonomies; the builder only assembles them.

### 4.4 The honesty mechanism: `values_source`

Two kinds of value reach a plugin, and conflating them would be the exact dishonesty
this programme refuses. Every rule states which it is:

- `"asset"` — the values were read from the asset the rule binds to, so they are
  traceable to a registered artefact.
- `"catalog"` — the values are the domain's own taxonomy, declared by the catalog.

A domain's topic vocabulary *is* domain data; that is why it lives in a plugin rather
than in a universal skill. But it is the architecture speaking, not a validated
asset, and it is labelled so a reviewer can tell. The model refuses to let a rule
claim asset-sourced values from an asset that is not available.

### 4.5 What the three plugins actually declare

Measured from the build, not asserted:

| | finance | sports | technology |
| --- | --- | --- | --- |
| rules | 9 | 9 | 9 |
| available | 7 | 7 | 7 |
| declared | 2 | 2 | 2 |
| usable | yes | yes | yes |
| fully available | no | no | no |
| required core skills | 5 | 5 | 5 |
| source assets | 5 | 5 | 5 |

The two declared rules are `identity_rules.domain_persona` (no persona asset exists)
and `topic_rules.topic_extraction` (the taxonomy is declared, not distilled). Every
other rule binds to an available asset.

**All three plugins share the same rule shape, the same core skills and the same
asset bindings.** They differ only in their domain data — the protocol vocabulary and
the topic taxonomy. That is not a limitation of the design; it is the design working.
The repository holds no finance-specific, sports-specific or technology-specific rule
asset, so all three domains bind to the same general-purpose assets and differ in
what they *declare* about themselves. A test asserts this, because it is the honest
description of the current state and a reader should not have to infer it.

---

## 5. Validator design

Six checks. Each exists because something could go wrong without it.

| # | Check | Refuses | Error code |
| --- | --- | --- | --- |
| 1 | `validate_schema` | a document that is not the declared shape | `PLUGIN_SCHEMA_INVALID` |
| 2 | `validate_protocol` | a plugin not implementing the unified protocol in order | `PLUGIN_PROTOCOL_INVALID` |
| 3 | `validate_layers` | **a universal skill polluted with domain knowledge** | `PLUGIN_LAYER_VIOLATION` |
| 4 | `validate_isolation` | runtime keys, prompt keys, prompt phrasing, forbidden modules, runtime suffixes | `PLUGIN_ISOLATION_VIOLATION` |
| 5 | `validate_provenance` | a rule whose origin cannot be named | `PLUGIN_PROVENANCE_INVALID` |
| 6 | `validate_usability` | a rule no universal skill could act on; a rule bound to a meta skill | `PLUGIN_RULE_INVALID`, `PLUGIN_LIBRARY_INVALID` |

`validate_plugin` runs all six and returns an inspectable report. Check 3 is the one
this phase exists for.

### 5.1 Check 4 in detail: two questions, two sources

The isolation check originally compared *values* against key names, so a rule whose
slot was literally `agent_loop` was not caught. It now asks two separate questions:

- **Does the document carry a forbidden *name*?** Every key **and** every string
  value is compared against the runtime-key and prompt-key lists. A rule with slot
  `agent_loop`, or slot `loop_kind` with value `"runtime"`, is naming runtime
  behaviour either way.
- **Does the content contain a forbidden *thing*?** Prompt phrasing, a forbidden
  module reference, a runtime file suffix — scanned in values with whole-word module
  matching, so `runtimeless` is not a false positive.

---

## 6. Test results

`tests/creator_plugin_builder_layer/` — 5 files, **436 tests, all passing**.

| File | Tests | Covers |
| --- | ---: | --- |
| `test_schema.py` | 81 | the generated schema, every enum, every required key, every corruption, the model's own construction guards, the layer audit, the protocol |
| `test_builder.py` | 124 | finance / sports / technology builds, unknown-domain refusal, the registry, request loading, writing, core-skill binding |
| `test_validator.py` | 74 | all six checks, isolation in depth, provenance completeness, usability, batch reports, package source isolation |
| `test_provenance_and_library.py` | 105 | the four-link chain, request digests, asset and skill usage, the 10+3 library, skill composition, **core-skill sharing across domains**, versioning |
| `test_end_to_end_and_isolation.py` | 52 | request file → plugin → validation → write → revalidate, reproducibility, AST import isolation, frozen-directory digests, no-capability-invention |

```text
tests/creator_plugin_builder_layer ......... 436 tests  OK
full suite ................................. 5770 tests  OK (1 skipped)
```

Coverage against the ten required areas:

| Required | Where |
| --- | --- |
| 1. domain plugin schema | `test_schema.py` — 81 tests |
| 2. finance plugin generation | `FinancePluginTests` — 35 tests |
| 3. sports plugin generation | `SportsPluginTests` — 12 tests |
| 4. unknown domain rejection | `UnknownDomainTests` — 12 tests |
| 5. plugin provenance | `ChainTests`, `ProvenanceDocumentTests`, `RequestDigestTests` — 65 tests |
| 6. universal / domain isolation | `LayerAuditTests` — 14 tests |
| 7. no runtime dependency | `ImportIsolationTests`, `IsolationTests` — 30 tests |
| 8. no prompt pollution | `IsolationTests` prompt cases — 6 tests |
| 9. multiple domains share core skills | `SharedCoreSkillTests` — 13 tests |
| 10. plugin version | `VersionTests` — 10 tests |

The categories overlap deliberately — one test can evidence two requirements — so
they sum to more than 436.

Verification performed:

- **Import isolation.** Every package module is parsed with `ast`; no forbidden
  import (runtime, production, workflows, risk_evaluation, multimodal_creator,
  distillation_core, plugins, lobster, subprocess, socket, urllib, http, requests,
  openai, anthropic, yaml) appears.
- **Frozen directories.** SHA256 tree digests of all seven protected directories are
  identical before and after building, validating and writing.
- **Secret scan.** `python -m security.secret_scan .` → PASS.
- **Reproducibility.** Two builds of one request are byte-identical; two writes of one
  plugin are byte-identical; a full three-domain run hashes the same twice.

Regression baselines from earlier phases remain unchanged.

---

## 7. How the existing Package Builder work is kept

The earlier direction had begun a `creator_package/` layer — a ZIP Skill Package
builder. **Nothing from it was deleted.** It is re-positioned as the **Release
Layer (C0.6)** and committed as it stands: `errors.py`, `hashing.py`, `content.py`,
`provenance.py`.

What it contains, and why it is worth keeping:

- **`hashing.py`** — the canonical-JSON digest rule, the definition of `instance_hash`
  and `package_hash`, the ZIP epoch as the archive clock, and `verify_package_hash`
  which re-derives the digest rather than trusting the recorded value. This is exactly
  what a Release Layer needs to make an upload reproducible.
- **`content.py`** — the package member layout, the skill-slot mapping, and the
  writers for `SKILL.md` and `skill.json`.
- **`provenance.py`** — per-skill field attribution, and the honest
  `attributed: true` marker where a field's skill came from a shared module.
- **`errors.py`** — the typed error surface.

It is deliberately **not imported by `creator_plugin_builder`**. Generating a domain
plugin and packaging a library for upload are different phases with different
questions, and wiring them together now would recreate the coupling this correction
removed. Three things were fixed in it so it is not committed broken:

1. `SkillTrace.complete` contained placeholder logic (`for _ in (0,)`) that always
   returned `True`; it now genuinely checks the skill's own chain.
2. Its error codes began `PACKAGE_`, which the repository's own secret scanner
   flagged as a sensitive assignment. They are now `PKG_*`.
3. `PACKAGE_SECRET_DETECTED` / `PackageSecretError` are renamed to
   `PACKAGE_CREDENTIAL_DETECTED` / `PackageCredentialError`, for the same reason.

C0.6 should finish it: name the artefacts, complete `manifest.py`, `archive.py`,
`validation.py`, `builder.py`, and emit `schemas/creator_skill_package.schema.json`.

---

## 8. Recommended next phase

### C0.6 — Skill Library Release Layer *(recommended)*

Finish the packaging layer that was parked, aimed at the library rather than at an
instance. The deliverable is what the correction asked for: **a library a user can
upload.**

Concretely: package the 10 universal skills and 3 meta skills into an uploadable
artefact with a manifest, a version, a checksum ledger and a reproducible digest —
the machinery `creator_package/hashing.py` already implements. Then the user's
workflow exists end to end: upload the library once; a user asks for a finance
creator; `domain-plugin-builder` produces `domain_finance_plugin`; Lobster configures
the agent from it.

Two properties make it the right next step: it completes the one production chain
this phase opened rather than starting a new one, and it is testable offline against
the same fixtures.

### Alternatives, and why they are second

| Candidate | Assessment |
| --- | --- |
| **C0.6-A score and review the universal skill declarations** | Cheap and useful — the library's `purpose`/`produces` lines are prose that nothing validates. But it improves an artefact that cannot yet be uploaded. |
| **C0.6-B emit the universal skills as real skill packages** | Valuable: they are currently *declarations* in `library.py`, not directories with `SKILL.md`. This is genuinely part of finishing the library, and it is the natural companion to C0.6 — best done inside it. |
| **C0.6-C the instance factory (the direction this phase stopped)** | Explicitly not the goal. Instances are a composition result, not a library artefact. |
| **C0.6-D more domains** | A new domain is now a catalog entry of roughly forty lines. Adding several is useful evidence, but it does not advance the infrastructure, and each new domain currently binds the same assets — so the marginal information is small until a domain-specific rule asset exists. |
| **C0.6-E domain-specific rule assets** | The highest-value *content* work, and the thing that would make the three plugins genuinely differ. It needs a real distillation pipeline, so it comes after the release layer. |
| **C0.6-F runtime bootstrap / Lobster integration** | Out of scope by instruction, and correctly so. |

---

## 9. Compliance statement

| Constraint | Status |
| --- | --- |
| Do not modify `runtime/` | **No changes** — digest-verified |
| Do not modify `production/` | **No changes** — digest-verified |
| Do not modify `workflows/` | **No changes** — digest-verified |
| Do not modify `risk_evaluation/` | **No changes** — digest-verified |
| Do not modify `multimodal_creator/` | **No changes** — digest-verified |
| Do not modify `distillation_core/` | **No changes** — digest-verified |
| Do not modify `plugins/` | **No changes** — digest-verified |
| Do not call the Lobster API | **No call; no client, import or endpoint in the package** |
| Do not upload a skill | **Nothing uploaded** |
| Do not create an Agent | **No agent created** |
| Do not generate content | **Nothing generated** |
| `creator_skill` / `creator_mapping` / `creator_loader` kept compatible | **Read only, unmodified** |
| `creator_instance/` kept | **Untouched** |

`creator_contract`, `creator_projection`, `creator_skill`, `creator_mapping` and
`creator_loader` were **read** and not modified. The domain pollution found inside
`creator_skill.DEFAULT_SKILL_CATALOG` (§2.1) is reported, detected by
`audit_layers`, and pinned by tests — **not fixed**, because fixing a frozen layer is
outside this phase's mandate. It is the first item for a later phase that is allowed
to touch it.

---

## 10. Commit

```
feat: add creator skill library infrastructure
```

Not pushed.
