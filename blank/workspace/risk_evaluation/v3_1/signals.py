"""The signal vocabulary the Phase 8.8 capability layers decide on.

A frame either matches or it does not, and that is the right model for a syntactic
shape. It is the wrong model for the two capabilities this phase adds, because
both turn on *how strongly* and *about what* something is said:

    The market will probably crash next month.   a modal, but not a prediction
    The value of investments may fall as well
      as rise.                                   a modal, and not a prediction
    The fee may indicate a higher turnover.      a modal about a fee

All three contain a modal and a market word. What separates them from a real
prediction is not another word but which signals are present, so the capability
layer has to name the signals it found. That naming is this module's whole job:
the names are a vocabulary, shared by the detectors, the benchmark's expectations
and the report, so "why did it not fire?" has an answer in the same terms as "why
did it fire?".

Signal names are stable strings because they appear in traces and in a frozen
benchmark's expectations. Renaming one is a breaking change to both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

#: A financial target the sentence is about. The Phase 8.4 entity lexicon decides
#: this, not a new list: a prediction is about a market quantity, and the entities
#: that can be one are already declared.
MARKET_ENTITY = "market_entity"
#: A directional outcome: something that can go up or down. A modal plus a
#: non-directional verb (`may fluctuate`) is a disclosure, not a prediction.
OUTCOME_EXPRESSION = "outcome_expression"
#: The modal or strength carrier, and which strength class it puts the statement
#: in. Reported as one signal because the class is what the decision turns on.
UNCERTAIN_PREDICTION_MODAL = "uncertain_prediction_modal"
#: When the statement is oriented to the future: a horizon marker, or a
#: prospective construction that is future by grammar.
FUTURE_MARKER = "future_marker"

#: --- advice signals ---------------------------------------------------------
#: Who the directive is aimed at, and whether that is the reader.
ADDRESS = "addressee"
#: The form the directive takes: bare imperative, modal address, advisory frame.
IMPERATIVE_STRUCTURE = "imperative_structure"
#: The financial thing the directive acts on, direct object or prepositional.
FINANCIAL_ACTION_OBJECT = "financial_action_object"
#: The directive names an action on a position rather than a method.
POSITION_ACTION = "position_action"

#: Signals a modal prediction needs. All four, which is what makes it a frame
#: rather than a keyword: the phase's example trace names three of them, and the
#: fourth (`outcome_expression`) is what keeps `may indicate` out.
PREDICTION_SIGNALS: tuple[str, ...] = (
    FUTURE_MARKER,
    MARKET_ENTITY,
    OUTCOME_EXPRESSION,
    UNCERTAIN_PREDICTION_MODAL,
)

#: Signals an advice finding needs.
ADVICE_SIGNALS: tuple[str, ...] = (
    ADDRESS,
    IMPERATIVE_STRUCTURE,
    FINANCIAL_ACTION_OBJECT,
    POSITION_ACTION,
)

SIGNAL_NAMES: tuple[str, ...] = (
    ADDRESS,
    FINANCIAL_ACTION_OBJECT,
    FUTURE_MARKER,
    IMPERATIVE_STRUCTURE,
    MARKET_ENTITY,
    OUTCOME_EXPRESSION,
    POSITION_ACTION,
    UNCERTAIN_PREDICTION_MODAL,
)

#: Which capability each signal belongs to.
SIGNAL_FAMILIES: Mapping[str, str] = {
    FUTURE_MARKER: "modal_prediction",
    MARKET_ENTITY: "modal_prediction",
    OUTCOME_EXPRESSION: "modal_prediction",
    UNCERTAIN_PREDICTION_MODAL: "modal_prediction",
    ADDRESS: "advice_boundary",
    IMPERATIVE_STRUCTURE: "advice_boundary",
    FINANCIAL_ACTION_OBJECT: "advice_boundary",
    POSITION_ACTION: "advice_boundary",
}

#: The two capabilities this phase adds.
MODAL_PREDICTION = "modal_prediction"
ADVICE_BOUNDARY = "advice_boundary"

CAPABILITIES: tuple[str, ...] = (MODAL_PREDICTION, ADVICE_BOUNDARY)


class SignalError(Exception):
    """Raised when a signal is not part of the declared vocabulary."""


@dataclass(frozen=True, slots=True)
class Signal:
    """One signal, with the text that carried it."""

    name: str
    span: tuple[int, int]
    text: str
    #: Free-form detail: which modal, which strength, which entity type. Kept so a
    #: trace can say more than the signal name without inventing a signal per case.
    detail: str = ""

    def __post_init__(self) -> None:
        if self.name not in SIGNAL_NAMES:
            raise SignalError(f"unknown signal {self.name!r}")
        if self.span[1] < self.span[0]:
            raise SignalError(f"{self.name}: bad span {self.span!r}")

    @property
    def family(self) -> str:
        return SIGNAL_FAMILIES[self.name]

    @property
    def marker(self) -> str:
        detail = f":{self.detail}" if self.detail else ""
        return f"signal:{self.name}{detail}"

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "family": self.family,
            "span": list(self.span),
            "text": self.text,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class SignalSet:
    """The signals found in one piece of text, by name."""

    signals: tuple[Signal, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "signals", tuple(self.signals))

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.name for item in self.signals))

    def get(self, name: str) -> Signal | None:
        for item in self.signals:
            if item.name == name:
                return item
        return None

    def all(self, name: str) -> tuple[Signal, ...]:
        return tuple(item for item in self.signals if item.name == name)

    def has(self, *names: str) -> bool:
        found = set(self.names)
        return all(name in found for name in names)

    def includes(self, names: Sequence[str]) -> bool:
        """Are all of `names` present? The frame's requirement, as a predicate."""

        return self.has(*names)

    @property
    def missing(self) -> tuple[str, ...]:
        """Declared signals this set does not have, for a "why not?" answer."""

        found = set(self.names)
        return tuple(name for name in SIGNAL_NAMES if name not in found)

    @property
    def markers(self) -> tuple[str, ...]:
        return tuple(item.marker for item in self.signals)

    def require(self, names: Sequence[str], *, reason: str = "") -> None:
        """Raise unless every name is present. For detector self-checks."""

        missing = [name for name in names if name not in set(self.names)]
        if missing:
            detail = f" ({reason})" if reason else ""
            raise SignalError(f"signals missing: {missing}{detail}")

    def family(self, family: str) -> tuple[Signal, ...]:
        if family not in CAPABILITIES:
            raise SignalError(f"unknown capability {family!r}")
        return tuple(item for item in self.signals if item.family == family)

    def as_dict(self) -> dict[str, object]:
        return {
            "names": list(self.names),
            "signals": [item.as_dict() for item in self.signals],
        }


def build(*signals: Signal) -> SignalSet:
    """A signal set in reading order, de-duplicated by (name, span)."""

    seen: dict[tuple[str, tuple[int, int]], Signal] = {}
    for item in signals:
        seen.setdefault((item.name, item.span), item)
    ordered = sorted(seen.values(), key=lambda item: (item.span[0], item.name))
    return SignalSet(tuple(ordered))


def describe() -> tuple[dict[str, object], ...]:
    """The signal table, for the report and the tests."""

    return tuple(
        {"name": name, "family": SIGNAL_FAMILIES[name]} for name in SIGNAL_NAMES
    )
