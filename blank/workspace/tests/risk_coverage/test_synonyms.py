"""The declared synonym, axis, chain, frame and withheld tables.

Everything a candidate can be built from lives in this module, so the tests here are
about the tables being *consistent with the evaluator*: a canonical word must be one the
evaluator really matches, a synonym must genuinely be new, a relation must be one the
evaluator defines, and a refusal must be recorded rather than merely omitted.
"""

from __future__ import annotations

import unittest

from risk_evaluation.coverage import lexicon, synonyms
from risk_evaluation.coverage.synonyms import (
    AXES,
    AXIS_FAILURE,
    CANONICAL_SOURCES,
    CHAINS,
    FRAME_VARIANTS,
    MODES,
    PREDICATE,
    PRESSURE,
    V3_RELATIONS,
    WITHHELD,
    Axis,
    Chain,
    SynonymError,
    TableReport,
    Withheld,
    axis,
    axes_for_category,
    categories,
    inflections,
    looks_inflected,
    novel_synonyms,
    provenance,
    validate,
    words,
)
from risk_evaluation.coverage.taxonomy import LEXICAL_GAP, SYNONYM_GAP


class ValidateTest(unittest.TestCase):
    """`validate()` is the check that the tables do not lie about the evaluator."""

    def test_the_tables_validate(self) -> None:
        self.assertTrue(validate().ok)

    def test_no_canonical_word_is_unknown_to_the_evaluator(self) -> None:
        self.assertEqual(validate().unknown_canonical, ())

    def test_every_canonical_word_is_a_word_the_evaluator_matches(self) -> None:
        for item in AXES:
            if item.canonical_source != "v3_lexicon":
                continue
            for word in item.canonical:
                with self.subTest(axis=item.name, word=word):
                    self.assertTrue(lexicon.known(word))

    def test_no_declared_synonym_is_already_matched(self) -> None:
        """Reported as table rot when it happens; the table is currently clean."""

        self.assertEqual(validate().redundant_synonyms, ())

    def test_every_declared_synonym_is_new_to_the_evaluator(self) -> None:
        declared = [word for item in AXES for word in item.synonyms]
        novel = [word for _name, word in validate().novel_synonyms]
        self.assertEqual(sorted(novel), sorted(declared))
        for word in declared:
            with self.subTest(word=word):
                self.assertFalse(lexicon.known(word))

    def test_no_declared_synonym_looks_inflected(self) -> None:
        self.assertEqual(validate().suspect_lemmas, ())

    def test_the_axes_without_a_relation_are_reported(self) -> None:
        self.assertEqual(
            set(validate().axes_without_relation), {"reported_source", "urgency_pressure"}
        )

    def test_the_report_describes_itself(self) -> None:
        body = validate().describe()
        self.assertTrue(body["ok"])
        self.assertEqual(body["axes"], len(AXES))
        self.assertEqual(body["redundant_synonyms"], [])
        self.assertIn("novel_synonyms", body)

    def test_a_report_with_an_unknown_canonical_word_is_not_ok(self) -> None:
        report = TableReport(
            unknown_canonical=(("axis", "zzz"),),
            redundant_synonyms=(),
            novel_synonyms=(),
            axes_without_relation=(),
        )
        self.assertFalse(report.ok)

    def test_a_report_with_a_suspect_lemma_is_not_ok(self) -> None:
        report = TableReport(
            unknown_canonical=(),
            redundant_synonyms=(),
            novel_synonyms=(),
            axes_without_relation=(),
            suspect_lemmas=(("axis", "promiseded"),),
        )
        self.assertFalse(report.ok)

    def test_a_redundant_synonym_alone_does_not_invalidate_the_report(self) -> None:
        """Redundancy is rot to report, not an error: the canonical words are the check."""

        report = TableReport(
            unknown_canonical=(),
            redundant_synonyms=(("axis", "guaranteed"),),
            novel_synonyms=(),
            axes_without_relation=(),
        )
        self.assertTrue(report.ok)


class AxisTest(unittest.TestCase):
    def test_axis_lookup_by_name(self) -> None:
        self.assertEqual(axis("guarantee_predicate").category, "financial_guarantee")

    def test_axis_lookup_of_an_undeclared_name_raises(self) -> None:
        with self.assertRaises(SynonymError) as caught:
            axis("nope")
        self.assertIn("no axis named", str(caught.exception))

    def test_axes_are_uniquely_named(self) -> None:
        names = [item.name for item in AXES]
        self.assertEqual(len(names), len(set(names)))

    def test_every_axis_names_a_category_and_a_guide_basis(self) -> None:
        for item in AXES:
            with self.subTest(axis=item.name):
                self.assertTrue(item.category)
                self.assertTrue(item.guide_basis)
                self.assertIn(item.mode, MODES)

    def test_an_undeclared_mode_is_refused(self) -> None:
        with self.assertRaises(SynonymError) as caught:
            Axis(
                name="x",
                category="c",
                mode="vibes",
                canonical=("guaranteed",),
                synonyms=("promise",),
                guide_basis="because",
            )
        self.assertIn("unknown mode", str(caught.exception))

    def test_a_relation_the_evaluator_does_not_define_is_refused(self) -> None:
        with self.assertRaises(SynonymError) as caught:
            Axis(
                name="x",
                category="c",
                mode=PREDICATE,
                canonical=("guaranteed",),
                synonyms=("promise",),
                guide_basis="because",
                relation="RISK_TRANSFERRED",
            )
        self.assertIn("does not define", str(caught.exception))

    def test_a_semantic_layer_axis_may_not_name_canonical_words(self) -> None:
        with self.assertRaises(SynonymError) as caught:
            Axis(
                name="x",
                category="c",
                mode=PRESSURE,
                canonical=("guaranteed",),
                synonyms=("act fast",),
                guide_basis="because",
                canonical_source="semantic_layer",
            )
        self.assertIn("claims the semantic layer", str(caught.exception))

    def test_a_v3_lexicon_axis_must_name_a_canonical_word(self) -> None:
        with self.assertRaises(SynonymError) as caught:
            Axis(
                name="x",
                category="c",
                mode=PREDICATE,
                canonical=(),
                synonyms=("promise",),
                guide_basis="because",
            )
        self.assertIn("names no canonical word", str(caught.exception))

    def test_a_declared_canonical_source_must_be_one_of_the_two(self) -> None:
        with self.assertRaises(SynonymError):
            Axis(
                name="x",
                category="c",
                mode=PREDICATE,
                canonical=("guaranteed",),
                synonyms=("promise",),
                guide_basis="because",
                canonical_source="somewhere",
            )

    def test_an_axis_without_synonyms_is_refused(self) -> None:
        with self.assertRaises(SynonymError) as caught:
            Axis(
                name="x",
                category="c",
                mode=PREDICATE,
                canonical=("guaranteed",),
                synonyms=(),
                guide_basis="because",
            )
        self.assertIn("declares no synonyms", str(caught.exception))

    def test_an_axis_without_a_guide_basis_is_refused(self) -> None:
        with self.assertRaises(SynonymError):
            Axis(
                name="x",
                category="c",
                mode=PREDICATE,
                canonical=("guaranteed",),
                synonyms=("promise",),
                guide_basis="",
            )

    def test_the_declared_canonical_sources_are_the_two_supported_ones(self) -> None:
        self.assertEqual(set(CANONICAL_SOURCES), {"v3_lexicon", "semantic_layer"})
        for item in AXES:
            self.assertIn(item.canonical_source, CANONICAL_SOURCES)

    def test_failure_type_follows_the_mode(self) -> None:
        self.assertEqual(axis("guarantee_predicate").failure_type, SYNONYM_GAP)
        self.assertEqual(axis("reported_source").failure_type, LEXICAL_GAP)
        self.assertEqual(axis("urgency_pressure").failure_type, LEXICAL_GAP)

    def test_the_mode_to_failure_map_covers_every_mode(self) -> None:
        self.assertEqual(set(AXIS_FAILURE), set(MODES))
        for mode, failure_type in AXIS_FAILURE.items():
            with self.subTest(mode=mode):
                self.assertIn(failure_type, {SYNONYM_GAP, LEXICAL_GAP})

    def test_an_axis_without_a_relation_cannot_be_auto_generated(self) -> None:
        for item in AXES:
            with self.subTest(axis=item.name):
                self.assertEqual(item.auto_generatable, item.relation is not None)

    def test_novel_and_redundant_partition_the_synonyms(self) -> None:
        for item in AXES:
            with self.subTest(axis=item.name):
                self.assertEqual(set(item.novel) | set(item.redundant), set(item.synonyms))
                self.assertEqual(set(item.novel) & set(item.redundant), set())

    def test_the_movement_axis_carries_time_series_verbs(self) -> None:
        self.assertIn("plummet", axis("movement_direction").synonyms)
        self.assertIn("skyrocket", axis("movement_direction").synonyms)

    def test_the_directive_axis_carries_only_transitive_phrasal_verbs(self) -> None:
        """`sit tight` and `take profit` were removed because they cannot take an object."""

        declared = axis("directive_verb").synonyms
        self.assertIn("snap up", declared)
        self.assertNotIn("sit tight", declared)
        self.assertNotIn("take profit", declared)


class RelationTableTest(unittest.TestCase):
    def test_the_declared_relations_are_the_ones_the_evaluator_defines(self) -> None:
        self.assertEqual(set(V3_RELATIONS), set(lexicon.relation_frames()))

    def test_every_axis_relation_is_a_declared_relation(self) -> None:
        for item in AXES:
            if item.relation is None:
                continue
            with self.subTest(axis=item.name):
                self.assertIn(item.relation, V3_RELATIONS)

    def test_the_axes_with_a_relation_are_the_six_vocabulary_axes(self) -> None:
        self.assertEqual(
            {item.name for item in AXES if item.relation is not None},
            {
                "guarantee_predicate",
                "risk_removed",
                "movement_direction",
                "certainty_carrier",
                "directive_verb",
                "position_word",
            },
        )


class InflectionsTest(unittest.TestCase):
    def test_promise_inflects_to_promised(self) -> None:
        self.assertIn("promised", inflections("promise"))

    def test_promise_inflects_to_its_other_forms(self) -> None:
        forms = set(inflections("promise"))
        self.assertTrue({"promise", "promises", "promising"} <= forms)

    def test_a_multi_word_proposal_is_returned_unchanged(self) -> None:
        self.assertEqual(inflections("snap up"), ("snap up",))

    def test_a_hyphenated_proposal_is_returned_unchanged(self) -> None:
        self.assertEqual(inflections("loss-proof"), ("loss-proof",))

    def test_a_non_alphabetic_proposal_is_returned_unchanged(self) -> None:
        self.assertEqual(inflections("12x"), ("12x",))

    def test_inflection_is_case_insensitive(self) -> None:
        self.assertEqual(inflections("Promise"), inflections("promise"))

    def test_inflection_is_deterministic(self) -> None:
        self.assertEqual(inflections("plummet"), inflections("plummet"))

    def test_every_form_returned_is_alphabetic(self) -> None:
        for form in inflections("vow"):
            with self.subTest(form=form):
                self.assertTrue(form.isalpha())


class LooksInflectedTest(unittest.TestCase):
    """The check that caught `promiseded` and `promiseding` before a reviewer saw them."""

    def test_a_doubled_ed_ending_is_flagged(self) -> None:
        self.assertTrue(looks_inflected("promiseded"))

    def test_a_doubled_ing_ending_is_flagged(self) -> None:
        self.assertTrue(looks_inflected("promisinging"))

    def test_both_documented_garbage_endings_are_flagged(self) -> None:
        """The two forms the `Axis` docstring names, neither of them hard-coded away.

        `_INFLECTED_ENDINGS` used to be declared and then ignored: `looks_inflected`
        hard-coded a shorter list, so `promiseding` — one of the two garbled forms the
        docstring names — went unflagged and the declaration was dead data.
        """

        self.assertTrue(looks_inflected("promiseded"))
        self.assertTrue(looks_inflected("promiseding"))

    def test_a_doubled_sibilant_ending_is_flagged(self) -> None:
        self.assertTrue(looks_inflected("processes"))

    def test_a_plain_inflected_form_is_not_flagged(self) -> None:
        """Deliberately conservative: `promised` is a real word shape."""

        self.assertFalse(looks_inflected("promised"))
        self.assertFalse(looks_inflected("guaranteed"))

    def test_a_phrase_is_never_flagged(self) -> None:
        self.assertFalse(looks_inflected("snap up"))

    def test_a_hyphenated_word_is_never_flagged(self) -> None:
        self.assertFalse(looks_inflected("loss-proofed"))

    def test_a_short_word_is_never_flagged(self) -> None:
        self.assertFalse(looks_inflected("ided"))


class WithheldTest(unittest.TestCase):
    def test_the_withheld_table_is_not_empty(self) -> None:
        self.assertTrue(WITHHELD)

    def test_every_refusal_carries_a_reason(self) -> None:
        for item in WITHHELD:
            with self.subTest(text=item.text):
                self.assertTrue(item.reason)
                self.assertTrue(item.category)
                self.assertTrue(item.text)

    def test_the_negated_guarantee_is_recorded_as_withheld(self) -> None:
        withheld_texts = {item.text for item in WITHHELD}
        self.assertIn("Returns cannot be guaranteed.", withheld_texts)

    def test_the_withheld_reason_names_the_false_positive_trade(self) -> None:
        item = next(i for i in WITHHELD if i.text == "Returns cannot be guaranteed.")
        self.assertIn("false positive", item.reason)

    def test_no_withheld_wording_is_a_declared_synonym(self) -> None:
        declared = {word for item in AXES for word in item.synonyms}
        for item in WITHHELD:
            with self.subTest(text=item.text):
                self.assertNotIn(item.text, declared)

    def test_a_refusal_requires_its_own_text_and_reason(self) -> None:
        item = Withheld(text="x", category="c", reason="r")
        self.assertEqual(item.text, "x")
        self.assertEqual(item.reason, "r")


class ChainTest(unittest.TestCase):
    def test_the_guarantee_chain_reports_the_first_three_steps_as_known(self) -> None:
        chain = next(item for item in CHAINS if item.name == "guarantee_weakening")
        steps = dict(chain.steps)
        self.assertTrue(steps["guaranteed"])
        self.assertTrue(steps["assured"])
        self.assertTrue(steps["certain"])

    def test_the_guarantee_chain_reports_promised_as_the_first_missing_step(self) -> None:
        chain = next(item for item in CHAINS if item.name == "guarantee_weakening")
        self.assertFalse(dict(chain.steps)["promised"])
        self.assertEqual(chain.first_missing, "promised")

    def test_the_movement_inflection_chain_is_fully_covered(self) -> None:
        """Recorded so the framework does not propose work that is not needed."""

        chain = next(item for item in CHAINS if item.name == "movement_inflection")
        self.assertTrue(all(present for _word, present in chain.steps))
        self.assertIsNone(chain.first_missing)

    def test_the_movement_lexical_chain_starts_missing_at_skyrocket(self) -> None:
        chain = next(item for item in CHAINS if item.name == "movement_lexical")
        self.assertEqual(chain.first_missing, "skyrocket")

    def test_the_directive_chain_starts_missing_at_the_first_phrasal_verb(self) -> None:
        chain = next(item for item in CHAINS if item.name == "directive_phrasal")
        self.assertEqual(chain.first_missing, "snap up")

    def test_every_chain_declares_a_guide_basis(self) -> None:
        for item in CHAINS:
            with self.subTest(chain=item.name):
                self.assertTrue(item.guide_basis)
                self.assertTrue(item.words)

    def test_a_chain_with_every_step_known_has_no_missing_step(self) -> None:
        chain = Chain(name="x", category="c", words=("guaranteed",), guide_basis="b")
        self.assertIsNone(chain.first_missing)

    def test_chain_steps_are_pairs_of_word_and_presence(self) -> None:
        chain = Chain(name="x", category="c", words=("guaranteed", "zzz"), guide_basis="b")
        self.assertEqual(chain.steps, (("guaranteed", True), ("zzz", False)))


class FrameVariantTest(unittest.TestCase):
    def test_the_declared_frame_variants_exist(self) -> None:
        self.assertGreaterEqual(len(FRAME_VARIANTS), 5)
        self.assertEqual(len({item.variant_id for item in FRAME_VARIANTS}), len(FRAME_VARIANTS))

    def test_the_negative_control_expects_no_finding(self) -> None:
        control = next(
            item for item in FRAME_VARIANTS if item.variant_id == "FRAME-GUAR-NEGATED"
        )
        self.assertFalse(control.expects_finding)
        self.assertEqual(control.text, "Returns cannot be guaranteed.")

    def test_every_frame_variant_declares_a_relation_and_a_basis(self) -> None:
        for item in FRAME_VARIANTS:
            with self.subTest(variant=item.variant_id):
                self.assertIn(item.relation, V3_RELATIONS)
                self.assertTrue(item.guide_basis)
                self.assertTrue(item.frame_kind)

    def test_describe_maps_a_control_variant_to_unknown(self) -> None:
        body = synonyms.describe()
        controls = [item for item in body["frame_variants"] if not item["expects_finding"]]
        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]["failure_type"], "UNKNOWN")


class ProvenanceTest(unittest.TestCase):
    def test_provenance_of_a_declared_synonym(self) -> None:
        body = provenance("promised")
        self.assertFalse(body["known_to_evaluator"])
        self.assertEqual(body["declared_axes"], [])
        self.assertIn("promised", body["inflections"])

    def test_provenance_of_a_declared_axis_word(self) -> None:
        body = provenance("plummet")
        self.assertFalse(body["known_to_evaluator"])
        self.assertEqual(body["declared_axes"], ["movement_direction"])

    def test_provenance_of_a_word_the_evaluator_knows(self) -> None:
        body = provenance("guaranteed")
        self.assertTrue(body["known_to_evaluator"])
        self.assertTrue(body["origins"])

    def test_provenance_of_an_unknown_word(self) -> None:
        body = provenance("zzz")
        self.assertFalse(body["known_to_evaluator"])
        self.assertEqual(body["origins"], [])
        self.assertEqual(body["declared_axes"], [])


class ModuleSurfaceTest(unittest.TestCase):
    def test_novel_synonyms_are_pairs_of_axis_and_word(self) -> None:
        pairs = novel_synonyms()
        self.assertTrue(pairs)
        for name, word in pairs:
            with self.subTest(axis=name, word=word):
                self.assertIn(name, [item.name for item in AXES])
                self.assertFalse(lexicon.known(word))

    def test_categories_are_returned_in_declaration_order(self) -> None:
        self.assertEqual(
            categories(),
            (
                "financial_guarantee",
                "market_prediction",
                "investment_advice",
                "unverified_information",
                "emotional_manipulation",
            ),
        )

    def test_axes_for_category_selects_the_axes(self) -> None:
        self.assertEqual(
            {item.name for item in axes_for_category("investment_advice")},
            {"directive_verb", "position_word"},
        )
        self.assertEqual(axes_for_category("nope"), ())

    def test_words_lists_canonical_synonyms_and_chain_steps(self) -> None:
        declared = words()
        self.assertIn("guaranteed", declared)
        self.assertIn("plummet", declared)
        self.assertIn("promised", declared)

    def test_describe_lists_every_axis_chain_and_refusal(self) -> None:
        body = synonyms.describe()
        self.assertEqual(len(body["axes"]), len(AXES))
        self.assertEqual(len(body["chains"]), len(CHAINS))
        self.assertEqual(len(body["withheld"]), len(WITHHELD))
        self.assertTrue(body["report"]["ok"])

    def test_describe_states_that_nothing_is_applied(self) -> None:
        self.assertIn("no candidate is applied", synonyms.describe()["note"])

    def test_the_position_axis_words_are_adjectival_for_its_frame(self) -> None:
        """A noun-shaped position word would produce a broken sentence."""

        for word in axis("position_word").synonyms:
            with self.subTest(word=word):
                self.assertNotIn(word, {"position", "allocation", "exposure"})

    def test_the_sourcing_axis_words_are_nouns_the_frame_can_name(self) -> None:
        for word in axis("reported_source").synonyms:
            with self.subTest(word=word):
                self.assertFalse(word.endswith("ed"))
