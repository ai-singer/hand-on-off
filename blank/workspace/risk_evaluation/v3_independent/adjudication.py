"""Adjudication of the disagreements, by a third agent.

155 field disagreements across 95 of the 300 cases went to an adjudicator that is not
either annotator and not the evaluator's author. It receives the text, both labels
with both reasons, and the guide, and rules on each disputed field with a guide
citation.

Three things this module refuses to do.

**It does not resolve anything by default.** A field with no ruling is `unresolved`,
and the case is excluded from the primary metrics while remaining in the dataset.
Substituting annotator A's value would produce a benchmark whose labels are one
annotator's wherever the other disagreed, and the disagreement rate would vanish from
the score without vanishing from the data.

**It does not adjudicate the fields that agree.** Only disputed fields are touched, so
the adjudicated label is A's and B's own agreement everywhere else.

**It does not hide the raw labels.** `labels_a.json`, `labels_b.json`,
`disagreements.json` and this module's rulings are all published. A reader who
distrusts a ruling can recompute the whole benchmark from the raw pair.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .agreement import Disagreement
from .build import (
    ALLOWED,
    ANNOTATION_DIR,
    CATEGORIES,
    LABEL_FIELDS,
    Annotation,
    BuildError,
)

ADJUDICATION_DIR = ANNOTATION_DIR / "adjudication"
ADJUDICATION_BATCH = 25

RESOLVED_A = "annotator_a"
RESOLVED_B = "annotator_b"
RESOLVED_THIRD = "third_reading"
UNRESOLVED = "unresolved"
RESOLUTIONS: tuple[str, ...] = (RESOLVED_A, RESOLVED_B, RESOLVED_THIRD, UNRESOLVED)


@dataclass(frozen=True, slots=True)
class Ruling:
    """One adjudicated field."""

    case_id: str
    field: str
    first: str
    second: str
    ruling: str
    basis: str
    resolution: str

    def __post_init__(self) -> None:
        if self.resolution not in RESOLUTIONS:
            raise BuildError(f"unknown resolution {self.resolution!r}")
        if self.field == "decision":
            for name in self.ruling.split(","):
                text = name.strip()
                if text and text not in CATEGORIES:
                    raise BuildError(f"{self.case_id}: unknown category {text!r}")
        elif self.field in ALLOWED:
            if self.resolution != UNRESOLVED and self.ruling not in ALLOWED[self.field]:
                raise BuildError(
                    f"{self.case_id}/{self.field}: ruling {self.ruling!r} is not one "
                    f"of {ALLOWED[self.field]}"
                )
        else:
            raise BuildError(f"{self.case_id}: unknown field {self.field!r}")

    @property
    def resolved(self) -> bool:
        return self.resolution != UNRESOLVED

    @property
    def categories(self) -> tuple[str, ...]:
        if self.field != "decision":
            return ()
        return tuple(
            sorted({part.strip() for part in self.ruling.split(",") if part.strip()})
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "field": self.field,
            "annotator_a": self.first,
            "annotator_b": self.second,
            "ruling": self.ruling,
            "basis": self.basis,
            "resolution": self.resolution,
        }


def write_adjudication_batches(
    disagreements: Sequence[Disagreement],
    cases: Mapping[str, str],
    *,
    root: str | Path | None = None,
    size: int = ADJUDICATION_BATCH,
) -> tuple[Path, ...]:
    """One file per adjudicator session, grouped by case."""

    target_dir = Path(root) if root is not None else ADJUDICATION_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    by_case: dict[str, list[Disagreement]] = {}
    for item in disagreements:
        by_case.setdefault(item.case_id, []).append(item)

    payload = [
        {
            "id": case_id,
            "text": cases[case_id],
            "disputes": [
                {
                    "field": item.field,
                    "annotator_a": item.annotator_a,
                    "annotator_b": item.annotator_b,
                    "reason_a": item.reason_a,
                    "reason_b": item.reason_b,
                }
                for item in items
            ],
        }
        for case_id, items in sorted(by_case.items())
    ]

    written: list[Path] = []
    index = 0
    for start in range(0, len(payload), size):
        chunk = payload[start : start + size]
        index += 1
        path = target_dir / f"cases_{index:02d}.json"
        path.write_text(
            json.dumps(chunk, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        written.append(path)
    return tuple(written)


def adjudication_target(index: int, *, root: str | Path | None = None) -> Path:
    target_dir = Path(root) if root is not None else ADJUDICATION_DIR
    return target_dir / f"rulings_{index:02d}.json"


def adjudication_sessions(*, root: str | Path | None = None) -> tuple[Path, ...]:
    target_dir = Path(root) if root is not None else ADJUDICATION_DIR
    return tuple(sorted(target_dir.glob("cases_*.json")))


def assemble_rulings(
    *, root: str | Path | None = None
) -> tuple[Ruling, ...]:
    target_dir = Path(root) if root is not None else ADJUDICATION_DIR
    files = sorted(target_dir.glob("rulings_*.json"))
    if not files:
        raise BuildError(f"no rulings_*.json under {target_dir}")
    found: dict[tuple[str, str], Ruling] = {}
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise BuildError(f"{path.name}: no items array")
        for item in items:
            case_id = str(item.get("id") or item.get("case_id") or "")
            field = str(item.get("field", "")).strip()
            if not case_id or not field:
                raise BuildError(f"{path.name}: a ruling is missing id or field")
            resolution = str(item.get("resolution", "")).strip()
            if resolution not in RESOLUTIONS:
                raise BuildError(
                    f"{path.name}: {case_id}/{field} resolution {resolution!r} is not "
                    f"one of {RESOLUTIONS}"
                )
            ruling = str(item.get("ruling", "")).strip()
            # An empty ruling is meaningful for `decision` - it means the guide
            # leaves no category - and meaningless for every other field, where it
            # would be a ruling that rules nothing. The `basis` requirement below
            # is what stops an empty `decision` from being a field nobody filled in.
            if resolution != UNRESOLVED and not ruling and field != "decision":
                raise BuildError(f"{path.name}: {case_id}/{field} resolved with no ruling")
            basis = str(item.get("basis", "")).strip()
            if resolution != UNRESOLVED and not basis:
                raise BuildError(
                    f"{path.name}: {case_id}/{field} ruled without citing the guide"
                )
            key = (case_id, field)
            if key in found:
                raise BuildError(f"{path.name}: {case_id}/{field} ruled twice")
            found[key] = Ruling(
                case_id=case_id,
                field=field,
                first=str(item.get("annotator_a", "")),
                second=str(item.get("annotator_b", "")),
                ruling=ruling,
                basis=basis,
                resolution=resolution,
            )
    return tuple(found[key] for key in sorted(found))


@dataclass(frozen=True, slots=True)
class AdjudicatedCase:
    """The label the benchmark carries, and how it was reached."""

    case_id: str
    annotation: Annotation
    disputed_fields: tuple[str, ...]
    unresolved_fields: tuple[str, ...]
    rulings: tuple[Ruling, ...]

    @property
    def resolved(self) -> bool:
        return not self.unresolved_fields

    @property
    def decision(self) -> tuple[str, ...]:
        return self.annotation.decision

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "annotation": self.annotation.as_dict(),
            "disputed_fields": list(self.disputed_fields),
            "unresolved_fields": list(self.unresolved_fields),
            "resolved": self.resolved,
            "rulings": [item.as_dict() for item in self.rulings],
        }


def adjudicate(
    labels: Mapping[str, Sequence[Annotation]],
    rulings: Sequence[Ruling],
    *,
    annotators: Sequence[str] = ("A", "B"),
) -> tuple[AdjudicatedCase, ...]:
    """Apply the rulings to the raw labels."""

    left = {item.case_id: item for item in labels[annotators[0]]}
    right = {item.case_id: item for item in labels[annotators[1]]}
    by_case: dict[str, list[Ruling]] = {}
    for item in rulings:
        by_case.setdefault(item.case_id, []).append(item)

    out: list[AdjudicatedCase] = []
    for case_id in sorted(left):
        a, b = left[case_id], right[case_id]
        items = by_case.get(case_id, [])
        values: dict[str, Any] = {
            name: getattr(a, name) for name in LABEL_FIELDS
        }
        values["decision"] = tuple(a.decision)
        unresolved: list[str] = []
        for item in items:
            if not item.resolved:
                unresolved.append(item.field)
                continue
            if item.field == "decision":
                values["decision"] = item.categories
            else:
                values[item.field] = item.ruling
        annotation = Annotation(
            case_id=case_id,
            claim=a.claim if a.claim != "none" else b.claim,
            speaker=values["speaker"],
            stance=values["stance"],
            intent=values["intent"],
            certainty=values["certainty"],
            severity=values["severity"],
            decision=tuple(values["decision"]),
            reason=(
                f"adjudicated ({len(items)} disputed fields)" if items else a.reason
            ),
            annotator="adjudicated" if items else a.annotator,
        )
        out.append(
            AdjudicatedCase(
                case_id=case_id,
                annotation=annotation,
                disputed_fields=tuple(sorted({item.field for item in items})),
                unresolved_fields=tuple(sorted(set(unresolved))),
                rulings=tuple(items),
            )
        )
    return tuple(out)


def write_rulings(
    path: str | Path | None = None, *, rulings: Sequence[Ruling] | None = None
) -> Path:
    target = Path(path) if path is not None else ADJUDICATION_DIR / "adjudication.json"
    if rulings is None:
        raise BuildError("write_rulings needs rulings")
    payload = {
        "rulings": [item.as_dict() for item in rulings],
        "counts": {
            "total": len(rulings),
            "resolved": sum(1 for item in rulings if item.resolved),
            "unresolved": sum(1 for item in rulings if not item.resolved),
        },
        "note": (
            "A third agent ruled on each disputed field, citing the guide. A field "
            "with no ruling is unresolved and its case is excluded from the primary "
            "metrics, not silently given an annotator's value."
        ),
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def write_adjudicated(
    path: str | Path | None = None, *, cases: Sequence[AdjudicatedCase] | None = None
) -> Path:
    target = Path(path) if path is not None else ADJUDICATION_DIR / "adjudicated.json"
    if cases is None:
        raise BuildError("write_adjudicated needs cases")
    payload = {
        "cases": [item.as_dict() for item in cases],
        "counts": {
            "total": len(cases),
            "resolved": sum(1 for item in cases if item.resolved),
            "unresolved": sum(1 for item in cases if not item.resolved),
            "disputed": sum(1 for item in cases if item.disputed_fields),
        },
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def describe() -> dict[str, Any]:
    return {
        "batch_size": ADJUDICATION_BATCH,
        "resolutions": list(RESOLUTIONS),
        "adjudicator": "a third machine agent, neither annotator",
        "unresolved_policy": "kept in the dataset, excluded from the primary metrics",
    }
