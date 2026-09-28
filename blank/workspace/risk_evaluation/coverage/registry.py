"""Candidate registry: the human review queue.

The framework proposes; it does not decide. Three directories hold the three states,
and the asymmetry between them is the design.

`pending/` is what the framework writes by default. A candidate lands here when the
analysis supports it and a human has not ruled on it.

`rejected/` is written only for rejections that can be *proved* from the framework's
own tables, with no judgement involved: the proposed words are already in the
lexicon, the proposal quotes the failing case's own text, or the target is a frozen
path this phase may not touch. A rejection that needed an opinion would be a decision
wearing a rejection's clothes.

`accepted/` is never written by this framework at all. Acceptance changes evaluator
behaviour and has to be earned against a benchmark that did not exist when the
candidate was made — so the directory carries a README stating that, and the code
that writes it does not exist.

Each candidate is named for what it covers, not for the case that produced it. The
grouping key is `(failure_type, target, risk_category)`, so twelve cases missing the
same axis become one candidate over twelve cases. A candidate per case would be a
list of twelve single-case rules, which is the thing the mandate forbids and the
thing that would not generalize.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import freeze, lexicon, synonyms
from .model import (
    ACCEPTED,
    PENDING,
    REJECTED,
    RECOMMEND_ACCEPT,
    RECOMMEND_DEFER,
    RECOMMEND_REJECT,
    CoverageCandidate,
    FailureAnalysis,
    FailureRecord,
    ReviewDecision,
    write_json,
)
from .generator import GeneratedCase
from .taxonomy import AUTO_GENERATABLE, HUMAN_REQUIRED, SYNONYM_GAP

REGISTRY_DIR = Path(__file__).with_name("coverage_candidates")
PENDING_DIR = REGISTRY_DIR / "pending"
ACCEPTED_DIR = REGISTRY_DIR / "accepted"
REJECTED_DIR = REGISTRY_DIR / "rejected"

CANDIDATE_PREFIX = "CAND-R1"

#: Provable rejection reasons. Each is checkable without an opinion.
REASON_ALREADY_KNOWN = "redundant-with-evaluator-lexicon"
REASON_LITERAL_CASE = "proposal-reuses-a-failing-cases-own-text"
REASON_FROZEN_TARGET = "target-is-frozen-for-this-phase"
REASON_EMPTY = "proposal-adds-nothing"

REJECTION_REASONS: tuple[str, ...] = (
    REASON_ALREADY_KNOWN,
    REASON_LITERAL_CASE,
    REASON_FROZEN_TARGET,
    REASON_EMPTY,
)

#: Paths this phase may not modify. A proposal aimed at one of these is refused here
#: rather than discovered later by a reviewer reading a diff.
FROZEN_PREFIXES: tuple[str, ...] = (
    "risk_evaluation/v3/",
    "risk_evaluation/v3_1/",
    "risk_evaluation/v3_independent/",
    "risk_evaluation/benchmarks/",
    "risk_evaluation/semantic_evaluator",
    "risk_evaluation/taxonomy",
    "runtime/",
    "production/",
    "workflows/",
    "plugins/",
)


class RegistryError(Exception):
    """Raised when a candidate would violate the framework's own rules."""


@dataclass(frozen=True, slots=True)
class RegistryReport:
    """What the registry holds, after a run."""

    pending: tuple[CoverageCandidate, ...]
    rejected: tuple[tuple[CoverageCandidate, str], ...]
    accepted: tuple[CoverageCandidate, ...]

    @property
    def counts(self) -> dict[str, int]:
        return {
            "pending": len(self.pending),
            "rejected": len(self.rejected),
            "accepted": len(self.accepted),
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "counts": self.counts,
            "pending": [
                {
                    "candidate_id": item.candidate_id,
                    "failure_type": item.failure_type,
                    "risk_category": item.risk_category,
                    "proposal": item.proposal,
                    "additions": list(item.additions),
                    "covers_cases": list(item.covers_cases),
                    "generality": item.generality,
                    "recommendation": item.recommendation,
                }
                for item in self.pending
            ],
            "rejected": [
                {
                    "candidate_id": item.candidate_id,
                    "failure_type": item.failure_type,
                    "proposal": item.proposal,
                    "reason": reason,
                }
                for item, reason in self.rejected
            ],
            "accepted": [
                {"candidate_id": item.candidate_id, "proposal": item.proposal}
                for item in self.accepted
            ],
            "policy": (
                "the framework writes pending and provable rejections only; "
                "accepted requires a human decision recorded with ReviewDecision"
            ),
        }


def rejection_reason(candidate: CoverageCandidate) -> str | None:
    """A provable reason to reject, or None to leave the decision to a human."""

    if not candidate.additions:
        # A candidate with nothing to add is either a structural finding for a human
        # or a mistake; it is not mechanically rejectable on that ground alone.
        return None
    if all(lexicon.known(word) for word in candidate.additions):
        return REASON_ALREADY_KNOWN
    lowered = candidate.proposal.lower()
    for case_id in candidate.covers_cases:
        if case_id.lower() in lowered:
            return REASON_LITERAL_CASE
    for prefix in FROZEN_PREFIXES:
        if prefix in candidate.proposal:
            return REASON_FROZEN_TARGET
    return None


def _candidate_id(index: int) -> str:
    return f"{CANDIDATE_PREFIX}-{index:04d}"


def _axis_for_record(record: FailureRecord) -> synonyms.Axis | None:
    if record.repair_candidate is None:
        return None
    target = record.repair_candidate.target
    if not target.startswith("axis:"):
        return None
    name = target.split(":", 1)[1]
    if name == "undeclared":
        return None
    try:
        return synonyms.axis(name)
    except Exception:  # noqa: BLE001 - a target naming no axis is not a candidate
        return None


def _category_label(record: FailureRecord) -> str:
    """The category a proposal names, as readable text rather than a tuple repr.

    `record.expected` is a tuple, and interpolating it produced proposals reading
    "the LEXICAL_GAP for ('market_prediction',)".
    """

    if record.expected:
        return record.expected[0]
    if record.actual:
        return f"{record.actual[0]} (asserted, not labelled)"
    return "no category"


def _proposal_for(
    failure_type: str,
    additions: Sequence[str],
    axis: synonyms.Axis | None,
    record: FailureRecord,
) -> str:
    if axis is not None:
        return (
            f"extend the {axis.name} axis of the {axis.category} pattern by adding "
            f"{', '.join(sorted(additions))}; the evaluator currently matches "
            f"{', '.join(axis.canonical)}"
        )
    if failure_type == SYNONYM_GAP:
        return (
            f"extend an evaluator lexicon by adding {', '.join(sorted(additions))}, "
            f"which the annotators read as {_category_label(record)}"
        )
    return (
        f"review the {failure_type} affecting {_category_label(record)}: the repair "
        "is structural and no word list is proposed"
    )


def _expected_impact(count: int, additions: Sequence[str], axis: synonyms.Axis | None) -> str:
    what = (
        f"{len(additions)} word(s) on the {axis.name} axis"
        if axis is not None
        else f"{len(additions)} word(s)"
    )
    return (
        f"would give {count} failing case(s) the vocabulary they lack; unmeasured "
        "until a benchmark that did not exist when this candidate was made is scored"
    )


def candidates_from_analysis(
    analysis: FailureAnalysis,
) -> tuple[CoverageCandidate, ...]:
    """Group failures into candidates by what they need, not by which case failed."""

    groups: dict[tuple[str, str, str], list[FailureRecord]] = defaultdict(list)
    for record in analysis.failures:
        repair = record.repair_candidate
        target = repair.target if repair is not None else "human-review"
        groups[(record.failure_type, target, repair.risk_category if repair else "")].append(
            record
        )

    out: list[CoverageCandidate] = []
    for index, key in enumerate(sorted(groups), start=1):
        failure_type, target, category = key
        records = sorted(groups[key], key=lambda item: item.case_id)
        first = records[0]
        axis = _axis_for_record(first)
        additions: tuple[str, ...] = ()
        for record in records:
            if record.repair_candidate is not None and record.repair_candidate.additions:
                additions = record.repair_candidate.additions
                break
        human_only = failure_type in HUMAN_REQUIRED
        if human_only:
            recommendation = RECOMMEND_DEFER
            reasons = (
                f"{failure_type} needs a human ruling: "
                + ("the category has no v3 relation to extend"
                   if axis is not None and not axis.auto_generatable
                   else "the classification rests on a judgement, not a word list"),
            )
        elif additions:
            recommendation = RECOMMEND_ACCEPT if failure_type in AUTO_GENERATABLE else RECOMMEND_DEFER
            reasons = (
                f"{len(records)} case(s) share this failure and this target, so the "
                "candidate generalizes across them",
                "no single case's literal text appears in the proposal",
            )
        else:
            recommendation = RECOMMEND_DEFER
            reasons = ("the repair is structural and is not a word list",)
        out.append(
            CoverageCandidate(
                candidate_id=_candidate_id(index),
                source_case=first.case_id,
                failure_type=failure_type,
                proposal=_proposal_for(failure_type, additions, axis, first),
                risk_category=category or (first.expected[0] if first.expected else ""),
                expected_impact=_expected_impact(len(records), additions, axis),
                status=PENDING,
                recommendation=recommendation,
                reasons=reasons,
                covers_cases=tuple(record.case_id for record in records),
                additions=additions,
                generator="analyzer",
            )
        )
    return tuple(out)


def candidates_from_generated(
    cases: Sequence[GeneratedCase], analysis: FailureAnalysis
) -> tuple[CoverageCandidate, ...]:
    """Candidates from the expansion set, with the failing cases they generalize."""

    by_axis: dict[str, list[GeneratedCase]] = defaultdict(list)
    for case in cases:
        axis_name = _axis_from_generation_rule(case.generation_rule)
        if axis_name:
            by_axis[axis_name].append(case)

    covered: dict[str, list[str]] = defaultdict(list)
    for record in analysis.failures:
        axis = _axis_for_record(record)
        if axis is not None:
            covered[axis.name].append(record.case_id)

    out: list[CoverageCandidate] = []
    for offset, axis_name in enumerate(sorted(by_axis), start=1):
        axis = synonyms.axis(axis_name)
        group = by_axis[axis_name]
        additions = axis.novel
        covers = tuple(sorted(covered.get(axis_name, ())))
        human_only = not axis.auto_generatable
        # A candidate with no failing case behind it is proactive, not motivated. It
        # is still worth queueing — that is what expansion means — but recommending
        # acceptance for it would be recommending a change nothing has asked for.
        motivated = bool(covers)
        if human_only or not motivated:
            recommendation = RECOMMEND_DEFER
        else:
            recommendation = RECOMMEND_ACCEPT
        out.append(
            CoverageCandidate(
                candidate_id=_candidate_id(9000 + offset),
                source_case=group[0].case_id,
                failure_type=axis.failure_type,
                proposal=(
                    f"extend the {axis.name} axis of the {axis.category} pattern by "
                    f"adding {', '.join(sorted(additions))}; "
                    f"{len(group)} generated case(s) exercise it"
                ),
                risk_category=axis.category,
                expected_impact=(
                    f"{len(group)} generated case(s) would be caught; "
                    f"{len(covers)} existing failing case(s) share this axis; "
                    "unmeasured against the current benchmark"
                ),
                status=PENDING,
                recommendation=recommendation,
                reasons=(
                    "generated from a declared axis and a declared frame, not from a "
                    "failing case's text",
                    (
                        "no v3 relation exists for this category, so the candidate "
                        "cannot be applied as a vocabulary extension"
                        if human_only
                        else (
                            "no failing case in the calibration set needs this axis, so "
                            "the candidate is proactive expansion rather than a repair"
                            if not motivated
                            else "the axis has a v3 relation, so a vocabulary extension "
                            "is expressible"
                        )
                    ),
                ),
                covers_cases=covers,
                additions=tuple(additions),
                generator="generator",
            )
        )
    return tuple(out)


def _axis_from_generation_rule(rule: str) -> str | None:
    marker = "axis:"
    if marker not in rule:
        return None
    name = rule.split(marker, 1)[1]
    if ":" in name:
        name = name.split(":", 1)[0]
    name = name.strip()
    try:
        synonyms.axis(name)
    except Exception:  # noqa: BLE001 - a rule naming no axis yields no candidate
        return None
    return name


def sort_candidates(
    candidates: Sequence[CoverageCandidate],
) -> tuple[CoverageCandidate, ...]:
    """Stable order: the most-covering candidate first, generality as a tie-break.

    Cover count leads rather than generality. Sorting on generality first put a
    candidate covering twenty cases below one covering a single case, because a broad
    lexical candidate has no word list to measure its generality by — which made the
    dashboard read as though the small candidates were the important ones.
    """

    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                -len(item.covers_cases),
                not item.is_general,
                item.failure_type,
                item.candidate_id,
            ),
        )
    )


def build(
    analysis: FailureAnalysis, cases: Sequence[GeneratedCase]
) -> tuple[CoverageCandidate, ...]:
    """Every candidate, deduplicated by proposal text."""

    seen: dict[str, CoverageCandidate] = {}
    for candidate in sort_candidates(
        candidates_from_analysis(analysis) + candidates_from_generated(cases, analysis)
    ):
        seen.setdefault(candidate.proposal, candidate)
    return tuple(seen.values())


def partition(
    candidates: Sequence[CoverageCandidate],
) -> tuple[tuple[CoverageCandidate, ...], tuple[tuple[CoverageCandidate, str], ...]]:
    """Split candidates into the review queue and the provable rejections."""

    pending: list[CoverageCandidate] = []
    rejected: list[tuple[CoverageCandidate, str]] = []
    for candidate in candidates:
        reason = rejection_reason(candidate)
        if reason is None:
            pending.append(candidate)
        else:
            rejected.append((candidate, reason))
    return tuple(pending), tuple(rejected)


ACCEPTED_README = """# Accepted candidates

This directory is written by a human, never by the framework.

A candidate may move here only after it has been scored against a benchmark that did
not exist when the candidate was proposed. Before that measurement, accepting a
candidate would be asserting an improvement nobody has observed — and the coverage
framework exists precisely because that assertion kept being made without evidence.

To accept a candidate:

1. Copy its JSON here unchanged.
2. Set `"status": "accepted"`.
3. Record a `ReviewDecision` naming the reviewer, the decision and the rationale.
4. Score the change against a new benchmark and record the result alongside it.

Candidate ids are stable. The framework will not reuse or overwrite a file in this
directory; if an id collides, the run fails loudly rather than overwriting a decision.
"""


REJECTED_README = """# Rejected candidates

Written only for rejections the framework can prove from its own tables, with no
judgement involved:

- `redundant-with-evaluator-lexicon` — every proposed word is one the evaluator
  already matches, so the candidate asks for nothing.
- `proposal-reuses-a-failing-cases-own-text` — the proposal quotes the case it came
  from, which would improve that case and nothing else.
- `target-is-frozen-for-this-phase` — the proposal names a path this phase may not
  modify.
- `proposal-adds-nothing` — recorded when a candidate carries an empty addition list
  that no structural reading can justify.

This directory is empty for the Phase R1 run, and that is the expected result rather
than a gap. Every candidate that run produced came from a declared axis, none quoted a
failing case, and none named a frozen path — so none of the four provable grounds
applied. A rejection that needed an opinion would be a decision wearing a rejection's
clothes, and those candidates stay in `pending/` for a human.

The file exists so the directory is present in the repository: git cannot track an
empty directory, and the layout the framework documents should be the layout a reader
finds.
"""


def _clear_owned(directory: Path) -> list[str]:
    """Remove candidate files this framework wrote on a previous run.

    Without this, changing the failure taxonomy leaves the earlier run's candidates
    on disk and a reviewer reads a queue that no longer corresponds to any analysis —
    five such files survived the first change of grouping key during development.

    Only `.json` is removed, and only from `pending/` and `rejected/`. `accepted/` is
    never passed to this function: a human decision outlives a framework re-run.
    """

    removed: list[str] = []
    if not directory.is_dir():
        return removed
    for path in sorted(directory.glob("*.json")):
        path.unlink()
        removed.append(path.name)
    return removed


def write(
    analysis: FailureAnalysis,
    cases: Sequence[GeneratedCase],
    *,
    registry_dir: str | Path | None = None,
) -> RegistryReport:
    """Write the registry. Never writes to `accepted/`."""

    root = Path(registry_dir) if registry_dir is not None else REGISTRY_DIR
    pending_dir = root / "pending"
    rejected_dir = root / "rejected"
    accepted_dir = root / "accepted"
    for directory in (pending_dir, rejected_dir, accepted_dir):
        directory.mkdir(parents=True, exist_ok=True)

    readme = accepted_dir / "README.md"
    if not readme.exists():
        readme.write_text(ACCEPTED_README, encoding="utf-8")
    rejected_readme = rejected_dir / "README.md"
    if not rejected_readme.exists():
        rejected_readme.write_text(REJECTED_README, encoding="utf-8")

    accepted_ids = {path.stem for path in accepted_dir.glob("*.json")}
    _clear_owned(pending_dir)
    _clear_owned(rejected_dir)

    candidates = build(analysis, cases)
    pending, rejected = partition(candidates)

    written: list[CoverageCandidate] = []
    for candidate in pending:
        if candidate.candidate_id in accepted_ids:
            # A human already ruled on this id. Re-proposing it under the same id
            # would overwrite a decision, so the candidate is skipped and the
            # decision stands.
            continue
        write_json(pending_dir / f"{candidate.candidate_id}.json", candidate.as_dict())
        written.append(candidate)
    for candidate, reason in rejected:
        body = candidate.as_dict()
        body["status"] = REJECTED
        body["rejection_reason"] = reason
        body["rejection_basis"] = (
            "provable from the framework's own tables without a judgement call"
        )
        write_json(rejected_dir / f"{candidate.candidate_id}.json", body)

    return RegistryReport(pending=tuple(written), rejected=rejected, accepted=())


def load(directory: str | Path) -> CoverageCandidate:
    """Read one candidate back, so a review can be checked against it."""

    body = json.loads(Path(directory).read_text(encoding="utf-8"))
    return CoverageCandidate(
        candidate_id=body["candidate_id"],
        source_case=body["source_case"],
        failure_type=body["failure_type"],
        proposal=body["proposal"],
        risk_category=body["risk_category"],
        expected_impact=body["expected_impact"],
        status=body.get("status", PENDING),
        recommendation=body.get("recommendation", RECOMMEND_DEFER),
        reasons=tuple(body.get("reasons", ())),
        covers_cases=tuple(body.get("covers_cases", ())),
        additions=tuple(body.get("additions", ())),
        generator=body.get("generator", ""),
    )


def apply_decision(
    candidate: CoverageCandidate, decision: ReviewDecision
) -> CoverageCandidate:
    """A human's ruling, applied to a candidate. The only path to `accepted`."""

    if decision.candidate_id != candidate.candidate_id:
        raise RegistryError(
            f"decision names {decision.candidate_id} but candidate is "
            f"{candidate.candidate_id}"
        )
    if decision.decision not in (ACCEPTED, REJECTED, PENDING):
        raise RegistryError(f"unknown decision {decision.decision!r}")
    if decision.decision == ACCEPTED and not decision.reviewer:
        raise RegistryError("an acceptance must name a reviewer")
    body = candidate.as_dict()
    body["status"] = decision.decision
    body["review_decision"] = decision.as_dict()
    return CoverageCandidate(
        candidate_id=candidate.candidate_id,
        source_case=candidate.source_case,
        failure_type=candidate.failure_type,
        proposal=candidate.proposal,
        risk_category=candidate.risk_category,
        expected_impact=candidate.expected_impact,
        status=decision.decision,
        recommendation=candidate.recommendation,
        reasons=candidate.reasons,
        covers_cases=candidate.covers_cases,
        additions=candidate.additions,
        generator=candidate.generator,
    )


def describe(report: RegistryReport | None = None) -> dict[str, object]:
    if report is None:
        return {
            "registry": str(REGISTRY_DIR.name),
            "directories": [PENDING_DIR.name, ACCEPTED_DIR.name, REJECTED_DIR.name],
            "provable_rejections": list(REJECTION_REASONS),
            "frozen_prefixes": list(FROZEN_PREFIXES),
            "writes_accepted": False,
        }
    return report.as_dict()
