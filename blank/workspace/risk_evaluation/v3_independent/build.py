"""Phase 8.9 run builder: batching, the exact prompts, and validation.

Three jobs, and the third is the one that matters.

**Batching.** The 300 slots are written to disk in fixed-size batches, one file per
generation agent and one per annotation session. The annotation batches are shuffled
with a different seed per annotator, so batch composition carries no signal and the
two annotators do not even share a case order.

**The prompts.** `GENERATION_PROMPT` and `ANNOTATION_PROMPT` are the literal text
handed to each agent, and they are published verbatim in the dataset manifest. That
is what turns "the text authors never saw the evaluator" from a claim into something
a reader can check. Neither prompt names a frame, a matcher, a pattern, an entity
list or a module path; both give the annotation guide and nothing else from the
repository.

**Validation.** Every generated record must echo the slot it was written for, and
`validate_generated()` compares that echo against the frame. A generator that
returned the wrong number of cases, a missing id, or a case whose language or source
register does not match its slot is a hard failure rather than something to average
away. The echo also means a mismatch between the frame as Python computed it and the
frame as the agents saw it cannot pass silently.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .frame import FrameDescriptor, build_frame, load_slots

RUN_ROOT = Path(__file__).resolve().parent / "run"
GENERATION_DIR = RUN_ROOT / "generation"
ANNOTATION_DIR = RUN_ROOT / "annotation"

GENERATOR_BATCH = 10
ANNOTATION_BATCH = 50
ANNOTATORS: tuple[str, ...] = ("A", "B")

#: Seeds for the annotation shuffle. Different per annotator on purpose: the two do
#: not share a case order, so a session boundary cannot be a shared cue.
ANNOTATION_SEEDS: Mapping[str, int] = {"A": 8291, "B": 4477}

#: The literal prompt every dataset author receives, with the slot file and output
#: path appended. Published verbatim in the manifest.
GENERATION_PROMPT = """\
You are writing text for an annotation dataset. You are one of several dataset
authors, working independently. You have NOT seen, and must not try to infer
anything about, any software that will later be evaluated on this text. Do not read
anything under risk_evaluation/. Read only the slot file named below.

Read the slot file {slots}.
It contains a JSON list of slots, each with case_id, group, source_type, language,
form, topic, and (for some) intent / boundary_meaning / boundary_basis.

Write one short passage of 1 to 2 sentences for EVERY slot. Then write
{{"items": [ ... ]}} to {target}, where each item echoes every field of its slot
plus "text" holding the passage:

  {{"case_id": "...", "group": "...", "source_type": "...", "language": "...",
    "form": "...", "topic": "...", "intent": "...", "boundary_kind": "...",
    "boundary_meaning": "...", "boundary_basis": "...", "text": "..."}}

Rules:
1. One passage per slot, 1 to 2 sentences, natural publishable financial writing.
   No bullet lists, no headings, no markdown.
2. language "en" means English; "zh" means Simplified Chinese, which must be natural
   Chinese and not a translation of English word order.
3. Write in the register of the slot's source_type:
   news_report = a news item reporting an event;
   analyst_note = a research note addressed to clients;
   forum_post = an investor forum or message-board post;
   educational_article = an explainer about how something works;
   marketing_material = promotional copy for a product;
   regulatory_filing = a formal disclosure or filing;
   social_post = a short social-media post;
   earnings_summary = a summary of reported results.
4. Use the slot's form:
   declarative_certain = a plain statement of fact;
   declarative_hedged = a statement softened by a modal or adverb;
   imperative = begins with a verb;
   interrogative = a question, or a heading phrased as one;
   conditional = the outcome depends on a stated condition;
   nominal = a noun-phrase construction rather than a full clause;
   quoted = a claim inside quotation marks or reported speech;
   passive = a passive construction.
5. Where the slot gives an intent, the passage must express that category, judged by
   the guide below, clearly enough that a careful reader would agree.
6. Where the slot's group is "safe", the passage must carry no category at all.
7. Where the slot gives a boundary_meaning, write exactly that shape: it is a case
   whose correct label a careful reader has to reason about. Do not make it easy.
8. Vary entity names, numbers and phrasing. Do not reuse a sentence pattern more
   than twice in your batch.
9. Output the JSON file only. Do not print the passages in your reply.

{guide}"""

#: The literal prompt every annotator receives.
ANNOTATION_PROMPT = """\
You are an annotator applying an annotation guide to text you have not seen before.
Read the cases file {cases}: a JSON list of records with "id" and "text".

You have NOT seen any software that will be evaluated on this text and you must not
try to guess what it would say. Label what each text DOES, by the guide below. Do
not read any labels written by anyone else, and do not read anything under
risk_evaluation/.

For every case, return exactly these fields:
  id          the id given, unchanged
  claim       the span that asserts something, quoted verbatim; or "none" when the
              text asserts nothing a category could attach to
  speaker     "author" | "third_party" | "unknown"
  stance      "endorsed" | "quoted" | "rejected" | "uncertain"
  intent      "GUARANTEE" | "RISK_REMOVED" | "PREDICTION" | "ADVICE" | "NONE"
  certainty   "certain" | "probable" | "possible" | "hypothetical" | "n/a"
  severity    "block" | "warning" | "none"
  decision    a JSON array of zero or more of: "investment_advice",
              "market_prediction", "financial_guarantee",
              "unverified_information", "emotional_manipulation"
  reason      at most two sentences, citing the guide section you relied on

Definitions:
- intent is the relation the claim carries, whoever said it. A NEGATED relation is
  still its relation: "Returns are not guaranteed" carries GUARANTEE. RISK_REMOVED
  is risk denied without the word guarantee (risk-free, cannot lose, never falls).
  NONE when the claim carries no such relation.
- severity is the highest severity among the categories you chose: block for
  financial_guarantee and investment_advice; warning for market_prediction,
  unverified_information and emotional_manipulation; none for an empty decision.
- certainty is "n/a" when the claim carries no certainty, as a directive does not.
- decision is what the ARTICLE is doing to its reader. Report every category that
  survives. Do not pick one, and do not hedge.

Rules:
1. Label every case in the file. Do not skip any.
2. Values must come from the lists above, exactly as spelled.
3. Output {{"items": [ ... ]}} to {target}, one item per case, and nothing else.
   Do not print the labels in your reply.

{guide}"""

#: The guide digest handed to every generator and annotator. It is the normative
#: document's content, and it is the only repository material either role receives.
GUIDE_DIGEST = """\
ANNOTATION GUIDE (normative: docs/RISK_ANNOTATION_GUIDE_v2.md)

Five risk categories:
- investment_advice: an action-directive aimed at the reader AND a financial object.
  Educational explanation and method guidance are NEGATIVE. Recipe or method
  guidance ("hold a diversified portfolio", "rebalance annually", "keep costs low")
  is not advice.
- market_prediction: a future market outcome asserted by the AUTHOR as CERTAIN.
  A reported expectation is not (an attributed expectation is a report).
  A hedged author claim is not: probable (probably, likely, expected to, should) and
  possible (may, might, could, possibly, perhaps) are not predictions.
  A conditional scenario is not.
  A price level IS a prediction when the author asserts it as its own certainty.
- financial_guarantee: risk removed or an outcome made unconditional. Includes
  "guaranteed", "protected", "assured", "risk-free", "cannot lose", "never falls".
  A DISCLAIMED guarantee is negative.
- unverified_information: a claim carried on an UNCHECKABLE source. A named,
  checkable source is negative. Unnamed examples: insiders, sources, traders,
  analysts, officials, reportedly, rumour, market chatter, an unnamed official.
- emotional_manipulation: pressure substituting for reasoning. Imperative to act
  (get out now, act fast), deadline or scarcity (before it is too late, last chance),
  herd framing (everyone is buying), belittling the reader (you would be crazy).
  Dramatic market vocabulary ALONE is not manipulation (crash, collapse, meltdown).

Certainty levels: certain (will, is, definitely, certainly, bound to), probable
(probably, likely, expected to, should), possible (may, might, could, possibly,
perhaps), hypothetical (if, inverted "should X", were ... to, assuming, unless).
Weakest carrier wins: "will probably crash" is probable. Conditional beats modal.

Speaker: the author is the voice of the text unless the text marks a claim as
someone else's. Precedence: unknown, then third_party, then author.
Stance: endorsed, quoted, rejected, or uncertain. A quotation becomes the article's
own claim only when the article endorses it in its own voice.
"""


class BuildError(Exception):
    """Raised when a run artifact is missing or malformed."""


def guide_digest() -> str:
    return GUIDE_DIGEST


def generation_prompt(slots_path: Path, target: Path) -> str:
    return GENERATION_PROMPT.format(
        slots=slots_path, target=target, guide=GUIDE_DIGEST
    )


def annotation_prompt(cases_path: Path, target: Path) -> str:
    return ANNOTATION_PROMPT.format(
        cases=cases_path, target=target, guide=GUIDE_DIGEST
    )


def write_generation_batches(
    slots: Sequence[FrameDescriptor] | None = None,
    *,
    root: str | Path | None = None,
    size: int = GENERATOR_BATCH,
) -> tuple[Path, ...]:
    active = tuple(slots) if slots is not None else build_frame()
    target_dir = Path(root) if root is not None else GENERATION_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    index = 0
    for start in range(0, len(active), size):
        chunk = active[start : start + size]
        index += 1
        path = target_dir / f"slots_{index:02d}.json"
        path.write_text(
            json.dumps([item.as_dict() for item in chunk], indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return tuple(written)


def generation_targets(*, root: str | Path | None = None) -> tuple[Path, ...]:
    target_dir = Path(root) if root is not None else GENERATION_DIR
    return tuple(sorted(target_dir.glob("slots_*.json")))


def generated_path(index: int, *, root: str | Path | None = None) -> Path:
    target_dir = Path(root) if root is not None else GENERATION_DIR
    return target_dir / f"generated_{index:02d}.json"


@dataclass(frozen=True, slots=True)
class GeneratedCase:
    case_id: str
    text: str
    slot: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.case_id, "text": self.text, "slot": dict(self.slot)}

    @property
    def language(self) -> str:
        return str(self.slot.get("language", ""))

    @property
    def group(self) -> str:
        return str(self.slot.get("group", ""))

    @property
    def source_type(self) -> str:
        return str(self.slot.get("source_type", ""))

    @property
    def form(self) -> str:
        return str(self.slot.get("form", ""))


def validate_generated(
    *, root: str | Path | None = None, slots: Sequence[FrameDescriptor] | None = None
) -> tuple[GeneratedCase, ...]:
    """Read every generation batch and prove it covers the frame exactly."""

    expected = {item.case_id: item.as_dict() for item in (tuple(slots) if slots is not None else build_frame())}
    target_dir = Path(root) if root is not None else GENERATION_DIR

    found: dict[str, GeneratedCase] = {}
    seen_files = 0
    for path in sorted(target_dir.glob("generated_*.json")):
        seen_files += 1
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise BuildError(f"{path.name}: no items array")
        for item in items:
            if not isinstance(item, dict):
                raise BuildError(f"{path.name}: an item is not an object")
            case_id = str(item.get("case_id") or item.get("id") or "")
            text = str(item.get("text") or "").strip()
            if not case_id:
                raise BuildError(f"{path.name}: an item has no case_id")
            if case_id not in expected:
                raise BuildError(f"{path.name}: unknown case_id {case_id!r}")
            if not text:
                raise BuildError(f"{path.name}: {case_id} has no text")
            if case_id in found:
                raise BuildError(f"{path.name}: {case_id} appears twice")
            echo = {
                key: item.get(key, "")
                for key in (
                    "group",
                    "source_type",
                    "language",
                    "form",
                    "topic",
                    "intent",
                    "boundary_kind",
                )
            }
            slot = expected[case_id]
            for key, value in echo.items():
                if str(value) != str(slot[key]):
                    raise BuildError(
                        f"{path.name}: {case_id} slot mismatch on {key}: "
                        f"echoed {value!r}, frame says {slot[key]!r}"
                    )
            found[case_id] = GeneratedCase(case_id, text, slot)

    if seen_files == 0:
        raise BuildError(f"no generated_*.json under {target_dir}")
    missing = sorted(set(expected) - set(found))
    if missing:
        raise BuildError(f"{len(missing)} slots were not generated: {missing[:8]}")
    return tuple(found[key] for key in sorted(found))


def write_annotation_batches(
    cases: Sequence[GeneratedCase],
    *,
    root: str | Path | None = None,
    size: int = ANNOTATION_BATCH,
    annotators: Sequence[str] = ANNOTATORS,
) -> Mapping[str, tuple[Path, ...]]:
    """One file per annotator session, shuffled differently per annotator."""

    target_dir = Path(root) if root is not None else ANNOTATION_DIR
    written: dict[str, tuple[Path, ...]] = {}
    for name in annotators:
        session_dir = target_dir / name
        session_dir.mkdir(parents=True, exist_ok=True)
        order = list(cases)
        random.Random(ANNOTATION_SEEDS.get(name, 0)).shuffle(order)
        paths: list[Path] = []
        index = 0
        for start in range(0, len(order), size):
            chunk = order[start : start + size]
            index += 1
            path = session_dir / f"cases_{index:02d}.json"
            path.write_text(
                json.dumps(
                    [{"id": item.case_id, "text": item.text} for item in chunk],
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            paths.append(path)
        written[name] = tuple(paths)
    return written


def annotation_target(index: int, annotator: str, *, root: str | Path | None = None) -> Path:
    target_dir = Path(root) if root is not None else ANNOTATION_DIR
    return target_dir / annotator / f"labels_{index:02d}.json"


def annotation_sessions(
    annotator: str, *, root: str | Path | None = None
) -> tuple[Path, ...]:
    target_dir = Path(root) if root is not None else ANNOTATION_DIR
    return tuple(sorted((target_dir / annotator).glob("cases_*.json")))


LABEL_FIELDS: tuple[str, ...] = (
    "speaker",
    "stance",
    "intent",
    "certainty",
    "severity",
)

SPEAKERS: tuple[str, ...] = ("author", "third_party", "unknown")
STANCES: tuple[str, ...] = ("endorsed", "quoted", "rejected", "uncertain")
INTENTS: tuple[str, ...] = ("GUARANTEE", "RISK_REMOVED", "PREDICTION", "ADVICE", "NONE")
CERTAINTIES: tuple[str, ...] = ("certain", "probable", "possible", "hypothetical", "n/a")
SEVERITIES: tuple[str, ...] = ("block", "warning", "none")
CATEGORIES: tuple[str, ...] = (
    "investment_advice",
    "market_prediction",
    "financial_guarantee",
    "unverified_information",
    "emotional_manipulation",
)

ALLOWED: Mapping[str, tuple[str, ...]] = {
    "speaker": SPEAKERS,
    "stance": STANCES,
    "intent": INTENTS,
    "certainty": CERTAINTIES,
    "severity": SEVERITIES,
}


@dataclass(frozen=True, slots=True)
class Annotation:
    case_id: str
    claim: str
    speaker: str
    stance: str
    intent: str
    certainty: str
    severity: str
    decision: tuple[str, ...]
    reason: str
    annotator: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.case_id,
            "claim": self.claim,
            "speaker": self.speaker,
            "stance": self.stance,
            "intent": self.intent,
            "certainty": self.certainty,
            "severity": self.severity,
            "decision": list(self.decision),
            "reason": self.reason,
            "annotator": self.annotator,
        }

    def field(self, name: str) -> str:
        if name == "decision":
            return ",".join(sorted(self.decision))
        return str(getattr(self, name))


def _annotation_from(item: Mapping[str, Any], annotator: str) -> Annotation:
    case_id = str(item.get("id") or item.get("case_id") or "")
    if not case_id:
        raise BuildError("an annotation has no id")
    values: dict[str, str] = {}
    for name in ALLOWED:
        value = str(item.get(name, "")).strip()
        if value not in ALLOWED[name]:
            raise BuildError(
                f"{annotator}/{case_id}: {name} must be one of {ALLOWED[name]}, "
                f"got {value!r}"
            )
        values[name] = value
    raw = item.get("decision")
    if not isinstance(raw, list):
        raise BuildError(f"{annotator}/{case_id}: decision must be an array")
    decision: list[str] = []
    for name in raw:
        text = str(name)
        if text not in CATEGORIES:
            raise BuildError(f"{annotator}/{case_id}: unknown category {text!r}")
        if text not in decision:
            decision.append(text)
    reason = str(item.get("reason", "")).strip()
    if not reason:
        raise BuildError(f"{annotator}/{case_id}: no reason given")
    return Annotation(
        case_id=case_id,
        claim=str(item.get("claim", "")).strip() or "none",
        decision=tuple(decision),
        reason=reason,
        annotator=annotator,
        **values,
    )


def assemble_annotations(
    cases: Sequence[GeneratedCase],
    *,
    root: str | Path | None = None,
    annotators: Sequence[str] = ANNOTATORS,
) -> Mapping[str, tuple[Annotation, ...]]:
    """Read every session file, proving each annotator labelled every case once."""

    expected = {item.case_id for item in cases}
    target_dir = Path(root) if root is not None else ANNOTATION_DIR
    assembled: dict[str, tuple[Annotation, ...]] = {}
    for name in annotators:
        found: dict[str, Annotation] = {}
        sessions = sorted((target_dir / name).glob("labels_*.json"))
        if not sessions:
            raise BuildError(f"annotator {name}: no labels_*.json")
        for path in sessions:
            payload = json.loads(path.read_text(encoding="utf-8"))
            items = payload.get("items") if isinstance(payload, dict) else payload
            if not isinstance(items, list):
                raise BuildError(f"{path.name}: no items array")
            for item in items:
                annotation = _annotation_from(item, name)
                if annotation.case_id not in expected:
                    raise BuildError(f"{path.name}: unknown case {annotation.case_id}")
                if annotation.case_id in found:
                    raise BuildError(
                        f"{name}: {annotation.case_id} labelled twice"
                    )
                found[annotation.case_id] = annotation
        missing = sorted(expected - set(found))
        if missing:
            raise BuildError(f"{name}: {len(missing)} cases unlabelled: {missing[:8]}")
        assembled[name] = tuple(found[key] for key in sorted(found))
    return assembled


def describe() -> dict[str, Any]:
    return {
        "run_root": str(RUN_ROOT.name),
        "generator_batch": GENERATOR_BATCH,
        "annotation_batch": ANNOTATION_BATCH,
        "annotators": list(ANNOTATORS),
        "annotation_seeds": dict(ANNOTATION_SEEDS),
        "label_fields": list(LABEL_FIELDS),
        "categories": list(CATEGORIES),
    }


def main() -> int:
    import sys

    if "--batches" in sys.argv:
        slots = write_generation_batches()
        print(f"wrote {len(slots)} generation batches to {GENERATION_DIR}")
        return 0
    slots = load_slots()
    print(json.dumps({"slots": len(slots), **describe()}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
