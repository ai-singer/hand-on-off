"""Evidence: every determination must be traceable to something in the text.

The Phase 8.2 rule is that a judgement without evidence is not allowed. That is
enforced in two places: `EvidenceLog` refuses to be empty when a claim is built,
and `Claim.__post_init__` raises if `evidence` is empty.

There are two shapes on purpose.

`EvidenceMark` is the structured form: which marker matched, what kind of
judgement it supported, which rule fired, and where in the text it sits. This is
what makes a determination auditable rather than assertable.

`render()` produces the flat string form the Phase 8.2 data model specifies,
e.g. `["Analysts", "expect"]`. Negative determinations carry a `rule:` tag
instead of a marker, because "no speaker marker was found" is itself a finding
that has to be recorded: otherwise the fallback cases would be the only ones
with no evidence, which is exactly backwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


#: What a mark supports.
SPEAKER = "speaker"
STANCE = "stance"
SPLIT = "split"
KINDS = (SPEAKER, STANCE, SPLIT)

#: Prefix for a determination made by the absence of a marker.
RULE_PREFIX = "rule:"


@dataclass(frozen=True, slots=True)
class EvidenceMark:
    """One traceable reason for a determination."""

    marker: str
    kind: str
    rule: str
    span: tuple[int, int] | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.marker.strip():
            raise ValueError("an evidence mark must name the marker it saw")
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, got {self.kind!r}")
        if not self.rule.strip():
            raise ValueError("an evidence mark must name the rule that fired")

    @property
    def is_absence(self) -> bool:
        """True when the evidence is that nothing was found."""

        return self.marker.startswith(RULE_PREFIX)

    def render(self) -> str:
        """The flat form used in `Claim.evidence`."""

        return self.marker

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "marker": self.marker,
            "kind": self.kind,
            "rule": self.rule,
        }
        if self.span is not None:
            payload["span"] = list(self.span)
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass(frozen=True, slots=True)
class EvidenceLog:
    """An ordered, de-duplicated collection of marks for one determination."""

    marks: tuple[EvidenceMark, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "marks", tuple(self.marks))

    def add(
        self,
        marker: str,
        *,
        kind: str,
        rule: str,
        span: tuple[int, int] | None = None,
        detail: str = "",
    ) -> "EvidenceLog":
        """A new log with one more mark. Logs are immutable."""

        return EvidenceLog(
            (*self.marks, EvidenceMark(marker, kind, rule, span, detail))
        )

    def extend(self, marks: Iterable[EvidenceMark]) -> "EvidenceLog":
        return EvidenceLog((*self.marks, *marks))

    def absence(self, *, kind: str, rule: str, detail: str = "") -> "EvidenceLog":
        """Record that a rule fired because nothing matched."""

        return self.add(f"{RULE_PREFIX}{rule}", kind=kind, rule=rule, detail=detail)

    def for_kind(self, kind: str) -> tuple[EvidenceMark, ...]:
        return tuple(mark for mark in self.marks if mark.kind == kind)

    def markers(self) -> tuple[str, ...]:
        """Flat strings, de-duplicated, in first-seen order."""

        seen: dict[str, None] = {}
        for mark in self.marks:
            seen.setdefault(mark.render(), None)
        return tuple(seen)

    def rules(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for mark in self.marks:
            seen.setdefault(mark.rule, None)
        return tuple(seen)

    def __len__(self) -> int:
        return len(self.marks)

    def __bool__(self) -> bool:
        return bool(self.marks)

    def as_dicts(self) -> tuple[dict[str, object], ...]:
        return tuple(mark.as_dict() for mark in self.marks)


def empty_log() -> EvidenceLog:
    return EvidenceLog()


def marks_for(markers: Sequence[str], *, kind: str, rule: str) -> EvidenceLog:
    """Build a log from plain marker strings. Convenience for callers."""

    log = EvidenceLog()
    for marker in markers:
        log = log.add(marker, kind=kind, rule=rule)
    return log
