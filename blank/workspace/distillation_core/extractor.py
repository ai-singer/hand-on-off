"""Common, domain-neutral extraction from normalized raw material."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from core.models import RawSource

from .classifier import MaterialRole, SourceClassifier


def _summary(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


class CommonExtractor:
    """Build the four shared signal families without domain assumptions."""

    def __init__(self, classifier: SourceClassifier | None = None) -> None:
        self._classifier = classifier or SourceClassifier()

    def extract(self, sources: Iterable[RawSource]) -> dict[str, list[dict]]:
        grouped: dict[MaterialRole, list[RawSource]] = defaultdict(list)
        for source in sources:
            grouped[self._classifier.classify(source)].append(source)

        return {
            MaterialRole.TOPIC.value: [
                {
                    "label": _summary(source.as_text(), 100),
                    "rationale": "Source was classified as a topic signal.",
                    "source_ids": [source.source_id],
                    "confidence": 0.7,
                    "origin": "common",
                }
                for source in grouped[MaterialRole.TOPIC]
            ],
            MaterialRole.STRUCTURE.value: [
                {
                    "name": source.metadata.get("template_name", "source-derived-structure"),
                    "sections": _extract_sections(source.as_text()),
                    "source_ids": [source.source_id],
                    "origin": "common",
                }
                for source in grouped[MaterialRole.STRUCTURE]
            ],
            MaterialRole.KNOWLEDGE.value: [
                {
                    "statement": _summary(source.as_text()),
                    "evidence_refs": [source.reference()],
                    "confidence": float(source.metadata.get("confidence", 0.65)),
                    "origin": "common",
                }
                for source in grouped[MaterialRole.KNOWLEDGE]
            ],
            MaterialRole.STYLE.value: [
                {
                    "name": source.metadata.get("style_name", "source-derived-style"),
                    "attributes": list(
                        source.metadata.get("style_attributes", ["preserve-source-tone"])
                    ),
                    "source_ids": [source.source_id],
                    "origin": "common",
                }
                for source in grouped[MaterialRole.STYLE]
            ],
        }


def _extract_sections(text: str) -> list[str]:
    sections = [
        line.lstrip("#-0123456789. ").strip()
        for line in text.splitlines()
        if line.strip()
    ]
    sections = [section for section in sections if section]
    return sections[:8] or ["opening", "development", "conclusion"]
