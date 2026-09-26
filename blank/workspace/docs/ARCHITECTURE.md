# Creator Agent Framework Architecture

## Goal

This workspace is a reusable Creator Agent template, not a single-account
application. It turns normalized raw material into one versioned,
schema-validated artifact, then offers replaceable generation and evaluation
boundaries for an OpenClaw Farm deployment.

## System view

```text
video / document / data / image adapters
                    |
                    v
              RawSource[]
                    |
                    v
       +--------------------------------+
       | DistillationEngine (one run)   |
       |                                |
       | common classification/extract  |
       |              +                 |
       | selected Creator plugin rules  |
       +--------------------------------+
                    |
                    v
       UnifiedDistillationArtifact
                    |
                    v
       shared + domain quality checks
                    |
                    v
          QualityGateController
             | PASS    | FAIL
             v         v
     generation adapter STOP/review
     (optional/injected)
```

There is no persisted “generic distillation result” followed by a second
specialized distillation. Common extraction and plugin enhancement participate
in the same engine invocation and produce a single artifact.

## Module boundaries

| Module | Responsibility | Must not contain |
| --- | --- | --- |
| `core/` | Raw input contract, plugin loader, schema validation, skill discovery | Creator/domain rules |
| `distillation_core/` | Source role classification, domain-neutral extraction, one-run merge | Finance keywords, generation, publication |
| `plugin_interface/` | Versioned plugin identity and contribution protocol | Concrete Creator behavior |
| `plugins/` | Domain value, filtering, structure, and evaluation policy | Changes to common engine behavior |
| `schemas/` | Public artifact contract | Plugin-private assumptions |
| `skills/` | Independently versioned operating capabilities | Hidden account state or secrets |
| `workflows/` | Composition of distillation, generation interface, and quality gate | Hard-coded model providers |
| `evaluation/` | Domain-neutral quality checks | Creator-specific scoring meaning |
| `tests/` | Contract, plugin, replacement, and skill tests | Production credentials or network calls |

## Contracts

### RawSource

`RawSource` supports `video`, `document`, `data`, and `image`. Binary extraction
is outside the core; adapters provide normalized text/structured content plus
provenance metadata. An explicit `distillation_role` can route material to one
of the four common signal families:

- `topic_candidate`
- `content_template`
- `knowledge_unit`
- `style_pattern`

Without a hint, the reference classifier uses conservative deterministic
signals and defaults to knowledge.

### UnifiedDistillationArtifact

`schemas/unified_distillation_artifact.json` requires all four common signal
families plus `domain_extension`, `risk_constraints`, and `evaluation_result`.
It also records artifact and plugin versions. The engine validates every result
before it can reach generation.

### Creator plugin

A configured module exports `create_plugin()`. The plugin sees original
sources and a read-only copy of common signals and returns a
`PluginContribution`. It may add candidates but cannot replace common values.
Unknown enhancement fields fail explicitly.

### Generation adapter

`GenerationAdapter` receives a validated artifact through `GenerationRequest`.
The reference project deliberately supplies no model or publishing adapter, so
deployments must document credentials, network behavior, timeouts, and side
effects when they add one. The adapter is invoked only through
`QualityGateController` after a PASS decision.

## Extension model

- Add domains by creating another plugin package and changing the selected
  module in runtime configuration; common code stays unchanged.
- Add reusable operator capabilities as skill directories with a `SKILL.md`
  and `manifest.json`.
- Add media/model integrations as adapters at input or generation boundaries.
- Version shared artifact changes independently from plugin-private schemas.

## Failure behavior

Invalid sources, duplicate source IDs, plugin load/contract failures, unknown
enhancement fields, and schema-invalid artifacts fail visibly. The framework
does not silently fall back to a generic result because doing so could hide
lost domain policy.

## Security and operations

The repository contains no credentials and its tests are offline. Publication,
real account mutation, and paid model calls are outside the reference runtime.
Deployments must use the farm secret store and retain source provenance needed
for later review.
