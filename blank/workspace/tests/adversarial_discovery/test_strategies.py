from __future__ import annotations

import re
import unittest

from risk_evaluation.adversarial.generator import (
    ATTRIBUTION_LEADS,
    AUTHORITY_TEMPLATES,
    CERTAINTY_MASKED,
    CONTROLS,
    IMPLICIT_TEXTS,
    PARAPHRASE_TEXTS,
    SEEDS,
)
from risk_evaluation.adversarial.strategies import (
    FAMILIES,
    NEUTRAL_CONTEXT,
    NEUTRAL_CONTEXT_CONTROL,
    REQUIRED_ATTACKS,
    STRATEGIES,
    AttackStrategy,
    strategy_spec,
)
from risk_evaluation.taxonomy import RISK_TAXONOMY


class StrategyInventoryTests(unittest.TestCase):
    """Requirement 2: every attack strategy exists and is described."""

    def test_seven_strategies_are_declared(self) -> None:
        self.assertEqual(len(STRATEGIES), 7)
        self.assertEqual(len(list(AttackStrategy)), 7)

    def test_the_required_strategies_are_present(self) -> None:
        required = {
            "direct_statement",
            "paraphrase",
            "authority_disguise",
            "attribution_confusion",
            "implicit_recommendation",
            "certainty_masking",
            "context_attack",
        }

        self.assertEqual({item.value for item in AttackStrategy}, required)

    def test_every_strategy_has_one_spec(self) -> None:
        self.assertEqual({spec.strategy for spec in STRATEGIES}, set(AttackStrategy))

    def test_every_spec_states_a_rationale_and_a_basis(self) -> None:
        for spec in STRATEGIES:
            self.assertTrue(spec.rationale.strip(), spec.name)
            self.assertTrue(spec.expectation_basis.strip(), spec.name)

    def test_family_codes_are_unique_and_three_letters(self) -> None:
        codes = [spec.code for spec in STRATEGIES]

        self.assertEqual(len(codes), len(set(codes)))
        for code in codes:
            self.assertRegex(code, r"^[A-Z]{3}$")

    def test_families_map_onto_declared_strategies(self) -> None:
        for family, strategy in FAMILIES.items():
            self.assertIn(strategy, {item.value for item in AttackStrategy}, family)

    def test_spec_lookup_accepts_a_value_or_a_member(self) -> None:
        spec = strategy_spec("paraphrase")

        self.assertIs(spec.strategy, AttackStrategy.PARAPHRASE)
        self.assertIs(strategy_spec(AttackStrategy.PARAPHRASE), spec)

    def test_spec_lookup_rejects_an_unknown_name(self) -> None:
        with self.assertRaises(ValueError):
            strategy_spec("not_a_strategy")


class SeedTests(unittest.TestCase):
    """Seeds are the plain form of each risk; a strategy's effect is measured
    against them, so they must exist for every category."""

    def test_every_category_has_seeds(self) -> None:
        self.assertEqual(
            set(SEEDS), {entry.name for entry in RISK_TAXONOMY}
        )

    def test_every_category_has_at_least_four_seeds(self) -> None:
        for name, seeds in SEEDS.items():
            self.assertGreaterEqual(len(seeds), 4, name)

    def test_seeds_are_unique_across_categories(self) -> None:
        flattened = [seed for seeds in SEEDS.values() for seed in seeds]

        self.assertEqual(len(flattened), len(set(flattened)))

    def test_seeds_are_non_empty_sentences(self) -> None:
        for seeds in SEEDS.values():
            for seed in seeds:
                self.assertTrue(seed.strip())
                self.assertTrue(seed.endswith("."), seed)


class TemplateTests(unittest.TestCase):
    def test_authority_templates_are_format_strings_with_one_seed_slot(self) -> None:
        for template in AUTHORITY_TEMPLATES:
            self.assertIn("{seed}", template)
            self.assertTrue(template.format(seed="X").strip())

    def test_authority_templates_avoid_attribution_verbs(self) -> None:
        """The strategy is only an attack if the claim stays the author's.

        A reporting verb would make the sentence genuinely attributed, and guide
        v2 then says the author-voice category is correctly withdrawn - which is
        a control, not an attack.
        """

        reporting = re.compile(
            r"\b(?:say|says|said|expect|expects|expected|forecast\w*|project\w*|"
            r"estimate\w*|believe\w*|publish\w*|wrote|writes|note|notes|noted)\b"
        )
        for template in AUTHORITY_TEMPLATES:
            self.assertIsNone(reporting.search(template), template)

    def test_attribution_leads_carry_no_risk_vocabulary(self) -> None:
        """Otherwise the case would be detected for the wrong reason."""

        for lead in ATTRIBUTION_LEADS:
            lowered = lead.lower()
            for token in ("cannot fail", "no risk", "guaranteed", "never"):
                self.assertNotIn(token, lowered, lead)

    def test_neutral_pools_are_disjoint(self) -> None:
        """Controls must not reuse the attacks' filler.

        Sharing it made a context attack and a context control share most of
        their tokens, which the contamination auditor flagged.
        """

        self.assertEqual(set(NEUTRAL_CONTEXT) & set(NEUTRAL_CONTEXT_CONTROL), set())

    def test_neutral_sentences_are_non_empty(self) -> None:
        for sentence in (*NEUTRAL_CONTEXT, *NEUTRAL_CONTEXT_CONTROL):
            self.assertTrue(sentence.strip())

    def test_paraphrases_cover_every_category_with_two_each(self) -> None:
        self.assertEqual(set(PARAPHRASE_TEXTS), {entry.name for entry in RISK_TAXONOMY})
        for name, texts in PARAPHRASE_TEXTS.items():
            self.assertEqual(len(texts), 2, name)

    def test_paraphrases_are_not_verbatim_seeds(self) -> None:
        for name, texts in PARAPHRASE_TEXTS.items():
            for text in texts:
                self.assertNotIn(text, SEEDS[name], name)

    def test_implicit_texts_are_declared(self) -> None:
        self.assertEqual(len(IMPLICIT_TEXTS), 5)

    def test_certainty_masked_covers_both_categories(self) -> None:
        self.assertEqual(
            set(CERTAINTY_MASKED), {"market_prediction", "financial_guarantee"}
        )
        self.assertEqual(len(CERTAINTY_MASKED["market_prediction"]), 6)
        self.assertEqual(len(CERTAINTY_MASKED["financial_guarantee"]), 4)

    def test_certainty_masked_texts_avoid_the_certainty_vocabulary(self) -> None:
        """Removing the marker vocabulary is the whole strategy."""

        markers = (" will ", " definitely", " certainly", " surely", " bound to")
        for texts in CERTAINTY_MASKED.values():
            for text in texts:
                lowered = f" {text.lower()} "
                for marker in markers:
                    self.assertNotIn(marker, lowered, text)


class ControlDefinitionTests(unittest.TestCase):
    def test_there_are_controls(self) -> None:
        self.assertGreaterEqual(len(CONTROLS), 10)

    def test_every_control_states_why_the_guide_excludes_it(self) -> None:
        for text, _target, _strategy, why in CONTROLS:
            self.assertTrue(why.strip(), text)
            self.assertIn("guide v2", why)

    def test_every_control_targets_a_real_category(self) -> None:
        known = {entry.name for entry in RISK_TAXONOMY}
        for text, target, _strategy, _why in CONTROLS:
            self.assertIn(target, known, text)

    def test_every_control_uses_a_declared_strategy(self) -> None:
        for text, _target, strategy, _why in CONTROLS:
            self.assertIsInstance(strategy, AttackStrategy, text)

    def test_controls_are_not_empty(self) -> None:
        for text, _target, _strategy, _why in CONTROLS:
            self.assertTrue(text.strip())


class CompositionTargetTests(unittest.TestCase):
    def test_the_required_family_counts_are_declared(self) -> None:
        self.assertEqual(
            REQUIRED_ATTACKS,
            {
                "direct": 10,
                "paraphrase": 10,
                "authority": 10,
                "attribution": 5,
                "implicit": 5,
                "context": 10,
            },
        )

    def test_the_required_counts_sum_to_fifty(self) -> None:
        self.assertEqual(sum(REQUIRED_ATTACKS.values()), 50)

    def test_every_required_family_is_a_declared_family(self) -> None:
        for family in REQUIRED_ATTACKS:
            self.assertIn(family, FAMILIES)


if __name__ == "__main__":
    unittest.main()
