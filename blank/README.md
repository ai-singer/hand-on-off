# Creator Agent Template Instance

`blank/workspace/` is the new deployable Creator Agent workspace. It preserves
the OpenClaw workspace envelope found in the original backup while adding a
plugin-oriented, single-pass distillation framework.

- Start with `BLANK_INSTANCE_ANALYSIS.md` for the source-state assessment.
- Read `workspace/docs/ARCHITECTURE.md` for module boundaries.
- Run tests from `workspace/` with
  `python -m unittest discover -s tests -v`.
- Keep `openclaw-backup-20260922.tar.gz` unchanged as the original recovery
  artifact.
