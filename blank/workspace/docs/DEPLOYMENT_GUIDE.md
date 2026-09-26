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
- production secrets stored outside this repository;
- a selected plugin module, for example `plugins.xiaolin_finance`.

No third-party Python dependency is required by the reference framework.

## Preflight

From `blank/workspace/`:

```powershell
python -m unittest discover -s tests -v
python -c "from core import load_plugin; print(load_plugin('plugins.xiaolin_finance').identity)"
```

Verify that neither `.env` nor `.openclaw/openclaw.json` exists in the source
workspace. The packaging script rejects both paths.

## Configuration

Copy `.env.example` values into the farm's environment configuration rather
than creating a committed `.env` file:

- `CREATOR_PLUGIN`: import path of the selected Creator plugin;
- `CREATOR_SCHEMA_PATH`: shared artifact schema path;
- `CREATOR_LOG_LEVEL`: deployment logging level.

Model, search, OCR, transcription, storage, and publication credentials belong
in the farm secret store and are consumed only by explicit adapters.

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
2. Set `CREATOR_PLUGIN` and non-secret runtime settings.
3. Attach only the input and generation adapters approved for that instance.
4. Run a dry input through the pipeline with publication disabled.
5. Confirm the artifact validates and that a `block` risk produces
   `review_required`.
6. Record the archive SHA-256 and plugin version in the release record.
7. Activate generation or publication only after the deployment owner approves
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
