---
name: identity-rules
version: 1.0.0
library_layer: universal
description: Turn a declared domain identity into an instance identity block.
---

# identity-rules

Turn a declared domain identity into an instance identity block.

## Layer

**Universal Creator Skill.** This skill is the same for every domain, and it carries no domain knowledge. If a domain fact is needed here, it belongs in a domain plugin instead.

## Capability

- skill type: `identity`
- produces: identity

## Declaration

This skill is a **declaration**, not an implementation. It states what is possible and what it consumes. It carries no prompt to send to a model, no executable body and no credential of any kind; its machine-readable form is `skill.json` beside this file.

## Companions

The library's skills, as of this version. A skill is selected alongside these, never instead of them. The list is the whole library rather than whichever subset a given archive happens to carry, so one skill's document is the same document wherever it is packaged.

- `domain-plugin-builder`
- `domain-plugin-validator`
- `generation-interface`
- `publishing-interface`
- `quality-review`
- `risk-review`
- `skill-composer`
- `source-discovery`
- `source-normalization`
- `template-extraction`
- `text-distillation`
- `visual-distillation`

## Provenance

- library version: `1.0.0`
- layer: `universal`
- manifest: `manifest.json`
