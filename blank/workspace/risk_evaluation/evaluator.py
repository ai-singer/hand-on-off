"""Risk intent evaluation interface and the current keyword-backed evaluator.

The framework separates *what a risk is* (taxonomy) from *how it is detected*
(evaluator). Today there is exactly one evaluator, and it is the existing
xiaolin_finance keyword rules wrapped read-only: no keyword is added, removed
or reweighted, and the plugin's own behaviour is what gets measured.

A future semantic or model-backed evaluator implements the same protocol and
replaces this one without touching the taxonomy, the result contract, the
artifact schema or the quality gate.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from core import RawSource, SourceType, load_plugin
from distillation_core import DistillationEngine

from .model import RiskEvaluationError, RiskEvaluationResult
from .taxonomy import categories_for_evaluator_category, category as taxonomy_category


_WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLUGIN_MODULE_PATH = "plugins.xiaolin_finance"


@runtime_checkable
class RiskIntentEvaluator(Protocol):
    """Replaceable risk intent evaluator.

    Implementations must be deterministic for identical input unless they
    document an external dependency, must not publish or mutate anything, and
    must report ambiguity rather than resolving it silently.
    """

    name: str

    def evaluate_text(
        self, text: str, *, source_ids: Sequence[str] = ()
    ) -> tuple[RiskEvaluationResult, ...]:
        """Evaluate raw text and return one result per detected risk."""

    def evaluate_artifact(
        self, artifact: Mapping[str, Any]
    ) -> tuple[RiskEvaluationResult, ...]:
        """Evaluate an existing artifact's risk constraints."""


@lru_cache(maxsize=8)
def _rule_category_map(plugin_module_path: str) -> Mapping[str, str]:
    """Map rule ids to categories for artifacts written before that field."""

    relative = Path(*plugin_module_path.split(".")) / "rules" / "filter_rules.json"
    payload = json.loads((_WORKSPACE_ROOT / relative).read_text(encoding="utf-8"))
    return {
        str(rule["id"]): str(rule.get("category", rule["id"]))
        for rule in payload["rules"]
    }


class KeywordRiskEvaluator:
    """Adapter over the existing plugin rules. Read-only by construction."""

    name = "keyword-xiaolin-finance-v1"

    def __init__(self, plugin_module_path: str = DEFAULT_PLUGIN_MODULE_PATH) -> None:
        self._plugin_module_path = plugin_module_path
        self._plugin = load_plugin(plugin_module_path)

    @property
    def plugin_module_path(self) -> str:
        return self._plugin_module_path

    @property
    def plugin_identity(self) -> Any:
        return self._plugin.identity

    def evaluate_text(
        self, text: str, *, source_ids: Sequence[str] = ()
    ) -> tuple[RiskEvaluationResult, ...]:
        if not isinstance(text, str) or not text.strip():
            raise RiskEvaluationError("evaluate_text requires non-empty text")
        source = RawSource(
            source_id=str(source_ids[0]) if source_ids else "risk-evaluation-input",
            source_type=SourceType.DOCUMENT,
            content=text,
        )
        artifact = DistillationEngine(self._plugin).distill([source])
        return self.evaluate_artifact(artifact)

    def evaluate_artifact(
        self, artifact: Mapping[str, Any]
    ) -> tuple[RiskEvaluationResult, ...]:
        constraints = artifact.get("risk_constraints", ())
        return tuple(self._translate(item) for item in constraints)

    def _translate(self, constraint: Mapping[str, Any]) -> RiskEvaluationResult:
        evaluator_category = self._evaluator_category(constraint)
        candidates = categories_for_evaluator_category(evaluator_category)
        primary = candidates[0] if candidates else evaluator_category
        entry = taxonomy_category(primary)

        detail = str(constraint.get("message", ""))
        if len(candidates) > 1:
            detail = (
                f"{detail} [evaluator cannot separate: {', '.join(candidates)}]"
            ).strip()

        return RiskEvaluationResult(
            category=primary,
            intent=entry.intent,
            # The match itself is deterministic, so confidence states how sure
            # the evaluator is about which category the match means. With N
            # candidate categories that is 1/N.
            confidence=round(1.0 / max(1, len(candidates)), 3),
            evidence_required=entry.evidence_required,
            severity=str(constraint.get("severity", entry.severity)),
            action=str(constraint.get("action", entry.action)),
            evaluator=self.name,
            detail=detail,
            source_ids=tuple(str(item) for item in constraint.get("source_ids", ())),
            candidates=candidates or (primary,),
        )

    def _evaluator_category(self, constraint: Mapping[str, Any]) -> str:
        declared = constraint.get("category")
        if isinstance(declared, str) and declared:
            return declared
        rule_id = constraint.get("rule_id")
        mapped = _rule_category_map(self._plugin_module_path).get(str(rule_id))
        if mapped:
            return mapped
        raise RiskEvaluationError(
            f"risk constraint has neither category nor a known rule_id: {rule_id!r}"
        )
