"""The four required measures, the differences they come from, and the replay."""

from __future__ import annotations

import json
import unittest

from risk_evaluation.attribution_experiment.cases import (
    EXPERIMENT_CASES,
    REPLAY_CASES,
    ExperimentCase,
    case_index,
)
from risk_evaluation.attribution_experiment.comparison import (
    BROKEN,
    DIFFERENT,
    FALSE_NEGATIVE,
    FALSE_POSITIVE,
    FIXED,
    TRUE_NEGATIVE,
    TRUE_POSITIVE,
    UNCHANGED,
    CaseComparison,
    EvaluatorMetrics,
    compare_case,
    policy_sensitivity,
    replay_report,
    run_comparison,
)
from risk_evaluation.attribution_experiment.decision import AUTHORIAL, STRICT
from risk_evaluation.attribution_experiment.evaluator import AttributionAwareEvaluator


class OutcomeTests(unittest.TestCase):
    def _comparison(self, expected: tuple[str, ...], baseline: tuple[str, ...], experiment: tuple[str, ...]) -> CaseComparison:
        case = ExperimentCase("X-1", "A", "text", expected)
        return CaseComparison(
            case=case,
            baseline_categories=baseline,
            experiment_categories=experiment,
            baseline_outcome=_outcome(case, baseline),
            experiment_outcome=_outcome(case, experiment),
        )

    def test_a_flagged_risk_is_a_true_positive(self) -> None:
        item = self._comparison(("financial_guarantee",), ("financial_guarantee",), ("financial_guarantee",))

        self.assertEqual(item.baseline_outcome, TRUE_POSITIVE)
        self.assertTrue(item.baseline_correct)

    def test_a_flagged_benign_text_is_a_false_positive(self) -> None:
        item = self._comparison((), ("financial_guarantee",), ("financial_guarantee",))

        self.assertEqual(item.baseline_outcome, FALSE_POSITIVE)
        self.assertFalse(item.baseline_correct)

    def test_a_missed_risk_is_a_false_negative(self) -> None:
        item = self._comparison(("financial_guarantee",), (), ())

        self.assertEqual(item.baseline_outcome, FALSE_NEGATIVE)

    def test_an_unflagged_benign_text_is_a_true_negative(self) -> None:
        item = self._comparison((), (), ())

        self.assertEqual(item.baseline_outcome, TRUE_NEGATIVE)

    def test_the_wrong_category_is_flagged_but_incorrect(self) -> None:
        """The binary flag and the category answer are different questions."""

        item = self._comparison(("unverified_information",), ("market_prediction",), ("market_prediction",))

        self.assertEqual(item.baseline_outcome, TRUE_POSITIVE)
        self.assertFalse(item.baseline_correct)


def _outcome(case: ExperimentCase, categories: tuple[str, ...]) -> str:
    from risk_evaluation.attribution_experiment.comparison import _outcome as impl

    return impl(case.expects_risk, bool(categories))


class TransitionTests(unittest.TestCase):
    def _item(self, expected, baseline, experiment) -> CaseComparison:
        case = ExperimentCase("X-1", "D", "text", expected)
        return CaseComparison(
            case=case,
            baseline_categories=baseline,
            experiment_categories=experiment,
            baseline_outcome=_outcome(case, baseline),
            experiment_outcome=_outcome(case, experiment),
        )

    def test_no_change_is_unchanged(self) -> None:
        item = self._item(("financial_guarantee",), ("financial_guarantee",), ("financial_guarantee",))

        self.assertFalse(item.changed)
        self.assertEqual(item.transition, UNCHANGED)

    def test_wrong_to_right_is_fixed(self) -> None:
        item = self._item(("financial_guarantee",), (), ("financial_guarantee",))

        self.assertEqual(item.transition, FIXED)

    def test_right_to_wrong_is_broken(self) -> None:
        item = self._item(("financial_guarantee",), ("financial_guarantee",), ())

        self.assertEqual(item.transition, BROKEN)

    def test_wrong_to_differently_wrong_is_different(self) -> None:
        item = self._item(
            ("financial_guarantee",), ("market_prediction",), ("investment_advice",)
        )

        self.assertEqual(item.transition, DIFFERENT)

    def test_dropped_and_added_categories_are_reported(self) -> None:
        item = self._item(
            ("financial_guarantee",), ("financial_guarantee", "unverified_information"), ("unverified_information",)
        )

        self.assertEqual(item.dropped_categories, ("financial_guarantee",))
        self.assertEqual(item.added_categories, ())


class MetricsTests(unittest.TestCase):
    def test_precision_recall_and_f1_are_derived_from_the_outcomes(self) -> None:
        metrics = EvaluatorMetrics(
            name="x",
            outcomes={
                TRUE_POSITIVE: 3,
                FALSE_POSITIVE: 1,
                FALSE_NEGATIVE: 1,
                TRUE_NEGATIVE: 5,
            },
            correct=8,
            cases=10,
            attribution_errors=2,
            attribution_cases=4,
        )

        self.assertEqual(metrics.precision, 0.75)
        self.assertEqual(metrics.recall, 0.75)
        self.assertEqual(metrics.f1, 0.75)
        self.assertEqual(metrics.accuracy, 0.8)

    def test_metrics_do_not_divide_by_zero(self) -> None:
        metrics = EvaluatorMetrics(
            name="x",
            outcomes={k: 0 for k in (TRUE_POSITIVE, FALSE_POSITIVE, FALSE_NEGATIVE, TRUE_NEGATIVE)},
            correct=0,
            cases=0,
            attribution_errors=0,
            attribution_cases=0,
        )

        self.assertEqual(metrics.precision, 0.0)
        self.assertEqual(metrics.recall, 0.0)
        self.assertEqual(metrics.f1, 0.0)


class PinnedResultTests(unittest.TestCase):
    """The measured result, pinned so it cannot drift unnoticed.

    These are the Phase 8.3 figures recorded in the report. Changing one is a
    deliberate act that requires re-measuring and updating the report.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_comparison()

    def test_the_dataset_is_fully_scored(self) -> None:
        self.assertEqual(len(self.report.cases), len(EXPERIMENT_CASES))

    def test_the_false_positive_change_is_minus_seven(self) -> None:
        self.assertEqual(self.report.baseline.false_positive, 10)
        self.assertEqual(self.report.experiment.false_positive, 3)
        self.assertEqual(self.report.false_positive_change, -7)

    def test_the_false_negative_change_is_minus_seven(self) -> None:
        self.assertEqual(self.report.baseline.false_negative, 9)
        self.assertEqual(self.report.experiment.false_negative, 2)
        self.assertEqual(self.report.false_negative_change, -7)

    def test_the_attribution_error_reduction_is_fourteen(self) -> None:
        self.assertEqual(self.report.baseline.attribution_errors, 20)
        self.assertEqual(self.report.experiment.attribution_errors, 6)
        self.assertEqual(self.report.attribution_error_reduction, 14)
        self.assertEqual(self.report.attribution_error_reduction_rate, 0.7)

    def test_the_exact_category_match_improves_by_fourteen(self) -> None:
        self.assertEqual(self.report.baseline.correct, 39)
        self.assertEqual(self.report.experiment.correct, 53)

    def test_no_case_was_broken(self) -> None:
        """The experiment never made a case worse on this dataset."""

        self.assertEqual(self.report.broken_cases, ())

    def test_fourteen_cases_were_fixed(self) -> None:
        self.assertEqual(len(self.report.fixed_cases), 14)

    def test_two_cases_changed_without_becoming_correct(self) -> None:
        self.assertEqual(
            [item.case_id for item in self.report.different_cases], ["D-03", "D-10"]
        )

    def test_the_decision_difference_count(self) -> None:
        self.assertEqual(len(self.report.decision_difference_cases), 16)

    def test_rerunning_reproduces_the_report(self) -> None:
        self.assertEqual(run_comparison().as_dict(), self.report.as_dict())

    def test_the_report_is_json_serializable(self) -> None:
        json.dumps(self.report.as_dict(), sort_keys=True)

    def test_render_states_all_four_measures(self) -> None:
        rendered = self.report.render()

        for token in (
            "false positives",
            "false negatives",
            "attribution error reduction",
            "decision difference cases",
        ):
            self.assertIn(token, rendered)


class ChangedCaseTests(unittest.TestCase):
    """Which cases moved, and why - the phase's focus."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_comparison()
        cls.by_id = {item.case_id: item for item in cls.report.cases}

    def test_fixed_cases_either_gain_a_risk_or_lose_a_false_positive(self) -> None:
        gained = [item for item in self.report.fixed_cases if item.experiment_categories]
        dropped = [item for item in self.report.fixed_cases if not item.experiment_categories]

        self.assertEqual(len(gained) + len(dropped), len(self.report.fixed_cases))
        self.assertTrue(gained)
        self.assertTrue(dropped)

    def test_the_phase_8_1_shape_is_fixed(self) -> None:
        for case_id in ("D-01", "D-02", "D-04", "D-05", "D-07", "D-08", "D-09"):
            item = self.by_id[case_id]

            self.assertEqual(item.transition, FIXED, case_id)
            self.assertEqual(item.baseline_categories, (), case_id)

    def test_a_citation_stops_being_an_author_risk(self) -> None:
        for case_id in ("B-02", "B-03", "B-06"):
            item = self.by_id[case_id]

            self.assertEqual(item.transition, FIXED, case_id)
            self.assertEqual(item.experiment_categories, (), case_id)

    def test_a_rejection_stops_being_an_author_risk(self) -> None:
        for case_id in ("C-01", "C-02", "C-03", "C-07"):
            item = self.by_id[case_id]

            self.assertEqual(item.transition, FIXED, case_id)
            self.assertEqual(item.experiment_categories, (), case_id)

    def test_suppressed_fixes_record_a_suppression_rule(self) -> None:
        """Groups B and C are fixed by R2 or R3 dropping a category."""

        for item in self.report.fixed_cases:
            if item.experiment_categories:
                continue
            rules = {rule for decision in item.decisions for rule in decision.rules}
            self.assertTrue(
                rules & {"R2-third-party-quoted", "R3-author-rejected"}, item.case_id
            )

    def test_restored_fixes_come_from_claim_isolation_not_suppression(self) -> None:
        """Group D is fixed by a different mechanism, and this pins which.

        The whole-text baseline reported nothing for
        `Economists forecast growth. This fund cannot lose money.` The experiment
        evaluates the second claim on its own, where the guarantee is found. No
        suppression rule is involved: the fix is that the borrowed attribution
        is no longer part of the string the category rules see.
        """

        item = self.by_id["D-01"]

        self.assertEqual(item.experiment_categories, ("financial_guarantee",))
        self.assertEqual(item.dropped_categories, ())
        authorial = [d for d in item.decisions if d.claim.text == "This fund cannot lose money."]
        self.assertEqual(len(authorial), 1)
        self.assertEqual(authorial[0].kept, ("financial_guarantee",))
        self.assertEqual(authorial[0].rules, ("R6-baseline-verdict",))

    def test_the_citation_claim_detects_nothing_to_suppress_in_group_d(self) -> None:
        """The borrowed sentence in group D is neutral, so nothing is dropped."""

        for case_id in ("D-01", "D-02", "D-04"):
            item = self.by_id[case_id]
            borrowed = item.decisions[0]

            self.assertEqual(borrowed.detected, (), case_id)
            self.assertEqual(borrowed.dropped, (), case_id)

    def test_the_remaining_errors_are_documented(self) -> None:
        """Two blind-spot cases, three coverage gaps, two annotation disputes."""

        wrong = [item.case_id for item in self.report.cases if not item.experiment_correct]

        self.assertEqual(
            sorted(wrong), ["A-02", "B-04", "C-08", "C-09", "D-03", "D-06", "D-10"]
        )

    def test_the_guarantee_blind_spot_is_shared_by_both(self) -> None:
        """Phase 8.1's predicative-guarantee gap is not an attribution problem."""

        for case_id in ("A-02", "D-06"):
            item = self.by_id[case_id]

            self.assertFalse(item.baseline_correct, case_id)
            self.assertFalse(item.experiment_correct, case_id)

    def test_the_annotation_disputes_are_flagged_not_hidden(self) -> None:
        """The experiment added the right category and kept the agnostic one.

        `unverified_information` survives by design, so the experiment reports
        two categories where the annotation recorded one.
        """

        for case_id in ("D-03", "D-10"):
            item = self.by_id[case_id]

            self.assertIn("investment_advice", item.experiment_categories, case_id)
            self.assertIn(
                "unverified_information", item.experiment_categories, case_id
            )
            self.assertEqual(item.expected, ("investment_advice",), case_id)


class GroupBreakdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_comparison()

    def test_every_group_is_reported(self) -> None:
        self.assertEqual(
            set(self.report.group_metrics("baseline")),
            set(self.report.group_metrics("experiment")),
        )

    def test_the_experiment_is_not_worse_in_any_group(self) -> None:
        baseline = self.report.group_metrics("baseline")
        experiment = self.report.group_metrics("experiment")

        for group, bucket in baseline.items():
            self.assertGreaterEqual(
                experiment[group]["correct"], bucket["correct"], group
            )

    def test_the_controls_are_untouched(self) -> None:
        """Group E must not move: over-correction would show up here."""

        baseline = self.report.group_metrics("baseline")["no_risk_education"]
        experiment = self.report.group_metrics("experiment")["no_risk_education"]

        self.assertEqual(baseline, experiment)


class PolicySensitivityTests(unittest.TestCase):
    def test_both_policies_are_reported(self) -> None:
        sensitivity = policy_sensitivity()

        self.assertEqual(set(sensitivity), {STRICT, AUTHORIAL})

    def test_the_authorial_policy_fixes_one_more_case(self) -> None:
        sensitivity = policy_sensitivity()

        self.assertEqual(sensitivity[STRICT].experiment.correct, 53)
        self.assertEqual(sensitivity[AUTHORIAL].experiment.correct, 54)

    def test_neither_policy_breaks_a_case(self) -> None:
        for policy, report in policy_sensitivity().items():
            self.assertEqual(report.broken_cases, (), policy)


class ReplayTests(unittest.TestCase):
    """Requirement 5: re-run the Phase 8.1 attribution_confusion failures."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = replay_report()

    def test_the_replay_set_is_scored(self) -> None:
        self.assertEqual(len(self.report.cases), len(REPLAY_CASES))
        self.assertGreaterEqual(len(self.report.cases), 10)

    def test_the_recorded_failures_are_now_caught(self) -> None:
        by_id = {item.case_id: item for item in self.report.cases}

        for case_id in ("ATT-01", "ATT-03", "ATT-05"):
            item = by_id[case_id]
            self.assertIn(
                item.expected[0], item.experiment_categories, case_id
            )

    def test_the_false_negative_count_falls_to_zero(self) -> None:
        self.assertEqual(self.report.baseline.false_negative, 5)
        self.assertEqual(self.report.experiment.false_negative, 0)

    def test_no_new_false_positive_is_introduced(self) -> None:
        self.assertEqual(self.report.baseline.false_positive, 0)
        self.assertEqual(self.report.experiment.false_positive, 0)

    def test_no_replay_case_was_broken(self) -> None:
        self.assertEqual(self.report.broken_cases, ())

    def test_the_controls_stay_silent(self) -> None:
        by_id = {item.case_id: item for item in self.report.cases}

        for case_id in ("CTL-02", "CTL-03", "CTL-04"):
            self.assertEqual(by_id[case_id].experiment_categories, (), case_id)

    def test_every_replay_case_exposes_the_attribution_information(self) -> None:
        for item in self.report.cases:
            self.assertTrue(item.decisions, item.case_id)
            for decision in item.decisions:
                self.assertTrue(decision.claim.evidence, decision.claim_id)

    def test_both_results_are_kept_for_every_replay_case(self) -> None:
        for item in self.report.cases:
            self.assertIsInstance(item.baseline_categories, tuple)
            self.assertIsInstance(item.experiment_categories, tuple)

    def test_the_replay_report_is_json_serializable(self) -> None:
        json.dumps(replay_report().as_dict(), sort_keys=True)


class ArtifactTests(unittest.TestCase):
    def test_the_comparison_report_is_written(self) -> None:
        from risk_evaluation.attribution_experiment.comparison import (
            run_comparison as run,
            write_report,
        )
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "report.json"
            write_report(target, run())
            payload = json.loads(target.read_text(encoding="utf-8"))

        self.assertEqual(payload["cases"], len(EXPERIMENT_CASES))
        self.assertIn("note", payload)

    def test_compare_case_agrees_with_the_report(self) -> None:
        evaluator = AttributionAwareEvaluator()
        item = compare_case(case_index()["D-01"], evaluator)

        self.assertEqual(item.experiment_categories, ("financial_guarantee",))


if __name__ == "__main__":
    unittest.main()
