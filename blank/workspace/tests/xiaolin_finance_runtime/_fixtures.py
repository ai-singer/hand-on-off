"""Shared fixtures for xiaolin_finance runtime validation.

All material here is synthetic text written for the tests. No real finance
material is collected, downloaded or reproduced.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

from core import RawSource, SourceType
from plugin_interface import PluginContribution, PluginIdentity


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = WORKSPACE_ROOT / "plugins" / "xiaolin_finance"
SHARED_SCHEMA_PATH = WORKSPACE_ROOT / "schemas" / "unified_distillation_artifact.json"
DEFAULT_CONFIG = WORKSPACE_ROOT / "config" / "runtime" / "default.json"
DEFAULT_WORKFLOW = "workflows/lobster/content_distillation.lobster"

PLUGIN_MODULE_PATH = "plugins.xiaolin_finance"
PLUGIN_NAME = "xiaolin_finance"
STUB_MODULE_PATH = "plugins.xiaolin_runtime_probe"

DISTILLATION_SECTIONS = (
    "business_mechanism",
    "financial_structure",
    "data_expression_pattern",
    "case_selection_logic",
    "misconception_analysis",
)

PROHIBITED_CATEGORIES = (
    "investment_advice",
    "market_prediction",
    "emotional_language",
    "unverified_fact",
)

#: One synthetic fixture per distilled section.
SECTION_FIXTURES = {
    "business_mechanism": (
        "The company business model connects subscription revenue with service cost."
    ),
    "financial_structure": (
        "The income statement and balance sheet describe the cost structure."
    ),
    "data_expression_pattern": (
        "The growth rate ratio compares this quarter with the previous one."
    ),
    "case_selection_logic": (
        "This enterprise is used as the case because its earnings are traceable."
    ),
    "misconception_analysis": (
        "A common misunderstanding is that revenue equals profit."
    ),
}

#: A report-shaped source carrying provenance metadata, as Step 2 describes.
REPORT_SOURCE = RawSource(
    source_id="report-1",
    source_type=SourceType.DOCUMENT,
    content=(
        "The income statement shows the revenue structure, the cost structure "
        "and the gross margin for the period."
    ),
    metadata={"source": "financial_report"},
)


def source(text: str, source_id: str = "fixture-1") -> RawSource:
    return RawSource(
        source_id=source_id,
        source_type=SourceType.DOCUMENT,
        content=text,
    )


def plugin_json(relative_path: str) -> Any:
    return json.loads((PLUGIN_ROOT / relative_path).read_text(encoding="utf-8"))


def write_config(directory: str | Path, **overrides: Any) -> Path:
    plugins = list(overrides.get("plugins", [PLUGIN_MODULE_PATH]))
    payload = {
        "instance": {"name": overrides.get("instance", "xiaolin-runtime-probe")},
        "workflow": {"default": overrides.get("workflow", DEFAULT_WORKFLOW)},
        "plugins": {
            "enabled": plugins,
            "default": overrides.get("default_plugin", plugins[0]),
        },
        "skills": {
            "enabled": list(
                overrides.get(
                    "skills",
                    ("source-ingestion", "unified-distillation", "quality-review"),
                )
            )
        },
        "version": overrides.get("version", "1.0.0"),
    }
    path = Path(directory) / "runtime.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class _StubPlugin:
    """A second plugin, used to prove the config controls selection."""

    @property
    def identity(self) -> PluginIdentity:
        return PluginIdentity(
            name="xiaolin-runtime-probe",
            version="0.1.0",
            domain="probe",
            creator_target="probe-creator",
        )

    def enhance(self, raw_sources, common_signals) -> PluginContribution:
        return PluginContribution(domain_extension={})


def register_stub_plugin() -> None:
    module = types.ModuleType(STUB_MODULE_PATH)
    module.create_plugin = _StubPlugin  # type: ignore[attr-defined]
    sys.modules[STUB_MODULE_PATH] = module


def unregister_stub_plugin() -> None:
    sys.modules.pop(STUB_MODULE_PATH, None)


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
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        return {"status": "generated", "format": request.format_name}
