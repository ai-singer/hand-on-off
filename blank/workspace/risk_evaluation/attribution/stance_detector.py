"""Stance detection: what does the author *do* with the claim?

Quoting a claim and endorsing it are different acts, and the difference decides
whether the article is making the claim or merely carrying it. Phase 7.5 had one
field for both, which is how an unrelated attribution came to withdraw an
author's own guarantee in Phase 8.1.

Four stances:

    quoted      the author reports it and stands apart from it
    endorsed    the author takes it up as their own
    rejected    the author argues against it
    uncertain   the author neither clearly reports nor clearly takes it up

Precedence is `rejected > endorsed > quoted > uncertain`, because a text that
argues against a claim is not making it even when it also reports it.

Stance is not always local. A sentence opening with `However` turns on the
*previous* claim: in `Analysts expect growth. However, we disagree.` the
rejection belongs to the analysts' claim, not to the author's disagreement. The
detector therefore exposes both an intrinsic verdict for a segment and the
rejection it projects backwards, and the analyzer applies both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from .claim_parser import ClaimSegment
from .evidence import EvidenceLog, EvidenceMark


QUOTED = "quoted"
ENDORSED = "endorsed"
REJECTED = "rejected"
UNCERTAIN = "uncertain"

#: Applied in this order; the first that matches wins.
STANCE_PRECEDENCE = (REJECTED, ENDORSED, QUOTED, UNCERTAIN)


#: Reporting frames: the author is carrying somebody else's words.
QUOTATION_MARKERS: tuple[str, ...] = (
    "said",
    "says",
    "say",
    "stated",
    "states",
    "according to",
    "reports say",
    "reportedly",
    "claims",
    "claimed",
    "told",
    "noted",
    "wrote",
    "writes",
    "argues that",
    "suggests",
    "suggested",
    "pointed out",
    "quoted",
    "quoting",
    "quotes",
    "saying",
    "per ",
    # Reporting verbs that make the claim somebody else's account of the
    # future. The analyzer downgrades these when the speaker is the author:
    # "we expect growth" is the author's own expectation, not a quotation.
    "expects",
    "expected",
    "expect",
    "predicts",
    "predicted",
    "predict",
    "forecasts",
    "forecast",
    "projects",
    "projected",
    "estimates",
    "estimated",
    "anticipates",
    "believes",
    "believe",
    "warns",
    "warned",
    "announced",
    "revealed",
    "disclosed",
    "published",
    "urged",
    "\u636e",  # 据
    "\u79f0",  # 称
    "\u8868\u793a",  # 表示
)

#: Endorsement frames: the author takes the claim up.
ENDORSEMENT_MARKERS: tuple[str, ...] = (
    "we agree",
    "we concur",
    "and this is correct",
    "this is correct",
    "we share this view",
    "we share that view",
    "consistent with our view",
    "confirms our view",
    "as we have argued",
    "as we argued",
    "indeed",
    "we endorse",
    "we support this",
    "\u6211\u4eec\u540c\u610f",  # 我们同意
    "\u6b63\u786e",  # 正确
)

#: Rejection frames: the author argues against the claim.
REJECTION_MARKERS: tuple[str, ...] = (
    "we disagree",
    "we do not agree",
    "we don't agree",
    "this is incorrect",
    "that is incorrect",
    "this is wrong",
    "that is wrong",
    "but evidence shows",
    "evidence shows otherwise",
    "there is no evidence",
    "no evidence for",
    "is misleading",
    "are misleading",
    "is misguided",
    "we doubt",
    "we are not convinced",
    "does not hold",
    "do not hold",
    "refute",
    "debunk",
    "dispute",
    "disputed",
    "rejected the claim",
    "does not endorse",
    "do not endorse",
    "\u6211\u4eec\u4e0d\u540c\u610f",  # 我们不同意
    "\u4e0d\u6210\u7acb",  # 不成立
    "\u9a73\u65a5",  # 驳斥
    "\u8f9f\u8c23",  # 辟谣
)

#: First-person markers that make a rejection frame the author's own act rather
#: than a report of somebody disagreeing.
AUTHOR_REJECTION_CUES: tuple[str, ...] = (
    "we",
    "our",
    "us",
    "i ",
    "i'",
    "\u6211\u4eec",
    "\u6211",
)

_REJECTION_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(item) for item in REJECTION_MARKERS if item.isascii()) + r")\b",
    re.IGNORECASE,
)
_ENDORSEMENT_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(item) for item in ENDORSEMENT_MARKERS if item.isascii()) + r")\b",
    re.IGNORECASE,
)
_QUOTATION_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(item) for item in QUOTATION_MARKERS if item.isascii()) + r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class StanceVerdict:
    """The stance of one segment, plus the rejection it projects backwards."""

    stance: str
    confidence: float
    evidence: EvidenceLog
    rejects_previous: bool = False
    rejection_evidence: EvidenceLog = EvidenceLog()

    @property
    def markers(self) -> tuple[str, ...]:
        return self.evidence.markers()

    def as_dict(self) -> dict[str, object]:
        return {
            "stance": self.stance,
            "confidence": self.confidence,
            "evidence": list(self.markers),
            "rejects_previous": self.rejects_previous,
        }


def _matches(text: str, markers: Sequence[str], pattern: re.Pattern[str]) -> list[str]:
    """ASCII markers via the compiled pattern, CJK markers by substring."""

    found: list[str] = []
    for match in pattern.finditer(text):
        found.append(match.group(0).lower())
    lowered = text.lower()
    for marker in markers:
        if not marker.isascii() and marker in lowered:
            found.append(marker)
    return found


def _author_rejection(text: str) -> bool:
    lowered = f" {text.lower()} "
    return any(cue in lowered for cue in AUTHOR_REJECTION_CUES)


class StanceDetector:
    """Rule-based stance detection over one claim segment."""

    name = "rule-based-stance-detector"
    version = "1.0.0"

    def detect(
        self,
        segment: ClaimSegment,
        *,
        previous: ClaimSegment | None = None,
    ) -> StanceVerdict:
        del previous  # reserved: stance is currently decided within the segment
        text = segment.text
        log = EvidenceLog()

        rejected = _matches(text, REJECTION_MARKERS, _REJECTION_RE)
        endorsed = _matches(text, ENDORSEMENT_MARKERS, _ENDORSEMENT_RE)
        quoted = _matches(text, QUOTATION_MARKERS, _QUOTATION_RE)

        # A contrastive lead is rejection evidence in its own right.
        if segment.opens_with_contrast:
            rejected = [*rejected, segment.lead]

        for marker in rejected:
            log = log.add(marker, kind="stance", rule="stance.rejection")
        for marker in endorsed:
            log = log.add(marker, kind="stance", rule="stance.endorsement")
        for marker in quoted:
            log = log.add(marker, kind="stance", rule="stance.quotation")

        rejects_previous = bool(rejected) and (
            segment.opens_with_contrast or _author_rejection(text)
        )
        rejection_log = EvidenceLog()
        if rejects_previous:
            for marker in rejected:
                rejection_log = rejection_log.add(
                    marker, kind="stance", rule="stance.rejection-backward"
                )

        if rejected:
            return StanceVerdict(
                REJECTED,
                self._confidence(len(rejected), base=0.7),
                log,
                rejects_previous=rejects_previous,
                rejection_evidence=rejection_log,
            )
        if endorsed:
            return StanceVerdict(
                ENDORSED, self._confidence(len(endorsed), base=0.7), log
            )
        if quoted:
            return StanceVerdict(
                QUOTED, self._confidence(len(quoted), base=0.65), log
            )

        return StanceVerdict(
            UNCERTAIN,
            0.3,
            log.absence(
                kind="stance",
                rule="stance.no-marker",
                detail="no reporting, endorsement or rejection marker in the claim",
            ),
        )

    def _confidence(self, hits: int, *, base: float) -> float:
        return round(min(0.95, base + 0.08 * (hits - 1)), 3)


def stance_evidence(verdict: StanceVerdict) -> tuple[EvidenceMark, ...]:
    return verdict.evidence.marks
