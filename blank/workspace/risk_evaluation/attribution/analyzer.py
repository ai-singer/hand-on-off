"""Attribution analyzer: text in, claims with a speaker and a stance out.

    text -> claim parser -> speaker inference -> stance detection -> result
                 |                  |                   |
                 +------------------+-------------------+
                                    |
                          evidence on every claim

Speaker inference lives here rather than in its own module because the phase's
directory structure names `claim_parser`, `stance_detector` and `analyzer`, and
speaker inference is what the analyzer does between the other two.

Two decisions worth stating, because they are where this layer differs from the
one it replaces:

**Speaker precedence is positional.** In `Analysts say X, and we agree` the
analysts are speaking; in `We believe analysts are wrong` the author is. The
marker that appears first marks the subject of the main clause, so it wins.
Ties go to `third_party`, on the grounds that a named outside party is a
stronger signal than the bare first person.

**An unmarked claim is the author's by default, and the evidence says so.** Most
financial prose contains no `we believe` at all. The taxonomy treats unmarked
text as the author's voice, so `is_authorial` does too - but the claim records
that the determination was a default rather than a finding, so a reader can tell
`no attribution is present` from `the author was identified`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .claim_parser import ClaimParser, ClaimSegment, claim_ids
from .evidence import EvidenceLog
from .model import (
    AUTHORISING_STANCES,
    Claim,
    AttributionError,
    AttributionResult,
    summarise,
)
from .stance_detector import (
    ENDORSED,
    QUOTED,
    REJECTED,
    UNCERTAIN,
    StanceDetector,
    StanceVerdict,
)


#: Speakers other than the author. Named parties and unnamed collectives are
#: both `third_party` here: the layer's question is "is the author speaking?",
#: and an anonymous insider is not the author.
THIRD_PARTY_MARKERS: tuple[str, ...] = (
    "analysts",
    "analyst",
    "experts",
    "expert",
    "researchers",
    "researcher",
    "economists",
    "economist",
    "according to",
    "reports say",
    "report says",
    "some investors",
    "investors say",
    "management",
    "the board",
    "regulators",
    "officials",
    "brokers",
    "bankers",
    "commentators",
    "the company said",
    "the company says",
    "the newsletter",
    "the broker note",
    "sources",
    "insiders",
    "a source",
    "people close to",
    "the report",
    "promoter",
    "a promoter",
    "spokesperson",
    "spokesman",
    "spokeswoman",
    "\u5206\u6790\u5e08",  # 分析师
    "\u4e13\u5bb6",  # 专家
    "\u7814\u7a76\u4eba\u5458",  # 研究人员
    "\u636e\u6089",  # 据悉
)

#: First-person and self-referential markers: the author speaking.
AUTHOR_MARKERS: tuple[str, ...] = (
    "i think",
    "i believe",
    "i argue",
    "we believe",
    "we think",
    "we argue",
    "we expect",
    "we disagree",
    "we agree",
    "we have argued",
    "we note",
    "our analysis",
    "our view",
    "in our view",
    "our research",
    "this article argues",
    "this article shows",
    "this piece argues",
    "\u6211\u4eec\u8ba4\u4e3a",  # 我们认为
    "\u672c\u6587\u8ba4\u4e3a",  # 本文认为
)

_ASCII_THIRD = tuple(item for item in THIRD_PARTY_MARKERS if item.isascii())
_ASCII_AUTHOR = tuple(item for item in AUTHOR_MARKERS if item.isascii())

_THIRD_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(item) for item in _ASCII_THIRD) + r")\b",
    re.IGNORECASE,
)
_AUTHOR_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(item) for item in _ASCII_AUTHOR) + r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SpeakerVerdict:
    speaker: str
    confidence: float
    evidence: EvidenceLog
    marker: str = ""

    @property
    def markers(self) -> tuple[str, ...]:
        return self.evidence.markers()

    @property
    def determined(self) -> bool:
        """True when markers decided this, rather than the default."""

        return bool(self.marker)

    def as_dict(self) -> dict[str, object]:
        return {
            "speaker": self.speaker,
            "confidence": self.confidence,
            "evidence": list(self.markers),
            "determined": self.determined,
        }


def _find(text: str, ascii_markers: Sequence[str], pattern: re.Pattern[str],
          all_markers: Sequence[str]) -> list[tuple[int, str]]:
    """(position, marker) for every marker present, ASCII and CJK alike."""

    found: list[tuple[int, str]] = []
    for match in pattern.finditer(text):
        found.append((match.start(), match.group(0).lower()))
    lowered = text.lower()
    for marker in all_markers:
        if marker.isascii():
            continue
        position = lowered.find(marker)
        if position >= 0:
            found.append((position, marker))
    del ascii_markers
    return sorted(found)


class SpeakerDetector:
    """Rule-based speaker inference over one claim segment."""

    name = "rule-based-speaker-detector"
    version = "1.0.0"

    def detect(self, segment: ClaimSegment) -> SpeakerVerdict:
        text = segment.text
        third = _find(text, _ASCII_THIRD, _THIRD_RE, THIRD_PARTY_MARKERS)
        author = _find(text, _ASCII_AUTHOR, _AUTHOR_RE, AUTHOR_MARKERS)

        # Positional precedence: the first marker names the subject. Ties go to
        # third_party, so the order of the two branches matters.
        if third and (not author or third[0][0] <= author[0][0]):
            markers = [marker for _position, marker in third]
            log = EvidenceLog()
            for marker in markers:
                log = log.add(marker, kind="speaker", rule="speaker.third-party")
            return SpeakerVerdict(
                "third_party", self._confidence(len(markers), base=0.75), log,
                marker=third[0][1],
            )

        if author:
            markers = [marker for _position, marker in author]
            log = EvidenceLog()
            for marker in markers:
                log = log.add(marker, kind="speaker", rule="speaker.author")
            return SpeakerVerdict(
                "author", self._confidence(len(markers), base=0.8), log,
                marker=author[0][1],
            )

        return SpeakerVerdict(
            "unknown",
            0.3,
            EvidenceLog().absence(
                kind="speaker",
                rule="speaker.no-marker",
                detail="no speaker marker in the claim",
            ),
        )

    def _confidence(self, hits: int, *, base: float) -> float:
        return round(min(0.95, base + 0.05 * (hits - 1)), 3)


class AttributionAnalyzer:
    """The Phase 8.2 pipeline."""

    name = "attribution-analyzer"
    version = "1.0.0"

    def __init__(
        self,
        *,
        parser: ClaimParser | None = None,
        speaker_detector: SpeakerDetector | None = None,
        stance_detector: StanceDetector | None = None,
    ) -> None:
        self._parser = parser if parser is not None else ClaimParser()
        self._speaker = (
            speaker_detector if speaker_detector is not None else SpeakerDetector()
        )
        self._stance = (
            stance_detector if stance_detector is not None else StanceDetector()
        )

    def analyze(self, text: str) -> AttributionResult:
        """Split `text` into claims and attribute each one."""

        if not isinstance(text, str):
            raise AttributionError(
                f"text must be a string, got {type(text).__name__}"
            )

        segments = self._parser.parse(text)
        if not segments:
            return AttributionResult(text=text, claims=(), summary=summarise(()))

        ids = claim_ids(len(segments))
        speakers = [self._speaker.detect(segment) for segment in segments]
        stances = [
            self._repair_author_quotation(speaker, self._stance.detect(
                segment, previous=segments[index - 1] if index else None
            ))
            for index, (segment, speaker) in enumerate(zip(segments, speakers))
        ]

        # A sentence opening with a contrastive marker turns on the claim before
        # it: "Analysts expect growth. However, we disagree." rejects the
        # analysts' claim, not the author's own.
        replaced = self._backward_rejections(segments, stances)

        claims: list[Claim] = []
        for index, segment in enumerate(segments):
            stance = replaced.get(index, stances[index])
            speaker = self._rejection_implies_author(speakers[index], stance)
            log = speaker.evidence.extend(stance.evidence.marks)
            if index in replaced:
                log = log.extend(stance.rejection_evidence.marks)
            confidence = round(min(speaker.confidence, stance.confidence), 3)
            claims.append(
                Claim(
                    claim_id=ids[index],
                    text=segment.text,
                    speaker=speaker.speaker,
                    stance=stance.stance,
                    confidence=confidence,
                    evidence=log.markers(),
                    spans=(segment.span,),
                    detail=log.marks,
                    rule=segment.boundary_rule,
                    index=index,
                )
            )

        built = tuple(claims)
        return AttributionResult(text=text, claims=built, summary=summarise(built))

    def analyze_claims(self, text: str) -> tuple[Claim, ...]:
        """Just the claims, for callers that do not need the summary."""

        return self.analyze(text).claims

    def _rejection_implies_author(
        self, speaker: SpeakerVerdict, verdict: StanceVerdict
    ) -> SpeakerVerdict:
        """Only the article's own voice can reject a claim inside the article.

        `But evidence shows otherwise.` carries no speaker marker, so it would
        be `unknown` - and `unknown` with `rejected` is marked *not authorial*,
        which would have a future evaluator treat the article's own
        counter-argument as somebody else's claim and suppress it. That is the
        Phase 8.1 failure mode reappearing in a new place.

        The rule is deliberately narrow: it applies only when no speaker marker
        was found. `Analysts dispute the rebound.` has a third-party marker, and
        there the rejection genuinely belongs to the analysts.
        """

        if verdict.stance != REJECTED or speaker.determined:
            return speaker
        log = EvidenceLog()
        for mark in verdict.evidence.marks:
            log = log.add(
                mark.marker,
                kind="speaker",
                rule="speaker.rejection-implies-author",
                span=mark.span,
                detail="a rejection is performed by the article's own voice",
            )
        if not log:
            log = log.absence(
                kind="speaker",
                rule="speaker.rejection-implies-author",
                detail="a rejection is performed by the article's own voice",
            )
        return SpeakerVerdict("author", 0.6, log, marker="rejection")

    def _repair_author_quotation(
        self, speaker: SpeakerVerdict, verdict: StanceVerdict
    ) -> StanceVerdict:
        """A reporting verb in the author's own voice is not a quotation.

        `We expect growth` contains a reporting verb, but the author is not
        quoting anybody: they are stating their own expectation. Left alone the
        stance detector would call it `quoted`, which would make the article's
        own view look like somebody else's - the exact mistake this phase
        exists to undo.
        """

        if speaker.speaker != "author" or verdict.stance != QUOTED:
            return self._endorse_author_default(speaker, verdict)
        log = EvidenceLog()
        for mark in verdict.evidence.marks:
            log = log.add(
                mark.marker,
                kind="stance",
                rule="stance.author-voice-repair",
                span=mark.span,
                detail="reporting verb in the author's own voice",
            )
        if not log:
            log = log.absence(
                kind="stance",
                rule="stance.author-voice-repair",
                detail="reporting verb in the author's own voice",
            )
        return StanceVerdict(
            stance=ENDORSED,
            confidence=round(min(0.85, verdict.confidence + 0.1), 3),
            evidence=log,
        )

    def _endorse_author_default(
        self, speaker: SpeakerVerdict, verdict: StanceVerdict
    ) -> StanceVerdict:
        """An author-voiced claim with no stance marker is put forward.

        `uncertain` means the author's attitude to somebody else's claim is not
        stated. It cannot mean the author's attitude to their own claim is not
        stated - putting a claim in your own voice is taking it up. Leaving this
        as `uncertain` would produce the odd pair `speaker=author, stance=
        uncertain`, and would hide the difference between an author asserting
        something and an author declining to say what they think about what
        somebody else asserted.
        """

        if speaker.speaker != "author" or verdict.stance != UNCERTAIN:
            return verdict
        log = EvidenceLog()
        for mark in speaker.evidence.marks:
            log = log.add(
                mark.marker,
                kind="stance",
                rule="stance.author-default-endorsed",
                span=mark.span,
                detail="author-voiced claim carries no hedge or rejection",
            )
        if not log:
            log = log.absence(
                kind="stance",
                rule="stance.author-default-endorsed",
                detail="author-voiced claim carries no hedge or rejection",
            )
        return StanceVerdict(stance=ENDORSED, confidence=0.6, evidence=log)

    def _backward_rejections(
        self,
        segments: Sequence[ClaimSegment],
        stances: Sequence[StanceVerdict],
    ) -> Mapping[int, StanceVerdict]:
        """Which earlier claims a later rejection applies to."""

        replaced: dict[int, StanceVerdict] = {}
        for index in range(1, len(segments)):
            verdict = stances[index]
            if not verdict.rejects_previous:
                continue
            previous = stances[index - 1]
            if previous.stance in (QUOTED, UNCERTAIN):
                # The evidence becomes the rejection itself. Keeping the
                # previous verdict's `no marker` absence mark here would report
                # that no stance was found for a claim now labelled rejected.
                replaced[index - 1] = StanceVerdict(
                    stance=REJECTED,
                    confidence=round(min(0.9, verdict.confidence), 3),
                    evidence=verdict.rejection_evidence,
                    rejects_previous=False,
                    rejection_evidence=verdict.rejection_evidence,
                )
        return replaced


#: The default analyzer, for callers that need no configuration.
DEFAULT_ANALYZER = AttributionAnalyzer()


def analyze(text: str) -> AttributionResult:
    """Module-level convenience for the standard pipeline."""

    return DEFAULT_ANALYZER.analyze(text)


def to_statement_source(claim: Claim) -> str:
    """Bridge a claim to taxonomy v2's `statement_source`.

    This is the interface a future risk evaluator would use: it maps the
    two-part determination onto the single field v2 already understands, without
    either module importing the other's internals.

        authorial claim            -> "author"
        reported or rejected claim -> "quoted"
        other third-party claim    -> "third_party"
        otherwise                  -> "unknown"
    """

    if not claim.is_attributed:
        return "author"
    if claim.stance in (QUOTED, REJECTED):
        return "quoted"
    if claim.speaker == "third_party":
        return "third_party"
    return "unknown"


def authorial_text(result: AttributionResult) -> str:
    """The part of a text the article is actually asserting.

    A future evaluator would run its category rules over this rather than over
    the whole paragraph, which is the structural fix Phase 8.1 pointed at.
    """

    return " ".join(claim.text for claim in result.authorial_claims)


@dataclass(frozen=True, slots=True)
class ClaimView:
    """A claim paired with what a risk evaluator would need from it."""

    claim: Claim
    statement_source: str
    detail: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim.claim_id,
            "text": self.claim.text,
            "speaker": self.claim.speaker,
            "stance": self.claim.stance,
            "statement_source": self.statement_source,
            "is_authorial": self.claim.is_authorial,
            "confidence": self.claim.confidence,
            "evidence": list(self.claim.evidence),
        }


def claim_views(result: AttributionResult) -> tuple[ClaimView, ...]:
    """Every claim with its v2-compatible `statement_source`."""

    return tuple(
        ClaimView(claim=claim, statement_source=to_statement_source(claim))
        for claim in result.claims
    )
