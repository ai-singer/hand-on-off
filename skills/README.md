# Creator Skill Library — skills

Thirteen skills, one directory each, ready to be read by a Shared Skill Library that
matches a skill by its description and then **loads `SKILL.md`**.

There are no archives here. A library reads `SKILL.md` from a skill directory, so an
archive would have to be extracted before anything could see it — these directories
are the deliverable, and zipping them would package the same thing twice.

## What is here

| Directory | Skill | Layer |
| --- | --- | --- |
| `identity-rules/` | `identity-rules` | universal |
| `source-discovery/` | `source-discovery` | universal |
| `source-normalization/` | `source-normalization` | universal |
| `text-distillation/` | `text-distillation` | universal |
| `visual-distillation/` | `visual-distillation` | universal |
| `template-extraction/` | `template-extraction` | universal |
| `quality-review/` | `quality-review` | universal |
| `risk-review/` | `risk-review` | universal |
| `publishing-interface/` | `publishing-interface` | universal |
| `generation-interface/` | `generation-interface` | universal |
| `domain-plugin-builder/` | `domain-plugin-builder` | meta |
| `domain-plugin-validator/` | `domain-plugin-validator` | meta |
| `skill-composer/` | `skill-composer` | meta |

Plus two index files:

- **`INDEX.json`** — every skill, its directory, its files and its size.
- **`CHECKSUMS.json`** — a digest per file, for verifying a copy.

## Inside one skill

```text
text-distillation/
├── SKILL.md          front matter + what the skill does  ← what a library reads
├── manifest.json     name, version, layer, entrypoint, capabilities
├── skill.json        the declaration, machine-readable
└── library.json      which library version it came from, and its companions
```

`SKILL.md` is at the root of every skill directory, which is named for the skill — the
same shape as `blank/workspace/skills/<name>/` in this repository. Nothing is nested
twice.

The front matter is the convention this repository's skills already use:

```yaml
---
name: text-distillation
version: 1.0.0
library_layer: universal
description: Distill normalized material into the text rules an instance carries.
---
```

`library_layer` is an addition; `name`, `version` and `description` are what every
existing skill carries.

## Two halves, one library

**Universal Creator Skills** (10) are the same skills for every domain. They carry
**no domain knowledge** — that is enforced at build time, not merely intended. If a
domain fact were needed in one, it would belong in a domain plugin instead.

**Meta Skills** (3) build and check the plugins. `domain-plugin-builder` turns a
domain request into a domain plugin; `domain-plugin-validator` checks one before
anything uses it; `skill-composer` assembles a skill set.

A domain plugin is **not** here. It is generated at run time by
`domain-plugin-builder`, and lives with the creator it configures. Shipping one would
make it stale the moment a domain is added — which is the failure mode this
architecture exists to prevent.

## What these skills are not

They are **declarations**, not implementations. Each says what is possible and what it
consumes. None contains a prompt, an executable body, a credential, or an execution
entry point.

That is deliberate, and it means the meta skills describe their capability rather than
running it. Binding them to an execution environment is a separate question.

## Verifying

Every file is byte-for-byte reproducible. To check a copy against `CHECKSUMS.json`:

```python
import hashlib, json, sys

ledger = json.load(open("CHECKSUMS.json"))["files"]
bad = [
    path
    for path, entry in ledger.items()
    if hashlib.sha256(open(path, "rb").read()).hexdigest() != entry["sha256"]
]
print("mismatches:", bad or "none")
sys.exit(1 if bad else 0)
```

## How these were produced

```python
from creator_library import build_skill_packages, unpack_skill_packages

unpack_skill_packages(build_skill_packages(), "skills/")
```

Each skill is validated on its own, from its own bytes, against five checks:
structure, manifest, isolation (no runtime, credential or prompt), layer (a universal
skill carries no domain knowledge), and agreement with the library archive.
