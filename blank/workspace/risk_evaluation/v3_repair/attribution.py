"""Attribution refinement: source typing and rejection cues over Phase 8.2.

Phase 8.2's `speaker`/`stance` answer is taken as given. This module changes it
only where the layer declined to answer, and it says why in every case:

    unknown + a typed source          -> third_party, and `quoted` when the source
                                         is reported through a reporting frame
    unknown/quoted + an author refusal -> author/rejected

Nothing here overrides a speaker the attribution layer did identify. A layer that
named the source has more information than a lexicon, and second-guessing it would
make the refinement unauditable rather than additive.

The two corrections are kept apart on purpose, because they fail differently. A
source finding that is wrong changes who is speaking; a rejection cue that is
wrong changes whether the article is arguing for or against a claim, and those
are the two errors that move a verdict in opposite directions.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rejection import AUTHOR as REJECTION_AUTHOR
from .rejection import RejectionFinding
from .rejection import detect as detect_rejection
from .sources import REPORTING_CUES, SourceFinding
from .sources import detect as detect_source

#: Categories the refinement can raise on its own. Only sourcing, because
#: sourcing is what it has evidence for.
UNVERIFIED = "unverified_information"


@dataclass(frozen=True, slots=True)
class Refinement:
    """What the refinement did to one claim's attribution."""

    speaker: str
    stance: str
    source: SourceFinding | None = None
    rejection: RejectionFinding | None = None
    sourcing_categories: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.evidence)

    @property
    def speaker_changed(self) -> bool:
        return any(item.startswith("rule:refine.speaker") for item in self.evidence)

    @property
    def stance_changed(self) -> bool:
        return any(item.startswith("rule:refine.stance") for item in self.evidence)

    def as_dict(self) -> dict[str, object]:
        return {
            "speaker": self.speaker,
            "stance": self.stance,
            "changed": self.changed,
            "source": self.source.as_dict() if self.source else None,
            "rejection": self.rejection.as_dict() if self.rejection else None,
            "sourcing_categories": list(self.sourcing_categories),
            "evidence": list(self.evidence),
        }


def refine(
    claim_text: str,
    *,
    speaker: str,
    stance: str,
) -> Refinement:
    """Refine one claim's speaker and stance, with evidence for each change."""

    if not isinstance(claim_text, str):
        raise TypeError(f"claim_text must be a string, got {type(claim_text).__name__}")

    rejection = detect_rejection(claim_text)
    if rejection is not None and rejection.is_authorial and speaker != "author":
        # A rejection is the article's own act, so it settles both axes: the
        # article is speaking, and what it is doing is arguing against.
        return Refinement(
            speaker="author",
            stance="rejected",
            rejection=rejection,
            evidence=(
                f"rule:refine.speaker:{speaker}->author",
                f"rule:refine.stance:{stance}->rejected",
                rejection.marker,
            ),
        )

    source = detect_source(claim_text)
    if source is None:
        return Refinement(speaker=speaker, stance=stance)

    new_speaker = speaker
    new_stance = stance
    evidence: list[str] = [source.marker]

    if speaker == "unknown":
        new_speaker = "third_party"
        evidence.append(f"rule:refine.speaker:{speaker}->third_party")

    if stance == "uncertain" and source.cue in REPORTING_CUES:
        new_stance = "quoted"
        evidence.append(f"rule:refine.stance:{stance}->quoted")

    sourcing: tuple[str, ...] = ()
    if source.uncheckable:
        sourcing = (UNVERIFIED,)
        evidence.append(f"rule:refine.sourcing:{UNVERIFIED}:{source.source_type}")
    else:
        evidence.append(f"rule:refine.sourcing:checkable:{source.source_type}")

    return Refinement(
        speaker=new_speaker,
        stance=new_stance,
        source=source,
        sourcing_categories=sourcing,
        evidence=tuple(evidence),
    )


def describe() -> dict[str, object]:
    """What the refinement can change, for the report and the tests."""

    return {
        "speaker_rule": "unknown -> third_party, only with a typed source",
        "stance_rule": "uncertain -> quoted, only when a reporting frame carries the source",
        "rejection_rule": "author refusal -> author/rejected",
        "overrides_identified_speaker": False,
        "sourcing_categories": [UNVERIFIED],
        "rejection_voices": [REJECTION_AUTHOR, "reported"],
    }
