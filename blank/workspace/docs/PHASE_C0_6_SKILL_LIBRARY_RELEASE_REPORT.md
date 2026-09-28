# PHASE_C0_6_SKILL_LIBRARY_RELEASE_REPORT.md

**Phase C0.6 — Skill Library Release Layer**

The production chain now ends where distribution begins:

```text
    Universal Skills + Meta Skills + domain-plugin-builder
          + domain-plugin-validator + Registry + Release Manifest
                                |
                                v
                    creator_skill_library.zip
                                |
                                v
                   Lobster Shared Skill Library
```

Upload the archive once. A user asks for a finance creator; the library's own
`domain-plugin-builder` turns that request into `domain_finance_plugin`;
`domain-plugin-validator` checks it; the agent is configured from the plugin plus the
universal skills. Three domains today, three hundred later, one library.

---

## 1. Implementation

`creator_library/` — 8 modules.

| Module | Responsibility |
| --- | --- |
| `paths.py` | Every archive path, declared once, plus the safe-name guard |
| `errors.py` | 16 stable codes, all extending the contract error |
| `emitter.py` | One library declaration in, one real skill directory out |
| `manifest.py` | The release manifest, `version.json`, `LIBRARY.md`, the published registry |
| `archive.py` | The deterministic zip: fixed clock, fixed order, fixed compression |
| `validation.py` | Eight checks |
| `builder.py` | `build_library`, `verify_artifact`, `write_library` |
| `__init__.py` | The public surface |

### 1.1 The build order, and why it is forced

Two digests are recorded and each depends on something the other cannot know:

```text
    1. emit members          45 files: 13 skills × 3, 4 root, registry, schema
    2. content_hash          over the members, excluding the two self-referential files
    3. manifest              records content_hash; carries a placeholder artifact_hash
    4. write the zip         ← artifact_hash becomes knowable here
    5. manifest again        with the real artifact_hash
    6. checksums.json        LAST — it must describe the finished archive
    7. write the zip again   the released bytes
```

Step 6 is why the ledger comes last. Writing it earlier produced a ledger that
described a state the archive never had — the first working build failed its own
checksum check, which is exactly the bug this ordering prevents.

**`content_hash` is load-bearing; `artifact_hash` is advisory.** The content hash is
computed before the manifest exists and never changes afterwards, so it is fully
re-derivable — and `verify_artifact` re-derives it from the archive's own bytes.
The artifact hash cannot be: writing a manifest that records a file's digest changes
that file. So the released archive's real digest differs from the one recorded inside
it, and the verification report says `ADVISORY` rather than pretending otherwise.

### 1.2 The emitted skill

Each declaration in `creator_plugin_builder.library` becomes a real directory:

```text
universal_skills/text-distillation/
├── SKILL.md          front matter + prose
├── manifest.json     name, version, library_layer, entrypoint, capabilities
└── skill.json        the declaration, machine-readable
```

The conventions are this repository's own. `skills/quality_review/` already ships a
`SKILL.md` with `name`/`version`/`description` front matter and a `manifest.json` with
`name`, `version`, `entrypoint`, `capabilities` — verified against every existing
manifest. A library using a different shape would be a second, incompatible convention.

Two deliberate divergences, both recorded in the manifest itself:

- **No `test_command`.** Every existing manifest carries one. A released skill is a
  pure declaration with nothing to run, and naming a Python test that does not exist
  inside the archive would be a broken instruction. `note` states the reason, and
  `exclusions` records it.
- **`library_layer` and `library_version` are added.** Which half of the library a
  skill belongs to is the single most important fact about it — a universal skill
  must be domain-free — so it travels with the skill instead of being inferred from
  the directory it sits in.

### 1.3 Input and output

```python
build_library(library_version="1.0.0") -> LibraryBuild
build.manifest          the release manifest
build.members           45 members, keyed by archive path
build.payload           the zip bytes
build.content_hash      the load-bearing digest
build.actual_artifact_hash  the digest of the released file
write_library(build, out_root) -> Path
verify_artifact(build)  re-derives every claim from the archive's own bytes
```

---

## 2. Package structure

```text
creator_skill_library/
├── LIBRARY.md                      what it is, how it is used, what it excludes
├── manifest.json                   the release manifest
├── checksums.json                  every member's digest
├── version.json                    format, library, builder versions; the archive clock
├── universal_skills/<skill>/       10 skills, domain-free
│   ├── SKILL.md
│   ├── manifest.json
│   └── skill.json
├── meta_skills/<skill>/            3 skills that build and check plugins
│   ├── SKILL.md
│   ├── manifest.json
│   └── skill.json
├── domain_plugins/
│   └── registry.json               which domains this library can build
└── schemas/
    └── domain_plugin.schema.json   the plugin contract a consumer validates against
```

45 members: 4 root, 39 skill files, 1 registry, 1 schema. 29,668 bytes.

**Generated domain plugins are not in the archive.** They are produced at run time by
`meta_skills/domain-plugin-builder` and live with the creator they configure. Shipping
them would make the library stale the moment a domain is added — the failure mode the
whole architecture exists to prevent. What the archive carries is the builder, the
schema, and the **registry** saying what it can build.

### 2.1 The release manifest

| Field | Holds |
| --- | --- |
| `library_id` | `creator_skill_library` |
| `library_version` | the released version |
| `format_version` / `manifest_schema_version` | the format and schema versions |
| `generated_by` / `created_at` | the builder, and a deterministic timestamp |
| `layers` | `universal` (10) and `meta` (3), each with its skill names |
| `skills[]` | every skill: layer, version, type, purpose, produces, entrypoint, directory |
| `domain_plugins` | the catalog version, the three buildable domains, `generated_at_runtime: true` |
| `schemas[]` | the domain plugin contract |
| `hashes` | `content_hash` and `artifact_hash` |
| `integrity` | the digest rule, the self-referential members, the member summary |
| `exclusions` | four entries: what is absent, and why |

**Forbidden keys**, checked at every depth: prompts, models, providers, credentials,
tokens, passwords, private keys, runtime, executors, handlers, callbacks, code,
scripts, deployment, endpoints, webhooks and `test_command`.

`entrypoint` is deliberately **not** forbidden. Every skill manifest in this repository
carries `"entrypoint": "SKILL.md"`, and forbidding the key would forbid the
repository's own convention. The isolation check distinguishes them by *value* — an
entrypoint to a markdown document is documentation; an entrypoint to anything else is
an executable.

### 2.2 The domain registry

```json
{
  "library_id": "creator_skill_library",
  "catalog_version": "1.0.0",
  "domain_count": 3,
  "generated_at_runtime": true,
  "domains": [
    {"domain": "finance",    "plugin_name": "domain_finance_plugin",    "buildable": true},
    {"domain": "sports",     "plugin_name": "domain_sports_plugin",     "buildable": true},
    {"domain": "technology", "plugin_name": "domain_technology_plugin", "buildable": true}
  ]
}
```

---

## 3. Validation

Eight checks, each raising a typed error with a stable code while
`validate_archive` reports all of them.

| # | Check | Refuses | Code |
| --- | --- | --- | --- |
| 1 | `validate_structure` | a member layout that is not the library layout | `LIBRARY_STRUCTURE_INVALID` |
| 2 | `validate_manifest_member` | an incomplete manifest, or a forbidden key at any depth | `LIBRARY_MANIFEST_INVALID` |
| 3 | `validate_skills` | a declared skill with no directory, or files that disagree | `LIBRARY_SKILL_MISSING` |
| 4 | `validate_layers` | a universal skill carrying domain knowledge | `LIBRARY_LAYER_VIOLATION` |
| 5 | `validate_isolation` | runtime, credentials, prompts, forbidden references | `LIBRARY_RUNTIME_DETECTED` / `LIBRARY_CREDENTIAL_DETECTED` / `LIBRARY_PROMPT_DETECTED` |
| 6 | `validate_checksums` | a recorded digest that does not match its member | `LIBRARY_CHECKSUM_MISMATCH` |
| 7 | `validate_reproducibility` | two builds of one input differing | `LIBRARY_NOT_REPRODUCIBLE` |
| 8 | `validate_registry` | a published registry disagreeing with the builder's catalog | `LIBRARY_REGISTRY_INVALID` |

### 3.1 Check 5: the hard one, and the false positives it had to stop producing

This is the check that decides whether the artefact is safe to upload. Getting it
right meant solving a genuine tension: **a library has to be able to say that it
carries no runtime and no credential**, and a naive scanner flags exactly those
sentences. Three corrections, each of which was a real bug:

1. **Module names.** `LIBRARY.md` explains that the library carries no `runtime/`,
   `workflows/` or `plugins/`. Flagging that makes the honest statement impossible to
   write. The check is now structural about *where* a match is: a **skill** is
   declarative, so a forbidden module name inside one is always a violation; the
   **root documents** may name what they exclude.
2. **A PEM header was excused as prose.** The string `-----BEGIN RSA ` followed by
   `PRIVATE KEY-----` contains spaces, and the space heuristic waved it through. It is
   the most unambiguous secret shape there is. Unambiguous token shapes are now
   checked *before* any heuristic.
3. **An assignment to prose was reported.** `api_key = set from the environment`
   matched a key name followed by text. The check now judges the *value* of an
   assignment: a placeholder, an allowlisted concept word, or a value containing a
   space is documentation; a single unbroken alphanumeric value carrying a digit is a
   secret.

**Prompts are forbidden everywhere, with no exception.** There is no honest reason for
prompt text to appear in a skill library.

### 3.2 Check 4 and the two meanings of a release

`validate_layers` distinguishes two legitimate uses:

- The **released** library must carry every skill the library declares — a partial
  release is not the library. `verify_artifact` requires this.
- A **deliberate subset** (for a test, or a slimmed deployment) must be *drawn from*
  the library: every released name is declared, and on the right layer. This is the
  weaker condition, and `require_complete=False` is its default.

---

## 4. Test results

`tests/creator_library_layer/` — 4 files, **396 tests, all passing**.

| File | Tests | Covers |
| --- | ---: | --- |
| `test_emitter.py` | 79 | paths and their safety guards, emitted files, the manifest convention, capabilities, front matter parsed by the project's own parser, domain-freedom of every emitted skill |
| `test_manifest.py` | 99 | the manifest, every required and forbidden key, the version document, the README, the domain registry, the schema entries, the exclusions |
| `test_archive_and_validation.py` | 130 | the zip's determinism and clock, the checksum ledger, all eight checks in isolation, every corruption they refuse |
| `test_builder_and_isolation.py` | 88 | the whole chain, writing, reproducibility, the release layer's own import isolation, frozen-directory digests, no-capability-invention |

```text
tests/creator_library_layer ............... 396 tests  OK
full suite ................................ 6166 tests  OK (1 skipped)
```

Verification performed:

- **The archive re-validates from its own bytes.** `verify_artifact` re-reads the zip
  rather than trusting the in-memory build, compares every member, re-derives the
  content hash, and marks the artifact hash `ADVISORY` with the reason.
- **Byte-for-byte reproducibility.** Two builds produce identical `payload`,
  `content_hash` and `artifact_hash`; member order is proven not to affect the bytes.
- **The zip clock is the ZIP epoch.** Every entry is stamped `(1980, 1, 1, 0, 0, 0)`
  and every entry is deflated at a fixed level.
- **Import isolation.** Every module parsed with `ast`; no forbidden import (runtime,
  production, workflows, risk_evaluation, multimodal_creator, distillation_core,
  plugins, lobster, subprocess, socket, urllib, http, requests, openai, anthropic,
  yaml).
- **The released schema validates the live plugins.** The archive's copy of
  `domain_plugin.schema.json` is used to validate plugins built by the live builder —
  so the schema a consumer gets is the schema the factory enforces.
- **Frozen directories.** SHA256 tree digests of all seven protected directories are
  identical before and after building.
- **Secret scan.** `python -m security.secret_scan .` → PASS.
- **The emitted skills parse with the project's own front-matter parser.**

Regression baselines from earlier phases are unchanged.

---

## 5. Bugs found and fixed

Six real defects, each caught by a test rather than by inspection.

| # | Bug | Where | Fix |
| --- | --- | --- | --- |
| 1 | **`package_hash` excluded self-referential members by bare name**, so a library's own `manifest.json` was silently included in its content hash — the two only matched because the divergence was masked. | `creator_package/hashing.py` | Match by `PurePosixPath(path).name`. |
| 2 | **The README quoted the content hash**, so writing the README changed the hash it quoted, and the released library disagreed with its own manifest. | `creator_library/manifest.py` | The README points at `manifest.json` and `checksums.json` instead of quoting a digest. A document cannot contain the hash of the archive containing it. |
| 3 | **The checksum ledger was written before the manifest**, so it described a state the archive never had and failed its own check. | `creator_library/archive.py`, `builder.py` | The ledger is written last, and is *returned* by `finalise` rather than added. |
| 4 | **The ledger's own row held the digest of a placeholder.** | `creator_package/hashing.py` | `checksum_ledger` takes `null_digest_for`; the ledger's own row is `null`, and `verify_ledger` skips exactly that row. |
| 5 | **Two modules exported `FORBIDDEN_MANIFEST_KEYS`**, and the emitter's list shadowed the manifest's in the package namespace — so `'password' in FORBIDDEN_MANIFEST_KEYS` was silently `False`. | `creator_library/emitter.py` | Renamed to `FORBIDDEN_SKILL_MANIFEST_KEYS`. Two different documents with different rules must not share a name. |
| 6 | **Three isolation false positives**: a PEM header excused as prose, a prose assignment reported as a secret, and a deny-list mention treated as a key. | `creator_library/validation.py` | Unambiguous token shapes are checked before heuristics; assignments are judged by their value; module-name scanning is structural about location. |

Bugs 1–4 are in `creator_package` — the layer parked in C0.5 — which is now load-bearing
for the release layer and had never been run end to end. Bug 5 was a genuine latent
hazard: a name collision that made a security-relevant list silently wrong.

### 5.1 A finding in the frozen layers, not fixed

`creator_package/hashing.py` still lives in the layer C0.5 parked. It is **imported**
by `creator_library` for `canonical_json`, the digest helpers, `package_hash` and
`checksum_ledger`. That is a real dependency, recorded here rather than resolved: the
honest options are to promote `hashing.py` into its own layer or to fold it into
`creator_library`, and either is a change to a committed layer. It is the first item
for a phase allowed to make that change.

---

## 6. Unsolved issues

| Id | Issue | Impact |
| --- | --- | --- |
| **R1** | `creator_package/hashing.py` is imported across a layer boundary that C0.5 declared would not exist. | Works, and is tested, but the layering is a fiction. Promote or fold. |
| **R2** | **The emitted meta skills are declarations, not implementations.** `SKILL.md` says what `domain-plugin-builder` does; the Python that does it lives in `creator_plugin_builder/` and is not in the archive. | A consumer reading the library knows the capability exists and what it produces, but the archive does not carry a runnable builder — deliberately, since a skill library is a configuration asset. Closing this needs whichever execution binding Lobster expects. |
| **R3** | **The universal skills bind to no asset.** Each declares its purpose and what it produces; none names the asset it reads. | The domain plugins carry asset bindings (`text_distillation_rules`, `visual_profile_m5`, `risk_policy_reference`); the universal skills do not. Closing it is the same work as R4. |
| **R4** | No finance-, sports- or technology-specific rule asset exists, so all three domains bind the same general-purpose assets and differ only in what they declare. | Carried forward from C0.5, unchanged. The highest-value content work available. |
| **R5** | `creator_projection.write_instance` still emits a contract-invalid aggregate (top-level `field_provenance`). | Carried forward from C0.4-B, unchanged. Unrelated to this phase; still reported, still not fixed. |
| **L3/L4** | C0.4-A's `source` module records `has_available_source: false` while two of its fields cite an available asset; `visual_rules` cites a `text_rules` asset. | Carried forward. |
| **L1-audit** | Domain vocabulary remains inside `creator_skill.DEFAULT_SKILL_CATALOG` (`text-distillation` names finance). | Carried forward from C0.5. `audit_layers` detects it; the library's own declarations are clean. |

None of R1–R5 is a defect in this phase's code. Each is either a layering question or
a disagreement in a frozen layer, both of which are reported rather than smoothed over.

---

## 7. Recommended next phase

### C0.7 — Library distribution and execution binding *(recommended)*

The chain now reaches a file. What it does not yet reach is a *consumer*: nothing
reads `creator_skill_library.zip`, and the meta skills inside it are declarations
rather than implementations (R2).

C0.7 should close that. Two pieces, in order:

1. **A library reader** — unpack and verify an archive a user downloaded, re-deriving
   the content hash and the ledger rather than trusting them. `creator_library`
   already has every primitive: `read_archive`, `verify_ledger`, `verify_library_hash`,
   `validate_archive`. What is missing is the entry point a real consumer would call.
2. **The execution binding** — what Lobster actually expects a Shared Skill Library to
   contain, so the meta skills become runnable rather than declarative. That is
   necessarily an interface question, and answering it is the first thing this
   programme cannot decide alone.

Then R1 resolves naturally: a reader that lives beside `hashing.py` will make the right
home for it obvious.

### Alternatives, and why they are second

| Candidate | Assessment |
| --- | --- |
| **C0.7-A domain-specific rule assets (R4)** | The highest-value *content* work, and the thing that would make the three plugins genuinely differ. But it is content, not infrastructure, and the library can be uploaded without it. |
| **C0.7-B emit real implementations for the meta skills** | Depends entirely on what Lobster expects; doing it blind would produce a second thing to rewrite. |
| **C0.7-C a library diff** | Cheap, and useful once libraries are versioned in the wild. There is one version today. |
| **C0.7-D clean the universal skill catalogue of domain vocabulary (L1-audit)** | Real, and small — but it touches a frozen layer, and `audit_layers` already detects the problem on every build. |
| **C0.7-E the instance factory** | Still not the goal. |
| **C0.7-F runtime bootstrap / Lobster deployment** | Out of scope by instruction. |

**Recommended scope: C0.7 alone, starting with the reader.** It is the last step
between "we have a file" and "a user can use it", and it is testable offline against
the archive this phase produces.

---

## 8. Compliance statement

| Constraint | Status |
| --- | --- |
| Do not modify `runtime/` | **No changes** — digest-verified |
| Do not modify `production/` | **No changes** — digest-verified |
| Do not modify `workflows/` | **No changes** — digest-verified |
| Do not modify `risk_evaluation/` | **No changes** — digest-verified |
| Do not modify `multimodal_creator/` | **No changes** — digest-verified |
| Do not modify `distillation_core/` | **No changes** — digest-verified |
| Do not modify `plugins/` | **No changes** — digest-verified |
| Do not call the Lobster API | **No client, import, endpoint or URL in the package** |
| Do not upload a skill | **Nothing uploaded** |
| Do not create an Agent | **No agent created** |
| Do not generate content | **Nothing generated** |
| Universal Skills kept domain-free | **Enforced by check 4 on every build** |
| `creator_skill` / `creator_mapping` / `creator_loader` kept compatible | **Read only, unmodified** |
| `creator_instance/` kept | **Untouched** |

Two committed layers were modified, and both are recorded above: `creator_package`
(bugs 1 and 4, in `hashing.py` — a function `creator_library` depends on and which had
never been exercised) and nothing else. `creator_contract`, `creator_projection`,
`creator_skill`, `creator_mapping`, `creator_loader` and `creator_plugin_builder` were
**read** and not modified.

---

## 9. Commit

```
feat: add creator skill library release layer
```

Not pushed.
