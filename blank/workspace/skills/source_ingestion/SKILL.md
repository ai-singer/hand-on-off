---
name: source_ingestion
version: 1.0.0
description: Normalize extracted video, document, data, or image material into RawSource records.
---

# Source ingestion

1. Receive an extracted payload and provenance metadata from an approved
   adapter. Do not place binary blobs or credentials in the artifact.
2. Assign a stable `source_id` and one supported `source_type`.
3. Put readable text or structured data in `content`.
4. Preserve provenance in `metadata`; optionally set `distillation_role` to
   `topic_candidate`, `content_template`, `knowledge_unit`, or `style_pattern`.
5. Construct `core.models.RawSource`. Surface validation failures explicitly.

This skill performs normalization only. OCR, transcription, remote retrieval,
and credential handling belong to injected deployment adapters.
