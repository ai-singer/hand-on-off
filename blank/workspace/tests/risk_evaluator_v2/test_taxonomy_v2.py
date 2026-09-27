from __future__ import annotations

import json
import unittest

from risk_evaluation.taxonomy import RISK_TAXONOMY, category as taxonomy_v1_category
from risk_evaluation.taxonomy_v2 import (
    ATTRIBUTION_AGNOSTIC_CATEGORIES,
    AUTHOR_VOICE_CATEGORIES,
    CATEGORY_PRECEDENCE,
    CERTAINTY_LEVELS,
    MARKET_CLAIM_CASES,
    STATEMENT_SOURCES,
    TAXONOMY_VERSION,
    applies_regardless_of_voice,
    categories_v2,
    category_v2,
    is_direct_prediction,
    market_claim_case,
    requires_author_voice,
    resolve_category_conflicts,
    taxonomy_v2_payload,
)


class DimensionTests(unittest.TestCase):
    """The two dimensions v2 adds are orthogonal to the categories."""

    def test_taxonomy_version_is_recorded(self) -> None:
        self.assertEqual(TAXONOMY_VERSION, "2.0.0")

    def test_statement_source_has_exactly_four_values(self) -> None:
        self.assertEqual(
            STATEMENT_SOURCES, ("author", "third_party", "quoted", "unknown")
        )

    def test_certainty_level_has_exactly_four_values(self) -> None:
        self.assertEqual(
            CERTAINTY_LEVELS, ("certain", "probable", "possible", "hypothetical")
        )

    def test_dimensions_share_no_value(self) -> None:
        """Otherwise a source could be mistaken for a certainty level."""

        self.assertEqual(set(STATEMENT_SOURCES) & set(CERTAINTY_LEVELS), set())

    def test_author_voice_categories_exclude_unverified_information(self) -> None:
        self.assertNotIn("unverified_information", AUTHOR_VOICE_CATEGORIES)

    def test_unverified_information_is_the_only_attribution_agnostic_category(
        self,
    ) -> None:
        self.assertEqual(
            ATTRIBUTION_AGNOSTIC_CATEGORIES, ("unverified_information",)
        )

    def test_the_five_categories_partition_into_voice_and_agnostic(self) -> None:
        names = {entry.name for entry in RISK_TAXONOMY}

        self.assertEqual(
            set(AUTHOR_VOICE_CATEGORIES) | set(ATTRIBUTION_AGNOSTIC_CATEGORIES), names
        )
        self.assertEqual(
            set(AUTHOR_VOICE_CATEGORIES) & set(ATTRIBUTION_AGNOSTIC_CATEGORIES), set()
        )

    def test_requires_author_voice_matches_the_declared_list(self) -> None:
        for entry in RISK_TAXONOMY:
            self.assertEqual(
                requires_author_voice(entry.name),
                entry.name in AUTHOR_VOICE_CATEGORIES,
                entry.name,
            )

    def test_applies_regardless_of_voice_matches_the_declared_list(self) -> None:
        self.assertTrue(applies_regardless_of_voice("unverified_information"))
        self.assertFalse(applies_regardless_of_voice("market_prediction"))


class MarketClaimCaseTests(unittest.TestCase):
    """v1 treated every market claim as one category; v2 separates three."""

    def test_three_cases_are_named(self) -> None:
        self.assertEqual(
            [case.name for case in MARKET_CLAIM_CASES],
            ["explicit_prediction", "attribution_expectation", "scenario_analysis"],
        )

    def test_exactly_one_case_is_a_direct_prediction(self) -> None:
        direct = [case.name for case in MARKET_CLAIM_CASES if case.is_direct_prediction]

        self.assertEqual(direct, ["explicit_prediction"])

    def test_each_case_carries_a_definition_and_example(self) -> None:
        for case in MARKET_CLAIM_CASES:
            self.assertTrue(case.definition.strip(), case.name)
            self.assertTrue(case.example.strip(), case.name)

    def test_author_plus_certain_is_the_direct_prediction(self) -> None:
        case = market_claim_case(statement_source="author", certainty_level="certain")

        self.assertEqual(case.name, "explicit_prediction")
        self.assertTrue(case.is_direct_prediction)

    def test_quoted_claim_is_an_attribution_expectation(self) -> None:
        case = market_claim_case(statement_source="quoted", certainty_level="certain")

        self.assertEqual(case.name, "attribution_expectation")
        self.assertFalse(case.is_direct_prediction)

    def test_third_party_claim_is_an_attribution_expectation(self) -> None:
        case = market_claim_case(
            statement_source="third_party", certainty_level="certain"
        )

        self.assertEqual(case.name, "attribution_expectation")

    def test_unknown_source_claim_is_an_attribution_expectation(self) -> None:
        case = market_claim_case(statement_source="unknown", certainty_level="certain")

        self.assertEqual(case.name, "attribution_expectation")

    def test_hypothetical_claim_is_scenario_analysis(self) -> None:
        case = market_claim_case(statement_source="author", certainty_level="hypothetical")

        self.assertEqual(case.name, "scenario_analysis")
        self.assertFalse(case.is_direct_prediction)

    def test_probable_claim_is_not_a_direct_prediction(self) -> None:
        case = market_claim_case(statement_source="author", certainty_level="probable")

        self.assertEqual(case.name, "scenario_analysis")

    def test_possible_claim_is_not_a_direct_prediction(self) -> None:
        case = market_claim_case(statement_source="author", certainty_level="possible")

        self.assertEqual(case.name, "scenario_analysis")

    def test_hypothetical_wins_over_attribution(self) -> None:
        """A quoted hypothetical is a scenario, not an expectation."""

        case = market_claim_case(statement_source="quoted", certainty_level="hypothetical")

        self.assertEqual(case.name, "scenario_analysis")

    def test_is_direct_prediction_needs_both_conditions(self) -> None:
        self.assertTrue(
            is_direct_prediction(statement_source="author", certainty_level="certain")
        )
        for source in STATEMENT_SOURCES:
            for level in CERTAINTY_LEVELS:
                expected = source == "author" and level == "certain"
                self.assertEqual(
                    is_direct_prediction(
                        statement_source=source, certainty_level=level
                    ),
                    expected,
                    f"{source}/{level}",
                )

    def test_unknown_statement_source_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            market_claim_case(statement_source="textbook", certainty_level="certain")

    def test_unknown_certainty_level_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            market_claim_case(statement_source="author", certainty_level="definite")


class PrecedenceTests(unittest.TestCase):
    def test_precedence_names_every_category_once(self) -> None:
        names = {entry.name for entry in RISK_TAXONOMY}

        self.assertEqual(set(CATEGORY_PRECEDENCE), names)
        self.assertEqual(len(CATEGORY_PRECEDENCE), len(set(CATEGORY_PRECEDENCE)))

    def test_resolution_returns_precedence_order(self) -> None:
        resolved = resolve_category_conflicts(
            ["emotional_manipulation", "investment_advice"],
            reader_pressure=True,
            statement_source="author",
        )

        self.assertEqual(resolved, ("investment_advice", "emotional_manipulation"))

    def test_dramatic_market_vocabulary_is_not_manipulation(self) -> None:
        resolved = resolve_category_conflicts(
            ["emotional_manipulation", "market_prediction"],
            reader_pressure=False,
            statement_source="author",
        )

        self.assertEqual(resolved, ("market_prediction",))

    def test_pressure_keeps_emotional_manipulation(self) -> None:
        resolved = resolve_category_conflicts(
            ["emotional_manipulation", "market_prediction"],
            reader_pressure=True,
            statement_source="author",
        )

        self.assertEqual(resolved, ("market_prediction", "emotional_manipulation"))

    def test_attribution_drops_author_voice_categories(self) -> None:
        resolved = resolve_category_conflicts(
            ["investment_advice", "market_prediction"],
            reader_pressure=True,
            statement_source="quoted",
        )

        self.assertEqual(resolved, ())

    def test_attribution_keeps_unverified_information(self) -> None:
        resolved = resolve_category_conflicts(
            ["investment_advice", "unverified_information"],
            reader_pressure=False,
            statement_source="quoted",
        )

        self.assertEqual(resolved, ("unverified_information",))

    def test_author_voice_keeps_every_category(self) -> None:
        resolved = resolve_category_conflicts(
            list(CATEGORY_PRECEDENCE),
            reader_pressure=True,
            statement_source="author",
        )

        self.assertEqual(resolved, CATEGORY_PRECEDENCE)

    def test_resolution_of_nothing_is_empty(self) -> None:
        self.assertEqual(
            resolve_category_conflicts(
                [], reader_pressure=True, statement_source="author"
            ),
            (),
        )

    def test_unknown_categories_are_kept_after_the_known_ones(self) -> None:
        resolved = resolve_category_conflicts(
            ["mystery", "investment_advice"],
            reader_pressure=True,
            statement_source="author",
        )

        self.assertEqual(resolved, ("investment_advice", "mystery"))


class PayloadTests(unittest.TestCase):
    def test_payload_records_every_governed_dimension(self) -> None:
        payload = taxonomy_v2_payload()

        for key in (
            "taxonomy_version",
            "categories",
            "statement_sources",
            "certainty_levels",
            "author_voice_categories",
            "attribution_agnostic_categories",
            "category_precedence",
            "market_claim_cases",
        ):
            self.assertIn(key, payload)

    def test_payload_is_json_serializable(self) -> None:
        json.dumps(taxonomy_v2_payload(), sort_keys=True)

    def test_categories_v2_is_the_unchanged_v1_taxonomy(self) -> None:
        self.assertEqual(categories_v2(), {entry.name: entry for entry in RISK_TAXONOMY})

    def test_category_v2_returns_the_v1_definition(self) -> None:
        for entry in RISK_TAXONOMY:
            self.assertEqual(category_v2(entry.name), taxonomy_v1_category(entry.name))

    def test_category_v2_rejects_an_unknown_name(self) -> None:
        with self.assertRaises(Exception):
            category_v2("not_a_category")


if __name__ == "__main__":
    unittest.main()
