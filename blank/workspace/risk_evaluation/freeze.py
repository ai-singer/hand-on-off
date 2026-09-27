"""Freeze and verify the evaluator definition used for independent validation.

Independent validation is only meaningful if the thing being measured cannot
change while it is being measured. This module hashes the semantic evaluator's
complete decision surface — signal patterns, intent patterns, negation cues,
the negation window, the confidence constants and the evaluator name — into
`frozen_baseline.json` along with both evaluator versions.

`verify_freeze()` recomputes the hash and fails if anything moved. The Phase 7.3
test suite asserts it, so a silent edit to the evaluator during or after
validation breaks the build rather than quietly invalidating the results.

The hash deliberately covers the *rule data and declared constants*, not the
module's implementation details: reformatting or adding a docstring must not
invalidate a validation run, but changing a pattern must.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Mapping

from . import semantic_evaluator as semantic_module


FREEZE_PATH = Path(__file__).resolve().parent / "frozen_baseline.json"
FREEZE_SCHEMA_VERSION = "1.0.0"

#: Benchmark whose results the freeze pins. The independent benchmark is a
#: different artefact and is versioned separately.
DEVELOPMENT_BENCHMARK = "risk_evaluation.benchmark@50-cases"
INDEPENDENT_BENCHMARK = "risk_evaluation.independent_benchmark@100-cases"


@dataclass(frozen=True, slots=True)
class FreezeStatus:
    frozen_hash: str
    current_hash: str
    matches: bool
    semantic_evaluator: str
    keyword_evaluator: str

    def render(self) -> str:
        state = "MATCH" if self.matches else "CHANGED"
        return (
            f"freeze {state}: {self.frozen_hash[:16]} vs {self.current_hash[:16]} "
            f"({self.semantic_evaluator} / {self.keyword_evaluator})"
        )


def semantic_decision_surface() -> dict[str, Any]:
    """Return the canonical, hashable description of the evaluator's logic."""

    return {
        "evaluator": semantic_module.SemanticRiskEvaluator.name,
        "negation_window": semantic_module.NEGATION_WINDOW,
        "negatable_signals": list(semantic_module.NEGATABLE_SIGNALS),
        "negation_cues": list(semantic_module.NEGATION_CUES),
        "signal_patterns": {
            name: list(patterns)
            for name, patterns in sorted(semantic_module.SIGNAL_PATTERNS.items())
        },
        "intent_patterns": [
            {
                "category": pattern.category,
                "required": list(pattern.required),
                "boosters": list(pattern.boosters),
                "rationale": pattern.rationale,
            }
            for pattern in semantic_module.INTENT_PATTERNS
        ],
        "confidence": {
            "base": semantic_module._CONFIDENCE_BASE,
            "step": semantic_module._CONFIDENCE_STEP,
            "cap": semantic_module._CONFIDENCE_CAP,
        },
    }


def decision_surface_hash(surface: Mapping[str, Any] | None = None) -> str:
    """Stable SHA-256 over the evaluator's decision surface."""

    payload = surface if surface is not None else semantic_decision_surface()
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def keyword_evaluator_version() -> str:
    module = import_module("risk_evaluation.evaluator")
    return str(module.KeywordRiskEvaluator.name)


def build_baseline() -> dict[str, Any]:
    """Full frozen record, ready to serialise."""

    surface = semantic_decision_surface()
    return {
        "freeze_schema_version": FREEZE_SCHEMA_VERSION,
        "semantic_evaluator": surface["evaluator"],
        "semantic_patterns_hash": decision_surface_hash(surface),
        "semantic_signal_classes": sorted(surface["signal_patterns"]),
        "semantic_intent_categories": sorted(
            pattern["category"] for pattern in surface["intent_patterns"]
        ),
        "keyword_evaluator": keyword_evaluator_version(),
        "development_benchmark": DEVELOPMENT_BENCHMARK,
        "independent_benchmark": INDEPENDENT_BENCHMARK,
        "frozen_before_independent_benchmark": True,
    }


def write_freeze(path: str | Path | None = None) -> Path:
    target = Path(path) if path is not None else FREEZE_PATH
    target.write_text(
        json.dumps(build_baseline(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def load_freeze(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else FREEZE_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def verify_freeze(path: str | Path | None = None) -> FreezeStatus:
    """Compare the recorded freeze against the evaluator as it stands now."""

    frozen = load_freeze(path)
    current = decision_surface_hash()
    return FreezeStatus(
        frozen_hash=str(frozen["semantic_patterns_hash"]),
        current_hash=current,
        matches=str(frozen["semantic_patterns_hash"]) == current,
        semantic_evaluator=str(frozen["semantic_evaluator"]),
        keyword_evaluator=str(frozen["keyword_evaluator"]),
    )


def main() -> int:
    import sys

    if "--write" in sys.argv:
        print(f"wrote {write_freeze()}")
        return 0
    status = verify_freeze()
    print(status.render())
    return 0 if status.matches else 1


if __name__ == "__main__":
    raise SystemExit(main())
