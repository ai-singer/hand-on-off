# PHASE_C0_4_B_INSTANCE_LOADER_REPORT.md

**Phase C0.4-B — Creator Instance Loader**

C0.4-A finally produced a `creator_instance` artifact. Nothing could read it::

```text
    creator_instance artifact
             |
             v   creator_loader          ← this phase
             |
    Loaded Creator Configuration
```

This phase is a **configuration-reading layer and nothing else.** It is not a
runtime. It does not execute an Agent, run a workflow, deploy to Lobster, call a
model, or generate content. It opens documents, checks them, and freezes what it
found.

---

## 1. Loader architecture

```text
creator_loader/
    errors.py        LoaderError + 12 subtypes, each with a stable code
    model.py         the frozen result: LoadedCreatorInstance and its parts
    resolver.py      AssetReferenceResolver — references, never contents
    provenance.py    parse both provenance shapes; trace a field to its origin
    validation.py    seven pre-load layers, plus assert_immutable
    loader.py        load_creator_instance, compare_loaded_instances
    __init__.py      the public surface
```

Three principles hold the layer together, and all three are enforced mechanically
rather than documented:

**1. The artifact is never modified, and a gap is never filled.** The package
contains no write call of any kind — `write_text`, `write_bytes`, `open`, `mkdir`,
`unlink`, `.pop`, `del` — and `tests/creator_loader_layer/test_isolation.py` asserts
that by reading the source. A missing field is reported as
`INSTANCE_FIELD_MISSING`; filling it would produce a fabricated instance.

**2. A capability is never enabled.** No assignment in the package writes
`"enabled": True`; a test asserts that too. The loader reads the state the artifact
records and reports it. It has no code path that turns `unavailable` into
`available`, and three tests load instances in all three shapes and confirm
`enabled_capabilities()` is empty.

**3. An asset reference is read; an asset is never executed.** The resolver asks the
C0.2 registry for an asset's *id, type, status, location*. It does not read the
asset's document and nothing is rendered from it. `AssetReference` has no field
capable of holding content, and a test asserts that.

### 1.1 The loader reads four layers and changes none of them

It reads C0.1 (`creator_contract`) for the contract schema, its validation, and the
module layout; C0.2 (`creator_projection`) for the asset registry; C0.4-A
(`creator_mapping`) for the field rules and the required-path list; and it does
**not** import `creator_skill` at all — skills are read through the artifact, not
re-composed. A test asserts each of those, including the absence.

### 1.2 Two on-disk layouts, and an explicit precedence

| Layout | Document | What it carries |
| --- | --- | --- |
| Aggregate | `instance.json` (C0.4-A) or `creator_instance.json` (C0.1) | the whole artifact: seven modules, per-field traces, per-module availability, factory identity |
| Modules | `<module>.json` × 7 + `provenance.json` | the modules, the contract provenance blocks, and the bare per-field map |

The aggregate is read when it is present. The `modules` layout exists for an
artifact whose aggregate is missing, and a caller asks for it by name
(`layout="modules"`). **Nothing falls back silently** — a malformed or stale
aggregate is reported, never quietly bypassed, and a test pins that.

The two layouts are **not equivalent**, and the loader does not pretend they are.
`provenance.json` has no `generated_by`, so the `modules` layout cannot name the
bundle that produced the instance; it reports `(not recorded)`. What it *can* do is
recover each module's availability from facts it does carry — the per-field records
name the asset and the mode, and each module's contract block states its own asset
status — and it marks every recovered record `derived_from_field_records: true` so a
caller can see which records came from where.

---

## 2. Input / output

### 2.1 Input

```python
load_creator_instance(
    path,                     # an instance directory, or a single aggregate document
    *,
    resolver=None,            # how asset references resolve; built from workspace_root
    workspace_root=None,      # defaults to this repository's workspace
    strict=True,              # run every pre-load check
    layout="prefer-aggregate",
) -> LoadedCreatorInstance
```

### 2.2 Output

`LoadedCreatorInstance` — a frozen dataclass whose every mapping field is wrapped in
`MappingProxyType` on construction, so it is immutable however it was built:

```text
LoadedCreatorInstance
    instance_id          the creator id, from the identity module
    source_path          where the artifact was read from
    contract_version     the C0.1 contract version
    modules              the seven configuration modules, frozen
    raw_provenance       the provenance block as it was read, frozen
    provenance           InstanceProvenance
    capabilities         {module: LoadedCapability}
    asset_references     {asset_id: AssetReference}
    validation           the check map the loader produced
```

`InstanceProvenance` separates four things a caller asks about separately:

```text
    kind               "mapped" | "projected" | "absent"
    generated_by       the producing line, e.g. "creator_mapping.mapper c0.4-a …"
    bundle_id          the skill bundle, or "(not recorded)"
    factory_version    the producing layer's version
    mapping_version    the mapping layer's version
    mapping_rule_count how many rules the mapping applied
    field_traces       {field: FieldTrace} — the per-field chains
    module_records     the per-module provenance records
    asset_references   {asset_id: AssetReference}
```

`LoadedCapability` reports one module's state and nothing more:

```text
    state          "available" | "declared" | "unavailable" | "absent"
    enabled        the artifact's own flag, or None where the shape has none
    reason         why, as the artifact states it
    skill_ids      the skills that fed this module
    asset_id       the asset the module's record names
    asset_status   that asset's status
```

Three accessors, deliberately distinct:

- `enabled_capabilities()` — modules the artifact marks enabled. Empty for every
  artifact this repository can currently produce, which is the honest answer.
- `unavailable_capabilities()` — `declared` or `unavailable`. **Not** `absent`.
- `absent_capabilities()` — the module records no own asset at all.

The `absent` distinction matters. C0.4-A's `source` module records
`asset_id: "(none)"` because its fields are derived from other modules' assets, not
because its capability is missing. Reporting that as `unavailable` would overstate
the gap the artifact actually has, so `source` is reported `absent` and stays out of
`unavailable_capabilities()`.

---

## 3. Validation flow

Seven layers run before a load completes. Each raises its own typed error carrying a
stable machine-readable code, so a caller can branch on `INSTANCE_FIELD_MISSING`
rather than parse a message.

| # | Layer | Checks | Code on failure |
| --- | --- | --- | --- |
| 1 | `validate_modules` | all seven modules present, each an object, plus provenance | `INSTANCE_MODULE_MISSING` |
| 2 | `validate_schema` | the document matches the C0.1 contract schema | `INSTANCE_SCHEMA_INVALID` |
| 3 | `validate_contract` | C0.1's own validation: schema, dependencies, capability declaration, isolation | `INSTANCE_CONTRACT_INVALID` |
| 4 | `validate_fields` | every field C0.4-A's 46 rules declare is present | `INSTANCE_FIELD_MISSING` |
| 5 | `validate_provenance_block` | provenance present, complete, of a recognised shape | `INSTANCE_PROVENANCE_INVALID` |
| 6 | `validate_capabilities` | no capability claims more than its record supports | `INSTANCE_CAPABILITY_INVALID` |
| 7 | `validate_traceability` | every field accounted for by the shape in use | `INSTANCE_PROVENANCE_INVALID` |

Then, after the object is built:

| # | Check | Proves |
| --- | --- | --- |
| 8 | `assert_immutable` | the loaded object rejects a write, empirically |
| 9 | `untraced_fields` / `untraced_projection_fields` | no trace was lost in the load |

### 3.1 The provenance-shape problem, and how it is handled

Two provenance shapes exist in this repository and they do not mean the same thing:

- **mapped** (C0.4-A) — `provenance.field_provenance` carries `fields` (one record
  per instance field) and `modules` (one availability record per module). Every
  field is traceable to a skill, an asset, a rule and a version.
- **projected** (C0.2) — no mapping payload at all. Provenance is per module: where
  the module came from, by what method, with what confidence.

The loader reads both and **says which one it found** (`provenance_kind`). It does
not trace a projected instance as though it were mapped, because that would invent a
chain the artifact never recorded. `trace_instance` on a projected instance returns
zero chains, `complete: None` — not `False`, because "there is nothing to trace" and
"everything is traced" are different facts — and a `detail` string explaining the
shape.

The classifier is structural and refuses to guess. A `field_provenance` key with
`fields` and `modules` is mapped *whether or not those maps are empty*; a payload
that has lost one of them is reported `absent` rather than quietly re-labelled
projected. That distinction is not academic: the first version of the classifier
waved a **damaged** artifact through as a projected one with no traces, and layer 5
passed it. A test now pins the correct behaviour.

### 3.2 Capability honesty

Layer 6 refuses a contradiction and never reconciles one by choosing a side:

- an available source that is not enabled → rejected
- enabled without an available source → rejected
- disabled with no declared reason → rejected
- a record that states no availability at all → rejected

The derivation table is explicit so a reader can check it and a test can pin each
branch:

| Record says | State |
| --- | --- |
| `has_available_source: true` | `available` |
| `asset_status: unavailable` (with a named asset) | `declared` |
| a named asset, status neither available nor unavailable | `unavailable` |
| no own asset (`asset_id: "(none)"`) | `absent` |

---

## 4. Provenance flow

### 4.1 Parsing

`normalize_provenance(block)` accepts three on-disk shapes and returns the aggregate
form:

```text
C0.4-A directory   {"modules": {<contract blocks>}, "field_provenance": {<field>: …}}
C0.2 directory     {"modules": {<contract blocks>}, "fields": {<module>: {<field>: …}}}
Aggregate          {<contract blocks>, "field_provenance": {"fields": …, "modules": …}}
```

It **moves and regroups what the artifact already says**. It never adds a value the
artifact did not carry.

Two traps in that normalisation are worth recording, because both were live bugs
during this phase:

1. The C0.4-A directory file has **both** `modules` and `field_provenance`, so a
   guard keyed on "`field_provenance` is absent" misread it as an aggregate. The
   discriminator has to be the *content* of `modules`.
2. Both a mapped availability record and a contract provenance block carry
   `asset_status`, so that key cannot tell them apart. What can is the pair only one
   of them has: `has_available_source` versus `projection_method`.

### 4.2 Tracing

`trace_instance(loaded, fields=None)` walks four steps:

```text
    request  →  skill bundle  →  asset  →  instance field
```

Each step is reported `recorded: true` or `false`. The **request step is always
`recorded: false`**, because the originating `CreatorRequest` lived in the composing
process and the instance artifact does not store it. The loader will not reconstruct
a plausible one: fabricating provenance is worse than admitting the gap.

A full chain, taken from the real finance artifact:

```json
{
  "field": "visual_rules.profile_id",
  "module": "visual_rules",
  "complete": true,
  "request":     {"recorded": false,
                  "detail": "the originating CreatorRequest is not stored in the
                             instance artifact; it belongs to the composing process"},
  "skill_bundle":{"recorded": true, "bundle_id": "bundle-18624330ee28c546"},
  "skill":       {"recorded": true, "skill_id": "visual-style-distillation",
                  "skill_type": "distillation", "version": "1.0.0"},
  "asset":       {"asset_id": "visual_profile_m5", "asset_type": "visual_rules",
                  "status": "available", "resolved": true, "recorded": true},
  "mapping":     {"rule_id": "RULE_VISUAL_001", "mode": "asset",
                  "mapping_version": "c0.4-a"},
  "instance_field": {"recorded": true, "field": "visual_rules.profile_id"}
}
```

---

## 5. Diff design

`compare_loaded_instances(a, b)` returns an `InstanceDiff` with four named axes,
because a caller usually cares about exactly one of them:

| Axis | Answers |
| --- | --- |
| `identity_changed` | did the creator's identity move? |
| `skills_changed` | did the skills, or the bundle, move? |
| `assets_changed` | did the assets move? |
| `capabilities_changed` | did a capability state move? |

plus three supporting axes: `fields_changed` (which field values differ, as
`module.field`), `modules_changed` (a module present in only one instance),
`kind_changed` (the provenance shape differs, reported as `mapped->projected`).

Four decisions worth stating:

- **A bundle change is a skill change.** There is no fifth axis for it; a caller
  reading `skills_changed` is already asking that question. It is reported as
  `bundle:<a>-><b>` inside the skills axis.
- **Identity prose is not an identity change.** A `reason` or `note` that reads
  differently without meaning differently is not reported.
- **Comparison reads only the loaded objects.** Nothing is re-read from disk, so a
  comparison cannot be affected by the artifact changing underneath it, and a test
  empties the artifact mid-comparison to prove it.
- **A diff is frozen**, and `as_dict()` returns mutable copies rather than the
  frozen internals.

`InstanceDiff` reads as a dataclass (`diff.skills_changed`), as a mapping
(`diff["skills_changed"]`), or as a document (`diff.as_dict()`), and an unknown key
raises `INSTANCE_DIFF_INVALID`. `summary()` gives a deterministic one-liner:
`"identical"`, or `"changed: identity, skills, capabilities, fields,
provenance_kind"`.

---

## 6. Test results

`tests/creator_loader_layer/` — 6 files, **598 tests, all passing**.

| File | Tests | Covers |
| --- | ---: | --- |
| `test_model_and_immutability.py` | 130 | enums, `freeze`/`thaw`, every model type, accessors, proxies at every depth, written immutability proofs, the public surface |
| `test_loader.py` | 109 | both layouts, both path forms, document reading, capability derivation, hand-edited artifacts, the 13 error codes, non-strict loads |
| `test_validation.py` | 88 | each of the seven layers in isolation, every field and module removal, the derivation table, and that no layer repairs anything |
| `test_provenance_and_trace.py` | 149 | shape classification, normalisation, availability recovery, parsing, resolution, asset collection, the four-step chain |
| `test_diff.py` | 70 | identical instances, each axis separately, prose insensitivity, access forms, argument rejection, mapped-vs-projected |
| `test_isolation.py` | 52 | AST import analysis, source-level read-only assertions, frozen-directory digests, artifact byte-identity, cross-layer compatibility |

```text
tests/creator_loader_layer ................ 598 tests  OK
full suite ................................ 5334 tests  OK (1 skipped)
```

The full-suite total is measured at commit `941cf9f`. It moves between runs because a
separate workstream is committing to this repository concurrently, so the stable
figure is the layer's own: **598**. Two consecutive full-suite runs at this commit
reported 5334 and 5362 total tests, both `OK`, the difference being tests another
workstream added mid-run.

Verification performed:

- **Import isolation.** Every `creator_loader` module is parsed with `ast`; no
  forbidden import (runtime, production, workflows, risk_evaluation,
  multimodal_creator, distillation_core, plugins, lobster, subprocess, socket,
  urllib, http, requests, and every model client) appears. Only the standard library
  and the three upstream creator layers are imported.
- **Read-only, mechanically.** No write call, no `del`, no `.pop`, no
  `"enabled": True` assignment exists in the package.
- **Frozen directories.** SHA256 tree digests of `runtime`, `production`,
  `workflows`, `risk_evaluation`, `multimodal_creator`, `distillation_core` and
  `plugins` are identical before and after loading, reading, validating and tracing.
- **Artifact byte-identity.** The instance directory's digests are unchanged after
  a successful load, a failed load, a `modules`-layout load and a non-strict load.
- **Secret scan.** `python -m security.secret_scan` over the new files: PASS.

Regression baselines were re-measured on the committed state of the previous phase
and remain unchanged: `creator_contract_layer` 205 OK · `creator_projection_layer`
340 OK (1 skipped) · `creator_skill_layer` 308 OK · `creator_mapping_layer` 256 OK.

---

## 7. Remaining blockers

| Id | Blocker | Impact |
| --- | --- | --- |
| **L1** | **`creator_projection.write_instance` writes a contract-invalid aggregate.** It emits a top-level `field_provenance` key, which `schemas/creator_instance.schema.json` forbids (`additionalProperties: false`). Every projected instance directory written by the current code therefore fails the C0.1 schema. | A projected artifact cannot be loaded through its aggregate. The loader reports `INSTANCE_SCHEMA_INVALID` rather than repairing it, and a test pins that. The projection's own in-memory instance *is* contract-valid, and the loader reads it correctly when written in the C0.1 layout — so the defect is in the writer, not in the loader. |
| **L2** | **The directory `provenance.json` is not self-sufficient.** It has no `generated_by`, so the bundle id, factory version and rule count cannot be recovered from it. | The `modules` layout reports `bundle_id: "(not recorded)"`. Availability is recovered and marked as derived; the bundle identity is not recoverable at all and is reported as unrecorded. |
| **L3** | **`source` reports `has_available_source: false` while two of its fields cite an available asset** (`source.data_sources` and `source.keywords`, both from `text_distillation_rules`). | A module-level availability claim that disagrees with its own field-level traces. The loader reports both faithfully — module state `absent`, field traces intact — and does not resolve the disagreement. It is a C0.4-A mapping question. |
| **L4** | **`visual_rules` cites `text_structure_templates`, a `text_rules` asset, as its module asset.** | Recorded, not repaired. Also a C0.4-A mapping question. |
| **L5** | The stale `creator_instance/template_creator/` directory in the workspace is a C0.2 artifact predating the current contract shape. | Loaded through `layout="modules"`, rejected through the aggregate. Left as it is: rewriting a committed artifact is not this layer's business. |
| **B7** | *(from C0.4-A, now closed)* instance-to-instance diff | Closed by `compare_loaded_instances`. |
| **B1–B6** | *(from C0.4-A)* missing sports and tech skills; generation and publishing unimplemented | Unchanged by this phase. Both capabilities remain correctly reported `declared`, never enabled. |

None of L1–L5 is a defect in the loader. Each is a disagreement between the artifact
and its contract, and the loader's job is to report such disagreements, not to
smooth them over.

---

## 8. Recommended next phase (C0.5)

### C0.5 — Instance-driven runtime selection *(recommended)*

The reasoning that produced C0.4-B still applies one level up. There are now **six
passing layers** — C0.1 contract, C0.2 projection, C0.3 skill factory, C0.4-A
mapping, C0.4-B loading — and the loader, which is the consumer that C0.4-A's report
called for, is itself consumed by nothing. A loader with no caller is an artifact
format with an extra step.

C0.5 should teach the runtime to select its plugin, skills and workflow **from a
loaded Creator Instance** instead of reading `config/runtime/default.json`
directly. That is the first point at which the whole ladder has a real consumer, and
it is the change that makes "an instance is configuration, never runtime" a
testable claim rather than an architectural intention.

It is also the phase that would close L1: a consumer that actually loads projected
instances will force `write_instance` to emit a contract-valid aggregate, and the
fix will be driven by a real need rather than by a report note.

### Alternatives, and why they are second

| Candidate | Assessment |
| --- | --- |
| **C0.5-A fix the projection writer (L1)** | Small, real, and it unblocks projected artifacts. Worth doing, but on its own it adds a fix with no new consumer. Best folded into C0.5, where a consumer forces it. |
| **C0.5-B author the missing skills** | Content work, not architecture. Would let sports and tech map completely. Unchanged reasoning from C0.4-A. |
| **C0.5-C instance CLI / inspection tool** | Genuinely useful and cheap — the loader's `as_dict()` and `trace_instance()` are already the right shape for it. But it is a convenience over C0.4-B, not a new capability, and it still leaves the ladder unconsumed. |
| **C0.5-D skill bundle packaging / upload** | Cannot happen without Lobster. Premature. |
| **C0.5-E multi-version instance registry** | Needs a shared library that does not exist. |

**Recommended scope: C0.5, with L1 folded in.** The programme's own pattern is the
argument: C0.4-A's report recommended building the first consumer rather than a
sixth producer, and that recommendation was right. Having built it, the next step is
the same recommendation one level up — make the consumer consumed.

---

## 9. Deliverables

### 9.1 `creator_loader/` package

```text
creator_loader/
    __init__.py      the public surface
    errors.py        LoaderError + 12 subtypes, 13 stable codes
    model.py         CapabilityState, ProvenanceKind, freeze/thaw,
                     AssetReference, LoadedCapability, FieldTrace,
                     InstanceProvenance, LoadedCreatorInstance, assert_immutable
    resolver.py      AssetReferenceResolver, collect_asset_ids
    provenance.py    classify_provenance, normalize_provenance,
                     availability_from_field_records, parse_provenance,
                     trace_instance, untraced_fields
    validation.py    seven pre-load layers, capability_state, validate_loaded
    loader.py        read_artifact, load_creator_instance,
                     compare_loaded_instances, InstanceDiff
```

### 9.2 Tests

`tests/creator_loader_layer/` — 6 files, 598 tests.

---

## 10. Compliance statement

| Constraint | Status |
| --- | --- |
| Do not modify `runtime/` | **No changes** — digest-verified |
| Do not modify `production/` | **No changes** — digest-verified |
| Do not modify `workflows/` | **No changes** — digest-verified |
| Do not modify `risk_evaluation/` | **No changes** — digest-verified |
| Do not modify `multimodal_creator/` | **No changes** — digest-verified |
| Do not modify `distillation_core/` | **No changes** — digest-verified |
| Do not modify `plugins/` | **No changes** — digest-verified |
| Do not integrate the Lobster interface | **Not integrated** |
| Do not upload to the Shared Skill Library | **Nothing uploaded** |
| Do not create a real Agent | **No agent created** |
| Do not call a model | **No model client imported or reachable** |
| Do not generate content | **Nothing generated; no asset content is even read** |
| Only add `creator_instance` reading capability | `creator_loader/` + tests + this report |

`creator_contract`, `creator_projection`, `creator_skill` and `creator_mapping` were
**read** and not modified. The one attributable defect found in them (L1, in
`creator_projection.write_instance`) is reported in §7 and pinned by a test; it was
not fixed, because fixing a frozen layer is outside this phase's mandate.

---

## 11. Commit

```
feat: add creator instance loader layer
```

Not pushed.
