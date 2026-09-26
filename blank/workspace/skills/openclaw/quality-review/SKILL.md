---
name: quality-review
version: 1.0.0
description: Enforce the pre-generation quality and risk gate for a unified artifact.
metadata:
  openclaw:
    requires:
      bins: ["python"]
---

# Quality review adapter

Pass the plugin-verified artifact envelope to:

    python -m workflows.lobster.runtime_adapter gate

Continue to content generation only when the JSON response contains
decision=PASS and can_continue=true. A non-zero exit or FAIL decision stops the
workflow.
