---
name: unified_distillation
version: 1.0.0
description: Run common extraction and one Creator plugin in a single validated distillation invocation.
---

# Unified distillation

1. Load exactly one configured Creator plugin through `core.load_plugin`.
2. Pass all `RawSource` values to one `DistillationEngine.distill()` call.
3. Do not serialize common extraction and feed it to a second domain process.
4. Reject plugin contract errors and schema-invalid output.
5. Return the one `UnifiedDistillationArtifact`; do not generate or publish
   content in this skill.
