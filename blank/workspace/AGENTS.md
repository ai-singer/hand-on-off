# Creator Agent Template Contract

This workspace is a deployable Creator Agent template. Its job is to turn raw
source material into a single validated distillation artifact, optionally hand
that artifact to a generation adapter, and run quality checks.

## Startup

1. Read `SOUL.md`, `USER.md`, and `IDENTITY.md`.
2. Read `docs/ARCHITECTURE.md` before changing framework boundaries.
3. Select the Creator plugin through `CREATOR_PLUGIN`; do not add domain policy
   to `core/` or `distillation_core/`.
4. Load only the skills required by the active workflow.

## Runtime contract

- Inputs are `core.models.RawSource` records for video, document, data, or
  image material.
- Distillation is one coordinated engine run. Never feed a completed generic
  artifact into a second domain-distillation pass.
- Every run must return a value conforming to
  `schemas/unified_distillation_artifact.json`.
- Content generation is an injected adapter and must not be embedded in the
  distillation core.
- External publication, paid actions, credential use, or production mutation
  require explicit user authorization.

## Change boundaries

- Common behavior belongs in `core/` or `distillation_core/`.
- Creator/domain behavior belongs in `plugins/<plugin_name>/`.
- Reusable operating procedures belong in versioned `skills/<skill_name>/`.
- Orchestration belongs in `workflows/`; quality policy belongs in
  `evaluation/` or a plugin evaluation package.
- Add or update focused tests whenever observable behavior changes.

## Verification

Run from this workspace root:

```bash
python -m unittest discover -s tests -v
```
