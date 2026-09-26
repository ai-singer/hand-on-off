---
name: source-ingestion
version: 1.0.0
description: Normalize approved source payloads into Creator Agent RawSource records.
metadata:
  openclaw:
    requires:
      bins: ["python"]
---

# Source ingestion adapter

Use this adapter only for already extracted text or structured source data.
From the workspace root, invoke:

    python -m workflows.lobster.runtime_adapter source-input

Provide the JSON source array through LOBSTER_ARG_SOURCES_JSON or standard
input. Treat a non-zero exit code as a hard workflow failure.
