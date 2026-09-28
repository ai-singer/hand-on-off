"""The two capability layers, applied to one claim.

The pipeline keeps the shape Phase 8.5 gave it:

    Claim -> Attribution -> Intent -> Decision

and this module is part of the intent stage, not a stage beside it. It runs after
the Phase 8.4 frames, and it does two things to what they produced:

**It replaces what it is authoritative for.** Where the modal layer reached a
verdict, its finding replaces the frame's finding on the same span, so a span has
one authority rather than two disagreeing ones. That is what lets
`The market will probably crash next month.` stop being a prediction: the frame
sees `will` and asserts, and the layer sees `will probably` and reports the
statement at `probable`, which guide v2 section 2 excludes.

**It vetoes where it has positive evidence against a relation.** A verdict that
declines - `method_guidance`, `third_person_subject`, `non_directional`,
`conditional_scenario` - removes the frame's finding, because the layer has
looked at the structure and concluded that the relation is not there.

What a declining verdict may **not** do is veto on the strength of not matching.
`no_modal`, `no_outcome`, `no_market_entity` and `no_directive` mean "this is not
the shape I look for", and treating that as evidence would let each layer delete
relations it simply does not cover. `Turnover expands sharply next quarter.` has
no modal at all, and the Phase 8.4 horizon frame is right to call it a prediction;
a layer that vetoed on `no_modal` would break it.

The same distinction decides what may reach the decision policy. A declined
verdict is evidence against a category and is passed on as `boundary_declined`, so
the semantic fallback cannot quietly reinstate it. A non-matching verdict is not.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from ..v3.decision import is_reporting_hedge
from ..v3.model import IntentEvidence
from .advice import ADVICE_VERDICT, DECLINING_VERDICTS as ADVICE_DECLINES
from .advice import AdviceDetection
from .advice import evaluate as evaluate_advice
from .modal import DECLINING_VERDICTS as MODAL_DECLINES
from .modal import ModalDetection
from .modal import evaluate as evaluate_modal
from .signals import CAPABILITIES, SignalError


class DetectionError(Exception):
    """Raised when a capability layer cannot be applied."""


#: How a layer treats a hedge the Phase 8.4 matcher already found on the frame it
#: is replacing. The two capabilities answer this differently, and the difference
#: is in the guide rather than in taste.
#:
#: **`preserve`** - the modal layer. Nothing in guide v2 makes a hedge constitutive
#: of a prediction, and a hedge can only ever make a statement weaker, so dropping
#: one could only raise a statement's strength. It did: `The claim that the stock
#: will certainly double is incorrect.` is reported speech, the matcher recorded
#: `claim` as its hedge, and a layer that replaced the finding without the hedge
#: turned a correctly suppressed statement into a `market_prediction`.
#:
#: **`constitutive`** - the advice layer, and only for hedges that are not
#: reporting. Guide v2 section 5 says a conditional *directive* is still advice:
#: `If you want higher returns, buy this stock.` is `investment_advice`, so a
#: conditional does not hedge a directive. Phase 8.5 already reached the same
#: conclusion for `should` in `DIRECTIVE_MODALS`. Reporting hedges are the
#: exception, because `Analysts say investors should buy the dip.` records that
#: somebody else is advising, and guide section 3.1 gives that question to the
#: attribution layer.
HEDGE_PRESERVE = "preserve"
HEDGE_CONSTITUTIVE = "constitutive"

HEDGE_POLICIES: tuple[str, ...] = (HEDGE_PRESERVE, HEDGE_CONSTITUTIVE)


@dataclass(frozen=True, slots=True)
class Veto:
    """A relation a capability layer declines, on a span.

    A veto with a `replacement` amends the frame's finding rather than removing
    it: the frame found the relation and the layer found out more about it. A veto
    without one removes the finding, which is what a declining verdict does.
    """

    capability: str
    relation: str
    span: tuple[int, int]
    verdict: str
    evidence: tuple[str, ...] = ()
    replacement: IntentEvidence | None = None
    hedge_policy: str = HEDGE_PRESERVE

    def __post_init__(self) -> None:
        if self.hedge_policy not in HEDGE_POLICIES:
            raise DetectionError(f"unknown hedge policy {self.hedge_policy!r}")

    @property
    def replaces(self) -> bool:
        return self.replacement is not None

    @property
    def marker(self) -> str:
        verb = "replace" if self.replaces else "veto"
        return f"{verb}:{self.capability}:{self.verdict}"

    def overlaps(self, span: tuple[int, int]) -> bool:
        """Do two spans share any character?

        Overlap rather than containment: a frame and a capability layer describe
        the same relation from different ends of the sentence, and a frame that
        starts earlier than the layer's verdict is still the same finding.
        """

        return span[0] < self.span[1] and self.span[0] < span[1]

    def amend(self, frame: IntentEvidence) -> IntentEvidence:
        """The frame's finding, re-characterised by the layer's.

        The frame's negation is kept: a layer that found an asserted prediction in
        a sentence the matcher had negated would be raising it, and the matcher's
        negation guard is not this layer's to overrule.
        """

        if self.replacement is None:  # pragma: no cover - guarded by `replaces`
            raise DetectionError("amend called on a veto with no replacement")
        hedge = frame.hedge or self.replacement.hedge
        if self.hedge_policy == HEDGE_CONSTITUTIVE and not is_reporting_hedge(hedge):
            hedge = self.replacement.hedge
        entity = frame.entity if frame.entity and frame.entity != "UNKNOWN" else self.replacement.entity
        return replace(
            self.replacement,
            entity=entity or "UNKNOWN",
            span=frame.span,
            negated=frame.negated,
            negation_scope=frame.negation_scope,
            hedge=hedge,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "capability": self.capability,
            "relation": self.relation,
            "span": list(self.span),
            "verdict": self.verdict,
            "replaces": self.replaces,
            "hedge_policy": self.hedge_policy,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class Detection:
    """Everything the two capability layers concluded about one claim."""

    findings: tuple[IntentEvidence, ...] = ()
    vetoes: tuple[Veto, ...] = ()
    boundary_declined: tuple[str, ...] = ()
    capabilities: tuple[dict[str, object], ...] = ()
    verdicts: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))
        object.__setattr__(self, "vetoes", tuple(self.vetoes))
        object.__setattr__(
            self, "boundary_declined", tuple(dict.fromkeys(self.boundary_declined))
        )
        object.__setattr__(
            self, "capabilities", tuple(dict(item) for item in self.capabilities)
        )

    @property
    def declared(self) -> bool:
        return bool(self.findings)

    def vetoed(self, relation: str, span: tuple[int, int]) -> Veto | None:
        """The veto that removes this relation on this span, if there is one."""

        for veto in self.vetoes:
            if veto.relation == relation and veto.overlaps(span):
                return veto
        return None

    def capability(self, name: str) -> dict[str, object] | None:
        for item in self.capabilities:
            if item.get("capability") == name:
                return item
        return None

    def apply(self, intents: Sequence[IntentEvidence]) -> tuple[IntentEvidence, ...]:
        """What survives the capability layers: amended, dropped, or added.

        A frame the layer is authoritative for is **amended**, not discarded and
        re-added: the frame still resolved the entity lexicon and still holds the
        matcher's negation and reporting hedge, and a replacement that threw those
        away would be raising a statement's strength rather than re-describing it.
        """

        kept: list[IntentEvidence] = []
        replaced: set[int] = set()
        for item in intents:
            veto = self.vetoed(item.relation, item.span)
            if veto is None:
                kept.append(item)
                continue
            if veto.replacement is None:
                continue
            kept.append(veto.amend(item))
            replaced.add(id(veto.replacement))
        kept.extend(
            item for item in self.findings if id(item) not in replaced
        )
        return tuple(kept)

    def as_dict(self) -> dict[str, object]:
        return {
            "verdicts": list(self.verdicts),
            "findings": [item.as_dict() for item in self.findings],
            "vetoes": [item.as_dict() for item in self.vetoes],
            "boundary_declined": list(self.boundary_declined),
            "capabilities": [dict(item) for item in self.capabilities],
            "evidence": list(self.evidence),
        }


def _modal_veto(found: ModalDetection) -> Veto | None:
    """Only a decisive verdict vetoes; see the module docstring."""

    decisive = found.declines or found.declared
    if not decisive:
        return None
    return Veto(
        capability="modal_prediction",
        relation="PREDICTION",
        span=found.span,
        verdict=found.verdict,
        evidence=found.evidence,
        replacement=found.finding,
        hedge_policy=HEDGE_PRESERVE,
    )


def _advice_veto(found: AdviceDetection) -> Veto | None:
    decisive = found.declines or found.declared
    if not decisive:
        return None
    return Veto(
        capability="advice_boundary",
        relation="ADVICE",
        span=found.span,
        verdict=found.verdict,
        evidence=found.evidence,
        replacement=found.finding,
        hedge_policy=HEDGE_CONSTITUTIVE,
    )


def evaluate(text: str) -> Detection:
    """Run both capability layers over one claim's text."""

    if not isinstance(text, str):
        raise DetectionError(f"text must be a string, got {type(text).__name__}")

    modal = evaluate_modal(text)
    advice = evaluate_advice(text)

    findings: list[IntentEvidence] = []
    vetoes: list[Veto] = []
    declined: list[str] = []
    evidence: list[str] = []

    if modal.finding is not None:
        findings.append(modal.finding)
    veto = _modal_veto(modal)
    if veto is not None:
        vetoes.append(veto)
    declined.extend(modal.declined_categories)
    evidence.extend(modal.evidence)

    if advice.finding is not None:
        findings.append(advice.finding)
    veto = _advice_veto(advice)
    if veto is not None:
        vetoes.append(veto)
    declined.extend(advice.declined_categories)
    evidence.extend(advice.evidence)

    return Detection(
        findings=tuple(findings),
        vetoes=tuple(vetoes),
        boundary_declined=tuple(declined),
        capabilities=(modal.as_dict(), advice.as_dict()),
        verdicts=(modal.verdict, advice.verdict),
        evidence=tuple(dict.fromkeys(evidence)),
    )


def capability(name: str):
    """The detector for one declared capability, for callers that want one."""

    if name not in CAPABILITIES:
        raise SignalError(f"unknown capability {name!r}; declared: {CAPABILITIES}")
    return evaluate_modal if name == "modal_prediction" else evaluate_advice


def describe() -> dict[str, object]:
    """The layer's declared surface, for the report and the tests."""

    return {
        "capabilities": {
            "modal_prediction": {
                "verdicts": list(ModalDetection.__dataclass_fields__),
                "declining": list(MODAL_DECLINES),
            },
            "advice_boundary": {
                "declaring": ADVICE_VERDICT,
                "declining": list(ADVICE_DECLINES),
            },
        },
        "veto_rule": "a decisive verdict replaces or removes the frame finding on its span",
        "no_veto_rule": "a non-matching verdict never vetoes: not-my-shape is not evidence",
        "boundary_channel": "a declined verdict names the category it declined",
    }
