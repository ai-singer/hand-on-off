"""Adversarial expansion generator: structured variants, never random text.

The framework's job is to find the wordings the evaluator misses. Random generation
would be the wrong instrument twice over: it cannot say what a case tests, and it
cannot say what label the case deserves, so its output could neither be reviewed nor
regressed against.

Generation here is therefore substitution into declared templates. A template names
the frame it exercises and the guide section that fixes its label; an axis names the
words substituted into it. Every case is a pair (template, word) drawn from tables in
`coverage.synonyms`, so the same run produces the same cases in the same order and
each one carries the reason it exists.

The mandate's own examples are all represented:

* `guaranteed -> assured -> certain -> promised` is the `guarantee_weakening` chain,
  and the chain reports which of those steps the evaluator already accepts rather
  than assuming the whole chain is a gap.
* `expand / expands / expanded / expanding` is the `movement_inflection` chain, which
  the evaluator already covers in full — a fact the generator records instead of
  quietly proposing work that is not needed.
* `Returns are guaranteed / Returns cannot be guaranteed / Returns are claimed to be
  guaranteed` is the frame-variant set, and all three are generated. The middle one is
  a labelled negative control: it is emitted with no expected category, so the set
  contains a wording a detector must *not* fire on. `synonyms.WITHHELD` records it for
  a different purpose — it is never turned into a repair *candidate* — and the earlier
  wording here said it was withheld from generation, which is not what the code does.

What generation refuses to do
-----------------------------

No generated case may enter a benchmark. `GeneratedCase` raises if
`excludes_from_benchmark` is false, and this module never writes to
`risk_evaluation/benchmarks/`. Generated cases live under
`risk_evaluation/coverage/generated_cases/` and are candidates for a *future*
benchmark, which is a decision for a human and a separate phase.

No candidate may reuse a case's literal text. `forbids_literal_case` is asserted for
every candidate the registry builds, and `withheld()` in `coverage.synonyms` lists the
adjacent wordings this framework declines to turn into repairs at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import freeze, lexicon, synonyms
from .model import GeneratedCase, write_json
from .taxonomy import FRAME_GAP, LEXICAL_GAP, MORPHOLOGY_GAP, SYNONYM_GAP

GENERATED_DIR = Path(__file__).with_name("generated_cases")
GENERATED_PATH = GENERATED_DIR / "generated_cases_r1.json"

#: Identifier prefix, so a generated case can never be mistaken for benchmark data.
CASE_PREFIX = "GEN-R1"


class GeneratorError(Exception):
    """Raised when generation would produce something it must not."""


#: Inflectional forms a template can require of its substituted word. A copular frame
#: needs a participle and a bare present-tense frame needs the third person singular;
#: substituting the lemma into either produces a sentence no annotator should have to
#: read, which is why the first run of this module emitted `Returns are vow.`
LEMMA = "lemma"
PARTICIPLE = "participle"
THIRD = "third"
FORMS = (LEMMA, PARTICIPLE, THIRD)


@dataclass(frozen=True, slots=True)
class Template:
    """A frame to substitute into, and the label the guide gives its instances."""

    template_id: str
    category: str
    relation: str
    pattern: str
    axis: str
    guide_basis: str
    failure_type: str = SYNONYM_GAP
    form: str = LEMMA
    language: str = "en"

    def __post_init__(self) -> None:
        if self.form not in FORMS:
            raise GeneratorError(
                f"template {self.template_id}: unknown form {self.form!r}"
            )

    def shape(self, word: str) -> str:
        """The word in the form this frame requires."""

        if self.form == LEMMA or " " in word or "-" in word:
            return word
        from ..v3.morphology import past_participle, third_person

        try:
            if self.form == PARTICIPLE:
                return past_participle(word)
            return third_person(word)
        except Exception as exc:  # noqa: BLE001 - a word that cannot inflect is a defect
            raise GeneratorError(
                f"template {self.template_id}: {word!r} cannot take the "
                f"{self.form} form ({exc})"
            ) from exc

    def render(self, word: str) -> str:
        shaped = self.shape(word)
        return self.pattern.format(word=shaped, Word=shaped[:1].upper() + shaped[1:])

    def render_verbatim(self, word: str) -> str:
        """Render without shaping, for a word that arrives already inflected.

        The declared chains quote surface forms — `guaranteed`, `assured`,
        `promised` — so passing one through `shape()` produced `promiseded`. A word a
        caller hands over in its final form is used as given.
        """

        return self.pattern.format(word=word, Word=word[:1].upper() + word[1:])


#: Templates. Each names the axis that supplies its words and the guide section that
#: fixes the label, so a reviewer can check the reasoning and not just the sentence.
TEMPLATES: tuple[Template, ...] = (
    Template(
        template_id="TPL-GUAR-COPULAR",
        category="financial_guarantee",
        relation="GUARANTEE",
        pattern="Returns are {word}.",
        axis="guarantee_predicate",
        guide_basis="Guide v2 section 7: an outcome made unconditional.",
        form=PARTICIPLE,
    ),
    Template(
        template_id="TPL-GUAR-ACTIVE",
        category="financial_guarantee",
        relation="GUARANTEE",
        pattern="We {word} that your capital is returned in full.",
        axis="guarantee_predicate",
        guide_basis="Guide v2 section 7: the author makes the outcome unconditional.",
    ),
    Template(
        template_id="TPL-RISK-ATTRIBUTIVE",
        category="financial_guarantee",
        relation="RISK_REMOVED",
        pattern="This is a {word} investment.",
        axis="risk_removed",
        guide_basis="Guide v2 section 7: risk denied outright without the word guarantee.",
    ),
    Template(
        template_id="TPL-PRED-CERTAINTY",
        category="market_prediction",
        relation="PREDICTION",
        pattern="Returns are {word}.",
        axis="certainty_carrier",
        guide_basis="Guide v2 section 2: author-voice certainty about a future outcome.",
    ),
    Template(
        template_id="TPL-PRED-MOVEMENT",
        category="market_prediction",
        relation="PREDICTION",
        pattern="Turnover {word} next quarter.",
        axis="movement_direction",
        guide_basis="Guide v2 section 2: the certainty is carried by a movement verb.",
        form=THIRD,
    ),
    Template(
        template_id="TPL-ADVICE-IMPERATIVE",
        category="investment_advice",
        relation="ADVICE",
        pattern="{Word} this fund.",
        axis="directive_verb",
        guide_basis="Guide v2 section 7: an action-directive aimed at the reader.",
    ),
    Template(
        template_id="TPL-ADVICE-SHOULD",
        category="investment_advice",
        relation="ADVICE",
        pattern="Investors should {word} this fund.",
        axis="directive_verb",
        guide_basis="Guide v2 section 7: a directive addressed to the reader.",
    ),
    Template(
        template_id="TPL-ADVICE-POSITION",
        category="investment_advice",
        relation="ADVICE",
        pattern="You should be {word} into the next quarter.",
        axis="position_word",
        guide_basis="Guide v2 section 7: advice named by the position it recommends.",
    ),
    Template(
        template_id="TPL-SOURCE-REPORTED",
        category="unverified_information",
        relation="PREDICTION",
        pattern="The {word} is that returns will triple.",
        axis="reported_source",
        guide_basis=(
            "Guide v2: a claim carried from a source that is not the author. The "
            "evaluator has no v3 relation for this category, so the case is generated "
            "for human review rather than as a vocabulary extension."
        ),
        failure_type=LEXICAL_GAP,
    ),
    Template(
        template_id="TPL-PRESSURE-URGENCY",
        category="emotional_manipulation",
        relation="PREDICTION",
        pattern="Buy now, {word}.",
        axis="urgency_pressure",
        guide_basis=(
            "Guide v2 section 8: pressure applied through urgency. No v3 relation "
            "exists for this category, so the case is for human review only."
        ),
        failure_type=LEXICAL_GAP,
    ),
)


def template(template_id: str) -> Template:
    for item in TEMPLATES:
        if item.template_id == template_id:
            return item
    raise GeneratorError(f"no template named {template_id!r}")


def frame_cases() -> tuple[GeneratedCase, ...]:
    """The declared frame variants, including the withheld control.

    A variant whose `expects_finding` is false is emitted with the label the guide
    gives it, so the expansion set contains a negative example as well as positive
    ones. Generating only the wordings a detector should catch would make the set
    unable to detect a detector that catches everything.
    """

    out: list[GeneratedCase] = []
    for index, variant in enumerate(synonyms.FRAME_VARIANTS, start=1):
        expected = (variant.category,) if variant.expects_finding else ()
        out.append(
            GeneratedCase(
                case_id=f"{CASE_PREFIX}-FRAME-{index:04d}",
                text=variant.text,
                expected_categories=expected,
                generation_rule=variant.variant_id,
                generation_reason=variant.guide_basis,
                failure_type=FRAME_GAP if variant.expects_finding else LEXICAL_GAP,
                risk_category=variant.category,
                parent_case=variant.variant_id,
                source_table="synonyms.FRAME_VARIANTS",
                language="en",
            )
        )
    return tuple(out)


def chain_cases() -> tuple[GeneratedCase, ...]:
    """One case per step of a declared chain, so covered steps are visible.

    The chain's declared `forms` decides how each step is substituted. A surface-form
    chain is rendered verbatim, because its words are already inflected; a lemma chain
    goes through the template's shaping, because a lemma in a third-person frame reads
    `Turnover skyrocket next quarter.`
    """

    out: list[GeneratedCase] = []
    for chain in synonyms.CHAINS:
        for step, (word, known) in enumerate(chain.steps, start=1):
            if known:
                continue
            axis = _axis_for_chain(chain.name)
            template_item = _template_for_axis(axis)
            if template_item is None:
                continue
            if chain.forms == synonyms.SURFACE:
                text = template_item.render_verbatim(word)
            else:
                text = template_item.render(word)
            out.append(
                GeneratedCase(
                    case_id=f"{CASE_PREFIX}-CHAIN-{chain.name.upper()}-{step:02d}",
                    text=text,
                    expected_categories=(chain.category,),
                    generation_rule=f"chain:{chain.name}:{word}",
                    generation_reason=(
                        f"{chain.guide_basis} The word {word!r} is the first step of "
                        f"chain {chain.name!r} the evaluator does not accept."
                    ),
                    failure_type=SYNONYM_GAP,
                    risk_category=chain.category,
                    parent_case="",
                    source_table="synonyms.CHAINS",
                )
            )
    return tuple(out)


def axis_cases() -> tuple[GeneratedCase, ...]:
    """Every novel synonym of every auto-generatable axis, in its template."""

    out: list[GeneratedCase] = []
    for item in TEMPLATES:
        axis = synonyms.axis(item.axis)
        if not axis.auto_generatable:
            # No relation to extend. The case is still worth generating for review,
            # and its expected label comes from the guide, not from a vocabulary.
            for word in axis.novel:
                out.append(
                    _case(item, word, axis, review_only=True)
                )
            continue
        for word in axis.novel:
            out.append(_case(item, word, axis, review_only=False))
    return tuple(out)


def _case(
    item: Template, word: str, axis: synonyms.Axis, *, review_only: bool
) -> GeneratedCase:
    return GeneratedCase(
        case_id=f"{CASE_PREFIX}-{item.template_id[4:]}-{_slug(word)}",
        text=item.render(word),
        expected_categories=(item.category,),
        generation_rule=f"template:{item.template_id}:axis:{axis.name}:{word}",
        generation_reason=(
            f"{item.guide_basis} The word {word!r} belongs to axis {axis.name!r}, "
            f"whose canonical words the evaluator matches as "
            f"{', '.join(axis.canonical)}."
            + (
                " No v3 relation exists for this category, so the case is generated "
                "for human review and is not a vocabulary proposal."
                if review_only
                else ""
            )
        ),
        failure_type=item.failure_type,
        risk_category=item.category,
        parent_case="",
        source_table=f"synonyms.AXES[{axis.name}]",
    )


def _slug(word: str) -> str:
    return "-".join(word.upper().replace("-", " ").split())


def _axis_for_chain(name: str) -> str:
    return {
        "guarantee_weakening": "guarantee_predicate",
        "movement_inflection": "movement_direction",
        "movement_lexical": "movement_direction",
        "directive_phrasal": "directive_verb",
    }[name]


def _template_for_axis(axis_name: str) -> Template | None:
    for item in TEMPLATES:
        if item.axis == axis_name:
            return item
    return None


def generate() -> tuple[GeneratedCase, ...]:
    """Every generated case, deduplicated by text and stably ordered."""

    seen: dict[str, GeneratedCase] = {}
    for case in frame_cases() + chain_cases() + axis_cases():
        seen.setdefault(case.text, case)
    return tuple(seen[key] for key in sorted(seen, key=lambda text: (len(text), text)))


def observe(cases: Sequence[GeneratedCase]) -> dict[str, Any]:
    """Run the frozen evaluator over the generated set and record what it does.

    This is the only place the generator touches the evaluator, and it only reads.
    The record is what makes the expansion set measurable: a case the evaluator
    already handles is evidence that a candidate is unnecessary, and a case it misses
    is evidence that one is.
    """

    from ..v3_independent import dataset as calibration
    from ..v3_independent import evaluation

    records = []
    for case in cases:
        record = dict(calibration.load_records()[0])
        record["id"] = case.case_id
        record["text"] = case.text
        record["expected_categories"] = list(case.expected_categories)
        records.append(record)
    results = evaluation.predict(records)
    observed: dict[str, Any] = {}
    for case, result in zip(cases, results):
        expected = set(case.expected_categories)
        predicted = set(result.predicted)
        if expected == predicted:
            verdict = "already_handled"
        elif predicted - expected:
            verdict = "over_triggered"
        elif expected - predicted:
            verdict = "missed"
        else:
            verdict = "unclear"
        observed[case.case_id] = {
            "expected": sorted(expected),
            "predicted": sorted(predicted),
            "verdict": verdict,
        }
    return observed


def payload(cases: Sequence[GeneratedCase] | None = None) -> dict[str, Any]:
    """The generated-case artifact, including what the evaluator currently does."""

    cases = tuple(cases if cases is not None else generate())
    observed = observe(cases)
    verdicts: dict[str, int] = {}
    for item in observed.values():
        verdicts[item["verdict"]] = verdicts.get(item["verdict"], 0) + 1
    return {
        "phase": "R1",
        "artifact": "adversarial-expansion-set",
        "source_hash": freeze.source_digest(),
        "benchmark_hash": freeze.benchmark_digest(),
        "evaluator_hash": freeze.evaluator_digest(),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "count": len(cases),
        "verdicts": dict(sorted(verdicts.items())),
        "templates": [
            {
                "template_id": item.template_id,
                "category": item.category,
                "relation": item.relation,
                "pattern": item.pattern,
                "axis": item.axis,
                "form": item.form,
                "guide_basis": item.guide_basis,
            }
            for item in TEMPLATES
        ],
        "withheld": [
            {"text": item.text, "category": item.category, "reason": item.reason}
            for item in synonyms.WITHHELD
        ],
        "cases": [
            {**case.as_dict(), "observed": observed[case.case_id]} for case in cases
        ],
        "not_a_benchmark": (
            "these cases are generated material for review. They are excluded from "
            "every registered benchmark by construction, and nothing here writes to "
            "risk_evaluation/benchmarks/."
        ),
    }


def write(path: str | Path | None = None, cases: Sequence[GeneratedCase] | None = None) -> Path:
    target = Path(path) if path is not None else GENERATED_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json(target, payload(cases))
    return target


def describe() -> dict[str, object]:
    cases = generate()
    return {
        "templates": len(TEMPLATES),
        "cases": len(cases),
        "withheld": len(synonyms.WITHHELD),
        "sources": sorted({case.source_table for case in cases}),
        "note": "structured substitution only: no random text, no model, no network",
    }
