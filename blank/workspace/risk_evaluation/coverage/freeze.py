"""Freeze the coverage framework, and prove it left the evaluator alone.

Three digests, for three different reasons.

`source_hash` covers this package. It is what makes the report reproducible: the same
hash plus the same benchmark gives the same failure distribution, so a later change in
the numbers means a later change in the analyzer.

`benchmark_hash` covers the Phase 8.9 calibration set. Its purpose is negative. The
framework is forbidden from improving its numbers by touching the data, and a hash
that a reviewer can recompute is the cheapest possible proof that it did not.

`evaluator_hash` covers the frozen evaluator sources. The analyzer imports those
modules to read their lexicons and runs them over the benchmark, so it holds them at
arm's length; `guard()` re-reads them from disk and fails if a single byte moved.

This freeze is additive. `evaluation_freeze_v3_2.json` and
`evaluation_freeze_v3_1.json` belong to earlier phases and are neither rewritten nor
re-verified here — a framework that silently re-froze someone else's artifact would
destroy the only record that the artifact was ever stable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

FREEZE_PATH = Path(__file__).with_name("coverage_freeze_r1.json")

#: Frozen evaluator sources the analyzer reads. Recorded, never edited.
EVALUATOR_SOURCES: tuple[str, ...] = (
    "risk_evaluation/v3/patterns.py",
    "risk_evaluation/v3/morphology.py",
    "risk_evaluation/v3/decision.py",
    "risk_evaluation/v3/model.py",
    "risk_evaluation/v3/pipeline.py",
    "risk_evaluation/v3_1/modal.py",
    "risk_evaluation/v3_1/advice.py",
    "risk_evaluation/v3_1/certainty.py",
    "risk_evaluation/v3_repair/sources.py",
    "risk_evaluation/v3_repair/rejection.py",
    "risk_evaluation/v3_independent/evaluation.py",
    "risk_evaluation/v3_independent/dataset.py",
)

#: Phase 8.9 files the calibration label depends on.
BENCHMARK_SOURCES: tuple[str, ...] = (
    "risk_evaluation/benchmarks/risk/independent/v1/cases.json",
    "risk_evaluation/benchmarks/risk/independent/v1/labels.json",
    "risk_evaluation/benchmarks/risk/independent/v1/adjudicated.json",
    "risk_evaluation/benchmarks/risk/independent/v1/disagreements.json",
    "risk_evaluation/benchmarks/risk/independent/v1/manifest.json",
)

#: Freezes owned by earlier phases. Listed so a reviewer can see they are untouched.
FOREIGN_FREEZES: tuple[str, ...] = (
    "risk_evaluation/v3_1/evaluation_freeze_v3_1.json",
    "risk_evaluation/v3_independent/evaluation_freeze_v3_2.json",
)


class FreezeError(Exception):
    """Raised when a frozen artifact no longer matches its digest."""


def repository_root() -> Path:
    """The workspace root, found by walking up to the package's parent."""

    return Path(__file__).resolve().parents[2]


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def digest_file(path: Path) -> str:
    if not path.is_file():
        raise FreezeError(f"frozen file is missing: {path}")
    return digest_bytes(path.read_bytes())


def digest_paths(paths: Iterable[Path], *, root: Path | None = None) -> str:
    """A digest over many files, order-independent in content but name-bound."""

    root = root or repository_root()
    entries: list[str] = []
    for path in sorted(paths, key=lambda item: str(item)):
        try:
            name = str(path.relative_to(root)).replace("\\", "/")
        except ValueError:
            name = path.name
        entries.append(f"{name}:{digest_file(path)}")
    if not entries:
        raise FreezeError("nothing to digest")
    return digest_bytes("\n".join(entries).encode("utf-8"))


def package_sources() -> tuple[Path, ...]:
    return tuple(sorted(Path(__file__).parent.glob("*.py")))


def source_digest() -> str:
    """A digest over every module in this framework."""

    return digest_paths(package_sources())


def evaluator_digest() -> str:
    root = repository_root()
    return digest_paths((root / name for name in EVALUATOR_SOURCES), root=root)


def benchmark_digest() -> str:
    root = repository_root()
    return digest_paths((root / name for name in BENCHMARK_SOURCES), root=root)


def foreign_freeze_digests() -> dict[str, str]:
    root = repository_root()
    return {name: digest_file(root / name) for name in FOREIGN_FREEZES}


def compute() -> dict[str, object]:
    """The freeze body, without writing anything."""

    return {
        "phase": "R1",
        "artifact": "risk-coverage-expansion-framework",
        "source_hash": source_digest(),
        "benchmark_hash": benchmark_digest(),
        "evaluator_hash": evaluator_digest(),
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_files": [
            str(path.relative_to(repository_root())).replace("\\", "/")
            for path in package_sources()
        ],
        "evaluator_sources": list(EVALUATOR_SOURCES),
        "benchmark_sources": list(BENCHMARK_SOURCES),
        "foreign_freezes_untouched": foreign_freeze_digests(),
        "scope": (
            "this freeze covers the coverage framework only; it neither rewrites nor "
            "re-verifies the freezes owned by earlier phases"
        ),
        "invariants": {
            "modifies_evaluator": False,
            "modifies_benchmark": False,
            "modifies_taxonomy": False,
            "modifies_decision_policy": False,
            "imports_production": False,
            "uses_network": False,
        },
    }


def write(path: str | Path | None = None) -> dict[str, object]:
    """Write the freeze file. Called once, at the end of a run."""

    target = Path(path) if path is not None else FREEZE_PATH
    body = compute()
    target.write_text(
        json.dumps(body, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return body


def load(path: str | Path | None = None) -> dict[str, object]:
    target = Path(path) if path is not None else FREEZE_PATH
    if not target.is_file():
        raise FreezeError(f"no freeze recorded at {target}")
    return json.loads(target.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class GuardReport:
    """Whether the frozen artifacts still match what the freeze recorded."""

    ok: bool
    checked: tuple[str, ...]
    mismatches: tuple[tuple[str, str, str], ...]
    missing: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "checked": list(self.checked),
            "mismatches": [
                {"artifact": name, "recorded": recorded, "current": current}
                for name, recorded, current in self.mismatches
            ],
            "missing": list(self.missing),
            "note": "the framework is read-only with respect to every frozen artifact",
        }


def guard(freeze: Mapping[str, object] | None = None) -> GuardReport:
    """Recompute the digests and compare them with the recorded freeze.

    The evaluator and benchmark digests are compared. The source digest is reported
    but not enforced: the freeze is written by the run it describes, so a mismatch
    there means the framework was edited after freezing, which is a fact for the
    reviewer rather than a failure of the evaluator.
    """

    recorded = dict(freeze) if freeze is not None else load()
    checked: list[str] = []
    mismatches: list[tuple[str, str, str]] = []
    missing: list[str] = []

    root = repository_root()
    for name in EVALUATOR_SOURCES + BENCHMARK_SOURCES:
        path = root / name
        if not path.is_file():
            missing.append(name)
            continue
        checked.append(name)

    for label, current in (
        ("evaluator_hash", evaluator_digest()),
        ("benchmark_hash", benchmark_digest()),
    ):
        expected = str(recorded.get(label, ""))
        if expected and expected != current:
            mismatches.append((label, expected, current))

    for name, expected in (recorded.get("foreign_freezes_untouched") or {}).items():
        path = root / str(name)
        if not path.is_file():
            missing.append(str(name))
            continue
        checked.append(str(name))
        current = digest_file(path)
        if str(expected) != current:
            mismatches.append((str(name), str(expected), current))

    return GuardReport(
        ok=not mismatches and not missing,
        checked=tuple(checked),
        mismatches=tuple(mismatches),
        missing=tuple(missing),
    )


def verify() -> dict[str, object]:
    """`guard()` against the recorded freeze, as a JSON-ready body."""

    report = guard()
    return {
        "ok": report.ok,
        **report.as_dict(),
        "recorded_source_hash": str(load().get("source_hash", "")),
        "current_source_hash": source_digest(),
    }
