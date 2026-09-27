from __future__ import annotations

import json
import unittest

from risk_evaluation.adversarial.case import ATTACK, CONTROL, detect_duplicates
from risk_evaluation.adversarial.generator import (
    DEBATABLE_EXPECTATIONS,
    AdversarialRiskGenerator,
    adversarial_records,
    attack_counts,
    control_counts,
    default_cases,
    group_counts,
    strategy_counts,
    summarise,
)
from risk_evaluation.adversarial.strategies import (
    REQUIRED_ATTACKS,
    STRATEGIES,
    AttackStrategy,
)
from risk_evaluation.taxonomy import RISK_TAXONOMY
from risk_evaluation.taxonomy_v2 import taxonomy_v2_payload


class CompositionTests(unittest.TestCase):
    """Requirement 2 and the Phase 8.1 benchmark composition."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = default_cases()

    def test_at_least_fifty_generated_cases(self) -> None:
        self.assertGreaterEqual(len(self.cases), 50)

    def test_every_required_family_meets_its_count(self) -> None:
        counts = attack_counts(self.cases)

        for family, required in REQUIRED_ATTACKS.items():
            self.assertGreaterEqual(counts[family], required, family)

    def test_the_required_families_are_exactly_met(self) -> None:
        counts = attack_counts(self.cases)

        for family, required in REQUIRED_ATTACKS.items():
            self.assertEqual(counts[family], required, family)

    def test_certainty_masking_is_an_attack_even_though_it_is_not_required(
        self,
    ) -> None:
        self.assertEqual(attack_counts(self.cases)["certainty"], 10)

    def test_there_are_sixty_attacks_and_thirteen_controls(self) -> None:
        self.assertEqual(group_counts(self.cases), {ATTACK: 60, CONTROL: 13})

    def test_every_strategy_produced_cases(self) -> None:
        counts = strategy_counts(self.cases)

        for spec in STRATEGIES:
            self.assertGreater(counts[spec.name], 0, spec.name)

    def test_every_category_is_targeted(self) -> None:
        targets = {case.target_category for case in self.cases}

        self.assertEqual(targets, {entry.name for entry in RISK_TAXONOMY})

    def test_summarise_reports_the_composition(self) -> None:
        summary = summarise(self.cases)

        self.assertEqual(summary["total"], len(self.cases))
        self.assertEqual(summary["groups"], {ATTACK: 60, CONTROL: 13})
        self.assertEqual(summary["attacks_by_family"]["direct"], 10)

    def test_summarise_is_json_serializable(self) -> None:
        json.dumps(summarise(self.cases), sort_keys=True)


class DeterminismTests(unittest.TestCase):
    """Requirement 3: generator output is stable."""

    def test_two_runs_produce_identical_output(self) -> None:
        first = AdversarialRiskGenerator().generate_all()
        second = AdversarialRiskGenerator().generate_all()

        self.assertEqual(
            [case.as_dict() for case in first], [case.as_dict() for case in second]
        )

    def test_case_ids_are_unique(self) -> None:
        ids = [case.case_id for case in default_cases()]

        self.assertEqual(len(ids), len(set(ids)))

    def test_the_generated_set_contains_no_duplicate_texts(self) -> None:
        self.assertEqual(detect_duplicates(default_cases()), {})

    def test_texts_are_non_empty(self) -> None:
        for case in default_cases():
            self.assertTrue(case.text.strip(), case.case_id)

    def test_every_case_records_its_rationale(self) -> None:
        for case in default_cases():
            self.assertTrue(case.metadata["rationale"], case.case_id)

    def test_generating_one_strategy_is_a_stable_subset(self) -> None:
        generator = AdversarialRiskGenerator()
        single = generator.generate(AttackStrategy.PARAPHRASE)
        everything = generator.generate_all()
        subset = [c for c in everything if c.attack_strategy is AttackStrategy.PARAPHRASE]

        self.assertEqual(len(single), len(subset))

    def test_generating_a_single_strategy_excludes_the_others(self) -> None:
        cases = AdversarialRiskGenerator().generate(AttackStrategy.CONTEXT_ATTACK)

        self.assertTrue(
            all(c.attack_strategy is AttackStrategy.CONTEXT_ATTACK for c in cases)
        )

    def test_a_single_strategy_is_accepted_by_name(self) -> None:
        by_name = AdversarialRiskGenerator().generate("paraphrase")
        by_member = AdversarialRiskGenerator().generate(AttackStrategy.PARAPHRASE)

        self.assertEqual(len(by_name), len(by_member))


class StrategyFocusTests(unittest.TestCase):
    def test_implicit_recommendation_targets_advice(self) -> None:
        cases = AdversarialRiskGenerator().generate(
            AttackStrategy.IMPLICIT_RECOMMENDATION
        )

        self.assertTrue(all(c.target_category == "investment_advice" for c in cases))

    def test_certainty_masking_targets_predictions_and_guarantees(self) -> None:
        cases = [
            c
            for c in AdversarialRiskGenerator().generate(AttackStrategy.CERTAINTY_MASKING)
            if c.expected_detection
        ]

        self.assertEqual(
            {c.target_category for c in cases},
            {"market_prediction", "financial_guarantee"},
        )

    def test_direct_cases_are_the_seed_statements_unchanged(self) -> None:
        cases = [
            c
            for c in AdversarialRiskGenerator().generate(AttackStrategy.DIRECT_STATEMENT)
            if c.expected_detection
        ]

        self.assertTrue(all(c.text == c.metadata["seed"] for c in cases))

    def test_context_cases_are_longer_than_their_seed(self) -> None:
        cases = [
            c
            for c in AdversarialRiskGenerator().generate(AttackStrategy.CONTEXT_ATTACK)
            if c.expected_detection
        ]

        self.assertTrue(all(len(c.text) > len(c.metadata["seed"]) for c in cases))

    def test_attribution_cases_name_the_lead_they_use(self) -> None:
        cases = [
            c
            for c in AdversarialRiskGenerator().generate(
                AttackStrategy.ATTRIBUTION_CONFUSION
            )
            if c.expected_detection
        ]

        self.assertTrue(all(c.metadata["lead"] in c.text for c in cases))


class TaxonomyCouplingTests(unittest.TestCase):
    """The generator reads taxonomy v2 and refuses anything outside it."""

    def test_taxonomy_version_is_recorded(self) -> None:
        self.assertEqual(AdversarialRiskGenerator().taxonomy_version, "2.0.0")

    def test_a_taxonomy_missing_a_seeded_category_is_rejected(self) -> None:
        broken = taxonomy_v2_payload()
        broken["categories"] = [
            entry
            for entry in broken["categories"]
            if entry["name"] != "financial_guarantee"  # type: ignore[index]
        ]

        with self.assertRaises(ValueError):
            AdversarialRiskGenerator(taxonomy=broken)

    def test_the_default_taxonomy_is_v2(self) -> None:
        self.assertEqual(
            AdversarialRiskGenerator().taxonomy_version,
            taxonomy_v2_payload()["taxonomy_version"],
        )


class FailureExampleTests(unittest.TestCase):
    """The generator consumes recorded failures so it does not repeat them."""

    def test_known_failures_are_not_regenerated(self) -> None:
        known = "This fund cannot lose money."
        generator = AdversarialRiskGenerator(failure_examples=[known])
        texts = {case.normalized_text for case in generator.generate_all()}

        self.assertNotIn(known.lower(), texts)

    def test_skipped_cases_are_reported(self) -> None:
        generator = AdversarialRiskGenerator(
            failure_examples=["This fund cannot lose money."]
        )
        generator.generate_all()

        self.assertTrue(generator.skipped)

    def test_no_failure_examples_means_nothing_is_skipped(self) -> None:
        generator = AdversarialRiskGenerator()
        generator.generate_all()

        self.assertEqual(generator.skipped, ())

    def test_matching_ignores_case_and_punctuation(self) -> None:
        generator = AdversarialRiskGenerator(
            failure_examples=["this FUND cannot lose money"]
        )
        texts = {case.normalized_text for case in generator.generate_all()}

        self.assertNotIn("this fund cannot lose money", texts)


class ControlGenerationTests(unittest.TestCase):
    def test_controls_can_be_switched_off(self) -> None:
        cases = AdversarialRiskGenerator(include_controls=False).generate_all()

        self.assertTrue(all(c.expected_detection for c in cases))
        self.assertEqual(group_counts(cases)[CONTROL], 0)

    def test_control_counts_track_the_control_set(self) -> None:
        counts = control_counts(default_cases())

        self.assertEqual(sum(counts.values()), 13)

    def test_controls_are_marked_as_such(self) -> None:
        for case in default_cases():
            if not case.expected_detection:
                self.assertIn("control:", case.metadata["expectation_note"])

    def test_control_ids_use_the_control_code(self) -> None:
        for case in default_cases():
            if not case.expected_detection:
                self.assertTrue(case.case_id.startswith("ADV-CTL-"), case.case_id)


class ExpectationStrengthTests(unittest.TestCase):
    """Expectations that a careful annotator could dispute are marked as such."""

    def test_some_expectations_are_marked_debatable(self) -> None:
        self.assertTrue(DEBATABLE_EXPECTATIONS)

    def test_every_case_states_its_expectation_strength(self) -> None:
        for case in default_cases():
            self.assertIn(
                case.metadata["expectation_strength"], ("clear", "debatable")
            )

    def test_debatable_texts_are_actually_in_the_set(self) -> None:
        texts = {case.text for case in default_cases()}

        self.assertTrue(DEBATABLE_EXPECTATIONS <= texts)

    def test_controls_are_all_clear_expectations(self) -> None:
        for case in default_cases():
            if not case.expected_detection:
                self.assertEqual(case.metadata["expectation_strength"], "clear")


class RecordExportTests(unittest.TestCase):
    def test_records_are_json_serializable(self) -> None:
        json.dumps(list(adversarial_records()), sort_keys=True)

    def test_every_case_yields_a_record(self) -> None:
        self.assertEqual(len(adversarial_records()), len(default_cases()))

    def test_records_carry_the_auditor_fields(self) -> None:
        for record in adversarial_records():
            for key in ("id", "text", "expected_categories", "group"):
                self.assertIn(key, record)

    def test_records_are_ordered_like_the_cases(self) -> None:
        self.assertEqual(
            [record["id"] for record in adversarial_records()],
            [case.case_id for case in default_cases()],
        )


if __name__ == "__main__":
    unittest.main()
