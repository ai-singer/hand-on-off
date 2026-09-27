from __future__ import annotations

import json
import unittest
from collections import Counter

from risk_evaluation.benchmark import BENCHMARK_CASES
from risk_evaluation.benchmark_v2 import (
    ANNOTATION_VERSION,
    ATTRIBUTION,
    BOUNDARY,
    CERTAINTY_LEVELS,
    CONDITIONAL,
    FOCUSES,
    GENERAL,
    GROUPS,
    MARKET_BOUNDARY,
    RISK,
    SAFE,
    SOURCE_TYPE,
    STATEMENT_SOURCES,
    V3_ANNOTATION_FIELDS,
    V3_CASES,
    AnnotationCaseV2,
    case_index,
    category_counts,
    certainty_counts,
    decontaminated_v3_cases,
    focus_counts,
    group_counts,
    source_counts,
    v3_records,
    v4_records,
)
from risk_evaluation.taxonomy import RISK_TAXONOMY


def _case(**overrides) -> AnnotationCaseV2:
    base = dict(
        case_id="x-01",
        group=RISK,
        focus=GENERAL,
        text="The stock will rise.",
        expected_categories=("market_prediction",),
        statement_source="author",
        certainty_level="certain",
        annotation_reason="synthetic",
    )
    base.update(overrides)
    return AnnotationCaseV2(**base)


class SizeAndBalanceTests(unittest.TestCase):
    """Phase 7.5 requires a 120-case benchmark with a fixed composition."""

    def test_case_count_is_at_least_120(self) -> None:
        self.assertEqual(len(V3_CASES), 120)

    def test_group_balance_is_70_25_25(self) -> None:
        self.assertEqual(
            dict(group_counts()), {RISK: 70, SAFE: 25, BOUNDARY: 25}
        )

    def test_risk_is_the_majority_group(self) -> None:
        counts = group_counts()

        self.assertGreater(counts[RISK], counts[SAFE] + counts[BOUNDARY])

    def test_attribution_focus_meets_the_minimum(self) -> None:
        self.assertGreaterEqual(focus_counts()[ATTRIBUTION], 20)

    def test_conditional_focus_meets_the_minimum(self) -> None:
        self.assertGreaterEqual(focus_counts()[CONDITIONAL], 20)

    def test_market_boundary_focus_meets_the_minimum(self) -> None:
        self.assertGreaterEqual(focus_counts()[MARKET_BOUNDARY], 20)

    def test_focus_counts_cover_every_focus(self) -> None:
        self.assertEqual(set(focus_counts()), set(FOCUSES))

    def test_focus_counts_sum_to_the_case_count(self) -> None:
        self.assertEqual(sum(focus_counts().values()), len(V3_CASES))

    def test_group_counts_sum_to_the_case_count(self) -> None:
        self.assertEqual(sum(group_counts().values()), len(V3_CASES))

    def test_every_category_appears_in_the_labels(self) -> None:
        self.assertEqual(
            set(category_counts()), {entry.name for entry in RISK_TAXONOMY}
        )

    def test_both_attribution_dimensions_are_exercised(self) -> None:
        self.assertEqual(set(source_counts()), set(STATEMENT_SOURCES))
        self.assertEqual(set(certainty_counts()), set(CERTAINTY_LEVELS))

    def test_non_author_sources_are_well_represented(self) -> None:
        counts = source_counts()
        non_author = sum(v for k, v in counts.items() if k != "author")

        self.assertGreaterEqual(non_author, 30)

    def test_hypothetical_cases_are_well_represented(self) -> None:
        self.assertGreaterEqual(certainty_counts()["hypothetical"], 20)


class CaseIntegrityTests(unittest.TestCase):
    def test_case_ids_are_unique(self) -> None:
        ids = [case.case_id for case in V3_CASES]

        self.assertEqual(len(ids), len(set(ids)))

    def test_cases_are_grouped_into_contiguous_annotation_blocks(self) -> None:
        """Each id prefix is one authored block, never split across the file."""

        runs: list[str] = []
        for case in V3_CASES:
            prefix = case.case_id.split("-")[0]
            if not runs or runs[-1] != prefix:
                runs.append(prefix)

        self.assertEqual(len(runs), len(set(runs)))

    def test_case_order_is_deterministic(self) -> None:
        self.assertEqual(
            [case.case_id for case in V3_CASES],
            [case.case_id for case in V3_CASES],
        )

    def test_texts_are_non_empty(self) -> None:
        for case in V3_CASES:
            self.assertTrue(case.text.strip(), case.case_id)

    def test_every_case_states_an_annotation_reason(self) -> None:
        for case in V3_CASES:
            self.assertTrue(case.annotation_reason.strip(), case.case_id)

    def test_every_case_is_annotated_under_version_two(self) -> None:
        for case in V3_CASES:
            self.assertEqual(case.annotation_version, ANNOTATION_VERSION, case.case_id)
            self.assertEqual(case.annotation_version, "2.0.0")

    def test_every_case_is_marked_synthetic_and_post_freeze(self) -> None:
        for case in V3_CASES:
            self.assertEqual(case.source_type, SOURCE_TYPE, case.case_id)
            self.assertTrue(case.created_after_evaluator_freeze, case.case_id)

    def test_expected_categories_are_real_taxonomy_categories(self) -> None:
        known = {entry.name for entry in RISK_TAXONOMY}
        for case in V3_CASES:
            for name in case.expected_categories:
                self.assertIn(name, known, case.case_id)

    def test_no_case_repeats_a_category(self) -> None:
        for case in V3_CASES:
            self.assertEqual(
                len(case.expected_categories),
                len(set(case.expected_categories)),
                case.case_id,
            )

    def test_safe_and_boundary_cases_carry_no_risk_label(self) -> None:
        for case in V3_CASES:
            if case.group in (SAFE, BOUNDARY):
                self.assertEqual(case.expected_categories, (), case.case_id)

    def test_risk_cases_carry_at_least_one_label(self) -> None:
        for case in V3_CASES:
            if case.group == RISK:
                self.assertTrue(case.expected_categories, case.case_id)

    def test_is_risky_agrees_with_the_group(self) -> None:
        for case in V3_CASES:
            self.assertEqual(case.is_risky, case.group == RISK, case.case_id)

    def test_risk_level_is_none_for_unlabelled_cases(self) -> None:
        for case in V3_CASES:
            if not case.expected_categories:
                self.assertEqual(case.risk_level, "none", case.case_id)

    def test_risk_level_is_a_known_severity_for_labelled_cases(self) -> None:
        for case in V3_CASES:
            if case.expected_categories:
                self.assertIn(case.risk_level, ("warning", "block"), case.case_id)


class CaseValidationTests(unittest.TestCase):
    """A mislabelled case must fail loudly at construction, not silently score."""

    def test_unknown_statement_source_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _case(statement_source="textbook")

    def test_unknown_certainty_level_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _case(certainty_level="definite")

    def test_unknown_group_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _case(group="unsure")

    def test_unknown_focus_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _case(focus="misc")

    def test_default_annotation_version_is_two(self) -> None:
        self.assertEqual(_case().annotation_version, "2.0.0")


class RecordExportTests(unittest.TestCase):
    def test_records_are_json_serializable(self) -> None:
        json.dumps(list(v3_records()), sort_keys=True)

    def test_records_declare_the_v2_annotation_fields(self) -> None:
        for record in v3_records():
            for field in V3_ANNOTATION_FIELDS:
                self.assertIn(field, record)

    def test_records_carry_the_two_new_dimensions(self) -> None:
        for record in v3_records():
            self.assertIn(record["statement_source"], STATEMENT_SOURCES)
            self.assertIn(record["certainty_level"], CERTAINTY_LEVELS)

    def test_case_index_maps_every_id(self) -> None:
        index = case_index()

        self.assertEqual(len(index), len(V3_CASES))
        for case in V3_CASES:
            self.assertIs(index[case.case_id], case)

    def test_counts_are_recomputed_not_stored(self) -> None:
        recomputed = Counter(case.group for case in V3_CASES)

        self.assertEqual(dict(group_counts()), dict(recomputed))


class DecontaminationTests(unittest.TestCase):
    """v3 reused familiar development sentences; the clean subset is v4."""

    def setUp(self) -> None:
        self.development = {case.text for case in BENCHMARK_CASES}
        self.clean = decontaminated_v3_cases()

    def test_v4_is_smaller_than_v3(self) -> None:
        self.assertLess(len(self.clean), len(V3_CASES))

    def test_v4_excludes_exactly_the_development_sentences(self) -> None:
        self.assertEqual(len(V3_CASES) - len(self.clean), 32)

    def test_no_v4_text_appears_in_the_development_benchmark(self) -> None:
        for case in self.clean:
            self.assertNotIn(case.text, self.development, case.case_id)

    def test_v4_keeps_case_identity_and_labels(self) -> None:
        original = case_index()
        for case in self.clean:
            self.assertIs(case, original[case.case_id])

    def test_v4_retains_the_attribution_focus_minimum(self) -> None:
        counts = Counter(case.focus for case in self.clean)

        self.assertGreaterEqual(counts[ATTRIBUTION], 20)

    def test_v4_retains_the_conditional_focus_minimum(self) -> None:
        counts = Counter(case.focus for case in self.clean)

        self.assertGreaterEqual(counts[CONDITIONAL], 20)

    def test_v4_falls_short_of_the_market_boundary_minimum(self) -> None:
        """Recorded as a known governance gap rather than hidden.

        v3 clears the >= 20 market-boundary minimum; the decontaminated subset
        does not, because five of its market-boundary cases were the reused
        development sentences. v4 is therefore clean but thin in exactly the
        dimension the phase wanted measured.
        """

        counts = Counter(case.focus for case in self.clean)

        self.assertEqual(counts[MARKET_BOUNDARY], 16)
        self.assertLess(counts[MARKET_BOUNDARY], 20)

    def test_v4_records_match_the_clean_subset(self) -> None:
        self.assertEqual(len(v4_records()), len(self.clean))

    def test_v4_is_a_subset_of_v3(self) -> None:
        v3_ids = {case.case_id for case in V3_CASES}
        v4_ids = {case.case_id for case in self.clean}

        self.assertTrue(v4_ids <= v3_ids)


if __name__ == "__main__":
    unittest.main()
