"""Agreement between the two annotators: Cohen's kappa, per field.

The phase requires two annotators and a kappa, and the protocol says what the number
is allowed to mean. This module computes it and nothing else: no pooling across
fields, no agreement-after-discussion presented as agreement, no band quoted without
the kappa beside it.

    kappa = (p_o - p_e) / (1 - p_e)

`p_o` is the observed agreement and `p_e` the agreement expected by chance from each
annotator's own marginals. Three properties are deliberate.

**One kappa per field.** `speaker`, `stance`, `intent`, `certainty` and `severity` are
categorical, so each gets one. `decision` is a set of up to five categories, so it
gets one *binary* kappa per category — present versus absent — plus an exact-set
agreement rate. A single pooled figure over all six would let two annotators agree
perfectly on `severity` (both said `none`) while disagreeing on `decision`, and
average that into a number about neither.

**Chance correction can go negative.** When `p_e` exceeds `p_o` the kappa is below
zero, which means worse than chance. That is reported as it falls; clamping it to 0
would turn a real finding into a neutral one.

**Degenerate marginals are refused, not guessed.** If every case in a field carries
the same value for both annotators then `p_e` is 1 and the kappa is undefined. That
is reported as `undefined` with the reason, not as 1.0.

The band is Landis and Koch's, and it is a convention rather than a result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .build import (
    LABEL_FIELDS,
    Annotation,
    BuildError,
    CATEGORIES,
)

AGREEMENT_PATH = Path(__file__).resolve().parent / "agreement_v3_2.json"

#: Landis and Koch. A convention, quoted beside every kappa and never instead of it.
#:
#: Expressed as upper bounds rather than as closed intervals, because the published
#: bands are written as `0.21-0.40` and `0.41-0.60` and a closed-interval table
#: therefore has a hole at every boundary: a kappa of 0.205 belongs to no band. With
#: bounds there is no hole, and 0.20 is `slight` and 0.21 is `fair`, which is what the
#: convention means.
BANDS: tuple[tuple[float, str], ...] = (
    (0.0, "worse than chance"),
    (0.21, "slight"),
    (0.41, "fair"),
    (0.61, "moderate"),
    (0.81, "substantial"),
)
ALMOST_PERFECT = "almost perfect"

UNDEFINED = "undefined"


def band_for(kappa: float) -> str:
    for bound, name in BANDS:
        if kappa < bound:
            return name
    return ALMOST_PERFECT


def cohen_kappa(left: Sequence[str], right: Sequence[str]) -> tuple[float | None, str]:
    """Cohen's kappa for two equally long categorical sequences.

    Returns `(None, reason)` when the statistic is undefined, rather than a number
    that looks like a result.
    """

    if len(left) != len(right):
        raise BuildError(
            f"kappa needs equal lengths, got {len(left)} and {len(right)}"
        )
    total = len(left)
    if total == 0:
        return None, "no cases"

    observed = sum(1 for a, b in zip(left, right) if a == b) / total
    values = sorted(set(left) | set(right))
    expected = 0.0
    for value in values:
        pa = sum(1 for item in left if item == value) / total
        pb = sum(1 for item in right if item == value) / total
        expected += pa * pb

    if expected >= 1.0:
        return None, "every case carries the same value, so chance agreement is 1"
    return round((observed - expected) / (1 - expected), 4), ""


@dataclass(frozen=True, slots=True)
class FieldAgreement:
    field: str
    cases: int
    observed: float
    expected: float
    kappa: float | None
    band: str
    note: str = ""

    @property
    def defined(self) -> bool:
        return self.kappa is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "cases": self.cases,
            "observed_agreement": self.observed,
            "expected_agreement": self.expected,
            "kappa": self.kappa,
            "band": self.band,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class Disagreement:
    case_id: str
    field: str
    annotator_a: str
    annotator_b: str
    reason_a: str = ""
    reason_b: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "field": self.field,
            "annotator_a": self.annotator_a,
            "annotator_b": self.annotator_b,
            "reason_a": self.reason_a,
            "reason_b": self.reason_b,
        }


@dataclass(frozen=True, slots=True)
class AgreementReport:
    cases: int
    fields: tuple[FieldAgreement, ...]
    categories: tuple[FieldAgreement, ...]
    exact_decision_agreement: float
    disagreements: tuple[Disagreement, ...]
    by_group: Mapping[str, Any]

    @property
    def field(self) -> Mapping[str, FieldAgreement]:
        return {item.field: item for item in self.fields}

    @property
    def category(self) -> Mapping[str, FieldAgreement]:
        return {item.field: item for item in self.categories}

    @property
    def defined_fields(self) -> tuple[FieldAgreement, ...]:
        return tuple(item for item in self.fields if item.defined)

    @property
    def lowest(self) -> FieldAgreement | None:
        defined = self.defined_fields
        if not defined:
            return None
        return min(defined, key=lambda item: item.kappa if item.kappa is not None else 0.0)

    @property
    def disagreement_rate(self) -> float:
        units = self.cases * (len(self.fields) + 1)
        return round(len(self.disagreements) / units, 4) if units else 0.0

    @property
    def affected_cases(self) -> tuple[str, ...]:
        return tuple(sorted({item.case_id for item in self.disagreements}))

    def for_case(self, case_id: str) -> tuple[Disagreement, ...]:
        return tuple(item for item in self.disagreements if item.case_id == case_id)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases": self.cases,
            "fields": [item.as_dict() for item in self.fields],
            "categories": [item.as_dict() for item in self.categories],
            "exact_decision_agreement": self.exact_decision_agreement,
            "disagreement_units": self.cases * (len(self.fields) + 1),
            "disagreements": len(self.disagreements),
            "disagreement_rate": self.disagreement_rate,
            "affected_cases": len(self.affected_cases),
            "by_group": {key: dict(value) for key, value in self.by_group.items()},
            "note": (
                "Cohen's kappa per field, on the raw labels, before any discussion. "
                "Computed between two machine annotators: it measures whether this "
                "protocol is unambiguous enough to be applied twice, not human "
                "agreement."
            ),
        }

    def render(self) -> str:
        lines = [f"cases : {self.cases}", "", "per field"]
        for item in self.fields:
            if item.defined:
                lines.append(
                    f"  {item.field:12} kappa {item.kappa:+.4f}  "
                    f"({item.band})  observed {item.observed:.4f}"
                )
            else:
                lines.append(f"  {item.field:12} {UNDEFINED}: {item.note}")
        lines.append("")
        lines.append("decision, per category")
        for item in self.categories:
            if item.defined:
                lines.append(
                    f"  {item.field:24} kappa {item.kappa:+.4f}  ({item.band})"
                )
            else:
                lines.append(f"  {item.field:24} {UNDEFINED}: {item.note}")
        lines.append("")
        lines.append(f"  exact decision-set agreement : {self.exact_decision_agreement:.4f}")
        lines.append(f"  disagreements                : {len(self.disagreements)}")
        lines.append(f"  cases with a disagreement    : {len(self.affected_cases)}")
        return "\n".join(lines)


def _field_agreement(field: str, left: Sequence[Annotation], right: Sequence[Annotation]) -> FieldAgreement:
    a = [item.field(field) for item in left]
    b = [item.field(field) for item in right]
    kappa, note = cohen_kappa(a, b)
    total = len(a)
    observed = round(sum(1 for x, y in zip(a, b) if x == y) / total, 4) if total else 0.0
    values = sorted(set(a) | set(b))
    expected = 0.0
    for value in values:
        pa = sum(1 for item in a if item == value) / total if total else 0.0
        pb = sum(1 for item in b if item == value) / total if total else 0.0
        expected += pa * pb
    return FieldAgreement(
        field=field,
        cases=total,
        observed=observed,
        expected=round(expected, 4),
        kappa=kappa,
        band=band_for(kappa) if kappa is not None else UNDEFINED,
        note=note,
    )


def _category_agreement(
    category: str, left: Sequence[Annotation], right: Sequence[Annotation]
) -> FieldAgreement:
    a = ["present" if category in item.decision else "absent" for item in left]
    b = ["present" if category in item.decision else "absent" for item in right]
    kappa, note = cohen_kappa(a, b)
    total = len(a)
    observed = round(sum(1 for x, y in zip(a, b) if x == y) / total, 4) if total else 0.0
    values = sorted(set(a) | set(b))
    expected = 0.0
    for value in values:
        pa = sum(1 for item in a if item == value) / total if total else 0.0
        pb = sum(1 for item in b if item == value) / total if total else 0.0
        expected += pa * pb
    return FieldAgreement(
        field=category,
        cases=total,
        observed=observed,
        expected=round(expected, 4),
        kappa=kappa,
        band=band_for(kappa) if kappa is not None else UNDEFINED,
        note=note,
    )


def measure(
    labels: Mapping[str, Sequence[Annotation]],
    *,
    groups: Mapping[str, str] | None = None,
    annotators: Sequence[str] = ("A", "B"),
) -> AgreementReport:
    """Cohen's kappa for every field, and the disagreements behind it."""

    if len(annotators) != 2:
        raise BuildError("agreement needs exactly two annotators")
    left_all = {item.case_id: item for item in labels[annotators[0]]}
    right_all = {item.case_id: item for item in labels[annotators[1]]}
    if set(left_all) != set(right_all):
        raise BuildError("the two annotators did not label the same cases")
    ids = sorted(left_all)
    left = [left_all[case_id] for case_id in ids]
    right = [right_all[case_id] for case_id in ids]

    fields = tuple(_field_agreement(name, left, right) for name in LABEL_FIELDS)
    categories = tuple(_category_agreement(name, left, right) for name in CATEGORIES)

    exact = round(
        sum(1 for a, b in zip(left, right) if set(a.decision) == set(b.decision)) / len(ids),
        4,
    )

    disagreements: list[Disagreement] = []
    for a, b in zip(left, right):
        for name in LABEL_FIELDS:
            if a.field(name) != b.field(name):
                disagreements.append(
                    Disagreement(
                        case_id=a.case_id,
                        field=name,
                        annotator_a=a.field(name),
                        annotator_b=b.field(name),
                    )
                )
        if set(a.decision) != set(b.decision):
            disagreements.append(
                Disagreement(
                    case_id=a.case_id,
                    field="decision",
                    annotator_a=",".join(sorted(a.decision)) or "(none)",
                    annotator_b=",".join(sorted(b.decision)) or "(none)",
                    reason_a=a.reason,
                    reason_b=b.reason,
                )
            )

    by_group: dict[str, Any] = {}
    if groups:
        for name in sorted(set(groups.values())):
            subset = [i for i in ids if groups.get(i) == name]
            index_left = {item.case_id: item for item in left}
            index_right = {item.case_id: item for item in right}
            sub_left = [index_left[i] for i in subset]
            sub_right = [index_right[i] for i in subset]
            entry: dict[str, Any] = {"cases": len(subset)}
            for field_name in ("speaker", "decision"):
                if field_name == "decision":
                    agree = sum(
                        1
                        for a, b in zip(sub_left, sub_right)
                        if set(a.decision) == set(b.decision)
                    )
                else:
                    agree = sum(
                        1
                        for a, b in zip(sub_left, sub_right)
                        if a.field(field_name) == b.field(field_name)
                    )
                entry[f"{field_name}_agreement"] = (
                    round(agree / len(subset), 4) if subset else 0.0
                )
            by_group[name] = entry

    return AgreementReport(
        cases=len(ids),
        fields=fields,
        categories=categories,
        exact_decision_agreement=exact,
        disagreements=tuple(disagreements),
        by_group=by_group,
    )


def write_report(
    path: str | Path | None = None, *, report: AgreementReport | None = None
) -> Path:
    target = Path(path) if path is not None else AGREEMENT_PATH
    if report is None:
        raise BuildError("write_report needs a measured report")
    payload = {
        **report.as_dict(),
        "raw": [item.as_dict() for item in report.disagreements],
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def describe() -> dict[str, Any]:
    return {
        "fields": list(LABEL_FIELDS),
        "categories": list(CATEGORIES),
        "bands": [
            {"upper_bound": bound, "band": name} for bound, name in BANDS
        ]
        + [{"upper_bound": None, "band": ALMOST_PERFECT}],
        "pooled_kappa_reported": False,
        "note": "one kappa per field and per category; never one pooled figure",
    }
