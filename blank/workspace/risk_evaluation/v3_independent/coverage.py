"""Phase 8.9 coverage matrix: what the dataset actually contains.

The phase asks for language, sentence form and source type, with news, analyst
reports, forum posts and educational articles named as examples. This module reports
the frame dimension against three outcomes, so a reader can see not only what was
collected but where the evaluator's behaviour differs across it.

    language       en, zh
    form           the eight syntactic shapes
    source_type    the eight registers
    topic          the ten subject areas
    boundary_kind  the fifteen boundary shapes

Each cell carries the case count, how many the evaluator got exactly right, and the
false positives and false negatives, because a coverage table that reported only
counts would say nothing about the thing it is there to show.

The matrix is built from the record's own `frame` block, which travelled with the
case from the sampling frame. A dimension inferred from the text would measure the
inference rather than the frame.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .evaluation import (
    FALSE_NEGATIVE,
    FALSE_POSITIVE,
    TRUE_NEGATIVE,
    TRUE_POSITIVE,
    CaseResult,
    predict,
)

COVERAGE_PATH = Path(__file__).resolve().parent / "coverage_matrix_v3_2.json"

#: The dimensions reported, and the attribute of `CaseResult` each reads.
DIMENSIONS: tuple[tuple[str, str], ...] = (
    ("language", "language"),
    ("form", "form"),
    ("source_type", "source_type"),
    ("topic", "topic"),
    ("group", "group"),
    ("boundary_kind", "boundary_kind"),
    ("intended_intent", "intended_intent"),
)


class CoverageError(Exception):
    """Raised when the matrix cannot be built."""


@dataclass(frozen=True, slots=True)
class Cell:
    dimension: str
    value: str
    cases: int
    correct: int
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def accuracy(self) -> float:
        return round(self.correct / self.cases, 4) if self.cases else 0.0

    @property
    def recall(self) -> float:
        total = self.tp + self.fn
        return round(self.tp / total, 4) if total else 0.0

    @property
    def precision(self) -> float:
        total = self.tp + self.fp
        return round(self.tp / total, 4) if total else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "value": self.value,
            "cases": self.cases,
            "correct": self.correct,
            "accuracy": self.accuracy,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "recall": self.recall,
            "precision": self.precision,
        }


@dataclass(frozen=True, slots=True)
class CoverageMatrix:
    results: tuple[CaseResult, ...]
    cells: tuple[Cell, ...]

    def for_dimension(self, dimension: str) -> tuple[Cell, ...]:
        return tuple(item for item in self.cells if item.dimension == dimension)

    @property
    def dimensions(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(item.dimension for item in self.cells)
        )

    @property
    def empty_cells(self) -> tuple[str, ...]:
        """Dimension values the frame declares but the data does not contain."""

        return tuple(
            f"{item.dimension}={item.value}"
            for item in self.cells
            if item.cases == 0
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases": len(self.results),
            "resolved": sum(1 for item in self.results if item.resolved),
            "dimensions": {
                dimension: [item.as_dict() for item in self.for_dimension(dimension)]
                for dimension in self.dimensions
            },
            "note": (
                "Built from each record's own frame block, so a dimension is the one "
                "the dataset author was given rather than one inferred from the text."
            ),
        }

    def render(self) -> str:
        lines: list[str] = []
        for dimension in self.dimensions:
            lines.append(dimension)
            for item in self.for_dimension(dimension):
                lines.append(
                    f"  {item.value:24} n {item.cases:3}  correct {item.correct:3} "
                    f"({item.accuracy:.3f})  tp {item.tp:3} fp {item.fp:2} fn {item.fn:3}"
                )
            lines.append("")
        return "\n".join(lines).rstrip()


def build(results: Sequence[CaseResult] | None = None) -> CoverageMatrix:
    active = tuple(results) if results is not None else predict()
    cells: list[Cell] = []
    for dimension, attribute in DIMENSIONS:
        buckets: dict[str, list[CaseResult]] = {}
        for item in active:
            value = str(getattr(item, attribute, "") or "(none)")
            buckets.setdefault(value, []).append(item)
        for value in sorted(buckets):
            items = buckets[value]
            cells.append(
                Cell(
                    dimension=dimension,
                    value=value,
                    cases=len(items),
                    correct=sum(1 for item in items if item.correct),
                    tp=sum(1 for item in items if item.outcome == TRUE_POSITIVE),
                    fp=sum(1 for item in items if item.outcome == FALSE_POSITIVE),
                    fn=sum(1 for item in items if item.outcome == FALSE_NEGATIVE),
                    tn=sum(1 for item in items if item.outcome == TRUE_NEGATIVE),
                )
            )
    return CoverageMatrix(results=active, cells=tuple(cells))


def write_matrix(
    path: str | Path | None = None, *, matrix: CoverageMatrix | None = None
) -> Path:
    target = Path(path) if path is not None else COVERAGE_PATH
    active = matrix if matrix is not None else build()
    target.write_text(
        json.dumps(active.as_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def describe() -> dict[str, Any]:
    return {
        "dimensions": [name for name, _ in DIMENSIONS],
        "source": "each record's own frame block",
    }


def main() -> int:
    import sys

    matrix = build()
    print(matrix.render())
    if "--write" in sys.argv:
        print()
        print(f"wrote {write_matrix(matrix=matrix)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
