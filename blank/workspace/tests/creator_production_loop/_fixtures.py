"""Synthetic source material for production loop validation.

Every fixture is written for these tests. No real finance material is
collected, downloaded or reproduced, and no content is generated.
"""

from __future__ import annotations

from pathlib import Path

from core import RawSource, SourceType
from plugin_interface import PluginContribution, PluginIdentity


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_MODULE_PATH = "plugins.xiaolin_finance"

#: The nine sections every unified artifact must carry.
ARTIFACT_SECTIONS = (
    "artifact_version",
    "plugin",
    "topic_candidate",
    "content_template",
    "knowledge_unit",
    "style_pattern",
    "domain_extension",
    "risk_constraints",
    "evaluation_result",
)

#: The four common signal families owned by the universal layer.
COMMON_FAMILIES = (
    "topic_candidate",
    "content_template",
    "knowledge_unit",
    "style_pattern",
)

DISTILLATION_SECTIONS = (
    "business_mechanism",
    "financial_structure",
    "data_expression_pattern",
    "case_selection_logic",
    "misconception_analysis",
)

# --- Step 2: one fixture per source adapter kind -------------------------------

#: Test A - business analysis text. The RawSource contract calls this
#: `document`; there is no `text` value in the enum.
DOCUMENT_SOURCE = RawSource(
    source_id="doc-text-1",
    source_type=SourceType.DOCUMENT,
    content=(
        "The company business model links subscription revenue to "
        "cash flow and margin data."
    ),
    metadata={"source": "business_analysis", "format": "text"},
)

#: Test B - structured financial metrics.
DATA_SOURCE = RawSource(
    source_id="data-metrics-1",
    source_type=SourceType.DATA,
    content={
        "period": "2026Q2",
        "revenue_structure": "subscription 60 percent, services 40 percent",
        "cost_structure": "fixed 45 percent, variable 55 percent",
        "gross_margin": 0.42,
    },
    metadata={"source": "financial_metrics", "format": "table"},
)

#: Test C - video summary input.
VIDEO_SOURCE = RawSource(
    source_id="video-summary-1",
    source_type=SourceType.VIDEO,
    content=(
        "Video summary: the presenter explains how the income statement and "
        "balance sheet reveal the cost structure."
    ),
    metadata={"source": "video_transcript_summary", "duration_seconds": 420},
)

#: Test D - image / OCR description input.
IMAGE_SOURCE = RawSource(
    source_id="image-ocr-1",
    source_type=SourceType.IMAGE,
    content="OCR caption: a chart comparing the growth rate ratio across four quarters.",
    metadata={"source": "ocr_description", "format": "chart_caption"},
)

SOURCE_KIND_FIXTURES = (
    ("document", DOCUMENT_SOURCE),
    ("data", DATA_SOURCE),
    ("video", VIDEO_SOURCE),
    ("image", IMAGE_SOURCE),
)

# --- Step 3: one source per distillation role, deliberately mixing types -------

ROLE_SOURCES = (
    RawSource(
        source_id="role-topic",
        source_type=SourceType.DOCUMENT,
        content="A common misunderstanding is that revenue equals profit.",
        metadata={"distillation_role": "topic_candidate"},
    ),
    RawSource(
        source_id="role-structure",
        source_type=SourceType.VIDEO,
        content="Section one explains the mechanism. Section two presents the evidence.",
        metadata={"distillation_role": "content_template"},
    ),
    RawSource(
        source_id="role-knowledge",
        source_type=SourceType.DATA,
        content={"income_statement": "revenue and cost structure for the period"},
        metadata={"distillation_role": "knowledge_unit"},
    ),
    RawSource(
        source_id="role-style",
        source_type=SourceType.IMAGE,
        content="OCR caption: plain explanatory tone with a steady rhythm.",
        metadata={"distillation_role": "style_pattern"},
    ),
)

# --- Step 5: evaluation loop cases --------------------------------------------

#: Case 1 - a finance explanation that explains mechanism and interprets data.
QUALITY_SOURCE = RawSource(
    source_id="quality-1",
    source_type=SourceType.DOCUMENT,
    content=(
        "The company business model connects subscription revenue with service "
        "cost, and the income statement shows how the growth rate ratio moved "
        "across periods."
    ),
    metadata={"source": "business_analysis"},
)

#: Case 2 - prohibited content that must never reach generation.
RISK_SOURCE = RawSource(
    source_id="risk-1",
    source_type=SourceType.DOCUMENT,
    content="This is a guaranteed buy at the current price.",
    metadata={"source": "social_post"},
)


class DomainFreePlugin:
    """Contributes nothing, so common output can be compared against it."""

    @property
    def identity(self) -> PluginIdentity:
        return PluginIdentity(
            name="domain_free",
            version="1.0.0",
            domain="none",
            creator_target="none",
        )

    def enhance(self, raw_sources, common_signals) -> PluginContribution:
        return PluginContribution(
            domain_extension={},
            evaluation_result={"score": 1.0, "passed": True},
        )


class RecordingGenerationAdapter:
    """Generation adapter that records consumption without producing content."""

    def __init__(self) -> None:
        self.calls = 0
        self.requests: list = []

    def generate(self, request):
        self.calls += 1
        self.requests.append(request)
        return {"status": "accepted", "format": request.format_name}
