# Creator Skill Library — thirteen skill archives

Thirteen archives, one skill each, for uploading to a Shared Skill Library that
ingests skills individually — it matches a skill by the description in SKILL.md's
front matter and then loads that file.

## The one thing that matters about these archives

**They are flat.** SKILL.md, manifest.json and skill.json sit at the **root** of each
archive:

```text
creator-text-distillation.zip
├── SKILL.md          <- at the root, where the library looks
├── manifest.json
└── skill.json
```

Nothing is wrapped in a directory. This is not a stylistic preference — zipping a
skill *folder* the obvious way produces text-distillation/SKILL.md, one level deeper
than the library looks. The archive lists correctly in any file browser and still
fails to load, because there is no entrypoint at the root.

So these were **not** built by zipping a directory. The three files are written
straight into the archive, and the validator refuses any archive containing a
directory component at all — the failure is silent otherwise, so it gets a check of
its own.

## What is here

| Archive | Skill | Layer |
| --- | --- | --- |
| creator-identity-rules.zip | identity-rules | universal |
| creator-source-discovery.zip | source-discovery | universal |
| creator-source-normalization.zip | source-normalization | universal |
| creator-text-distillation.zip | text-distillation | universal |
| creator-visual-distillation.zip | visual-distillation | universal |
| creator-template-extraction.zip | template-extraction | universal |
| creator-quality-review.zip | quality-review | universal |
| creator-risk-review.zip | risk-review | universal |
| creator-publishing-interface.zip | publishing-interface | universal |
| creator-generation-interface.zip | generation-interface | universal |
| creator-domain-plugin-builder.zip | domain-plugin-builder | meta |
| creator-domain-plugin-validator.zip | domain-plugin-validator | meta |
| creator-skill-composer.zip | skill-composer | meta |

Plus two index files:

- **INDEX.json** — every archive, its digest, its entrypoint and its members.
- **CHECKSUMS.json** — the same digests, for verifying a download.

## The three files

| File | What it is | Who reads it |
| --- | --- | --- |
| SKILL.md | front matter + what the skill does | the library — it matches on description and loads this |
| manifest.json | name, version, layer, entrypoint, capabilities | a consumer that needs the capability list machine-readably |
| skill.json | the declaration, structured | a consumer that wants more than capabilities |

The front matter is the convention this repository's skills already use:

```yaml
---
name: text-distillation
version: 1.0.0
library_layer: universal
description: Distill normalized material into the text rules an instance carries.
---
```

library_layer is an addition; name, version and description are what every existing
skill carries, and description is the field the library matches on.

## Two halves, one library

**Universal Creator Skills** (10) are the same skills for every domain. They carry
**no domain knowledge** — enforced at build time, not merely intended. If a domain
fact were needed in one, it would belong in a domain plugin instead.

**Meta Skills** (3) build and check the plugins. domain-plugin-builder turns a domain
request into a domain plugin; domain-plugin-validator checks one before anything uses
it; skill-composer assembles a skill set.

A domain plugin is **not** in these archives. It is generated at run time by
domain-plugin-builder and lives with the creator it configures. Shipping one would
make it stale the moment a domain is added — the failure mode this architecture
exists to prevent.

## What these skills are not

They are **declarations**, not implementations. Each says what is possible and what it
consumes. None contains a prompt, an executable body, a credential, or an execution
entry point.

That is deliberate, and it means the meta skills describe their capability rather than
running it. Binding them to an execution environment is a separate question.

## Verifying

Every archive is byte-for-byte reproducible. To check a download against
CHECKSUMS.json:

```python
import hashlib, json, sys, zipfile

ledger = json.load(open("CHECKSUMS.json"))["packages"]
bad = []
for name, entry in ledger.items():
    payload = open(name, "rb").read()
    if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
        bad.append(f"{name}: digest")
        continue
    with zipfile.ZipFile(name) as archive:
        names = archive.namelist()
    if "SKILL.md" not in names or any("/" in n for n in names):
        bad.append(f"{name}: not flat")
print("problems:", bad or "none")
sys.exit(1 if bad else 0)
```

## How these were produced

```python
from creator_library import build_skill_packages, write_skill_packages

write_skill_packages(build_skill_packages(), "skills/")
```

Each archive is validated on its own, from its own bytes, against five checks:
structure (including flatness), manifest, isolation (no runtime, credential or
prompt), layer (a universal skill carries no domain knowledge), and agreement with
creator_skill_library.zip.