---
name: template-extraction
version: 1.0.0
library_layer: universal
description: Extract reusable structure from finished material.
---

# template-extraction

Extract reusable structure from finished material.

## Layer

**Universal Creator Skill.** This skill is the same for every domain, and it carries no domain knowledge. If a domain fact is needed here, it belongs in a domain plugin instead.

## Capability

- skill type: `distillation`
- produces: structure templates

## Declaration

This skill is a **declaration**, not an implementation. It states what is possible and what it consumes. It carries no prompt to send to a model, no executable body and no credential of any kind; its machine-readable form is `skill.json` beside this file.

## Companions

The library's skills, as of this version. A skill is selected alongside these, never instead of them. The list is the whole library rather than whichever subset a given archive happens to carry, so one skill's document is the same document wherever it is packaged.

- `domain-plugin-builder`
- `domain-plugin-validator`
- `generation-interface`
- `identity-rules`
- `publishing-interface`
- `quality-review`
- `risk-review`
- `skill-composer`
- `source-discovery`
- `source-normalization`
- `text-distillation`
- `visual-distillation`

## Provenance

- library version: `1.0.0`
- layer: `universal`
- manifest: `manifest.json`
