---
name: unified-distillation
version: 1.0.0
description: Run one configured common-plus-Creator distillation and return a validated artifact.
metadata:
  openclaw:
    requires:
      bins: ["python"]
---

# Unified distillation adapter

Pass the source-ingestion JSON result to:

    python -m workflows.lobster.runtime_adapter distill

Run this command exactly once. Creator plugin enhancement is part of this
invocation and must not be repeated as a second distillation pass.
