"""Steps 1 to 4: the repair layers, each on the wording that motivated it.

Every case here is taken from a Phase 8.6 failure record rather than invented, so
a test that passes says the confirmed defect is answered and a test that fails
says it came back.
"""

from __future__ import annotations

import unittest

from risk_evaluation.v3 import evaluate
from risk_evaluation.v3.model import NEGATION_SCOPES
from risk_evaluation.v3.patterns import MOVEMENT_LEMMAS
from risk_evaluation.v3_repair.attribution import UNVERIFIED, refine
from risk_evaluation.v3_repair.negation import (
    LOCAL,
    POSITIVE,
    PROPOSITIONAL,
    SCOPES,
    NegationError,
    NegationScope,
    classify,
    describe as describe_scopes,
)
from risk_evaluation.v3_repair.rejection import (
    AUTHOR,
    REPORTED,
    VOICES,
    RejectionError,
    RejectionFinding,
    detect as detect_rejection,
    describe as describe_cues,
)
from risk_evaluation.v3_repair.sources import (
    NAMED_AUTHORITY,
    NAMED_SOURCE,
    PROFESSIONAL_GROUP,
    PUBLISHED_MATERIAL,
    SOURCE_TYPES,
    UNNAMED_SOURCE,
    SourceError,
    SourceFinding,
    detect as detect_source,
    detect_type,
    describe as describe_sources,
)


def _scope_of(text: str, predicate: str, *, negated: bool) -> NegationScope:
    """Classify a whole sentence as if the frame were the whole of it."""

    start = text.lower().index(predicate.lower())
    return classify(
        text,
        frame_span=(0, len(text)),
        predicate_span=(start, start + len(predicate)),
        negated=negated,
    )


class NegationScopeTests(unittest.TestCase):
    """Step 2: Case A, Case B and Case C must be three different findings."""

    CASE_A = "Returns are guaranteed."
    CASE_B = "Returns are not guaranteed."
    CASE_C = "It is not true that returns are guaranteed."

    def test_case_a_is_positive(self) -> None:
        found = _scope_of(self.CASE_A, "guaranteed", negated=False)

        self.assertEqual(found.scope, POSITIVE)
        self.assertFalse(found.negated)
        self.assertFalse(found.denies_claim)

    def test_case_b_is_local(self) -> None:
        found = _scope_of(self.CASE_B, "guaranteed", negated=True)

        self.assertEqual(found.scope, LOCAL)
        self.assertTrue(found.negated)
        self.assertFalse(found.denies_claim)
        self.assertIn("not", found.marker)

    def test_case_c_is_propositional(self) -> None:
        found = _scope_of(self.CASE_C, "guaranteed", negated=True)

        self.assertEqual(found.scope, PROPOSITIONAL)
        self.assertTrue(found.negated)
        self.assertTrue(found.denies_claim)
        self.assertIn("not-true", found.marker)

    def test_the_three_cases_are_mutually_distinct(self) -> None:
        scopes = {
            _scope_of(self.CASE_A, "guaranteed", negated=False).scope,
            _scope_of(self.CASE_B, "guaranteed", negated=True).scope,
            _scope_of(self.CASE_C, "guaranteed", negated=True).scope,
        }

        self.assertEqual(scopes, {POSITIVE, LOCAL, PROPOSITIONAL})

    def test_the_scope_never_contradicts_the_matchers_verdict(self) -> None:
        """Phase 8.4's guard is not overridden, only refined."""

        for negated in (False, True):
            for text in (self.CASE_A, self.CASE_B, self.CASE_C):
                found = _scope_of(text, "guaranteed", negated=negated)
                self.assertEqual(found.negated, negated, text)

    def test_a_marker_inside_the_predicate_is_not_propositional(self) -> None:
        """`The return is not guaranteed.` denies the predicate, not the claim."""

        found = _scope_of("The return is not guaranteed to be paid.", "guaranteed", negated=True)

        self.assertEqual(found.scope, LOCAL)

    def test_an_unknown_scope_is_rejected(self) -> None:
        with self.assertRaises(NegationError):
            NegationScope("sideways")

    def test_the_scopes_are_the_declared_three(self) -> None:
        self.assertEqual(SCOPES, (POSITIVE, LOCAL, PROPOSITIONAL))
        self.assertEqual(set(NEGATION_SCOPES), set(SCOPES))
        self.assertEqual(len(describe_scopes()), 3)


class NegationPipelineTests(unittest.TestCase):
    """The scope reaches the trace, and the decision is still a decline."""

    def test_the_sentence_carries_a_trace_in_every_case(self) -> None:
        for text in (
            "Returns are guaranteed.",
            "Returns are not guaranteed.",
            "It is not true that returns are guaranteed.",
        ):
            result = evaluate(text)
            self.assertTrue(result.traces, text)
            self.assertTrue(result.claims[0].evidence, text)

    def test_case_a_is_kept(self) -> None:
        result = evaluate("Returns are guaranteed.")

        self.assertEqual(result.categories, ("financial_guarantee",))
        self.assertFalse(result.claims[0].intents[0].negated)

    def test_case_b_produces_a_negated_guarantee_with_a_scope(self) -> None:
        result = evaluate("Returns are not guaranteed.")
        intents = result.claims[0].intents

        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].relation, "GUARANTEE")
        self.assertTrue(intents[0].negated)
        self.assertEqual(intents[0].negation_scope, LOCAL)
        self.assertEqual(result.categories, ())

    def test_case_c_produces_a_negated_guarantee_with_a_different_scope(self) -> None:
        result = evaluate("It is not true that returns are guaranteed.")
        intents = result.claims[0].intents

        self.assertEqual(intents[0].negation_scope, PROPOSITIONAL)
        self.assertEqual(result.categories, ())

    def test_the_suppression_reason_says_which_denial_it_was(self) -> None:
        local = evaluate("Returns are not guaranteed.")
        propositional = evaluate("It is not true that returns are guaranteed.")

        local_reason = local.traces[0].suppressed[0].reason
        propositional_reason = propositional.traces[0].suppressed[0].reason

        self.assertIn("negated in its predicate", local_reason)
        self.assertIn("rejected, not asserted", propositional_reason)
        self.assertNotEqual(local_reason, propositional_reason)

    def test_the_predicate_is_denied_not_deleted(self) -> None:
        """The phase forbids repairing this by removing the negation guard."""

        result = evaluate("Returns are not guaranteed.")

        self.assertEqual(result.claims[0].intents[0].predicate, "guaranteed")
        self.assertTrue(result.claims[0].intents[0].negated)


class MovementVerbTests(unittest.TestCase):
    """Step 1: the inflected verb, and the growth that must not come with it."""

    def test_the_lemmas_are_lemmas_not_an_alternation(self) -> None:
        self.assertTrue(MOVEMENT_LEMMAS)
        for lemma in MOVEMENT_LEMMAS:
            self.assertTrue(lemma.isalpha(), lemma)
            self.assertEqual(lemma, lemma.lower())

    def test_the_phase_8_6_case_is_detected(self) -> None:
        result = evaluate("Turnover expands sharply next quarter.")

        self.assertEqual(result.categories, ("market_prediction",))
        self.assertEqual(result.claims[0].intents[0].predicate, "expands")

    def test_a_sample_of_inflections_is_detected(self) -> None:
        """One sentence per verb shape: s-form, past, gerund, irregular, -y."""

        for text in (
            "The share price will climb next year.",
            "Turnover will contract next year.",
            "The index will rally from here.",
            "Earnings will multiply next year.",
            "The price will double next year.",
            "The share price will rise next year.",
            "The share price will fall next year.",
            "The share price will recover next year.",
        ):
            result = evaluate(text)
            self.assertEqual(
                result.categories, ("market_prediction",), (text, result.categories)
            )
            self.assertTrue(result.claims[0].intents, text)

    def test_inflected_forms_of_the_movement_lemmas_match(self) -> None:
        """Checked on the generated alternation, not only through the pipeline.

        A frame needs more than a verb, so a sentence that fails to produce a
        category may be failing on the subject rather than on the inflection.
        This asserts the inflection itself.
        """

        import re

        from risk_evaluation.v3.patterns import MOVEMENT_VERBS

        pattern = re.compile(MOVEMENT_VERBS, re.IGNORECASE)
        for token in (
            "expands",
            "expanded",
            "expanding",
            "dropped",
            "rallies",
            "rallied",
            "doubled",
            "multiplied",
            "decreases",
            "climbed",
            "rose",
            "risen",
            "fell",
            "fallen",
            "grew",
            "grown",
        ):
            self.assertIsNotNone(pattern.search(token), token)

    def test_a_non_movement_verb_is_not_inflected_into_the_frames(self) -> None:
        """`holding` is not `hold`, and nothing here may pretend it is.

        `The expense ratio is the annual cost of holding a fund.` was a Phase 8.6
        false positive. Giving the movement verbs their inflections must not give
        the directive verbs theirs.
        """

        import re

        from risk_evaluation.v3.patterns import MOVEMENT_VERBS

        self.assertIsNone(re.compile(MOVEMENT_VERBS, re.IGNORECASE).search("holding"))
        self.assertEqual(
            evaluate("The expense ratio is the annual cost of holding a fund.").categories,
            (),
        )

    def test_the_inflections_did_not_add_false_positives(self) -> None:
        """Stated as a property, because "no growth" is the phase's requirement.

        Inflecting a verb can only add matches, and every added match is a frame
        that was not firing before. What must stay true is that the *decisions*
        on the two negatives the inflections touch do not move.
        """

        for text in (
            "The manager's report is published with the annual accounts.",
            "The prospectus sets out the fund's investment objective.",
        ):
            self.assertEqual(evaluate(text).categories, (), text)


class SourceTypingTests(unittest.TestCase):
    """Step 3: a source is typed, and checkability is the point of the typing."""

    def test_the_four_phase_types_plus_one_are_declared(self) -> None:
        self.assertEqual(
            set(SOURCE_TYPES),
            {
                NAMED_AUTHORITY,
                PROFESSIONAL_GROUP,
                UNNAMED_SOURCE,
                PUBLISHED_MATERIAL,
                NAMED_SOURCE,
            },
        )
        self.assertEqual(len(describe_sources()), 5)

    def test_named_authorities_are_checkable(self) -> None:
        for text, name in (
            ("The regulator said the review is ongoing.", "regulator"),
            ("The custodian confirmed the transfer.", "custodian"),
            ("The trustee published the annual statement.", "trustee"),
            ("The exchange said trading was orderly.", "exchange"),
        ):
            found = detect_source(text)
            self.assertIsNotNone(found, text)
            self.assertEqual(found.source_type, NAMED_AUTHORITY, text)
            self.assertEqual(found.name.lower(), name, text)
            self.assertTrue(found.checkable, text)

    def test_a_document_is_checkable_and_not_called_unknown(self) -> None:
        for text in (
            "The marketing material states that returns are guaranteed.",
            "The advert says the price will certainly double.",
            "According to the prospectus, charges are capped.",
        ):
            found = detect_source(text)
            self.assertIsNotNone(found, text)
            self.assertEqual(found.source_type, PUBLISHED_MATERIAL, text)
            self.assertTrue(found.checkable, text)

    def test_an_unnamed_source_is_uncheckable(self) -> None:
        for text in (
            "An unnamed official confirmed the restatement.",
            "An anonymous official confirmed the probe.",
            "A person familiar with the matter says the deal is off.",
            "Market chatter suggests the float will be cut.",
            "Reportedly the fund has changed its mandate.",
        ):
            found = detect_source(text)
            self.assertIsNotNone(found, text)
            self.assertEqual(found.source_type, UNNAMED_SOURCE, text)
            self.assertFalse(found.checkable, text)

    def test_a_role_collective_is_uncheckable_until_a_proper_noun_names_it(self) -> None:
        bare = detect_source("Traders say the shares are cheap.")
        named = detect_source("Goldman traders say the shares are cheap.")

        self.assertEqual(bare.source_type, PROFESSIONAL_GROUP)
        self.assertFalse(bare.checkable)
        self.assertEqual(named.source_type, PROFESSIONAL_GROUP)
        self.assertTrue(named.checkable)

    def test_a_name_the_lexicon_cannot_type_is_still_named(self) -> None:
        """`According to the report` names a document, not an unknown source."""

        found = detect_source("According to the report, charges are capped.")

        self.assertEqual(found.source_type, NAMED_SOURCE)
        self.assertTrue(found.checkable)

    def test_a_possessive_subject_is_not_a_speaker(self) -> None:
        """`The manager's report is published` - the report is the subject."""

        self.assertIsNone(detect_source("The manager's report is published with the annual accounts."))

    def test_a_source_noun_without_a_reporting_verb_is_not_a_speaker(self) -> None:
        self.assertIsNone(detect_source("The prospectus sets out the fund's investment objective."))
        self.assertIsNone(detect_source("Investors should allocate more to bonds."))

    def test_a_reporting_verb_is_inflected_from_its_lemma(self) -> None:
        """The same defect as step 1, one layer down.

        The hand-written list carried `claims` and not `claim`, so `Sources claim
        the merger talks have stalled.` had a source noun and no verb to attach it
        to. Every form of every lemma must match.
        """

        import re

        from risk_evaluation.v3_repair.sources import REPORTING_VERBS

        pattern = re.compile(rf"\b(?:{REPORTING_VERBS})\b", re.IGNORECASE)
        for token in (
            "say",
            "says",
            "said",
            "claim",
            "claims",
            "claimed",
            "argue",
            "argues",
            "argued",
            "deny",
            "denies",
            "denied",
            "testify",
            "testifies",
            "testified",
        ):
            self.assertIsNotNone(pattern.search(token), token)

    def test_hearsay_names_a_source_that_is_not_there(self) -> None:
        """`Word on the street`, `Rumour has it`, `I heard` - all uncheckable."""

        for text in (
            "Word on the street is that the board will resign.",
            "Rumour has it the chief executive is leaving.",
            "I heard the custodian is being replaced.",
            "Word on the street is that the audit is late.",
        ):
            found = detect_source(text)
            self.assertIsNotNone(found, text)
            self.assertEqual(found.source_type, UNNAMED_SOURCE, text)
            self.assertEqual(found.cue, "hearsay", text)
            self.assertFalse(found.checkable, text)

    def test_a_sentence_initial_capital_is_not_a_proper_noun(self) -> None:
        """`Some commentators` names nobody, however it is capitalised."""

        self.assertFalse(detect_source("Some commentators argue the shares are cheap.").checkable)
        self.assertFalse(detect_source("The traders say the shares are cheap.").checkable)
        self.assertTrue(detect_source("Goldman traders say the shares are cheap.").checkable)
        self.assertTrue(
            detect_source("Goldman Sachs traders say the shares are cheap.").checkable
        )

    def test_a_definite_publication_is_checkable(self) -> None:
        """`The newsletter recommends buying this stock.` - guide 7, checkable."""

        found = detect_source("The newsletter recommends buying this stock.")

        self.assertIsNotNone(found)
        self.assertEqual(found.source_type, PUBLISHED_MATERIAL)
        self.assertTrue(found.checkable)

    def test_a_type_can_be_probed_on_its_own(self) -> None:
        self.assertIsNotNone(detect_type("The regulator said the review is ongoing.", NAMED_AUTHORITY))
        self.assertIsNone(detect_type("The regulator said the review is ongoing.", UNNAMED_SOURCE))

    def test_an_unknown_type_is_rejected(self) -> None:
        with self.assertRaises(SourceError):
            SourceFinding("vibes", "someone", (0, 7), "reporting_verb", True)

    def test_a_nameless_finding_is_rejected(self) -> None:
        with self.assertRaises(SourceError):
            SourceFinding(NAMED_AUTHORITY, " ", (0, 1), "reporting_verb", True)

    def test_non_string_input_is_rejected(self) -> None:
        with self.assertRaises(SourceError):
            detect_source(None)  # type: ignore[arg-type]


class RejectionCueTests(unittest.TestCase):
    """Step 4: the eight rejections Phase 8.6 could not see."""

    CASES = (
        "We reject the suggestion that returns are guaranteed.",
        "We are unconvinced that capital is protected here.",
        "The idea that the fund cannot fall is not supported.",
        "We see no basis for the view that the price will triple.",
        "The assertion that losses are impossible is false.",
        "Claims that the fund is risk-free are overstated.",
        "We do not accept that the index will recover.",
        "We would not describe this as a safe bet.",
        "Contrary to the marketing, the return is not guaranteed.",
    )

    def test_every_phase_8_6_miss_is_now_found(self) -> None:
        for text in self.CASES:
            found = detect_rejection(text)
            self.assertIsNotNone(found, text)
            self.assertEqual(found.voice, AUTHOR, text)

    def test_a_third_party_rejection_is_not_the_articles(self) -> None:
        """Expanding the cues must not swallow somebody else's rejection."""

        found = detect_rejection(
            "The regulator rejected the claim that returns are guaranteed."
        )

        self.assertIsNotNone(found)
        self.assertEqual(found.voice, REPORTED)
        self.assertFalse(found.is_authorial)

    def test_an_impersonal_denial_needs_something_to_deny(self) -> None:
        """`is false` about an alarm is not a rejection of a claim."""

        self.assertIsNone(detect_rejection("The alarm is false."))
        self.assertIsNotNone(detect_rejection("The assertion that losses are impossible is false."))

    def test_a_neutral_sentence_is_not_a_rejection(self) -> None:
        for text in (
            "The expense ratio is the annual cost of holding a fund.",
            "The prospectus sets out the fund's investment objective.",
            "Stamp duty applies to certain share purchases.",
            "Returns are guaranteed.",
        ):
            self.assertIsNone(detect_rejection(text), text)

    def test_the_voices_are_the_declared_two(self) -> None:
        self.assertEqual(VOICES, (AUTHOR, REPORTED))
        cues = [entry["cue"] for entry in describe_cues()]
        self.assertTrue(cues)
        self.assertTrue(all(cue.strip() for cue in cues))
        self.assertIn("reject", cues)
        self.assertIn("reported-rejection", cues)

    def test_an_unknown_voice_is_rejected(self) -> None:
        with self.assertRaises(RejectionError):
            RejectionFinding("nobody", "reject", "we reject", (0, 9))

    def test_non_string_input_is_rejected(self) -> None:
        with self.assertRaises(RejectionError):
            detect_rejection(None)  # type: ignore[arg-type]


class RefinementTests(unittest.TestCase):
    """The three steps together, over Phase 8.2's verdict."""

    def test_a_rejection_overrides_both_axes(self) -> None:
        found = refine(
            "We reject the suggestion that returns are guaranteed.",
            speaker="unknown",
            stance="uncertain",
        )

        self.assertEqual((found.speaker, found.stance), ("author", "rejected"))
        self.assertTrue(found.changed)
        self.assertTrue(found.speaker_changed)
        self.assertTrue(found.stance_changed)

    def test_an_unnamed_source_becomes_third_party_and_unverified(self) -> None:
        found = refine(
            "An unnamed official confirmed the restatement.",
            speaker="unknown",
            stance="uncertain",
        )

        self.assertEqual((found.speaker, found.stance), ("third_party", "quoted"))
        self.assertEqual(found.sourcing_categories, (UNVERIFIED,))

    def test_a_checkable_source_does_not_become_unverified(self) -> None:
        for text in (
            "The regulator said the review is ongoing.",
            "The custodian confirmed the transfer.",
            "The advert says the price will certainly double.",
            "According to the report, the fund cannot lose money.",
        ):
            found = refine(text, speaker="unknown", stance="quoted")
            self.assertEqual(found.sourcing_categories, (), text)

    def test_an_identified_speaker_is_never_overridden(self) -> None:
        found = refine(
            "The regulator said the review is ongoing.",
            speaker="author",
            stance="endorsed",
        )

        self.assertEqual((found.speaker, found.stance), ("author", "endorsed"))

    def test_a_rejection_outranks_a_quotation(self) -> None:
        """`Claims that ... are overstated` is the article, not the claimant."""

        found = refine(
            "Claims that the fund is risk-free are overstated.",
            speaker="unknown",
            stance="quoted",
        )

        self.assertEqual((found.speaker, found.stance), ("author", "rejected"))
        self.assertEqual(found.sourcing_categories, ())

    def test_a_plain_sentence_is_left_alone(self) -> None:
        for text in (
            "The expense ratio is the annual cost of holding a fund.",
            "Returns are guaranteed.",
        ):
            found = refine(text, speaker="unknown", stance="uncertain")
            self.assertFalse(found.changed, text)
            self.assertEqual((found.speaker, found.stance), ("unknown", "uncertain"))

    def test_hearsay_becomes_third_party_and_quoted(self) -> None:
        """The Phase 8.6 wording, end to end through the pipeline."""

        for text in (
            "Word on the street is that the board will resign.",
            "I heard the custodian is being replaced.",
            "Rumour has it the chief executive is leaving.",
            "Sources claim the merger talks have stalled.",
            "Some commentators argue the shares are cheap.",
        ):
            result = evaluate(text)
            self.assertEqual(
                result.categories, ("unverified_information",), (text, result.categories)
            )
            self.assertEqual(result.claims[0].speaker, "third_party", text)
            self.assertEqual(result.claims[0].stance, "quoted", text)

    def test_an_indefinite_promoter_is_deliberately_not_a_source(self) -> None:
        """A measured contradiction between two frozen labels, left open.

        `A promoter claimed the fund cannot lose money.` (IV-094) is annotated
        `unverified_information`; `The article quotes a promoter saying do not
        miss this opportunity.` (83-CTL-04, a Phase 8.3 control) is annotated as
        no risk. Adding `promoter` to the group lexicon fixes one and breaks the
        other, so neither the noun nor a rule that special-cases the quotation is
        shipped. This test records the state so the next phase finds the conflict
        rather than rediscovering it.
        """

        self.assertIsNone(detect_source("A promoter claimed the fund cannot lose money."))
        self.assertEqual(evaluate("A promoter claimed the fund cannot lose money.").categories, ())
        self.assertEqual(
            evaluate(
                "The article quotes a promoter saying do not miss this opportunity."
            ).categories,
            (),
        )

    def test_every_change_is_evidenced(self) -> None:
        found = refine(
            "Reportedly the fund has suspended redemptions.",
            speaker="unknown",
            stance="quoted",
        )

        self.assertTrue(found.evidence)
        self.assertTrue(any(item.startswith("source:") for item in found.evidence))
        self.assertTrue(any(item.startswith("rule:refine.") for item in found.evidence))

    def test_the_refinement_serialises(self) -> None:
        found = refine(
            "Traders say the shares are cheap.", speaker="unknown", stance="quoted"
        )
        payload = found.as_dict()

        self.assertEqual(payload["speaker"], "third_party")
        self.assertIsNotNone(payload["source"])
        self.assertIsNone(payload["rejection"])


if __name__ == "__main__":
    unittest.main()
