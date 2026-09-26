---
name: quality_review
version: 1.0.0
description: Combine common quality signals, plugin evaluation, and risk constraints into a review decision.
---

# Quality review

1. Verify the artifact against the shared JSON Schema.
2. Inspect common source-reference coverage and signal-family coverage.
3. Preserve the plugin's rule-level evaluation evidence.
4. Stop automatic progression when a `block` constraint exists.
5. Return `pass` or `review_required` with explicit reasons. Never weaken a
   plugin risk rule to make the workflow pass.
