"""Failure analyzer: read the Phase 8.9 benchmark, explain every failure.

This module measures. It never repairs, never edits a label, and never writes to the
evaluator. Its whole output is a list of `FailureRecord`s and the artifact built from
them, each carrying the observations that justify its classification.

Where the evidence comes from
-----------------------------

Nothing here is inferred from the case text alone, because a text-only reading cannot
tell a missing word from a missing rule. Three independent sources are combined:

*The evaluator's own trace.* `CaseResult` carries the relations it expected and found,
the speakers and stances it resolved, and a `veto:` or `capability:` line whenever a
capability layer examined the structure and declined it. A decline is decisive
evidence: the structure was looked at and rejected, so no vocabulary addition would
have changed that case.

*The frozen lexicons, read-only.* `coverage.lexicon` answers whether a token is a word
the evaluator spells out, an inflected form of one it declares as a lemma, or neither.

*The declared tables.* `coverage.synonyms` supplies the synonym axes, so a failure
whose text contains `plummet` is attributed to a named axis rather than to a hunch.

Why the thresholds are where they are
-------------------------------------

Two gates were set by measurement, not taste, and both were wrong in the first draft.

**Speaker mismatch is not evidence by itself.** The evaluator resolves `('unknown',)`
for 280 of 300 cases while the label says `author` for 193 of them, so treating a
mismatch as an attribution failure would have reported roughly a hundred attribution
gaps. The Phase 8.9 adjudication found four. A mismatch therefore counts only when it
is material: the label's speaker is a third party while the evaluator asserted an
author-voice category, the label is author-voice while the evaluator asserted
unverified sourcing, or the evaluator's own trace named attribution as decisive.

**Not every annotator disagreement makes the label doubtful.** 95 cases carry a
field-level dispute, but 33 of those disputes are about `certainty`, `stance` or
`speaker` — fields the decision set does not turn on. Only a dispute about the
decision set itself (fields `decision` or `intent`) is classified as an
ANNOTATION_CONFLICT, which keeps the type meaningful instead of draining every other
signal into it.

The analyzer also records what it could not explain. A failing case that produces no
evidence at all is reported as UNKNOWN rather than dropped, because a silent omission
is how a coverage number becomes a comfortable fiction.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import lexicon, synonyms, taxonomy
from .model import (
    EVIDENCE_KINDS,
    Evidence,
    FailureAnalysis,
    FailureRecord,
    RepairCandidate,
    write_json,
)

#: Directories the analyzer reads from. It writes to neither.
CALIBRATION_ID = "risk/independent/v1"
ANALYSIS_PATH = Path(__file__).with_name("failure_analysis_r1.json")

#: Fields a dispute must touch for the label itself to be in doubt.
DECISION_FIELDS = ("decision", "intent")

#: Categories that only the author's own voice can carry.
AUTHOR_VOICE = ("market_prediction", "emotional_manipulation")

#: Categories that imply a source other than the author.
NON_AUTHOR_VOICE = ("unverified_information",)

#: Relations per category, so a lemma hit can be checked for relevance.
CATEGORY_RELATIONS: Mapping[str, tuple[str, ...]] = {
    "financial_guarantee": ("GUARANTEE", "RISK_REMOVED"),
    "market_prediction": ("PREDICTION",),
    "investment_advice": ("ADVICE",),
}


class AnalyzerError(Exception):
    """Raised when the analyzer cannot produce a defensible record."""


def _band(value: float) -> str:
    if value >= 0.9:
        return "high"
    if value >= 0.7:
        return "moderate"
    if value >= 0.5:
        return "low"
    return "very low"


@dataclass(frozen=True, slots=True)
class AdjudicationView:
    """The adjudication files, indexed for lookup by case id."""

    disputed_fields: Mapping[str, tuple[str, ...]]
    resolutions: Mapping[str, tuple[str, ...]]
    unresolved: frozenset[str]
    third_readings: frozenset[str]

    @staticmethod
    def load(directory: str | Path) -> "AdjudicationView":
        directory = Path(directory)
        adjudicated = json.loads(
            (directory / "adjudicated.json").read_text(encoding="utf-8")
        )
        disputed: dict[str, tuple[str, ...]] = {}
        resolutions: dict[str, list[str]] = {}
        unresolved: set[str] = set()
        third: set[str] = set()
        for case in adjudicated["cases"]:
            case_id = case["case_id"]
            disputed[case_id] = tuple(case.get("disputed_fields") or ())
            if case.get("unresolved_fields"):
                unresolved.add(case_id)
            for ruling in case.get("rulings") or ():
                resolution = str(ruling.get("resolution") or "")
                resolutions.setdefault(case_id, []).append(resolution)
                if resolution in ("third_reading", "unresolved"):
                    third.add(case_id)
                    if resolution == "unresolved":
                        unresolved.add(case_id)
        return AdjudicationView(
            disputed_fields=disputed,
            resolutions={k: tuple(v) for k, v in resolutions.items()},
            unresolved=frozenset(unresolved),
            third_readings=frozenset(third - unresolved),
        )


@dataclass(frozen=True, slots=True)
class SignalCensus:
    """How often each signal fired, so a threshold can be judged against data."""

    counts: Mapping[str, int]

    def as_dict(self) -> dict[str, int]:
        return dict(sorted(self.counts.items()))


#: Veto reasons that are about structure rather than about vocabulary. A veto that
#: says a boundary looked for a financial object and did not find one is a lexicon
#: observation in disguise; a veto that says the subject was third-person is not.
STRUCTURAL_VETO_MARKERS = ("subject", "imperative", "modal", "no-relation", "structure")
LEXICAL_VETO_MARKERS = ("object", "no_directive", "keyword")


def _structural_vetoes(lines: Sequence[str]) -> tuple[str, ...]:
    """Vetoes that indict the frame rather than the word list."""

    out: list[str] = []
    for line in lines:
        if not line.startswith("veto:"):
            continue
        lowered = line.lower()
        if any(marker in lowered for marker in LEXICAL_VETO_MARKERS):
            continue
        if any(marker in lowered for marker in STRUCTURAL_VETO_MARKERS):
            out.append(line)
    return tuple(out)


#: Words that cue a relation, so their presence means the frame had something to
#: match and declined anyway.
_CUE_TABLES: Mapping[str, tuple[str, ...]] = {
    "ADVICE": ("v3.patterns.DIRECTIVES", "v3_1.advice.POSITION_LEMMAS"),
    "PREDICTION": ("v3.patterns.MOVEMENT_VERBS", "v3.patterns.CERTAINTY_ADJECTIVES"),
    "GUARANTEE": ("v3.patterns.GUARANTORS",),
    "RISK_REMOVED": (),
}


@lru_cache(maxsize=1)
def _relation_for_origin() -> Mapping[str, str]:
    """Which relation a lexicon slice's origin belongs to, if any."""

    out: dict[str, str] = {}
    frames = lexicon.relation_frames()
    for item in lexicon.slices():
        for relation in frames:
            if f".{relation}." in item.origin or item.origin.endswith(f".{relation}"):
                out[item.origin] = relation
                break
    return out


def _relation_for_slice(origin: str) -> str | None:
    return _relation_for_origin().get(origin)
def _relation_cue_words() -> Mapping[str, frozenset[str]]:
    """The words that cue each relation, so a frame gap can be told from a word gap."""

    out: dict[str, frozenset[str]] = {}
    for relation in lexicon.relation_frames():
        words: set[str] = set()
        prefixes = _CUE_TABLES.get(relation, ())
        for item in lexicon.slices():
            if item.lemmas:
                continue
            if not any(item.origin.startswith(prefix) for prefix in prefixes):
                continue
            words.update(item.words)
        out[relation] = frozenset(words)
    return out


def _relation_cue_evidence(
    text: str, expected_relations: Sequence[str]
) -> Evidence | None:
    """A cue word for an expected relation, present in the text.

    This is what separates a frame gap from a word gap. If the text carries a
    directive, a movement verb or a certainty adjective and the relation still did not
    fire, the frame is the problem; if it carries none of them and no known entity
    either, the word list is.
    """

    lowered = text.lower()
    tables = _relation_cue_words()
    for relation in expected_relations:
        for word in tables.get(relation, frozenset()):
            if " " in word:
                continue
            if re.search(rf"\b{re.escape(word)}\b", lowered):
                return Evidence(
                    "relation_cue_present",
                    f"the text carries the cue {word!r} for {relation}, so the frame "
                    "had something to match and declined",
                    "direct",
                )
    return None


def _morphology_evidence(
    text: str, expected_relations: Sequence[str]
) -> Evidence | None:
    """A token that inflects to a lemma the evaluator declares, when relevant.

    Relevance is checked so an incidental hit cannot be reported as the cause: the
    lemma's own slice must belong to a relation the case expected. Without that gate
    every case containing any inflected verb would look like a morphology gap.
    """

    hits: list[tuple[str, str]] = []
    for token in lexicon.tokens(text):
        lemma = lexicon.morphology_hit(token)
        if lemma is None:
            continue
        origins = lexicon.origin_of(lemma)
        relations = {_relation_for_slice(origin) for origin in origins}
        relations.discard(None)
        if expected_relations and not (relations & set(expected_relations)):
            continue
        hits.append((token, lemma))
    if not hits:
        return None
    detail = ", ".join(f"{token}->{lemma}" for token, lemma in hits[:6])
    return Evidence(
        "known_lemma_unmatched_form",
        f"inflected forms of declared lemmas appear but are not listed: {detail}",
        "direct",
    )


def _synonym_evidence(
    text: str, category: str | None
) -> tuple[Evidence | None, str | None]:
    """A declared synonym present in the text, with the axis it belongs to."""

    lowered = text.lower()
    for axis in synonyms.AXES:
        if category is not None and axis.category != category:
            continue
        for word in axis.novel:
            if word in lowered:
                return (
                    Evidence(
                        "declared_synonym_present",
                        f"axis {axis.name!r}: the declared synonym {word!r} appears in "
                        f"the text, while the evaluator matches "
                        f"{', '.join(axis.canonical)} instead",
                        "direct",
                    ),
                    axis.name,
                )
    return None, None


def _speaker_evidence(
    record: Mapping[str, Any], result: Any, decisive_lines: Sequence[str]
) -> Evidence | None:
    """A speaker mismatch, admitted only when it is material to the outcome."""

    intended = str(record.get("speaker") or "unknown")
    observed = tuple(result.speakers)
    if not observed:
        return None
    if intended in observed:
        return None
    predicted = set(result.predicted)
    expected = set(result.expected)
    material = False
    ground = ""
    if predicted & set(AUTHOR_VOICE) and intended == "third_party":
        material, ground = True, "the evaluator asserted an author-voice category"
    elif predicted & set(NON_AUTHOR_VOICE) and intended == "author":
        material, ground = True, "the evaluator asserted non-author sourcing"
    elif expected & set(AUTHOR_VOICE) and intended == "author" and "unknown" in observed:
        named = [line for line in decisive_lines if "speaker" in line or "attribution" in line]
        if named:
            material, ground = True, f"the trace named attribution: {named[0]}"
    if not material:
        return None
    return Evidence(
        "speaker_mismatch",
        f"the label's speaker is {intended!r} and the evaluator resolved "
        f"{observed}; {ground}",
        "direct",
    )


def _stance_evidence(
    record: Mapping[str, Any], result: Any
) -> tuple[Evidence | None, bool]:
    """A stance mismatch, plus whether the speakers agreed.

    Gated on the evaluator having asserted something. When no relation fired and no
    category was predicted, the resolved stance is a default rather than a reading, so
    treating it as a disagreement reported 123 stance gaps out of 151 failures — a
    number that says nothing about stance and everything about the gate being absent.
    """

    if not result.found_relations and not result.predicted:
        return None, False
    intended = str(record.get("stance") or "unknown")
    observed = tuple(result.stances)
    speakers_match = str(record.get("speaker") or "unknown") in tuple(result.speakers)
    if intended in observed or not observed:
        return None, speakers_match
    return (
        Evidence(
            "stance_mismatch",
            f"the label's stance is {intended!r} and the evaluator resolved {observed} "
            "while asserting a finding",
            "direct",
        ),
        speakers_match,
    )


def evidence_for(
    record: Mapping[str, Any],
    result: Any,
    view: AdjudicationView,
    catalogue: Counter[str],
) -> tuple[Evidence, ...]:
    """Every observation that bears on this case, in precedence order."""

    case_id = str(record["id"])
    evidence: list[Evidence] = []

    if case_id in view.unresolved:
        evidence.append(
            Evidence(
                "annotation_unresolved",
                "the adjudication recorded this case as unresolved, so the expected "
                "label is not settled",
                "direct",
            )
        )
    if case_id in view.third_readings:
        evidence.append(
            Evidence(
                "adjudicator_third_reading",
                "the adjudicator resolved this case by a reading neither annotator "
                "proposed, which means the taxonomy itself did not settle it",
                "direct",
            )
        )
    disputed = view.disputed_fields.get(case_id, ())
    if disputed:
        catalogue["disputed_any_field"] += 1
        decision_fields = tuple(f for f in disputed if f in DECISION_FIELDS)
        if decision_fields:
            catalogue["disputed_decision_field"] += 1
            evidence.append(
                Evidence(
                    "annotators_disagreed",
                    "the annotators differed on "
                    + ", ".join(decision_fields)
                    + ", so the label this case is scored against was itself contested",
                    "direct",
                )
            )
        else:
            catalogue["disputed_other_field_only"] += 1
            evidence.append(
                Evidence(
                    "annotators_disagreed_elsewhere",
                    "the annotators differed on "
                    + ", ".join(disputed)
                    + ", which the decision set does not turn on",
                    "direct",
                )
            )

    decisive_lines = [
        line
        for line in list(result.evidence)
        + [f"{item.get('rule')}:{item.get('reason')}" for item in result.suppressed]
        if line.startswith("veto:") or line.startswith("capability:")
    ]

    speaker = _speaker_evidence(record, result, decisive_lines)
    if speaker is not None:
        evidence.append(speaker)
    else:
        evidence.append(
            Evidence(
                "speaker_match",
                "the label's speaker is not contradicted decisively, so an "
                "attribution failure is not claimed",
                "inferred",
            )
        )
    stance, speakers_match = _stance_evidence(record, result)
    if stance is not None:
        evidence.append(stance)
    if speaker is None and speakers_match:
        evidence.append(
            Evidence(
                "speaker_match_for_stance",
                "the speakers do not differ decisively, so a stance difference would "
                "be the whole explanation",
                "inferred",
            )
        )

    text = str(record.get("text") or result.text)
    expected = tuple(result.expected)
    expected_relations = tuple(result.expected_relations)
    category = expected[0] if len(expected) == 1 else None

    morph = _morphology_evidence(text, expected_relations)
    if morph is not None:
        catalogue["morphology_hit"] += 1
        evidence.append(morph)

    synonym_evidence, axis_name = _synonym_evidence(text, category)
    if synonym_evidence is not None:
        catalogue["declared_synonym_present"] += 1
        evidence.append(synonym_evidence)

    hooks = lexicon.entity_hooks(text)
    if hooks:
        catalogue["entity_hooks_present"] += 1
        evidence.append(
            Evidence(
                "hooks_present",
                f"the text names entities the evaluator knows: {', '.join(hooks[:6])}",
                "direct",
            )
        )
    else:
        catalogue["no_entity_hook"] += 1
        evidence.append(
            Evidence(
                "no_hook_at_all",
                "the text names no entity the evaluator's lexicon recognises, so no "
                "frame could have matched however it was worded",
                "inferred",
            )
        )

    if expected_relations and not result.found_relations:
        catalogue["relation_expected_not_found"] += 1
        evidence.append(
            Evidence(
                "no_frame_matched",
                f"the label expects {', '.join(expected_relations)} and the evaluator "
                "found no relation at all",
                "direct",
            )
        )
        cue = _relation_cue_evidence(text, expected_relations)
        if cue is not None:
            catalogue["relation_cue_present"] += 1
            evidence.append(cue)
        elif morph is None and synonym_evidence is None:
            catalogue["no_relation_cue"] += 1
            evidence.append(
                Evidence(
                    "no_relation_cue",
                    f"the text carries no cue word for {', '.join(expected_relations)} "
                    "in any form the evaluator declares, and no declared synonym or "
                    "inflected form either, so the relation had nothing to match",
                    "inferred",
                )
            )
    structural = _structural_vetoes(decisive_lines)
    if structural and not result.found_relations:
        catalogue["capability_declined"] += 1
        evidence.append(
            Evidence(
                "capability_declined",
                "the evaluator's own trace shows a capability layer examined the "
                f"structure and declined it: {structural[0][:120]}",
                "direct",
            )
        )
    if result.found_relations and set(result.found_relations) - set(expected_relations):
        evidence.append(
            Evidence(
                "relation_misattributed",
                f"the evaluator found {', '.join(result.found_relations)} where the "
                f"label expects {', '.join(expected_relations) or '(none)'}",
                "direct",
            )
        )
    evidence.append(
        Evidence(
            "prediction_outcome",
            f"expected {list(result.expected) or '(none)'} and predicted "
            f"{list(result.predicted) or '(none)'}",
            "declared",
        )
    )
    return tuple(evidence)


def _category_for(result: Any) -> tuple[str, str]:
    """Which category a repair is about, and on what authority.

    A false positive has no expected category, so the category the evaluator wrongly
    asserted is used and the ground is recorded as such. The alternative — leaving it
    blank — hides which category a suppression would have to fix. When nothing at all
    is available the literal `unclassified` is used, so the record still names its
    subject instead of failing the invariant silently.
    """

    expected = tuple(result.expected)
    if len(expected) == 1:
        return expected[0], "expected"
    if expected:
        return expected[0], "first-of-many-expected"
    predicted = tuple(result.predicted)
    if predicted:
        return predicted[0], "asserted-but-unlabelled"
    return "unclassified", "unknown"


def _outcome_for(result: Any) -> str:
    expected = set(result.expected)
    predicted = set(result.predicted)
    if expected and predicted and expected != predicted:
        if predicted - expected and expected - predicted:
            return "misattribution"
        if predicted - expected:
            return "false_positive"
        return "false_negative"
    if predicted - expected:
        return "false_positive"
    if expected - predicted:
        return "false_negative"
    return "failure"


def build_case(
    record: Mapping[str, Any],
    result: Any,
    view: AdjudicationView,
    catalogue: Counter[str],
) -> FailureRecord:
    """One failure, classified and explained, or a record that says why not."""

    evidence = evidence_for(record, result, view, catalogue)
    expected = tuple(result.expected)
    category, category_ground = _category_for(result)
    failure_type, _rule = taxonomy.classify(evidence)
    if failure_type == taxonomy.UNKNOWN and not any(
        item.name == "annotation_unresolved" for item in evidence
    ):
        # The taxonomy has no rule for this case. Recorded as an observation so the
        # artifact shows why the case is unexplained, instead of leaving a gap a
        # reader would have to infer from the absence of a reason.
        catalogue["no_rule_matched"] += 1
        evidence = evidence + (
            Evidence(
                "no_rule_matched",
                "no rule in the taxonomy accounts for this failure; the evaluator "
                "asserted a category the label does not carry and the text offers no "
                "missing word to blame",
                "inferred",
            ),
        )
    axis_name = _axis_name_from(evidence)
    frame = record.get("frame") or {}
    return taxonomy.build_record(
        case_id=str(record["id"]),
        input_text=str(record.get("text") or ""),
        expected=expected,
        actual=tuple(result.predicted),
        evidence=evidence,
        risk_category=category,
        additions=_additions_for(failure_type, axis_name, evidence),
        target=_target_for(failure_type, axis_name),
        outcome=_outcome_for(result),
        language=str(frame.get("language") or result.language or ""),
        group=str(result.group or ""),
        form=str(frame.get("form") or result.form or ""),
        source_type=str(result.source_type or ""),
        intended_intent=str(frame.get("intended_intent") or ""),
        expected_relations=tuple(result.expected_relations),
        found_relations=tuple(result.found_relations),
        detail=f"{category_ground}: {taxonomy.MEANING[failure_type]}",
    )


def _axis_name_from(evidence: Sequence[Evidence]) -> str | None:
    """Recover the axis an evidence item names.

    Matched against the declared axis names rather than by splitting on quotes: the
    detail quotes both the synonym and the axis, and a positional parse silently
    returned the synonym — which then failed to resolve as an axis.
    """

    for item in evidence:
        if item.name != "declared_synonym_present":
            continue
        for axis in synonyms.AXES:
            if repr(axis.name) in item.detail:
                return axis.name
    return None


def _additions_for(
    failure_type: str,
    axis_name: str | None,
    evidence: Sequence[Evidence],
) -> tuple[str, ...]:
    """Words a repair would add, from the declared axis only.

    Never the case's own text. A repair that quoted this sentence's nouns would
    improve this case and nothing else, which is the one thing the framework is built
    to refuse.
    """

    if failure_type == taxonomy.SYNONYM_GAP and axis_name:
        return synonyms.axis(axis_name).novel
    if failure_type == taxonomy.MORPHOLOGY_GAP:
        for item in evidence:
            if item.name != "known_lemma_unmatched_form":
                continue
            forms: list[str] = []
            for chunk in item.detail.split(":")[-1].split(","):
                token = chunk.strip().split("->")[0].strip()
                if token:
                    forms.append(token)
            return tuple(forms)
    return ()


def _target_for(failure_type: str, axis_name: str | None) -> str:
    """What a repair aims at, decided by the failure type before anything else.

    The order matters. A case can carry both a synonym observation and a morphology
    observation, and the classifier picks the higher-precedence one; reading `axis_name`
    first then labelled a MORPHOLOGY_GAP and even an ANNOTATION_CONFLICT with an axis
    they do not target, which is how `axis:position_word | MORPHOLOGY_GAP` reached the
    dashboard.
    """

    if failure_type == taxonomy.MORPHOLOGY_GAP:
        return "morphology:declared-lemma-forms"
    if failure_type == taxonomy.FRAME_GAP:
        return "frame:relation"
    if failure_type == taxonomy.LEXICAL_GAP:
        return "lexicon:entities"
    if failure_type == taxonomy.SYNONYM_GAP:
        return f"axis:{axis_name}" if axis_name else "axis:undeclared"
    return "human-review"


def analyze(
    records: Sequence[Mapping[str, Any]] | None = None,
    *,
    directory: str | Path | None = None,
    analysis_path: str | Path | None = None,
) -> FailureAnalysis:
    """Run the frozen evaluator over the benchmark and explain every failure.

    Only failures produce records. A case the evaluator got right is not a coverage
    gap, and including it would inflate every count in the report.
    """

    from ..v3_independent import dataset as calibration
    from ..v3_independent import evaluation

    if records is None:
        records = calibration.load_records(directory)
    records = list(records)
    if not records:
        raise AnalyzerError("no benchmark records were supplied")

    view = AdjudicationView.load(directory or calibration.BENCHMARK_DIR)
    results = evaluation.predict(records)
    by_id = {str(record["id"]): record for record in records}

    catalogue: Counter[str] = Counter()
    failures: list[FailureRecord] = []
    for result in results:
        if set(result.expected) == set(result.predicted):
            continue
        record = by_id.get(result.case_id)
        if record is None:
            raise AnalyzerError(f"no record for result {result.case_id}")
        failures.append(build_case(record, result, view, catalogue))

    analysis = FailureAnalysis(
        cases=len(results),
        failures=tuple(failures),
        by_type=taxonomy.counts_by_type(failures),
    )
    _ = names_of(analysis)
    if analysis_path is not None:
        write_json(Path(analysis_path), analysis)
    return analysis


def names_of(analysis: FailureAnalysis) -> tuple[str, ...]:
    return tuple(record.case_id for record in analysis.failures)


def metrics() -> dict[str, object]:
    """The Phase 8.9 scores, read from the phase's own evaluator, not restated.

    The primary scope is the resolved cases: the evaluator's own report excludes the
    three cases whose adjudication never settled a field, and re-deriving the figures
    from all 300 would quietly disagree with the phase it is measuring.
    """

    from ..v3_independent import dataset as calibration
    from ..v3_independent import evaluation

    records = calibration.load_records()
    report = evaluation.evaluate(records)
    primary = report["primary"]
    return {
        "benchmark": calibration.BENCHMARK_ID,
        "benchmark_version": calibration.BENCHMARK_VERSION,
        "cases": len(records),
        "scope": primary["scope"],
        "scored_cases": primary["cases"],
        "precision": primary["precision"],
        "recall": primary["recall"],
        "f1": primary["f1"],
        "accuracy": primary["accuracy"],
        "confusion": {
            "tp": primary["true_positives"],
            "fp": primary["false_positives"],
            "fn": primary["false_negatives"],
            "tn": primary["true_negatives"],
        },
        "unresolved_cases": report["unresolved"]["case_ids"],
        "relation": {
            key: report["relation"][key]
            for key in ("tp", "fp", "fn", "tn", "precision", "recall", "f1")
        },
    }


def summary(analysis: FailureAnalysis) -> dict[str, object]:
    """Aggregate view: distribution, confidence, and the shape of the failures."""

    by_type = Counter(record.failure_type for record in analysis.failures)
    by_group = Counter(record.group for record in analysis.failures)
    by_language = Counter(record.language for record in analysis.failures)
    by_form = Counter(record.form for record in analysis.failures)
    by_source = Counter(record.source_type for record in analysis.failures)
    by_category = Counter(
        record.expected[0] if record.expected else "(none)"
        for record in analysis.failures
    )
    bands = Counter(
        _band(record.confidence)
        for record in analysis.failures
        if record.evidence
    )
    auto = sum(
        1 for record in analysis.failures if record.failure_type in taxonomy.AUTO_GENERATABLE
    )
    human = sum(
        1 for record in analysis.failures if record.failure_type in taxonomy.HUMAN_REQUIRED
    )
    return {
        "cases": analysis.cases,
        "failures": len(analysis.failures),
        "by_type": dict(by_type.most_common()),
        "by_group": dict(by_group.most_common()),
        "by_language": dict(by_language.most_common()),
        "by_form": dict(by_form.most_common()),
        "by_source_type": dict(by_source.most_common()),
        "by_expected_category": dict(by_category.most_common()),
        "confidence_bands": dict(bands.most_common()),
        "mean_confidence": round(analysis.mean_confidence, 4),
        "auto_generatable": auto,
        "human_required": human,
    }


def payload(
    analysis: FailureAnalysis, catalogue: Mapping[str, int] | None = None
) -> dict[str, object]:
    """The artifact body: what was measured, against what, and what it found."""

    from . import freeze

    return {
        "phase": "R1",
        "framework": "risk-coverage-expansion",
        "calibration_id": CALIBRATION_ID,
        "source_hash": freeze.source_digest(),
        "benchmark_hash": freeze.benchmark_digest(),
        "evaluator_hash": freeze.evaluator_digest(),
        "failure_types": list(taxonomy.FAILURE_TYPES),
        "metrics": metrics(),
        "summary": summary(analysis),
        "signal_census": dict(sorted((catalogue or {}).items())),
        "table_report": synonyms.validate().describe(),
        "lexicon": lexicon.describe(),
        "failures": [record.as_dict() for record in analysis.failures],
        "note": (
            "analysis only: no evaluator file, benchmark label or decision policy was "
            "modified, and no candidate has been applied"
        ),
    }


def census(analysis: FailureAnalysis) -> SignalCensus:
    """Signal counts for a completed analysis."""

    counts: Counter[str] = Counter()
    for record in analysis.failures:
        for item in record.evidence:
            counts[item.name] += 1
    counts["failures"] = len(analysis.failures)
    counts["cases"] = analysis.cases
    return SignalCensus(counts=dict(counts))
