"""Deterministic classification of source intent for reference extraction."""

from __future__ import annotations

from enum import Enum

from core.models import RawSource


class MaterialRole(str, Enum):
    TOPIC = "topic_candidate"
    STRUCTURE = "content_template"
    KNOWLEDGE = "knowledge_unit"
    STYLE = "style_pattern"


_ROLE_KEYWORDS = {
    MaterialRole.STRUCTURE: ("outline", "structure", "chapter", "section", "步骤", "结构", "大纲"),
    MaterialRole.STYLE: ("tone", "voice", "style", "rhythm", "语气", "风格", "节奏"),
    MaterialRole.TOPIC: ("topic", "question", "trend", "主题", "选题", "趋势"),
}


class SourceClassifier:
    """Classify by explicit metadata first, then conservative text signals."""

    def classify(self, source: RawSource) -> MaterialRole:
        explicit = source.metadata.get("distillation_role")
        if explicit is not None:
            try:
                return MaterialRole(str(explicit))
            except ValueError as exc:
                allowed = ", ".join(item.value for item in MaterialRole)
                raise ValueError(
                    f"unknown distillation_role {explicit!r}; expected {allowed}"
                ) from exc

        normalized = source.as_text().lower()
        for role, keywords in _ROLE_KEYWORDS.items():
            if any(keyword in normalized for keyword in keywords):
                return role
        return MaterialRole.KNOWLEDGE
