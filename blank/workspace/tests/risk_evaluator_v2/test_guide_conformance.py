"""Do the published guide and the shipped evaluator agree?

Guide v2 is the normative document: it defines the two dimensions, the three
market-claim cases, the attribution precedence and the category precedence. The
evaluator is supposed to implement it. This module checks that claim against the
guide's own published examples rather than against the evaluator's behaviour.

Where they disagree, the disagreement is pinned as a named defect so it cannot be
quietly forgotten. The evaluator was deliberately *not* changed to close these
gaps after the Phase 7.5 benchmark had been measured: adjusting patterns in
response to known failing examples is tuning, not validation. They are reported
as defects and carried forward instead.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from risk_evaluation.benchmark_v2 import case_index
from risk_evaluation.semantic_evaluator_v2 import SemanticRiskEvaluatorV2
from risk_evaluation.taxonomy_v2 import (
    CATEGORY_PRECEDENCE,
    is_direct_prediction,
)


GUIDE_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "RISK_ANNOTATION_GUIDE_v2.md"
)

#: The guide's section 5 table: (text, certainty_level, categories).
GUIDE_TABLE_ROWS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "If the margin holds, the company could grow, but that is uncertain.",
        "hypothetical",
        (),
    ),
    (
        "If you want higher returns, buy this stock.",
        "hypothetical",
        ("investment_advice",),
    ),
    ("The stock may rise.", "possible", ()),
    ("The stock will rise.", "certain", ("market_prediction",)),
)


class GuideExistsTests(unittest.TestCase):
    def test_guide_v2_is_published(self) -> None:
        self.assertTrue(GUIDE_PATH.is_file())

    def test_guide_declares_its_version(self) -> None:
        text = GUIDE_PATH.read_text(encoding="utf-8")

        self.assertIn("Risk Annotation Guide v2", text)

    def test_guide_states_both_dimensions(self) -> None:
        text = GUIDE_PATH.read_text(encoding="utf-8")

        self.assertIn("statement_source", text)
        self.assertIn("certainty_level", text)

    def test_guide_states_all_four_source_values(self) -> None:
        text = GUIDE_PATH.read_text(encoding="utf-8")

        for value in ("author", "third_party", "quoted", "unknown"):
            self.assertIn(value, text)

    def test_guide_states_all_four_certainty_values(self) -> None:
        text = GUIDE_PATH.read_text(encoding="utf-8")

        for value in ("certain", "probable", "possible", "hypothetical"):
            self.assertIn(value, text)

    def test_guide_states_the_precedence_chain_in_order(self) -> None:
        text = GUIDE_PATH.read_text(encoding="utf-8")

        self.assertIn(" > ".join(CATEGORY_PRECEDENCE), re.sub(r"\s+", " ", text))

    def test_guide_carries_a_conformance_status_section(self) -> None:
        """A guide that documents behaviour the code lacks must say so."""

        self.assertIn("Conformance status", GUIDE_PATH.read_text(encoding="utf-8"))


class GuideTableTests(unittest.TestCase):
    """Rows the evaluator *does* reproduce. These are the conformance baseline."""

    def setUp(self) -> None:
        self.evaluator = SemanticRiskEvaluatorV2()

    def test_reproduced_rows_match_the_published_table(self) -> None:
        reproduced = (
            GUIDE_TABLE_ROWS[1],
            GUIDE_TABLE_ROWS[2],
        )
        for text, certainty, categories in reproduced:
            analysis = self.evaluator.analyze(text)

            self.assertEqual(analysis.certainty_level, certainty, text)
            self.assertEqual(analysis.categories, categories, text)

    def test_conditional_directive_rule_is_implemented(self) -> None:
        analysis = self.evaluator.analyze(GUIDE_TABLE_ROWS[1][0])

        self.assertEqual(analysis.certainty_level, "hypothetical")
        self.assertIn("investment_advice", analysis.categories)


class GuideDefectTests(unittest.TestCase):
    """The five published examples the evaluator does not reproduce.

    None of these is a stylistic disagreement; each is a case where the guide
    states an outcome and the evaluator produces a different one. They are the
    Phase 7.5 defect list.
    """

    def setUp(self) -> None:
        self.evaluator = SemanticRiskEvaluatorV2()

    def test_defect_1_implied_certainty_is_not_flagged(self) -> None:
        """Guide row 4: "The stock will rise." must be `market_prediction`."""

        text, certainty, categories = GUIDE_TABLE_ROWS[3]
        analysis = self.evaluator.analyze(text)

        self.assertEqual(analysis.certainty_level, certainty)
        self.assertNotEqual(analysis.categories, categories)

    def test_defect_2_conditional_outcome_with_holds_fires_advice(self) -> None:
        """Guide row 1 must report no category."""

        text, certainty, categories = GUIDE_TABLE_ROWS[0]
        analysis = self.evaluator.analyze(text)

        self.assertEqual(analysis.certainty_level, certainty)
        self.assertNotEqual(analysis.categories, categories)

    def test_defect_3_inverted_should_outcome_fires_advice(self) -> None:
        """The guide's own marker-table example for inverted `should`."""

        analysis = self.evaluator.analyze(
            "Should the market decline, the position would lose value."
        )

        self.assertEqual(analysis.certainty_level, "hypothetical")
        self.assertEqual(analysis.categories, ("investment_advice",))

    def test_defect_4_were_to_misses_a_multiword_subject(self) -> None:
        """The guide's own `were … to` example."""

        analysis = self.evaluator.analyze(
            "Were the deal to close, revenue might rise."
        )

        self.assertEqual(analysis.certainty_level, "possible")

    def test_defect_5_precedence_has_no_effect_on_the_report(self) -> None:
        """Guide section 6.2 documents an ordering the implementation discards.

        `resolve_category_conflicts` returns precedence order, but the caller
        converts it to a `set` and then sorts alphabetically, so precedence
        currently selects nothing and orders nothing.
        """

        case = case_index()["fg-05"]
        analysis = self.evaluator.analyze(case.text)

        self.assertEqual(
            analysis.categories, ("financial_guarantee", "investment_advice")
        )
        self.assertNotEqual(
            list(analysis.categories),
            [name for name in CATEGORY_PRECEDENCE if name in analysis.categories],
        )

    def test_the_defect_count_is_recorded(self) -> None:
        """Five published examples disagree. The report states the same number."""

        disagreeing = 0
        for text, certainty, categories in GUIDE_TABLE_ROWS:
            analysis = self.evaluator.analyze(text)
            if (
                analysis.certainty_level != certainty
                or analysis.categories != categories
            ):
                disagreeing += 1

        self.assertEqual(disagreeing, 2)
        self.assertEqual(len(GUIDE_TABLE_ROWS), 4)


class GuideInternalConsistencyTests(unittest.TestCase):
    """The guide must not contradict the taxonomy module it describes."""

    def setUp(self) -> None:
        self.text = GUIDE_PATH.read_text(encoding="utf-8")

    def test_guide_lists_the_declared_precedence_verbatim(self) -> None:
        flattened = re.sub(r"\s+", " ", self.text)

        self.assertIn(" > ".join(CATEGORY_PRECEDENCE), flattened)

    def test_guide_agrees_with_is_direct_prediction_on_the_three_cases(self) -> None:
        self.assertTrue(
            is_direct_prediction(statement_source="author", certainty_level="certain")
        )
        for case in ("author/probable", "third_party/certain", "quoted/certain"):
            source, level = case.split("/")
            self.assertFalse(
                is_direct_prediction(statement_source=source, certainty_level=level),
                case,
            )

    def test_guide_says_existing_versions_are_never_relabelled(self) -> None:
        self.assertIn("never relabelled in place", self.text)


if __name__ == "__main__":
    unittest.main()
