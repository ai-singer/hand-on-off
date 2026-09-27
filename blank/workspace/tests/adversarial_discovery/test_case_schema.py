from __future__ import annotations

import json
import unittest

from risk_evaluation.adversarial.case import (
    ATTACK,
    CONTROL,
    GROUPS,
    AdversarialCase,
    case_id_for,
    detect_duplicates,
    normalize_text,
)
from risk_evaluation.adversarial.strategies import AttackStrategy
from risk_evaluation.taxonomy import RISK_TAXONOMY


def _case(**overrides) -> AdversarialCase:
    base = dict(
        case_id="ADV-DIR-01",
        text="This fund cannot lose money.",
        target_category="financial_guarantee",
        attack_strategy=AttackStrategy.DIRECT_STATEMENT,
        expected_detection=True,
        metadata={"rationale": "synthetic"},
    )
    base.update(overrides)
    return AdversarialCase(**base)


class SchemaValidationTests(unittest.TestCase):
    """Requirement 1: case schema validation."""

    def test_a_well_formed_case_is_accepted(self) -> None:
        case = _case()

        self.assertEqual(case.case_id, "ADV-DIR-01")
        self.assertEqual(case.group, ATTACK)

    def test_case_id_shape_is_enforced(self) -> None:
        for bad in ("ADV-001", "adv-dir-01", "ADV-DIR-1", "DIR-01", ""):
            with self.assertRaises(ValueError, msg=bad):
                _case(case_id=bad)

    def test_empty_text_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _case(text="   ")

    def test_unknown_target_category_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            _case(target_category="not_a_category")

    def test_every_taxonomy_category_is_a_valid_target(self) -> None:
        for entry in RISK_TAXONOMY:
            self.assertEqual(_case(target_category=entry.name).target_category, entry.name)

    def test_strategy_must_be_an_enum_member(self) -> None:
        with self.assertRaises(ValueError):
            _case(attack_strategy="direct_statement")

    def test_every_strategy_is_accepted(self) -> None:
        for strategy in AttackStrategy:
            self.assertEqual(
                _case(attack_strategy=strategy).attack_strategy, strategy
            )

    def test_expected_detection_must_be_a_bool(self) -> None:
        for bad in (1, 0, "true", None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                _case(expected_detection=bad)

    def test_false_expectation_makes_the_case_a_control(self) -> None:
        case = _case(expected_detection=False)

        self.assertEqual(case.group, CONTROL)
        self.assertIn(case.group, GROUPS)

    def test_metadata_is_copied_not_aliased(self) -> None:
        source = {"rationale": "original"}
        case = _case(metadata=source)
        source["rationale"] = "mutated"

        self.assertEqual(case.metadata["rationale"], "original")

    def test_case_is_hashable_by_id(self) -> None:
        self.assertEqual(len({_case(), _case()}), 1)


class CaseProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = _case()

    def test_as_dict_carries_the_documented_fields(self) -> None:
        payload = self.case.as_dict()

        self.assertEqual(
            set(payload),
            {
                "id",
                "text",
                "target_category",
                "attack_strategy",
                "expected_detection",
                "metadata",
            },
        )

    def test_id_property_matches_the_record_field(self) -> None:
        self.assertEqual(self.case.id, self.case.case_id)
        self.assertEqual(self.case.as_dict()["id"], self.case.case_id)

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(self.case.as_dict(), sort_keys=True)

    def test_annotation_record_has_the_fields_the_registry_and_auditor_read(
        self,
    ) -> None:
        record = self.case.annotation_record()

        for key in ("id", "text", "expected_categories", "group"):
            self.assertIn(key, record)

    def test_annotation_record_carries_the_adversarial_fields(self) -> None:
        record = self.case.annotation_record()

        self.assertEqual(record["attack_strategy"], "direct_statement")
        self.assertTrue(record["expected_detection"])
        self.assertEqual(record["expected_categories"], ["financial_guarantee"])

    def test_annotation_record_is_json_serializable(self) -> None:
        json.dumps(self.case.annotation_record(), sort_keys=True)

    def test_severity_follows_the_target_category(self) -> None:
        self.assertEqual(_case(target_category="investment_advice").severity, "high")
        self.assertEqual(_case(target_category="market_prediction").severity, "medium")

    def test_expectation_basis_is_exposed(self) -> None:
        case = _case(metadata={"expectation_basis": "guide v2 section 7"})

        self.assertEqual(case.expectation_basis, "guide v2 section 7")


class CaseIdTests(unittest.TestCase):
    def test_family_code_is_derived_from_the_strategy(self) -> None:
        self.assertEqual(case_id_for(AttackStrategy.DIRECT_STATEMENT, 1), "ADV-DIR-01")
        self.assertEqual(case_id_for(AttackStrategy.CONTEXT_ATTACK, 12), "ADV-CTX-12")

    def test_control_ids_use_their_own_code(self) -> None:
        self.assertEqual(
            case_id_for(AttackStrategy.PARAPHRASE, 3, control=True), "ADV-CTL-03"
        )

    def test_ids_are_two_digit_padded(self) -> None:
        self.assertTrue(case_id_for(AttackStrategy.PARAPHRASE, 7).endswith("-07"))

    def test_a_strategy_value_string_is_accepted(self) -> None:
        self.assertEqual(case_id_for("paraphrase", 1), "ADV-PAR-01")

    def test_an_unknown_strategy_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            case_id_for("telepathy", 1)


class DuplicateDetectionTests(unittest.TestCase):
    """Requirement 6: duplicate case detection."""

    def test_normalisation_ignores_case_and_punctuation(self) -> None:
        self.assertEqual(
            normalize_text("Buy THIS stock!"), normalize_text("buy  this   stock")
        )

    def test_normalisation_preserves_chinese_text(self) -> None:
        self.assertEqual(normalize_text("立即买入这只股票。"), "立即买入这只股票")

    def test_identical_texts_are_reported_as_one_group(self) -> None:
        cases = [
            _case(case_id="ADV-DIR-01", text="Buy this stock."),
            _case(case_id="ADV-DIR-02", text="buy this stock"),
        ]
        found = detect_duplicates(cases)

        self.assertEqual(len(found), 1)
        self.assertEqual(next(iter(found.values())), ("ADV-DIR-01", "ADV-DIR-02"))

    def test_distinct_texts_are_not_reported(self) -> None:
        cases = [
            _case(case_id="ADV-DIR-01", text="Buy this stock."),
            _case(case_id="ADV-DIR-02", text="Sell this bond."),
        ]

        self.assertEqual(detect_duplicates(cases), {})

    def test_normalized_text_is_exposed_on_the_case(self) -> None:
        self.assertEqual(_case(text="Buy THIS!").normalized_text, "buy this")


if __name__ == "__main__":
    unittest.main()
