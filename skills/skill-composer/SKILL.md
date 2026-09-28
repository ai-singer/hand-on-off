---
name: skill-composer
version: 1.0.0
library_layer: meta
description: Assemble the set of universal skills a composed creator needs.
---

# skill-composer

Assemble the set of universal skills a composed creator needs.

## Layer

**Meta Skill.** This skill operates on domain plugin documents and on the library itself. A generated plugin is built and checked *by* the meta skills; it never runs them.

## Capability

- skill type: `composer`
- produces: a skill selection
- accepts: `creator_request`

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
- `source-discovery`
- `source-normalization`
- `template-extraction`
- `text-distillation`
- `visual-distillation`

## Provenance

- library version: `1.0.0`
- layer: `meta`
- manifest: `manifest.json`
