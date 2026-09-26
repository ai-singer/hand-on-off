# Creator Agent Runtime Architecture

## Purpose

This layer maps the existing Creator Agent Framework into an OpenClaw workspace
and Lobster workflow without changing the common distillation protocol or the
Creator plugin interface.

## Runtime composition

~~~text
OpenClaw workspace
  |
  +-- RuntimeConfig
  |     selects workflow, plugin, Skills, and profile version
  |
  +-- OpenClaw Skill adapters
  |     translate native Skill discovery into stable Python commands
  |
  +-- Lobster workflow
        source input
          -> one unified distillation invocation
          -> plugin enhancement checkpoint
          -> QualityGateController
               | PASS -> GenerationRequest handoff
               | FAIL -> STOP / review_required
~~~

## Runtime configuration

`config.runtime.load_runtime_config()` loads a dependency-free JSON profile.
The default profile is `config/runtime/default.json`. A deployment can select
another profile with `CREATOR_RUNTIME_CONFIG` or Lobster's
`runtime_config` argument.

Plugin module paths are data. Adding a technology or education plugin requires
installing that plugin and changing the profile; it does not require a common
core change.

Invalid profiles fail explicitly when required sections are missing, the
default plugin is not enabled, names are duplicated, versions are invalid, or
OpenClaw Skill names violate the hyphenated slug contract.

## Quality Gate Controller

`evaluation.QualityGateController` receives the existing quality report and
returns PASS or FAIL. It owns the only method that may call
`GenerationAdapter.generate()`.

- PASS with an injected adapter: invoke once and record the invocation.
- PASS without an adapter: return a valid no-generation result.
- FAIL: return without invoking the adapter.

The controller changes execution control only; it does not change the quality
rubric, unified artifact, distillation engine, or plugin protocol.

## Lobster mapping

`workflows/lobster/content_distillation.lobster` contains executable commands
and standard input links. `node_contracts.json` contains the full node contract
metadata requested for deployment review.

The Creator plugin enhancement node is intentionally a checkpoint. The
preceding DistillationEngine call already performs common extraction and plugin
enhancement in one run. The checkpoint verifies plugin identity and preserves
the one-pass invariant.

`workflows.lobster.runtime_adapter` is a small JSON command adapter. It
normalizes source input, loads runtime configuration, runs distillation,
verifies the configured plugin identity, evaluates the gate, and emits a
GenerationRequest handoff.

## Skill adapter layers

`skills/internal/catalog.json` points to the unchanged internal Skills.
`skills/openclaw/` contains deployable wrappers with OpenClaw-compatible names
and explicit metadata:

- metadata;
- version;
- description;
- entrypoint;
- dependencies;
- runtime_requirements;
- test.

The Python adapter registry supports deterministic discovery, loading, and
version inspection without executing Skill instructions.

## Deployment boundary

This template does not add model calls, publishing, credentials, or account
mutation. The final Lobster node produces a validated generation handoff.
Instance owners must inject the approved generation implementation and retain
the existing authorization requirements for external side effects.

## Failure behavior

- malformed input: stop at source_input;
- plugin/config mismatch: stop at the plugin checkpoint;
- invalid artifact or plugin failure: stop during unified distillation;
- failed quality/risk result: stop before generation;
- missing deployment generation adapter: retain the handoff without pretending
  content was generated;
- command failure: return non-zero with a JSON error on stderr.
