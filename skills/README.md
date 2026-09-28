# Creator Skill Library — upload packages

Thirteen skill packages, one per skill, for uploading to a Shared Skill Library that
ingests skills **individually** rather than as a collection.

Upload them one at a time. Each is self-contained.

## What is here

| File | Skill | Layer |
| --- | --- | --- |
| `creator-identity-rules.zip` | `identity-rules` | universal |
| `creator-source-discovery.zip` | `source-discovery` | universal |
| `creator-source-normalization.zip` | `source-normalization` | universal |
| `creator-text-distillation.zip` | `text-distillation` | universal |
| `creator-visual-distillation.zip` | `visual-distillation` | universal |
| `creator-template-extraction.zip` | `template-extraction` | universal |
| `creator-quality-review.zip` | `quality-review` | universal |
| `creator-risk-review.zip` | `risk-review` | universal |
| `creator-publishing-interface.zip` | `publishing-interface` | universal |
| `creator-generation-interface.zip` | `generation-interface` | universal |
| `creator-domain-plugin-builder.zip` | `domain-plugin-builder` | meta |
| `creator-domain-plugin-validator.zip` | `domain-plugin-validator` | meta |
| `creator-skill-composer.zip` | `skill-composer` | meta |

Plus two index files:

- **`INDEX.json`** — every package with its size, digest and entrypoint.
- **`CHECKSUMS.json`** — the same digests, for verifying a download.

The whole library also ships as a single archive at
`blank/workspace/creator_skill_library.zip`, which is the same thirteen skills with a
release manifest, a domain registry and the domain plugin schema.

## Inside one package

```text
<skill-name>/
├── SKILL.md          front matter + what the skill does
├── manifest.json     name, version, layer, entrypoint, capabilities
├── skill.json        the declaration, machine-readable
└── library.json      which library version it came from, and its companions
```

The single top-level directory is the skill's own name — the same shape as
`blank/workspace/skills/<name>/` in this repository.

## Two halves, one library

**Universal Creator Skills** (10) are the same skills for every domain. They carry
**no domain knowledge** — that is enforced at build time, not merely intended. If a
domain fact were needed in one, it would belong in a domain plugin instead.

**Meta Skills** (3) build and check the plugins. `domain-plugin-builder` turns a
domain request into a domain plugin; `domain-plugin-validator` checks one before
anything uses it; `skill-composer` assembles a skill set.

A domain plugin is **not** in these packages. It is generated at run time by
`domain-plugin-builder`, and lives with the creator it configures. Shipping one would
make it stale the moment a domain is added — which is the failure mode this
architecture exists to prevent.

## What these packages are not

They are **declarations**, not implementations. Each says what is possible and what it
consumes. None contains a prompt, an executable body, a credential, or an execution
entry point.

That is deliberate, and it means the meta skills describe their capability rather than
running it. Binding them to an execution environment is a separate question.

## Verifying

Every package is byte-for-byte reproducible. To check a download against
`CHECKSUMS.json`:

```python
import hashlib, json, sys

ledger = json.load(open("CHECKSUMS.json"))["packages"]
bad = [
    name
    for name, entry in ledger.items()
    if hashlib.sha256(open(name, "rb").read()).hexdigest() != entry["sha256"]
]
print("mismatches:", bad or "none")
sys.exit(1 if bad else 0)
```

## How these were produced

```python
from creator_library import build_library, build_skill_packages, write_skill_packages

library = build_library()                                   # the whole library
write_skill_packages(build_skill_packages(), "skills/")     # the thirteen packages
```

Each package is validated on its own, from its own bytes, against five checks:
structure, manifest, isolation (no runtime, credential or prompt), layer (a universal
skill carries no domain knowledge), and agreement with the library archive.