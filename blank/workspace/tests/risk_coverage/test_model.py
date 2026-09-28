"""The coverage data model: evidence, failure records, candidates, generated cases.

The structural constraints of this phase live in `__post_init__` rather than in prose,
so most of what follows asserts that the records *refuse* things: a classification with
no evidence, a generated case that could enter a benchmark, a candidate that cannot
generalize.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from risk_evaluation.coverage.model import (
    ACCEPTED,
    EVIDENCE_KINDS,
    EVIDENCE_STRENGTH,
    PENDING,
    RECOMMENDATIONS,
    RECOMMEND_ACCEPT,
    RECOMMEND_DEFER,
    RECOMMEND_REJECT,
    REJECTED,
    STATUSES,
    CoverageCandidate,
    CoverageError,
    Evidence,
    FailureAnalysis,
    FailureRecord,
    GeneratedCase,
    RegressionCandidate,
    RepairCandidate,
    ReviewDecision,
    load_json,
    write_json,
)
from risk_evaluation.coverage.taxonomy import (
    FRAME_GAP,
    LEXICAL_GAP,
    MORPHOLOGY_GAP,
    UNKNOWN,
)

from ._support import (
    candidate,
    evidence,
    failure_analysis,
    failure_record,
    generated_case,
)


class EvidenceStrengthTest(unittest.TestCase):
    """Confidence is derived from evidence strength and from nothing else."""

    def test_the_four_declared_kinds_exist(self) -> None:
        self.assertEqual(
            set(EVIDENCE_KINDS), {"direct", "declared", "inferred", "absent"}
        )

    def test_every_kind_has_a_declared_strength(self) -> None:
        for kind in EVIDENCE_KINDS:
            self.assertIn(kind, EVIDENCE_STRENGTH)

    def test_direct_evidence_is_full_strength(self) -> None:
        self.assertEqual(evidence("no_hook_at_all", "direct").strength, 1.0)

    def test_declared_evidence_is_eight_tenths(self) -> None:
        self.assertEqual(evidence("prediction_outcome", "declared").strength, 0.8)

    def test_inferred_evidence_is_six_tenths(self) -> None:
        self.assertEqual(evidence("no_rule_matched", "inferred").strength, 0.6)

    def test_absent_evidence_is_a_half(self) -> None:
        self.assertEqual(evidence("nothing", "absent").strength, 0.5)

    def test_strengths_are_strictly_ordered(self) -> None:
        self.assertGreater(
            EVIDENCE_STRENGTH["direct"], EVIDENCE_STRENGTH["declared"]
        )
        self.assertGreater(
            EVIDENCE_STRENGTH["declared"], EVIDENCE_STRENGTH["inferred"]
        )
        self.assertGreater(
            EVIDENCE_STRENGTH["inferred"], EVIDENCE_STRENGTH["absent"]
        )

    def test_an_unknown_kind_is_refused(self) -> None:
        with self.assertRaises(CoverageError) as caught:
            Evidence(name="x", detail="y", kind="certain")
        self.assertIn("kind must be one of", str(caught.exception))

    def test_a_blank_name_is_refused(self) -> None:
        with self.assertRaises(CoverageError):
            Evidence(name="   ", detail="y")

    def test_a_blank_detail_is_refused(self) -> None:
        with self.assertRaises(CoverageError) as caught:
            Evidence(name="x", detail="\t\n")
        self.assertIn("x", str(caught.exception))

    def test_as_dict_carries_the_strength(self) -> None:
        item = evidence("hooks_present", "direct")
        self.assertEqual(
            item.as_dict(),
            {
                "name": "hooks_present",
                "detail": "hooks_present was observed",
                "kind": "direct",
                "strength": 1.0,
            },
        )

    def test_render_names_the_kind(self) -> None:
        self.assertEqual(
            evidence("no_relation_cue", "inferred").render(),
            "[inferred] no_relation_cue: no_relation_cue was observed",
        )


class FailureRecordConstraintTest(unittest.TestCase):
    """A classification with no evidence is an opinion, and is refused."""

    def test_empty_evidence_is_refused(self) -> None:
        with self.assertRaises(CoverageError) as caught:
            failure_record(evidence=())
        self.assertIn("every failure must carry evidence", str(caught.exception))

    def test_a_blank_case_id_is_refused(self) -> None:
        with self.assertRaises(CoverageError) as caught:
            failure_record(case_id="  ")
        self.assertIn("needs a case id", str(caught.exception))

    def test_blank_text_is_refused(self) -> None:
        with self.assertRaises(CoverageError) as caught:
            failure_record(input_text="")
        self.assertIn("needs its text", str(caught.exception))

    def test_sequences_are_frozen_into_tuples(self) -> None:
        record = failure_record(
            expected=["a", "b"], actual=["b"], evidence=[evidence("x")]
        )
        self.assertIsInstance(record.expected, tuple)
        self.assertIsInstance(record.actual, tuple)
        self.assertIsInstance(record.evidence, tuple)
        self.assertEqual(record.expected, ("a", "b"))


class FailureRecordConfidenceTest(unittest.TestCase):
    """Confidence is the weakest *required* link, not the strongest observation."""

    def test_confidence_is_the_weakest_required_item(self) -> None:
        record = failure_record(
            evidence=(evidence("a", "direct"), evidence("b", "inferred")),
            required_evidence=("a", "b"),
        )
        self.assertEqual(record.confidence, 0.6)

    def test_a_sole_required_direct_item_is_full_confidence(self) -> None:
        record = failure_record(
            evidence=(evidence("a", "direct"),), required_evidence=("a",)
        )
        self.assertEqual(record.confidence, 1.0)

    def test_a_non_required_item_does_not_lower_confidence(self) -> None:
        with_extra = failure_record(
            evidence=(
                evidence("a", "direct"),
                evidence("speaker_match", "inferred"),
                evidence("prediction_outcome", "declared"),
            ),
            required_evidence=("a",),
        )
        self.assertEqual(with_extra.confidence, 1.0)

    def test_a_non_required_item_does_not_raise_confidence(self) -> None:
        """The negative observation is the point: it must not be averaged in."""

        with_extra = failure_record(
            evidence=(
                evidence("a", "inferred"),
                evidence("decoration", "direct"),
            ),
            required_evidence=("a",),
        )
        self.assertEqual(with_extra.confidence, 0.6)

    def test_without_requirements_every_non_declared_item_counts(self) -> None:
        record = failure_record(
            evidence=(
                evidence("a", "direct"),
                evidence("b", "absent"),
                evidence("prediction_outcome", "declared"),
            ),
            required_evidence=(),
        )
        self.assertEqual(record.confidence, 0.5)

    def test_declared_items_only_are_used_as_a_last_resort(self) -> None:
        record = failure_record(
            evidence=(evidence("prediction_outcome", "declared"),),
            required_evidence=(),
        )
        self.assertEqual(record.confidence, 0.8)

    def test_a_required_item_that_is_declared_falls_back_to_the_rest(self) -> None:
        """A declared observation is not part of the argument even when required."""

        record = failure_record(
            evidence=(
                evidence("outcome", "declared"),
                evidence("other", "inferred"),
            ),
            required_evidence=("outcome",),
        )
        self.assertEqual(record.confidence, 0.6)

    def test_confidence_is_a_float_rounded_to_four_places(self) -> None:
        record = failure_record(
            evidence=(evidence("a", "declared"),), required_evidence=("a",)
        )
        self.assertIsInstance(record.confidence, float)
        self.assertEqual(record.confidence, round(record.confidence, 4))

    def test_confidence_basis_names_the_deciding_item(self) -> None:
        record = failure_record(
            evidence=(evidence("a", "direct"), evidence("b", "inferred")),
            required_evidence=("a", "b"),
        )
        self.assertEqual(record.confidence_basis, "b (inferred, 0.60)")

    def test_confidence_basis_follows_the_same_filter_as_confidence(self) -> None:
        record = failure_record(
            evidence=(
                evidence("a", "direct"),
                evidence("speaker_match", "inferred"),
            ),
            required_evidence=("a",),
        )
        self.assertEqual(record.confidence_basis, "a (direct, 1.00)")

    def test_confidence_basis_on_a_declared_only_record(self) -> None:
        record = failure_record(
            evidence=(evidence("prediction_outcome", "declared"),),
            required_evidence=(),
        )
        self.assertEqual(record.confidence_basis, "prediction_outcome (declared, 0.80)")

    def test_decisive_is_the_strongest_evidence_not_the_required_one(self) -> None:
        record = failure_record(
            evidence=(evidence("a", "inferred"), evidence("b", "direct")),
            required_evidence=("a",),
        )
        self.assertEqual(record.decisive.name, "b")
        self.assertEqual(record.confidence, 0.6)


class FailureRecordSetTest(unittest.TestCase):
    """`missing` and `extra` are the two halves of a failed exact-set match."""

    def test_missing_is_a_sorted_set_difference(self) -> None:
        record = failure_record(expected=("b", "a", "c"), actual=("c",))
        self.assertEqual(record.missing, ("a", "b"))

    def test_extra_is_a_sorted_set_difference(self) -> None:
        record = failure_record(expected=("a",), actual=("c", "b", "a"))
        self.assertEqual(record.extra, ("b", "c"))

    def test_duplicates_do_not_leak_into_missing(self) -> None:
        record = failure_record(expected=("a", "a", "b"), actual=())
        self.assertEqual(record.missing, ("a", "b"))

    def test_missing_and_extra_are_disjoint(self) -> None:
        record = failure_record(expected=("a", "b"), actual=("b", "c"))
        self.assertEqual(record.missing, ("a",))
        self.assertEqual(record.extra, ("c",))
        self.assertEqual(set(record.missing) & set(record.extra), set())

    def test_as_dict_serialises_the_findings(self) -> None:
        record = failure_record(
            case_id="IND-0007",
            repair_candidate=RepairCandidate(
                type="synonym_extension",
                risk_category="market_prediction",
                additions=("zoomy",),
                target="axis:movement_direction",
            ),
        )
        body = record.as_dict()
        self.assertEqual(body["case_id"], "IND-0007")
        self.assertEqual(body["confidence"], record.confidence)
        self.assertEqual(body["confidence_basis"], record.confidence_basis)
        self.assertEqual(body["evidence"][0]["kind"], "inferred")
        self.assertEqual(body["repair_candidate"]["additions"], ["zoomy"])
        self.assertIsNone(failure_record().as_dict()["repair_candidate"])

    def test_render_quotes_the_text_and_the_evidence(self) -> None:
        rendered = failure_record(
            case_id="IND-0009",
            input_text="Turnover will plummet.",
            evidence=(evidence("declared_synonym_present", "direct"),),
            required_evidence=("declared_synonym_present",),
        ).render()
        self.assertIn("IND-0009 [LEXICAL_GAP]", rendered)
        self.assertIn("Turnover will plummet.", rendered)
        self.assertIn("[direct] declared_synonym_present", rendered)


class RepairCandidateTest(unittest.TestCase):
    def test_a_type_is_required(self) -> None:
        with self.assertRaises(CoverageError):
            RepairCandidate(type=" ", risk_category="market_prediction")

    def test_a_risk_category_is_required(self) -> None:
        with self.assertRaises(CoverageError):
            RepairCandidate(type="synonym_extension", risk_category="")

    def test_as_dict_lists_the_additions(self) -> None:
        body = RepairCandidate(
            type="frame_extension", risk_category="investment_advice", target="frame:relation"
        ).as_dict()
        self.assertEqual(body["additions"], [])
        self.assertEqual(body["target"], "frame:relation")


class CoverageCandidateTest(unittest.TestCase):
    def test_generality_counts_the_cases_claimed(self) -> None:
        self.assertEqual(candidate(covers_cases=("a", "b", "c")).generality, 3)

    def test_a_candidate_with_no_cases_is_not_general(self) -> None:
        item = candidate(covers_cases=(), additions=("zoomy",))
        self.assertEqual(item.generality, 0)
        self.assertFalse(item.is_general)

    def test_a_candidate_with_cases_but_no_additions_is_not_general(self) -> None:
        item = candidate(covers_cases=("IND-0001",), additions=())
        self.assertEqual(item.generality, 1)
        self.assertFalse(item.is_general)

    def test_a_candidate_with_cases_and_additions_is_general(self) -> None:
        self.assertTrue(candidate().is_general)

    def test_a_blank_id_is_refused(self) -> None:
        with self.assertRaises(CoverageError):
            candidate(candidate_id="")

    def test_a_blank_source_case_is_refused(self) -> None:
        with self.assertRaises(CoverageError) as caught:
            candidate(source_case=" ")
        self.assertIn("needs a source case", str(caught.exception))

    def test_a_blank_proposal_is_refused(self) -> None:
        with self.assertRaises(CoverageError):
            candidate(proposal="")

    def test_an_undeclared_status_is_refused(self) -> None:
        with self.assertRaises(CoverageError) as caught:
            candidate(status="maybe")
        self.assertIn("status must be one of", str(caught.exception))

    def test_an_undeclared_recommendation_is_refused(self) -> None:
        with self.assertRaises(CoverageError):
            candidate(recommendation="approve")

    def test_the_default_status_is_pending_and_the_default_recommendation_defers(
        self,
    ) -> None:
        item = candidate()
        self.assertEqual(item.status, PENDING)
        self.assertEqual(item.recommendation, RECOMMEND_DEFER)
        self.assertTrue(item.forbids_literal_case)

    def test_as_dict_reports_the_covers_count(self) -> None:
        body = candidate(covers_cases=("a", "b")).as_dict()
        self.assertEqual(body["covers_count"], 2)
        self.assertEqual(body["additions"], ["zoomy"])
        self.assertEqual(body["status"], PENDING)


class GeneratedCaseTest(unittest.TestCase):
    """A generated case may never enter a formal benchmark."""

    def test_excludes_from_benchmark_false_is_refused(self) -> None:
        with self.assertRaises(CoverageError) as caught:
            generated_case(excludes_from_benchmark=False)
        self.assertIn("may not enter a formal benchmark", str(caught.exception))

    def test_excluded_is_the_default(self) -> None:
        self.assertIs(generated_case().excludes_from_benchmark, True)

    def test_a_generation_reason_is_required(self) -> None:
        with self.assertRaises(CoverageError) as caught:
            generated_case(generation_reason="   ")
        self.assertIn("must say why it was generated", str(caught.exception))

    def test_a_generation_rule_is_required(self) -> None:
        with self.assertRaises(CoverageError):
            generated_case(generation_rule="")

    def test_a_blank_id_is_refused(self) -> None:
        with self.assertRaises(CoverageError):
            generated_case(case_id=" ")

    def test_blank_text_is_refused(self) -> None:
        with self.assertRaises(CoverageError):
            generated_case(text="\n")

    def test_expects_risk_follows_the_expected_categories(self) -> None:
        self.assertTrue(generated_case().expects_risk)
        self.assertFalse(generated_case(expected_categories=()).expects_risk)

    def test_as_dict_reports_the_exclusion(self) -> None:
        body = generated_case().as_dict()
        self.assertIs(body["excludes_from_benchmark"], True)
        self.assertIs(body["expects_risk"], True)
        self.assertEqual(body["expected_categories"], ["financial_guarantee"])


class RegressionAndDecisionTest(unittest.TestCase):
    def test_a_regression_candidate_needs_its_original_failure(self) -> None:
        with self.assertRaises(CoverageError):
            RegressionCandidate(
                case_id="REG-1",
                original_failure=" ",
                proposed_change="add a word",
                expected_behavior="a finding appears",
            )

    def test_a_regression_candidate_needs_a_proposed_change(self) -> None:
        with self.assertRaises(CoverageError):
            RegressionCandidate(
                case_id="REG-1",
                original_failure="IND-1",
                proposed_change="",
                expected_behavior="a finding appears",
            )

    def test_a_regression_candidate_needs_expected_behaviour(self) -> None:
        with self.assertRaises(CoverageError):
            RegressionCandidate(
                case_id="REG-1",
                original_failure="IND-1",
                proposed_change="add a word",
                expected_behavior="  ",
            )

    def test_a_regression_candidate_defaults_to_pending(self) -> None:
        item = RegressionCandidate(
            case_id="REG-1",
            original_failure="IND-1",
            proposed_change="add a word",
            expected_behavior="a finding appears",
        )
        self.assertEqual(item.approval_status, PENDING)
        self.assertEqual(item.as_dict()["approval_status"], PENDING)

    def test_an_undeclared_approval_status_is_refused(self) -> None:
        with self.assertRaises(CoverageError):
            RegressionCandidate(
                case_id="REG-1",
                original_failure="IND-1",
                proposed_change="add a word",
                expected_behavior="a finding appears",
                approval_status="approved",
            )

    def test_a_decision_cannot_be_pending(self) -> None:
        with self.assertRaises(CoverageError) as caught:
            ReviewDecision(
                candidate_id="CAND-R1-0001",
                decision=PENDING,
                reviewer="reviewer",
                rationale="looks fine",
            )
        self.assertIn("a decision is accepted or rejected", str(caught.exception))

    def test_a_decision_needs_a_rationale(self) -> None:
        with self.assertRaises(CoverageError):
            ReviewDecision(
                candidate_id="CAND-R1-0001",
                decision=ACCEPTED,
                reviewer="reviewer",
                rationale="   ",
            )

    def test_a_decision_serialises_the_reviewer(self) -> None:
        body = ReviewDecision(
            candidate_id="CAND-R1-0001",
            decision=REJECTED,
            reviewer="a reviewer",
            rationale="the words are already matched",
        ).as_dict()
        self.assertEqual(body["decision"], REJECTED)
        self.assertEqual(body["reviewer"], "a reviewer")

    def test_statuses_and_recommendations_are_the_declared_ones(self) -> None:
        self.assertEqual(set(STATUSES), {PENDING, ACCEPTED, REJECTED})
        self.assertEqual(
            set(RECOMMENDATIONS),
            {RECOMMEND_ACCEPT, RECOMMEND_REJECT, RECOMMEND_DEFER},
        )


class FailureAnalysisTest(unittest.TestCase):
    def _failures(self) -> tuple[FailureRecord, ...]:
        return (
            failure_record(case_id="IND-0001", failure_type=LEXICAL_GAP),
            failure_record(case_id="IND-0002", failure_type=LEXICAL_GAP),
            failure_record(case_id="IND-0003", failure_type=LEXICAL_GAP),
            failure_record(case_id="IND-0004", failure_type=FRAME_GAP),
            failure_record(case_id="IND-0005", failure_type=UNKNOWN),
        )

    def test_count_is_the_number_of_failures(self) -> None:
        self.assertEqual(failure_analysis(self._failures(), cases=300).count, 5)

    def test_types_orders_by_count_then_by_name(self) -> None:
        analysis = failure_analysis(self._failures(), cases=300)
        self.assertEqual(
            list(analysis.types().items()),
            [(LEXICAL_GAP, 3), (FRAME_GAP, 1), (UNKNOWN, 1)],
        )

    def test_failure_rate_is_the_share_of_scored_cases(self) -> None:
        self.assertEqual(failure_analysis(self._failures(), cases=300).failure_rate, 0.0167)

    def test_failure_rate_is_zero_without_cases(self) -> None:
        self.assertEqual(failure_analysis((), cases=0).failure_rate, 0.0)

    def test_of_type_selects_the_records(self) -> None:
        analysis = failure_analysis(self._failures(), cases=300)
        self.assertEqual(len(analysis.of_type(LEXICAL_GAP)), 3)
        self.assertEqual(analysis.of_type(MORPHOLOGY_GAP), ())

    def test_mean_confidence_averages_the_records(self) -> None:
        records = (
            failure_record(
                case_id="IND-0001",
                evidence=(evidence("a", "direct"),),
                required_evidence=("a",),
            ),
            failure_record(
                case_id="IND-0002",
                evidence=(evidence("b", "inferred"),),
                required_evidence=("b",),
            ),
        )
        self.assertEqual(failure_analysis(records).mean_confidence, 0.8)

    def test_mean_confidence_is_zero_without_failures(self) -> None:
        self.assertEqual(failure_analysis(()).mean_confidence, 0.0)

    def test_as_dict_summarises_the_analysis(self) -> None:
        body = failure_analysis(self._failures(), cases=300).as_dict()
        self.assertEqual(body["cases"], 300)
        self.assertEqual(body["failures"], 5)
        self.assertEqual(body["by_type"][LEXICAL_GAP], 3)
        self.assertEqual(len(body["records"]), 5)
        self.assertIn("mean_confidence", body)


class JsonRoundTripTest(unittest.TestCase):
    def test_write_json_creates_the_parent_directories(self) -> None:
        with TemporaryDirectory() as raw:
            target = Path(raw) / "nested" / "deeper" / "payload.json"
            written = write_json(target, {"a": 1})
            self.assertEqual(written, target)
            self.assertTrue(target.is_file())

    def test_write_json_is_sorted_and_newline_terminated(self) -> None:
        with TemporaryDirectory() as raw:
            target = Path(raw) / "payload.json"
            write_json(target, {"b": 1, "a": 2})
            text = target.read_text(encoding="utf-8")
            self.assertEqual(
                text, json.dumps({"b": 1, "a": 2}, indent=2, sort_keys=True) + "\n"
            )
            self.assertLess(text.index('"a"'), text.index('"b"'))

    def test_write_json_keeps_non_ascii_text_readable(self) -> None:
        with TemporaryDirectory() as raw:
            target = Path(raw) / "payload.json"
            write_json(target, {"text": "Returns are guaranteed \u2014 always."})
            self.assertIn("\u2014", target.read_text(encoding="utf-8"))

    def test_records_round_trip_through_json(self) -> None:
        with TemporaryDirectory() as raw:
            target = Path(raw) / "analysis.json"
            analysis = failure_analysis(
                (failure_record(case_id="IND-0042"),), cases=300
            )
            write_json(target, analysis.as_dict())
            body = load_json(target)
            self.assertEqual(body["failures"], 1)
            self.assertEqual(body["records"][0]["case_id"], "IND-0042")
            self.assertEqual(
                body["records"][0]["evidence"][0]["name"], "no_hook_at_all"
            )

    def test_load_json_returns_lists_where_the_writer_had_lists(self) -> None:
        with TemporaryDirectory() as raw:
            target = Path(raw) / "payload.json"
            write_json(target, {"items": [1, 2, 3]})
            self.assertEqual(load_json(target)["items"], [1, 2, 3])
