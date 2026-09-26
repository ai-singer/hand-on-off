# OpenClaw Farm Deployment Guide

## Deployment unit

The deployable unit is the `workspace/` directory packaged as a `.tar.gz` with
`workspace/` at the archive root. This mirrors the layout observed in the
original blank-instance backup. The original backup remains untouched.

This guide prepares an artifact; it does not upload, activate, or mutate a
production instance. Use the farm's approved import mechanism for those
environment-specific steps.

## Prerequisites

- Python 3.11 or newer;
- `tar` available on the packaging host;
- a farm runtime able to expose the workspace Python modules;
- the official Lobster plugin installed and allowed for the target agent;
- production secrets stored outside this repository;
- a selected plugin module, for example `plugins.xiaolin_finance`.

No third-party Python dependency is required by the reference framework.

## Preflight

From `blank/workspace/`:

```powershell
python -m unittest discover -s tests -v
python -c "from core import load_plugin; print(load_plugin('plugins.xiaolin_finance').identity)"
python -c "from config.runtime import load_runtime_config; print(load_runtime_config())"
python -c "from skills.openclaw import discover_openclaw_skills; print(sorted(discover_openclaw_skills()))"
```

Verify that neither `.env` nor `.openclaw/openclaw.json` exists in the source
workspace. The packaging script rejects both paths.

## Runtime configuration

`config/runtime/default.json` is the template runtime profile. An instance may
select a different file with `CREATOR_RUNTIME_CONFIG` or the Lobster
`runtime_config` argument.

The profile owns:

- `instance.name`;
- `workflow.default`;
- `plugins.enabled` and `plugins.default`;
- `skills.enabled`;
- the runtime profile `version`.

To add a technology or education plugin later, add its module path to
`plugins.enabled` and select it as `plugins.default`. No common-core edit is
required.

Model, search, OCR, transcription, storage, and publication credentials belong
in the farm secret store and are consumed only by explicit adapters.

## 龙虾部署结构

### Workflow 映射

`workflows/lobster/content_distillation.lobster` is the executable mapping.
`workflows/lobster/node_contracts.json` records the name, purpose, input,
output, dependency, and failure behavior for the same five nodes:

~~~text
source_input
  -> unified_distillation
  -> creator_plugin_enhancement checkpoint
  -> quality_gate
  -> content_generation handoff (PASS only)
~~~

The plugin checkpoint validates enhancement created inside the preceding
single engine invocation; it does not run a second distillation pass.

The final template node emits a `GenerationRequest` handoff. The blank
framework deliberately does not supply a model or publishing implementation.

### Skill 加载

Existing framework Skills remain unchanged under `skills/<internal-name>/`.
`skills/internal/catalog.json` maps those packages for the adapter layer.
OpenClaw-compatible wrappers live under `skills/openclaw/` and use hyphenated
names:

- `source-ingestion`;
- `unified-distillation`;
- `quality-review`.

Each wrapper declares metadata, version, description, entrypoint,
dependencies, runtime requirements, and a focused test command. Verify native
loading on the target instance with `openclaw skills list` or the equivalent
farm preflight.

### Quality Gate control

`QualityGateController` is the only component allowed to invoke an injected
generation adapter. A FAIL decision returns `review_required` and records
`generation_adapter_invoked=false`. Lobster also guards the final step with
`$quality_gate.json.can_continue`.

## Package

From `blank/workspace/`:

```powershell
.\scripts\package_workspace.ps1
```

The script writes a timestamped archive under `blank/dist/`, prints its SHA-256
hash, and refuses to overwrite an existing artifact. Tests and cache files are
excluded; framework docs and plugin rule data remain included.

## Deploy and smoke test

1. Import the generated archive using the farm's approved workspace restore or
   instance creation flow.
2. Select and mount the instance-owned runtime profile; set
   `CREATOR_RUNTIME_CONFIG` when it is not the packaged default.
3. Attach only the input and generation adapters approved for that instance.
4. Run a dry input through the Lobster workflow with publication disabled.
5. Confirm a safe input reaches the generation handoff.
6. Confirm a `block` risk produces `review_required` and does not execute the
   generation step.
7. Record the archive SHA-256 and plugin/runtime versions in the release record.
8. Activate generation or publication only after the deployment owner approves
   the adapter side effects.

## Rollback

Keep the previously deployed workspace archive and configuration reference.
Rollback restores that immutable archive and its matching plugin/runtime
settings. Do not mix a new plugin's private schema with an older workspace
release. The original `openclaw-backup-20260922.tar.gz` is a source snapshot,
not an automatically validated production rollback.

## Production readiness boundary

This foundation supplies contracts, deterministic reference behavior, tests,
and packaging. A production gate must still validate real adapter connectivity,
secret access, observability, retention policy, capacity, and the farm-specific
restore/activation process.
