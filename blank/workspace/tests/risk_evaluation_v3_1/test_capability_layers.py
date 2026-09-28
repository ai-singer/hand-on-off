"""The two capability layers, on the wordings that motivated them.

Every case here comes from the gap and defect probes run before any Phase 8.8 code
existed, so a test that passes says a measured defect is answered and a test that
fails says it came back.
"""

from __future__ import annotations

import re
import unittest

from risk_evaluation.taxonomy_v2 import CERTAINTY_LEVELS
from risk_evaluation.v3 import evaluate
from risk_evaluation.v3.model import NEGATION_SCOPES
from risk_evaluation.v3_1 import advice, certainty, detectors, modal, signals
from risk_evaluation.v3_1.advice import (
    ADVICE_VERDICT,
    GERUND_SUBJECT,
    METHOD_GUIDANCE,
    NO_DIRECTIVE,
    THIRD_PERSON_SUBJECT,
)
from risk_evaluation.v3_1.advice import evaluate as advice_of
from risk_evaluation.v3_1.certainty import (
    CERTAIN,
    HYPOTHETICAL,
    POSSIBLE,
    PROBABLE,
    CertaintyError,
    Carrier,
    Strength,
    rank,
    strongest,
    weakest,
)
from risk_evaluation.v3_1.modal import (
    CONDITIONAL_SCENARIO,
    NON_DIRECTIONAL_VERDICT,
    NON_PREDICTION_MODAL,
    PREDICTION_VERDICT,
    WEAK_PREDICTION,
)
from risk_evaluation.v3_1.modal import evaluate as modal_of
from risk_evaluation.v3_1.signals import (
    SIGNAL_NAMES,
    Signal,
    SignalError,
    SignalSet,
    build,
)


class SignalVocabularyTests(unittest.TestCase):
    def test_the_signals_are_the_declared_eight(self) -> None:
        self.assertEqual(len(SIGNAL_NAMES), 8)
        self.assertEqual({item["name"] for item in signals.describe()}, set(SIGNAL_NAMES))
        self.assertEqual(
            set(signals.SIGNAL_NAMES),
            set(signals.PREDICTION_SIGNALS) | set(signals.ADVICE_SIGNALS),
        )
        self.assertEqual(len(signals.describe()), 8)

    def test_every_signal_belongs_to_a_capability(self) -> None:
        for name in SIGNAL_NAMES:
            self.assertIn(signals.SIGNAL_FAMILIES[name], signals.CAPABILITIES, name)
        for capability in signals.CAPABILITIES:
            self.assertTrue(
                [
                    name
                    for name in SIGNAL_NAMES
                    if signals.SIGNAL_FAMILIES[name] == capability
                ],
                capability,
            )

    def test_an_unknown_signal_is_rejected(self) -> None:
        with self.assertRaises(SignalError):
            Signal("vibes", (0, 4), "vibes")

    def test_a_backwards_span_is_rejected(self) -> None:
        with self.assertRaises(SignalError):
            Signal(signals.MARKET_ENTITY, (5, 2), "index")

    def test_a_signal_set_reports_presence_and_absence(self) -> None:
        found = build(
            Signal(signals.MARKET_ENTITY, (0, 9), "the index", "VALUE"),
            Signal(signals.FUTURE_MARKER, (10, 20), "next year", "horizon"),
        )
        self.assertTrue(found.has(signals.MARKET_ENTITY))
        self.assertFalse(found.has(signals.OUTCOME_EXPRESSION))
        self.assertTrue(found.includes((signals.MARKET_ENTITY, signals.FUTURE_MARKER)))
        self.assertFalse(found.includes(signals.PREDICTION_SIGNALS))
        self.assertEqual(found.get(signals.MARKET_ENTITY).detail, "VALUE")

    def test_a_signal_set_is_in_reading_order(self) -> None:
        found = build(
            Signal(signals.OUTCOME_EXPRESSION, (20, 25), "rise"),
            Signal(signals.MARKET_ENTITY, (0, 9), "the index"),
        )
        self.assertEqual(
            found.names, (signals.MARKET_ENTITY, signals.OUTCOME_EXPRESSION)
        )

    def test_require_raises_with_a_reason(self) -> None:
        found = build(Signal(signals.MARKET_ENTITY, (0, 9), "the index"))
        with self.assertRaises(SignalError):
            found.require(signals.PREDICTION_SIGNALS, reason="not a prediction")

    def test_every_signal_has_a_stable_marker(self) -> None:
        signal = Signal(signals.MARKET_ENTITY, (0, 9), "The Index", "VALUE")
        self.assertEqual(signal.marker, "signal:market_entity:VALUE")
        self.assertEqual(signal.as_dict()["family"], "modal_prediction")

    def test_a_signal_family_can_be_selected(self) -> None:
        found = build(
            Signal(signals.MARKET_ENTITY, (0, 9), "the index"),
            Signal(signals.ADDRESS, (0, 3), "you"),
        )
        self.assertEqual(len(found.family(signals.MODAL_PREDICTION)), 1)
        self.assertEqual(len(found.family(signals.ADVICE_BOUNDARY)), 1)


class CertaintyTests(unittest.TestCase):
    def test_the_order_is_the_taxonomys_four_levels_weakest_first(self) -> None:
        self.assertEqual(set(certainty.ORDER), set(CERTAINTY_LEVELS))
        self.assertEqual(certainty.ORDER[0], HYPOTHETICAL)
        self.assertEqual(certainty.ORDER[-1], CERTAIN)

    def test_weakest_wins(self) -> None:
        self.assertEqual(weakest(CERTAIN, PROBABLE), PROBABLE)
        self.assertEqual(weakest(CERTAIN, PROBABLE, POSSIBLE), POSSIBLE)
        self.assertEqual(weakest(HYPOTHETICAL, POSSIBLE), HYPOTHETICAL)

    def test_no_carrier_means_asserted_not_hedged(self) -> None:
        """An all-empty call is `certain`: absence of a hedge is not a hedge."""

        self.assertEqual(weakest(), CERTAIN)
        self.assertEqual(weakest("", CERTAIN), CERTAIN)

    def test_strongest_is_the_other_direction(self) -> None:
        self.assertEqual(strongest(POSSIBLE, CERTAIN), CERTAIN)
        self.assertEqual(strongest(), CERTAIN)

    def test_an_unknown_level_is_rejected(self) -> None:
        with self.assertRaises(CertaintyError):
            rank("fairly likely")

    def test_only_certain_is_not_hedged(self) -> None:
        for level in (PROBABLE, POSSIBLE, HYPOTHETICAL):
            self.assertTrue(Strength(level).hedged, level)
        self.assertFalse(Strength(CERTAIN).hedged)

    def test_the_decisive_carrier_is_the_weakest_one(self) -> None:
        found = Strength(
            PROBABLE,
            (
                Carrier(CERTAIN, "will", (0, 4), "verb"),
                Carrier(PROBABLE, "probably", (5, 13), "adverb"),
            ),
        )
        self.assertEqual(found.marker, "probably")
        self.assertEqual(len(found.carriers), 2)

    def test_the_guide_markers_are_carriers(self) -> None:
        cases = (
            ("The share price will rise.", CERTAIN),
            ("The share price is certain to rise.", CERTAIN),
            ("Growth will definitely continue.", CERTAIN),
            ("Profits are likely to grow.", PROBABLE),
            ("The market will probably crash.", PROBABLE),
            ("The fund should outperform.", PROBABLE),
            ("The stock may rise.", POSSIBLE),
            ("The index might fall.", POSSIBLE),
            ("Yields could double.", POSSIBLE),
            ("Perhaps the fund will recover.", POSSIBLE),
            ("It is possible that the price will double.", POSSIBLE),
            ("There is a chance the shares will recover.", POSSIBLE),
            ("Were the deal to close, revenue might rise.", HYPOTHETICAL),
            ("If rates fall, the stock may rise.", HYPOTHETICAL),
            ("Should the market decline, the position would lose value.", HYPOTHETICAL),
            ("Depending on the assumptions, the valuation ranges widely.", HYPOTHETICAL),
            ("A descriptive sentence with no carrier at all.", CERTAIN),
        )
        for text, expected in cases:
            self.assertEqual(modal_of(text).strength.level, expected, text)

    def test_the_weakest_carrier_decides_not_the_verb(self) -> None:
        """`will probably` is `probable`, and that is the whole of Capability 1."""

        self.assertEqual(modal_of("The market will probably crash.").strength.level, PROBABLE)
        self.assertEqual(modal_of("The market will certainly crash.").strength.level, CERTAIN)

    def test_every_carrier_level_is_declared(self) -> None:
        for level, _kind, _pattern in certainty.CARRIERS:
            self.assertIn(level, certainty.ORDER, level)

    def test_every_carrier_pattern_compiles(self) -> None:
        for _level, _kind, pattern in certainty.CARRIERS:
            re.compile(pattern)


class ModalPredictionTests(unittest.TestCase):
    """Capability 1, on the measured defect set."""

    def test_the_three_measured_false_positives_are_declined(self) -> None:
        for text in (
            "The market will probably crash next month.",
            "There is a chance the shares will recover.",
            "It is possible that the price will double.",
        ):
            found = modal_of(text)
            self.assertIn(found.verdict, {WEAK_PREDICTION, CONDITIONAL_SCENARIO}, text)
            self.assertTrue(found.declines, text)
            self.assertEqual(evaluate(text).categories, (), text)

    def test_a_certain_prediction_is_a_prediction(self) -> None:
        found = modal_of("The share price will rise next year.")
        self.assertEqual(found.verdict, PREDICTION_VERDICT)
        self.assertEqual(found.strength.level, CERTAIN)
        self.assertIsNotNone(found.finding)
        self.assertTrue(found.finding.asserted)
        self.assertEqual(found.finding.certainty, CERTAIN)
        self.assertFalse(found.declines)

    def test_a_weak_prediction_is_reported_and_hedged(self) -> None:
        found = modal_of("The index may recover next quarter.")
        self.assertEqual(found.verdict, WEAK_PREDICTION)
        self.assertEqual(found.strength.level, POSSIBLE)
        self.assertIsNotNone(found.finding)
        self.assertFalse(found.finding.asserted)
        self.assertTrue(found.finding.hedge)

    def test_the_phase_8_6_relation_gap_is_closed(self) -> None:
        """Seven of eight weak predictions produced no relation before Phase 8.8."""

        cases = (
            ("Yields could double this year.", "double"),
            ("The share price is likely to rise.", "rise"),
            ("Earnings will probably decline.", "decline"),
            ("The fund might outperform its benchmark next year.", "outperform"),
            ("The valuation is expected to increase.", "increase"),
            ("The payout could grow over the next two years.", "grow"),
            ("Perhaps the share price will double this year.", "double"),
        )
        for text, predicate in cases:
            found = modal_of(text)
            self.assertIsNotNone(found.finding, text)
            self.assertEqual(found.finding.predicate, predicate, text)
            relations = [
                intent.relation
                for intent in evaluate(text).claims[0].intents
            ]
            self.assertIn("PREDICTION", relations, text)

    def test_the_four_signals_are_all_required_and_all_reported(self) -> None:
        found = modal_of("The share price will rise next year.")
        self.assertEqual(set(found.signal_names), set(signals.PREDICTION_SIGNALS))

    def test_a_symmetric_pair_is_not_directional(self) -> None:
        for text in (
            "The value of investments may fall as well as rise.",
            "Fund values can go down as well as up.",
            "Investment returns are not guaranteed and may go down as well as up.",
        ):
            found = modal_of(text)
            self.assertEqual(found.verdict, NON_DIRECTIONAL_VERDICT, text)
            self.assertTrue(found.declines, text)

    def test_a_non_directional_verb_is_a_disclosure(self) -> None:
        for text in (
            "The price of units may fluctuate.",
            "Yields may differ between share classes.",
            "Returns may vary depending on market conditions.",
        ):
            found = modal_of(text)
            self.assertEqual(found.verdict, NON_DIRECTIONAL_VERDICT, text)
            self.assertTrue(found.declines, text)

    def test_an_epistemic_modal_is_not_a_prediction(self) -> None:
        for text in (
            "The fee may indicate a higher turnover.",
            "This document may include forward-looking statements.",
            "The index may refer to a benchmark maintained by the provider.",
            "Charges may apply to early redemptions.",
            "The report may reflect estimates rather than actual results.",
        ):
            found = modal_of(text)
            self.assertEqual(found.verdict, NON_PREDICTION_MODAL, text)
            self.assertTrue(found.declines, text)
            self.assertEqual(evaluate(text).categories, (), text)

    def test_a_conditional_reports_no_relation_at_all(self) -> None:
        """Guide 5: a conditional asserts nothing unconditionally."""

        for text in (
            "Should the index fall, the fund would underperform.",
            "The position would lose value if rates rise.",
        ):
            found = modal_of(text)
            self.assertEqual(found.verdict, CONDITIONAL_SCENARIO, text)
            self.assertIsNone(found.finding, text)
            self.assertEqual(evaluate(text).categories, (), text)

    def test_not_matching_is_not_evidence_against_a_prediction(self) -> None:
        """The distinction that keeps the layer from deleting what it cannot see.

        `Turnover expands sharply next quarter.` has no modal at all, and the
        Phase 8.4 horizon frame is right to call it a prediction. A layer that
        treated "not my shape" as evidence would break it.
        """

        found = modal_of("Turnover expands sharply next quarter.")
        self.assertEqual(found.verdict, "no_modal")
        self.assertFalse(found.declines)
        self.assertEqual(found.declined_categories, ())
        self.assertEqual(evaluate("Turnover expands sharply next quarter.").categories, ("market_prediction",))

    def test_every_verdict_is_declared_and_a_declining_one_names_a_category(self) -> None:
        self.assertEqual(len(modal.VERDICTS), len(set(modal.VERDICTS)))
        for verdict in modal.DECLINING_VERDICTS:
            self.assertIn(verdict, modal.VERDICTS, verdict)

    def test_a_non_string_is_rejected(self) -> None:
        with self.assertRaises(modal.ModalError):
            modal_of(None)  # type: ignore[arg-type]

    def test_the_capability_serialises(self) -> None:
        payload = modal_of("The index may recover next quarter.").as_dict()
        self.assertEqual(payload["capability"], "modal_prediction")
        self.assertEqual(payload["verdict"], WEAK_PREDICTION)
        self.assertTrue(payload["declines"])
        self.assertTrue(payload["signals"]["names"])

    def test_the_comparison_outcomes_are_inflected(self) -> None:
        for text in (
            "The fund will outperform its benchmark.",
            "The fund might underperform next year.",
            "The share price is likely to beat consensus.",
        ):
            found = modal_of(text)
            self.assertTrue(
                found.verdict in {PREDICTION_VERDICT, WEAK_PREDICTION}, (text, found.verdict)
            )
            self.assertIsNotNone(found.finding, text)


class AdviceBoundaryTests(unittest.TestCase):
    """Capability 2, on the measured defect set."""

    def test_the_six_measured_false_negatives_are_fixed(self) -> None:
        cases = (
            "You ought to trim your position.",
            "It would be prudent to trim your holdings.",
            "A sensible investor would avoid this fund.",
            "Investors would be wise to reduce their holdings.",
            "We would suggest selling the shares.",
            "Now is the time to buy the dip.",
        )
        for text in cases:
            found = advice_of(text)
            self.assertEqual(found.verdict, ADVICE_VERDICT, text)
            self.assertIsNotNone(found.finding, text)
            self.assertTrue(found.finding.asserted, text)
            self.assertEqual(evaluate(text).categories, ("investment_advice",), text)

    def test_the_hold_keep_stay_remain_gap_is_closed(self) -> None:
        for text in (
            "Keep your cash in this fund.",
            "Stay invested in this fund.",
            "Remain in the fund until the merger closes.",
            "Hold this fund through the downturn.",
        ):
            found = advice_of(text)
            self.assertEqual(found.verdict, ADVICE_VERDICT, text)
            self.assertEqual(evaluate(text).categories, ("investment_advice",), text)

    def test_the_third_person_false_positives_are_declined(self) -> None:
        for text in (
            "Custodians hold fund assets in safekeeping.",
            "Funds hold cash to meet redemptions.",
            "Prices remain below their five-year average.",
            "Yields stay low while policy is unchanged.",
            "Investors keep cash buffers to meet short-term needs.",
        ):
            found = advice_of(text)
            self.assertEqual(found.verdict, THIRD_PERSON_SUBJECT, text)
            self.assertTrue(found.declines, text)
            self.assertEqual(evaluate(text).categories, (), text)

    def test_a_gerund_heading_a_clause_is_not_a_directive(self) -> None:
        for text in (
            "Holding diversified assets reduces risk.",
            "Rebalancing restores a portfolio to its target allocation.",
            "Holding a fund through a downturn requires patience.",
        ):
            found = advice_of(text)
            self.assertEqual(found.verdict, GERUND_SUBJECT, text)
            self.assertEqual(evaluate(text).categories, (), text)

    def test_an_infinitive_subject_is_not_a_directive(self) -> None:
        found = advice_of("To hold a fund is to accept its charges.")
        self.assertEqual(found.verdict, "infinitive_subject")
        self.assertEqual(evaluate("To hold a fund is to accept its charges.").categories, ())

    def test_method_guidance_is_negative(self) -> None:
        for text in (
            "Investors should hold a diversified portfolio rather than a single stock.",
            "To reduce risk, hold a diversified portfolio.",
            "Investors should keep costs low.",
        ):
            found = advice_of(text)
            self.assertEqual(found.verdict, METHOD_GUIDANCE, text)
            self.assertTrue(found.declines, text)
            self.assertEqual(evaluate(text).categories, (), text)

    def test_a_gerund_that_is_a_noun_is_not_a_verb(self) -> None:
        """`any single holding` is a noun, so the sentence has no verb at all."""

        found = advice_of("Diversification lowers the impact of any single holding.")
        self.assertEqual(found.verdict, NO_DIRECTIVE)
        self.assertEqual(evaluate("Diversification lowers the impact of any single holding.").categories, ())

    def test_a_purpose_clause_does_not_hide_the_directive(self) -> None:
        """`To reduce risk, hold ...` is a directive in its main clause."""

        found = advice_of("To reduce risk, hold a diversified portfolio.")
        self.assertEqual(found.verdict, METHOD_GUIDANCE)
        self.assertIn("imperative", found.boundary.lower() + found.structure.lower())

    def test_direct_advice_is_found_with_all_four_signals(self) -> None:
        found = advice_of("You should hold this stock.")
        self.assertEqual(found.verdict, ADVICE_VERDICT)
        self.assertEqual(set(found.signal_names), set(signals.ADVICE_SIGNALS))
        self.assertEqual(found.addressee, "you")
        self.assertEqual(found.directive, "hold")

    def test_an_imperative_is_clause_initial_not_sentence_initial(self) -> None:
        """Guide 5: a conditional directive is still advice."""

        found = advice_of("If you want higher returns, buy this stock.")
        self.assertEqual(found.verdict, ADVICE_VERDICT)
        self.assertEqual(evaluate("If you want higher returns, buy this stock.").categories, ("investment_advice",))

    def test_a_transparent_verb_introduces_the_directive(self) -> None:
        found = advice_of("Consider moving your capital into the equity fund.")
        self.assertEqual(found.verdict, ADVICE_VERDICT)
        self.assertEqual(found.directive, "move")

    def test_a_reported_recommendation_is_a_directive(self) -> None:
        """Phase 8.5 labels `The newsletter recommends buying this stock.` ADVICE."""

        found = advice_of("The newsletter recommends buying this stock.")
        self.assertEqual(found.verdict, ADVICE_VERDICT)
        self.assertEqual(found.boundary, "reported_directive")

    def test_a_reported_directive_to_a_role_is_found_when_it_is_reported(self) -> None:
        found = advice_of("The exchange said traders should reduce their exposure.")
        self.assertEqual(found.verdict, ADVICE_VERDICT)
        self.assertEqual(found.addressee, "traders")

    def test_an_unreported_role_directive_is_not_advice(self) -> None:
        """Without a reporting frame it is a statement about traders."""

        found = advice_of("Traders should reduce their exposure.")
        self.assertEqual(found.verdict, THIRD_PERSON_SUBJECT)
        self.assertTrue(found.declines)

    def test_every_verdict_is_declared(self) -> None:
        self.assertEqual(len(advice.VERDICTS), len(set(advice.VERDICTS)))
        for verdict in advice.DECLINING_VERDICTS:
            self.assertIn(verdict, advice.VERDICTS, verdict)

    def test_a_non_string_is_rejected(self) -> None:
        with self.assertRaises(advice.AdviceError):
            advice_of(None)  # type: ignore[arg-type]

    def test_the_capability_serialises(self) -> None:
        payload = advice_of("Buy this stock today.").as_dict()
        self.assertEqual(payload["capability"], "advice_boundary")
        self.assertEqual(payload["verdict"], ADVICE_VERDICT)
        self.assertEqual(payload["directive"], "buy")


class DetectorIntegrationTests(unittest.TestCase):
    """The layers inside the pipeline: Claim -> Attribution -> Intent -> Decision."""

    def test_a_declared_finding_replaces_the_frame_finding_on_its_span(self) -> None:
        detection = detectors.evaluate("The market will probably crash next month.")
        intents = detection.apply(())
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].certainty, PROBABLE)
        self.assertFalse(intents[0].asserted)

    def test_a_declining_verdict_removes_the_frame_finding(self) -> None:
        detection = detectors.evaluate("Custodians hold fund assets in safekeeping.")
        self.assertTrue(detection.vetoes)
        self.assertEqual(detection.apply(()), ())
        self.assertIn("investment_advice", detection.boundary_declined)

    def test_a_non_matching_verdict_neither_vetoes_nor_declines(self) -> None:
        detection = detectors.evaluate("Turnover expands sharply next quarter.")
        self.assertEqual(detection.vetoes, ())
        self.assertEqual(detection.boundary_declined, ())

    def test_an_amendment_keeps_the_matchers_hedge(self) -> None:
        """The bug that broke `AR-08`.

        `The claim that the stock will certainly double is incorrect.` is reported
        speech. The matcher recorded `claim` as its hedge, and a replacement that
        dropped the hedge turned a correctly suppressed statement into a finding.
        """

        from risk_evaluation.v3.model import IntentEvidence

        detection = detectors.evaluate(
            "The claim that the stock will certainly double is incorrect."
        )
        frame = IntentEvidence(
            relation="PREDICTION",
            entity="INSTRUMENT",
            frame="active",
            predicate="double",
            pattern_id="test",
            span=(0, 30),
            hedge="claim",
        )
        amended = detection.apply((frame,))
        self.assertEqual(len(amended), 1)
        self.assertEqual(amended[0].hedge, "claim")
        self.assertFalse(amended[0].asserted)

    def test_an_amendment_keeps_the_matchers_negation(self) -> None:
        from risk_evaluation.v3.model import IntentEvidence

        detection = detectors.evaluate("The index may recover next quarter.")
        frame = IntentEvidence(
            relation="PREDICTION",
            entity="VALUE",
            frame="active",
            predicate="recover",
            pattern_id="test",
            span=(0, 20),
            negated=True,
            negation_scope="local",
        )
        amended = detection.apply((frame,))
        self.assertTrue(amended[0].negated)
        self.assertEqual(amended[0].negation_scope, "local")

    def test_advice_hedges_are_constitutive_except_reporting_ones(self) -> None:
        """`would` does not hedge a directive; `said` does."""

        from risk_evaluation.v3.model import IntentEvidence

        def frame(hedge: str) -> IntentEvidence:
            return IntentEvidence(
                relation="ADVICE",
                entity="INSTRUMENT",
                frame="copular",
                predicate="avoid",
                pattern_id="test",
                span=(0, 25),
                hedge=hedge,
            )

        text = "A sensible investor would avoid this fund."
        detection = detectors.evaluate(text)
        self.assertTrue(
            detection.apply((frame("would"),))[0].asserted,
            "inside a declared advisory frame `would` constitutes the directive; "
            "guide 5 keeps a conditional directive as advice",
        )

        reported = detectors.evaluate("The exchange said traders should reduce their exposure.")
        self.assertFalse(
            reported.apply((frame("said"),))[0].asserted,
            "a reporting hedge must survive: it is the attribution layer's evidence",
        )

    def test_the_pipeline_carries_claim_level_evidence(self) -> None:
        result = evaluate("The share price will rise next year.")
        claim = result.claims[0]
        self.assertTrue(claim.evidence)
        self.assertTrue(claim.capabilities)
        self.assertTrue(claim.intents[0].signals)
        self.assertTrue(claim.intents[0].signal_list)
        self.assertTrue(any(s.startswith("certainty:") for s in claim.intents[0].signal_list))

    def test_the_trace_carries_the_signals_and_the_verdict(self) -> None:
        payload = evaluate("The share price will rise next year.").trace_dicts()[0]
        intent = payload["intents"][0]
        self.assertIn("signals", intent)
        self.assertIn("market_entity", intent["signals"])
        self.assertTrue(payload["claim"])

    def test_the_boundary_channel_reaches_the_decision(self) -> None:
        result = evaluate("Custodians hold fund assets in safekeeping.")
        self.assertIn("investment_advice", result.claims[0].boundary_declined)

    def test_the_fallback_cannot_reinstate_a_declined_boundary(self) -> None:
        """The decided case, with the fallback made to fire on purpose."""

        result = evaluate("Holding diversified assets reduces risk.")
        self.assertEqual(result.categories, ())
        trace = result.traces[0]
        for decision in trace.suppressed:
            if decision.category == "investment_advice":
                self.assertIn(decision.rule, {"D8-semantic-fallback", "D2-hedged-intent"})

    def test_both_layers_run_on_every_claim(self) -> None:
        for text in (
            "The share price will rise next year.",
            "Buy this stock today.",
            "Returns may vary.",
            "Custodians hold fund assets in safekeeping.",
        ):
            detection = detectors.evaluate(text)
            self.assertEqual(len(detection.verdicts), 2, text)
            self.assertEqual(len(detection.capabilities), 2, text)

    def test_capability_names_are_declared(self) -> None:
        self.assertEqual(
            set(signals.CAPABILITIES), {"modal_prediction", "advice_boundary"}
        )
        with self.assertRaises(SignalError):
            detectors.capability("sentiment")

    def test_the_adapter_can_be_ablated(self) -> None:
        """The capability is switchable, so it can be measured rather than asserted."""

        from risk_evaluation.v3.adapters.intent_pattern import IntentPatternAdapter
        from risk_evaluation.v3.model import ClaimInput

        claim = ClaimInput(
            claim_id="c1",
            text="The market will probably crash next month.",
            span=(0, 38),
            source_text="The market will probably crash next month.",
        )
        with_capabilities = IntentPatternAdapter().evaluate(claim)
        without = IntentPatternAdapter(capabilities=False).evaluate(claim)

        self.assertTrue(
            any(item.asserted for item in without.intents),
            "without the layer the inherited frame asserts, which is the old defect",
        )
        self.assertFalse(
            any(item.asserted for item in with_capabilities.intents),
            "with the layer the statement is `probable` and nothing is asserted",
        )

    def test_the_detector_rejects_a_non_string(self) -> None:
        with self.assertRaises(detectors.DetectionError):
            detectors.evaluate(None)  # type: ignore[arg-type]


class TaxonomyAlignmentTests(unittest.TestCase):
    """The layers use the taxonomy's vocabulary rather than their own."""

    def test_certainty_levels_come_from_the_taxonomy(self) -> None:
        self.assertEqual(set(certainty.ORDER), set(CERTAINTY_LEVELS))

    def test_a_finding_certainty_must_be_a_taxonomy_level(self) -> None:
        from risk_evaluation.v3.model import IntentEvidence, ModelError

        with self.assertRaises(ModelError):
            IntentEvidence(
                relation="PREDICTION",
                entity="VALUE",
                frame="active",
                predicate="rise",
                pattern_id="test",
                span=(0, 4),
                certainty="probably-ish",
            )

    def test_the_negation_scopes_are_unchanged(self) -> None:
        """Phase 8.8 does not touch the Phase 8.7 negation work."""

        self.assertEqual(set(NEGATION_SCOPES), {"positive", "local", "propositional"})

    def test_a_finding_records_its_boundary_verdict(self) -> None:
        found = modal_of("The index may recover next quarter.")
        self.assertEqual(found.finding.boundary, WEAK_PREDICTION)
        found = advice_of("Buy this stock today.")
        self.assertEqual(found.finding.boundary, "imperative")


if __name__ == "__main__":
    unittest.main()
