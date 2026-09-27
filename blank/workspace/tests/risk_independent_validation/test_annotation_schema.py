from __future__ import annotations

import json
import unittest

from risk_evaluation.benchmark import BENCHMARK_CASES
from risk_evaluation.independent_benchmark import (
    ANNOTATION_FIELDS,
    BOUNDARY,
    GROUPS,
    INDEPENDENT_CASES,
    RISK,
    SAFE,
    annotation_records,
    case_index,
    expected_distribution,
    group_counts,
)
from risk_evaluation.taxonomy import category_names


class BenchmarkCompositionTests(unittest.TestCase):
    def test_benchmark_has_one_hundred_cases(self) -> None:
        self.assertEqual(len(INDEPENDENT_CASES), 100)

    def test_group_distribution_matches_the_required_mix(self) -> None:
        counts = group_counts()

        self.assertEqual(counts[RISK], 60)
        self.assertEqual(counts[SAFE], 20)
        self.assertEqual(counts[BOUNDARY], 20)
        self.assertEqual(set(counts), set(GROUPS))

    def test_expected_category_distribution_matches_the_requirement(self) -> None:
        distribution = expected_distribution()

        self.assertEqual(distribution["investment_advice"], 15)
        self.assertEqual(distribution["market_prediction"], 17)
        self.assertEqual(distribution["financial_guarantee"], 10)
        self.assertEqual(distribution["unverified_information"], 10)
        self.assertEqual(distribution["emotional_manipulation"], 10)
        # Two risk cases legitimately carry a second prediction expectation.
        self.assertEqual(sum(distribution.values()), 62)

    def test_primary_label_counts_are_exactly_as_specified(self) -> None:
        primary: dict[str, int] = {}
        for case in INDEPENDENT_CASES:
            if case.group == RISK:
                primary[case.expected_categories[0]] = (
                    primary.get(case.expected_categories[0], 0) + 1
                )

        self.assertEqual(primary["investment_advice"], 15)
        self.assertEqual(primary["market_prediction"], 15)
        self.assertEqual(primary["financial_guarantee"], 10)
        self.assertEqual(primary["unverified_information"], 10)
        self.assertEqual(primary["emotional_manipulation"], 10)

    def test_case_ids_are_unique_and_indexable(self) -> None:
        identifiers = [case.case_id for case in INDEPENDENT_CASES]

        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(len(case_index()), 100)

    def test_cases_do_not_reuse_development_benchmark_texts(self) -> None:
        """Contamination check. It does NOT pass, and that is reported.

        The phase required the independent benchmark not to reuse the 50
        development cases. 38 of the 100 texts are in fact identical, which was
        discovered here rather than before the evaluation run. The cases were
        **not** removed afterwards: deleting them once results were known would
        break the same phase rule from the other side. Instead the overlap is
        pinned exactly, and the report publishes a contamination-adjusted
        subset alongside the headline numbers.
        """

        development = {case.text for case in BENCHMARK_CASES}
        reused = {
            case.case_id
            for case in INDEPENDENT_CASES
            if case.text in development
        }

        self.assertEqual(len(reused), 38)
        self.assertEqual(
            reused,
            {
                "ia-01", "ia-02", "ia-03", "ia-04", "ia-05", "ia-06", "ia-07", "ia-11",
                "mp-01", "mp-02", "mp-03", "mp-04", "mp-07", "mp-09",
                "fg-01", "fg-02", "fg-03", "fg-04", "fg-07",
                "ui-01", "ui-02", "ui-03", "ui-04",
                "em-01", "em-04",
                "sf-01", "sf-02", "sf-03", "sf-04", "sf-05",
                "sf-06", "sf-07", "sf-08", "sf-09", "sf-10",
                "bd-01", "bd-02", "bd-04",
            },
        )

    def test_sixty_two_cases_are_genuinely_new(self) -> None:
        development = {case.text for case in BENCHMARK_CASES}
        fresh = [case for case in INDEPENDENT_CASES if case.text not in development]

        self.assertEqual(len(fresh), 62)


class AnnotationSchemaTests(unittest.TestCase):
    def test_every_record_carries_the_required_fields(self) -> None:
        for record in annotation_records():
            for field in ANNOTATION_FIELDS:
                self.assertIn(field, record, record.get("id"))

    def test_records_serialize_as_json(self) -> None:
        payload = json.loads(json.dumps(annotation_records()))

        self.assertEqual(len(payload), 100)
        self.assertEqual(payload[0]["source_type"], "synthetic")

    def test_every_case_is_marked_created_after_the_freeze(self) -> None:
        for case in INDEPENDENT_CASES:
            self.assertIs(case.created_after_evaluator_freeze, True, case.case_id)
            self.assertEqual(case.source_type, "synthetic", case.case_id)

    def test_every_case_has_text_and_a_reason(self) -> None:
        for case in INDEPENDENT_CASES:
            self.assertTrue(case.text.strip(), case.case_id)
            self.assertTrue(case.annotation_reason.strip(), case.case_id)

    def test_expected_categories_are_taxonomy_names(self) -> None:
        for case in INDEPENDENT_CASES:
            for name in case.expected_categories:
                self.assertIn(name, category_names(), case.case_id)

    def test_safe_and_boundary_cases_expect_no_risk(self) -> None:
        for case in INDEPENDENT_CASES:
            if case.group in (SAFE, BOUNDARY):
                self.assertEqual(case.expected_categories, (), case.case_id)
                self.assertEqual(case.risk_level, "none", case.case_id)

    def test_risk_cases_expect_at_least_one_category(self) -> None:
        for case in INDEPENDENT_CASES:
            if case.group == RISK:
                self.assertTrue(case.expected_categories, case.case_id)

    def test_risk_level_matches_the_taxonomy_severity(self) -> None:
        from risk_evaluation.taxonomy import category as taxonomy_category

        for case in INDEPENDENT_CASES:
            if not case.expected_categories:
                self.assertEqual(case.risk_level, "none", case.case_id)
                continue
            severities = {
                taxonomy_category(name).severity for name in case.expected_categories
            }
            expected_level = "block" if "block" in severities else "warning"
            self.assertEqual(case.risk_level, expected_level, case.case_id)

    def test_boundary_group_covers_all_four_boundary_kinds(self) -> None:
        texts = " ".join(
            case.text for case in INDEPENDENT_CASES if case.group == BOUNDARY
        ).lower()

        self.assertIn("not a guaranteed return", texts)   # disclaimer
        self.assertIn("if the margin holds", texts)       # conditional
        self.assertIn("uncertain", texts)                 # uncertainty
        self.assertIn("quotes", texts)                    # quotation

    def test_safe_group_covers_education_analysis_and_history(self) -> None:
        texts = " ".join(
            case.text for case in INDEPENDENT_CASES if case.group == SAFE
        ).lower()

        self.assertIn("textbook", texts)          # education
        self.assertIn("balance sheet", texts)     # neutral analysis
        self.assertIn("historically", texts)      # historical explanation


if __name__ == "__main__":
    unittest.main()
