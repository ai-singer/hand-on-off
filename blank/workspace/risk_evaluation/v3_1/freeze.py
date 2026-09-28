"""The Phase 8.8 freeze, and the verification of the baseline it started from.

Two artifacts, and they answer different questions.

**`phase_8_8_baseline_freeze.json`** was taken before the first change and records
the five components as Phase 8.7 left them. Recomputing them now says which of
those five the capability expansion moved. The answer is part of the result: a
capability that changed the taxonomy or the decision policy would be doing
something this phase was not asked to do.

**`evaluation_freeze_v3_1.json`** records the state the Phase 8.8 numbers were
measured against, so a later phase can tell whether it is looking at the same
pipeline. It freezes more than Phase 8.7's did, because this phase adds things the
Phase 8.6 schema has no slot for:

    capability_hashes     the four Phase 8.8 modules, by source bytes
    capability_table_hash the declared verdicts, signals, directives and carriers
    benchmark_hash        the 80 capability cases
    baseline_hash         the pre-change baseline this phase started from
    gate                  whether the regression passed, and the counts behind it

The gate is recorded in the freeze rather than only in the report. A freeze that
records a hash of a pipeline that broke a case would be a freeze of a failure, and
putting the verdict in the same artifact makes that visible instead of leaving it to
whoever reads both.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..v3.decision import RELATION_REQUIRED, RULES
from ..v3.model import V3_VERSION
from ..v3_validation.freeze import VERIFIED_KEYS, build_freeze
from . import advice, certainty, detectors, evaluation, modal, signals
from .benchmark.cases import CASES, MINIMUM_CASES, PROVENANCE
from .regression import dataset_hash as capability_dataset_hash

BASELINE_PATH = Path(__file__).resolve().parent / "phase_8_8_baseline_freeze.json"
FREEZE_PATH = Path(__file__).resolve().parent / "evaluation_freeze_v3_1.json"
FREEZE_SCHEMA_VERSION = "3.2.0"
FREEZE_KIND = "capability-expansion"

#: The Phase 8.8 modules, by dotted name, frozen by source bytes.
CAPABILITY_MODULES: Mapping[str, str] = {
    "signals": "risk_evaluation.v3_1.signals",
    "certainty": "risk_evaluation.v3_1.certainty",
    "modal": "risk_evaluation.v3_1.modal",
    "advice": "risk_evaluation.v3_1.advice",
    "detectors": "risk_evaluation.v3_1.detectors",
}


class FreezeError(Exception):
    """Raised when a Phase 8.8 freeze cannot be taken or verified."""


def _sha(payload: Any) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def capability_hash(dotted: str) -> str:
    module = importlib.import_module(dotted)
    location = getattr(module, "__file__", None)
    if not location:  # pragma: no cover - defensive
        raise FreezeError(f"{dotted} has no source file to freeze")
    return hashlib.sha256(Path(location).read_bytes()).hexdigest()


def capability_hashes() -> dict[str, str]:
    return {name: capability_hash(dotted) for name, dotted in CAPABILITY_MODULES.items()}


def capability_table_hash() -> str:
    """The declared verdicts, signals, directives, carriers and rules."""

    return _sha(
        {
            "signals": list(signals.SIGNAL_NAMES),
            "signal_families": dict(signals.SIGNAL_FAMILIES),
            "capabilities": list(signals.CAPABILITIES),
            "certainty_order": list(certainty.ORDER),
            "certainty_carriers": [
                {"level": level, "kind": kind, "pattern": pattern}
                for level, kind, pattern in certainty.CARRIERS
            ],
            "modal_verdicts": list(modal.VERDICTS),
            "modal_declining": list(modal.DECLINING_VERDICTS),
            "modal_comparison_lemmas": list(modal.COMPARISON_LEMMAS),
            "modal_non_directional": list(modal.NON_DIRECTIONAL_LEMMAS),
            "modal_epistemic": list(modal.EPISTEMIC_LEMMAS),
            "advice_verdicts": list(advice.VERDICTS),
            "advice_declining": list(advice.DECLINING_VERDICTS),
            "advice_position_lemmas": list(advice.POSITION_LEMMAS),
            "advice_method_lemmas": list(advice.METHOD_LEMMAS),
            "advice_advisory_frames": [name for name, _ in advice.ADVISORY_FRAMES],
            "advice_reporting_verbs": advice.REPORTING_VERBS,
            "veto_hedge_policies": list(detectors.HEDGE_POLICIES),
            "relation_required": {
                key: list(value) for key, value in sorted(RELATION_REQUIRED.items())
            },
            "decision_rules": [
                {"rule_id": item.rule_id, "base_action": item.base_action}
                for item in RULES
            ],
            "error_kinds": list(evaluation.ERROR_KINDS),
        }
    )


def benchmark_hash() -> str:
    return capability_dataset_hash()


def baseline_hash() -> str:
    """A digest of the baseline freeze's five components."""

    baseline = load_baseline()
    return _sha({key: baseline[key] for key in VERIFIED_KEYS})


def load_baseline(path: str | Path | None = None) -> Mapping[str, Any]:
    target = Path(path) if path is not None else BASELINE_PATH
    if not target.is_file():
        raise FreezeError(f"no Phase 8.8 baseline freeze at {target}")
    return json.loads(target.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class BaselineVerification:
    """Which of the five inherited components the capability expansion moved."""

    matches: bool
    mismatches: tuple[str, ...]
    baseline: Mapping[str, Any]
    current: Mapping[str, Any]

    @property
    def moved(self) -> tuple[str, ...]:
        return self.mismatches

    def render(self) -> str:
        if self.matches:
            return "phase 8.8 baseline MATCH: no inherited component moved"
        return "phase 8.8 baseline MOVED: " + ", ".join(self.mismatches)

    def as_dict(self) -> dict[str, Any]:
        return {
            "matches": self.matches,
            "moved": list(self.moved),
            "baseline": {key: self.baseline.get(key) for key in VERIFIED_KEYS},
            "current": {key: self.current.get(key) for key in VERIFIED_KEYS},
        }


def verify_baseline(path: str | Path | None = None) -> BaselineVerification:
    baseline = load_baseline(path)
    current = build_freeze()
    mismatches = tuple(
        key for key in VERIFIED_KEYS if baseline.get(key) != current.get(key)
    )
    return BaselineVerification(
        matches=not mismatches,
        mismatches=mismatches,
        baseline=baseline,
        current=current,
    )


def build_capability_freeze(*, gate: Any | None = None) -> dict[str, Any]:
    from .regression import build_gate

    current = build_freeze()
    active_gate = gate if gate is not None else build_gate()
    return {
        "freeze_schema_version": FREEZE_SCHEMA_VERSION,
        "freeze_kind": FREEZE_KIND,
        "pipeline": current["pipeline"],
        "pipeline_version": V3_VERSION,
        "capabilities": list(signals.CAPABILITIES),
        # `VERIFIED_KEYS` already carries `benchmark_hash`, and it is Phase 8.6's
        # independent benchmark. The capability benchmark needs its own key: writing
        # it under the same name would overwrite the evidence that Phase 8.6's
        # labels are untouched, which is the check this freeze most needs to keep.
        **{key: current[key] for key in VERIFIED_KEYS},
        "capability_hashes": capability_hashes(),
        "capability_table_hash": capability_table_hash(),
        "capability_benchmark": PROVENANCE["benchmark"],
        "capability_benchmark_hash": benchmark_hash(),
        "capability_case_count": len(CASES),
        "minimum_cases": MINIMUM_CASES,
        "benchmark_provenance": dict(PROVENANCE),
        "baseline_hash": baseline_hash(),
        "baseline_verification": verify_baseline().as_dict(),
        "gate": {
            "status": active_gate.status,
            "broken": list(active_gate.broken),
            "fixed_count": active_gate.fixed,
            "sets": len(active_gate.sets),
            "cases": sum(item.cases for item in active_gate.sets),
        },
        "supersedes": {
            "phase_8_6": "risk_evaluation/v3_validation/evaluation_freeze_v3.json",
            "phase_8_7": "risk_evaluation/v3_repair/evaluation_freeze_v3_repair.json",
        },
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def write_capability_freeze(path: str | Path | None = None) -> Path:
    target = Path(path) if path is not None else FREEZE_PATH
    target.write_text(
        json.dumps(build_capability_freeze(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def load_capability_freeze(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else FREEZE_PATH
    if not target.is_file():
        raise FreezeError(f"no Phase 8.8 freeze at {target}")
    return json.loads(target.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class FreezeVerification:
    matches: bool
    mismatches: tuple[str, ...]
    gate_status: str
    frozen: Mapping[str, Any]
    current: Mapping[str, Any]

    def render(self) -> str:
        if self.matches:
            return f"evaluation freeze v3_1 MATCH (gate {self.gate_status})"
        return "evaluation freeze v3_1 CHANGED: " + ", ".join(self.mismatches)

    def as_dict(self) -> dict[str, Any]:
        return {
            "matches": self.matches,
            "mismatches": list(self.mismatches),
            "gate_status": self.gate_status,
        }


def verify_capability_freeze(path: str | Path | None = None) -> FreezeVerification:
    frozen = load_capability_freeze(path)
    current = build_capability_freeze()
    keys: Sequence[str] = (
        *VERIFIED_KEYS,
        "capability_table_hash",
        "capability_benchmark_hash",
        "baseline_hash",
    )
    mismatches = [key for key in keys if frozen.get(key) != current.get(key)]
    for name, digest in current["capability_hashes"].items():
        if frozen.get("capability_hashes", {}).get(name) != digest:
            mismatches.append(f"capability_hashes.{name}")
    if frozen.get("gate", {}).get("status") != current["gate"]["status"]:
        mismatches.append("gate.status")
    return FreezeVerification(
        matches=not mismatches,
        mismatches=tuple(mismatches),
        gate_status=current["gate"]["status"],
        frozen=frozen,
        current=current,
    )


def describe() -> dict[str, Any]:
    """The freeze's shape, for the report and the tests."""

    return {
        "baseline_path": BASELINE_PATH.name,
        "freeze_path": FREEZE_PATH.name,
        "schema_version": FREEZE_SCHEMA_VERSION,
        "kind": FREEZE_KIND,
        "verified_keys": list(VERIFIED_KEYS),
        "capability_modules": dict(CAPABILITY_MODULES),
        "components": [
            *VERIFIED_KEYS,
            "capability_table_hash",
            "capability_benchmark_hash",
            "baseline_hash",
            "gate.status",
        ],
    }


def main() -> int:
    import sys

    if "--write" in sys.argv:
        print(f"wrote {write_capability_freeze()}")
        return 0
    baseline = verify_baseline()
    print(baseline.render())
    for key in baseline.moved:
        print(
            f"  {key}: {baseline.baseline.get(key)[:16]} -> "
            f"{baseline.current.get(key)[:16]}"
        )
    print()
    result = verify_capability_freeze()
    print(result.render())
    if not result.matches:
        for key in result.mismatches:
            print(f"  {key}")
        return 1
    frozen = result.frozen
    for key in (
        *VERIFIED_KEYS,
        "capability_table_hash",
        "capability_benchmark_hash",
        "baseline_hash",
    ):
        print(f"  {key:28} {str(frozen[key])[:16]}")
    for name, digest in sorted(frozen["capability_hashes"].items()):
        print(f"  capability:{name:16} {digest[:16]}")
    gate = frozen["gate"]
    print(f"  {'gate':28} {gate['status']} broken {len(gate['broken'])}")
    print(
        f"  {'capability_benchmark':28} {frozen['capability_benchmark']} "
        f"({frozen['capability_case_count']} cases)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
