"""The attribution data model: who said it, and what the author does with it.

Phase 7.5's `statement_source` collapsed two different questions into one field.
Saying *"Analysts expect the stock to rise"* and *"Analysts expect the stock to
rise, and we agree"* produced the same value, even though the second is the
article's own view and the first is not. Phase 8.1 then showed the consequence:
an unrelated attribution anywhere in a passage withdrew every author-voice
category in it.

This model separates the questions:

    speaker   who is speaking      author | third_party | unknown
    stance    what the author does  endorsed | quoted | rejected | uncertain
              with what was said

A claim is only the article's own when `speaker == author`, or when the author
has taken it up (`stance == endorsed`). A claim the author reports
(`quoted`) or argues against (`rejected`) is not the article's claim, however
risky its wording.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .evidence import EvidenceLog, EvidenceMark


#: Who is speaking. Deliberately three values: "quoted" is a *stance*, not a
#: speaker, which is the conflation this phase exists to undo.
SPEAKERS = ("author", "third_party", "unknown")

#: What the author does with the claim.
STANCES = ("endorsed", "quoted", "rejected", "uncertain")

#: Stances in which the article is putting the claim forward as its own.
AUTHORISING_STANCES = ("endorsed",)

#: Stances in which the claim is attributed away from the article.
DISTANCING_STANCES = ("quoted", "rejected")


class AttributionError(Exception):
    """Raised when a claim cannot be built."""


@dataclass(frozen=True, slots=True)
class Claim:
    """One assertion in a text, with who made it and what the author does."""

    claim_id: str
    text: str
    speaker: str
    stance: str
    confidence: float
    evidence: tuple[str, ...]
    spans: tuple[tuple[int, int], ...] = ()
    detail: tuple[EvidenceMark, ...] = ()
    rule: str = ""
    index: int = 0

    def __post_init__(self) -> None:
        if not self.claim_id.strip():
            raise AttributionError("a claim must have an id")
        if not self.text.strip():
            raise AttributionError(f"{self.claim_id}: text must not be empty")
        if self.speaker not in SPEAKERS:
            raise AttributionError(
                f"{self.claim_id}: speaker must be one of {SPEAKERS}, "
                f"got {self.speaker!r}"
            )
        if self.stance not in STANCES:
            raise AttributionError(
                f"{self.claim_id}: stance must be one of {STANCES}, "
                f"got {self.stance!r}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise AttributionError(
                f"{self.claim_id}: confidence must be within 0..1, "
                f"got {self.confidence}"
            )
        # The Phase 8.2 rule, enforced structurally: no determination without
        # evidence, including a determination made by finding nothing.
        if not self.evidence:
            raise AttributionError(
                f"{self.claim_id}: every claim must carry evidence for its "
                f"speaker and stance"
            )
        object.__setattr__(self, "evidence", tuple(str(item) for item in self.evidence))
        object.__setattr__(self, "spans", tuple(self.spans))
        object.__setattr__(self, "detail", tuple(self.detail))

    @property
    def id(self) -> str:
        """Alias matching the documented record field name."""

        return self.claim_id

    @property
    def is_default_voice(self) -> bool:
        """True when nothing was attributed and nothing was asserted either.

        Most financial prose carries no `we believe` and no `analysts say`. The
        taxonomy treats unmarked text as the author's voice, so this layer does
        too - but a reader has to be able to tell "no attribution is present"
        from "the author was identified", which is what this flag is for.
        """

        return self.speaker == "unknown" and self.stance == "uncertain"

    @property
    def is_authorial(self) -> bool:
        """Is this claim the article's own?

        True when the author is speaking, when the author has taken up a third
        party's claim by endorsing it, or when the text carries no attribution
        at all and the default voice therefore applies.
        """

        return (
            self.speaker == "author"
            or self.stance in AUTHORISING_STANCES
            or self.is_default_voice
        )

    @property
    def is_attributed(self) -> bool:
        """Is this claim presented as somebody else's?"""

        return not self.is_authorial

    @property
    def is_rejected(self) -> bool:
        return self.stance == "rejected"

    def rules(self) -> tuple[str, ...]:
        """The rules that produced this claim, in order, de-duplicated."""

        seen: dict[str, None] = {}
        for mark in self.detail:
            seen.setdefault(mark.rule, None)
        if self.rule:
            seen.setdefault(self.rule, None)
        return tuple(seen)

    def as_dict(self) -> dict[str, Any]:
        """The documented shape first, then what makes it auditable."""

        return {
            "id": self.claim_id,
            "text": self.text,
            "speaker": self.speaker,
            "stance": self.stance,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "index": self.index,
            "is_authorial": self.is_authorial,
            "spans": [list(span) for span in self.spans],
            "rules": list(self.rules()),
            "detail": [mark.as_dict() for mark in self.detail],
        }

    def render(self) -> str:
        return (
            f"{self.claim_id} speaker={self.speaker} stance={self.stance} "
            f"confidence={self.confidence:.2f} evidence={list(self.evidence)}"
        )


@dataclass(frozen=True, slots=True)
class AttributionResult:
    """Everything the attribution layer determined about one text."""

    text: str
    claims: tuple[Claim, ...]
    summary: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "claims", tuple(self.claims))
        object.__setattr__(self, "summary", dict(self.summary))

    @property
    def authorial_claims(self) -> tuple[Claim, ...]:
        """Claims the article is putting forward as its own."""

        return tuple(claim for claim in self.claims if claim.is_authorial)

    @property
    def attributed_claims(self) -> tuple[Claim, ...]:
        """Claims presented as somebody else's."""

        return tuple(claim for claim in self.claims if claim.is_attributed)

    @property
    def rejected_claims(self) -> tuple[Claim, ...]:
        return tuple(claim for claim in self.claims if claim.is_rejected)

    def claim(self, claim_id: str) -> Claim:
        for item in self.claims:
            if item.claim_id == claim_id:
                return item
        raise AttributionError(f"no claim {claim_id!r} in this result")

    def as_dict(self) -> dict[str, Any]:
        return {
            "claims": [claim.as_dict() for claim in self.claims],
            "summary": dict(sorted(self.summary.items())),
        }

    def render(self) -> str:
        lines = [f"claims: {len(self.claims)}"]
        for claim in self.claims:
            lines.append(f"  {claim.render()}")
            lines.append(f"      {claim.text}")
        lines.append(f"summary: {dict(sorted(self.summary.items()))}")
        return "\n".join(lines)


def summarise(claims: Sequence[Claim]) -> dict[str, Any]:
    """The `summary` block: counts and the claim ids each conclusion covers."""

    speakers: dict[str, int] = {name: 0 for name in SPEAKERS}
    stances: dict[str, int] = {name: 0 for name in STANCES}
    for claim in claims:
        speakers[claim.speaker] += 1
        stances[claim.stance] += 1

    authorial = [claim.claim_id for claim in claims if claim.is_authorial]
    attributed = [claim.claim_id for claim in claims if claim.is_attributed]
    rejected = [claim.claim_id for claim in claims if claim.is_rejected]

    return {
        "claim_count": len(claims),
        "speakers": speakers,
        "stances": stances,
        "authorial_claims": authorial,
        "attributed_claims": attributed,
        "rejected_claims": rejected,
        "has_attribution": bool(attributed),
        "has_rejection": bool(rejected),
        "mixed": bool(authorial) and bool(attributed),
    }


def log_to_claim_evidence(log: EvidenceLog) -> tuple[str, ...]:
    """Flat evidence strings for a claim, de-duplicated."""

    return log.markers()
