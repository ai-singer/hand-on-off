"""The read-only view of the evaluator's declared vocabulary.

`lexicon` answers one question per failing case — is the concept there, or only the
wording? — so the tests here are about what it can and cannot see: patterns expanded
as written, forms the evaluator never spells out, and the absence of a mutable
registration step.
"""

from __future__ import annotations

import re
import unittest

from risk_evaluation.coverage import freeze, lexicon
from risk_evaluation.coverage.lexicon import (
    LexiconError,
    LexiconSlice,
    declared_lemmas,
    describe,
    entity_hooks,
    entity_types,
    form_to_lemma,
    generated_forms,
    known,
    known_words,
    morphology_hit,
    origin_of,
    relation_frames,
    slices,
    tokens,
    words_from_pattern,
)


class WordsFromPatternTest(unittest.TestCase):
    """Patterns are expanded as the evaluator writes them, and no further."""

    def test_an_optional_s_suffix_yields_both_spellings(self) -> None:
        words = words_from_pattern("returns?")
        self.assertIn("return", words)
        self.assertIn("returns", words)

    def test_an_optional_suffix_group_yields_all_three_forms(self) -> None:
        words = words_from_pattern("guarantee(?:s|d)?")
        self.assertEqual(set(words), {"guarantee", "guarantees", "guaranteed"})

    def test_an_optional_group_is_not_invented_where_it_is_absent(self) -> None:
        """`expands` must not produce `expand`, or MORPHOLOGY_GAP could never fire."""

        words = words_from_pattern("expands")
        self.assertEqual(words, ("expands",))
        self.assertNotIn("expand", words)

    def test_a_non_inflectional_optional_group_is_left_alone(self) -> None:
        words = words_from_pattern("do(?:es|did)?")
        self.assertIn("do", words)
        self.assertNotIn("does", words)

    def test_alternation_is_split(self) -> None:
        self.assertEqual(set(words_from_pattern("rise|fall")), {"rise", "fall"})

    def test_a_compiled_pattern_is_unwrapped(self) -> None:
        self.assertEqual(
            words_from_pattern(re.compile(r"returns?")), words_from_pattern("returns?")
        )

    def test_regex_syntax_is_dropped_rather_than_entering_the_lexicon(self) -> None:
        self.assertEqual(words_from_pattern(r"\bfoo\b"), ("foo",))
        self.assertNotIn("b", words_from_pattern(r"\bfoo\b"))

    def test_a_named_group_is_dropped(self) -> None:
        self.assertEqual(words_from_pattern(r"(?P<x>bar)"), ("bar",))

    def test_a_character_class_does_not_enter_a_lone_letter(self) -> None:
        # `[s]` must not be read as a declared one-letter word.
        self.assertEqual(words_from_pattern(r"[s]"), ())

    def test_digits_are_not_words(self) -> None:
        self.assertEqual(words_from_pattern("words 12"), ("words",))

    def test_single_letter_words_are_kept_only_when_they_are_words(self) -> None:
        self.assertEqual(set(words_from_pattern("a fund")), {"a", "fund"})
        self.assertNotIn("x", words_from_pattern("x fund"))

    def test_hyphenated_words_survive(self) -> None:
        self.assertIn("risk-free", words_from_pattern("risk-free"))

    def test_words_are_deduplicated_in_order_of_appearance(self) -> None:
        self.assertEqual(words_from_pattern("rise fall rise"), ("rise", "fall"))

    def test_a_non_string_is_refused(self) -> None:
        with self.assertRaises(LexiconError):
            words_from_pattern(None)

    def test_an_integer_is_refused(self) -> None:
        with self.assertRaises(LexiconError):
            words_from_pattern(7)


class KnownWordTest(unittest.TestCase):
    def test_the_guarantee_predicate_alternatives_are_known(self) -> None:
        # These live inside `_GUARANTEE_PREDICATE`, which the first draft of the
        # lexicon missed entirely.
        self.assertTrue(known("assured"))
        self.assertTrue(known("protected"))

    def test_a_declared_spelling_is_known(self) -> None:
        self.assertTrue(known("guaranteed"))
        self.assertTrue(known("returns"))

    def test_an_invented_word_is_not_known(self) -> None:
        self.assertFalse(known("zzz"))
        self.assertFalse(known("assuredly"))

    def test_lookup_ignores_case_and_surrounding_space(self) -> None:
        self.assertTrue(known("  ASSURED "))

    def test_the_known_vocabulary_is_not_empty(self) -> None:
        self.assertGreater(len(known_words()), 100)

    def test_declared_lemmas_are_known_words(self) -> None:
        self.assertTrue(set(declared_lemmas()) <= set(known_words()))

    def test_the_evaluator_does_not_spell_out_every_form_it_can_build(self) -> None:
        unlisted = [word for word in generated_forms() if word not in known_words()]
        self.assertGreater(
            len(unlisted),
            100,
            "the gap between built forms and written forms is what MORPHOLOGY_GAP "
            "measures; folding the two sets together would erase the signal",
        )


class MorphologyHitTest(unittest.TestCase):
    """Only a lemma the evaluator declares may vouch for a form it never wrote."""

    def test_a_spelled_out_word_returns_none(self) -> None:
        self.assertIsNone(morphology_hit("guaranteed"))
        self.assertIsNone(morphology_hit("assured"))

    def test_an_unlisted_inflected_form_returns_its_lemma(self) -> None:
        self.assertEqual(morphology_hit("acknowledges"), "acknowledge")
        self.assertEqual(morphology_hit("acknowledging"), "acknowledge")

    def test_an_unknown_token_returns_none(self) -> None:
        self.assertIsNone(morphology_hit("zzz"))

    def test_a_non_word_returns_none(self) -> None:
        for token in ("", "   ", "123", "co-op's", "-"):
            with self.subTest(token=token):
                self.assertIsNone(morphology_hit(token))

    def test_the_lemma_returned_is_one_the_evaluator_declares(self) -> None:
        lemma = morphology_hit("acknowledges")
        self.assertIsNotNone(lemma)
        self.assertIn(lemma, declared_lemmas())

    def test_a_form_the_evaluator_could_inflect_but_never_lists_is_still_a_hit(
        self,
    ) -> None:
        """The distinction is `known`, not derivability: unlisted forms are hits."""

        self.assertEqual(morphology_hit("acknowledges"), "acknowledge")
        self.assertNotIn("acknowledges", known_words())

    def test_form_to_lemma_is_inverted_from_declared_lemmas(self) -> None:
        for form, lemma in list(form_to_lemma().items())[:50]:
            with self.subTest(form=form):
                self.assertIn(lemma, declared_lemmas())
                self.assertRegex(form, r"^[a-z][a-z-]*$")


class EntityTest(unittest.TestCase):
    def test_the_guarantee_sentence_names_a_return(self) -> None:
        self.assertIn("RETURN", entity_types("Returns are guaranteed on this fund"))

    def test_entity_types_are_deduplicated_in_order(self) -> None:
        kinds = entity_types("Returns are guaranteed on this fund")
        self.assertEqual(len(kinds), len(set(kinds)))
        self.assertEqual(kinds[0], "RETURN")

    def test_entity_hooks_are_lowercased(self) -> None:
        hooks = entity_hooks("Returns are guaranteed on this Fund")
        self.assertEqual(list(hooks), [hook.lower() for hook in hooks])

    def test_a_plural_hook_is_kept_as_the_plural_the_evaluator_spells_out(self) -> None:
        hooks = entity_hooks("Returns are guaranteed.")
        self.assertIn("returns", hooks)
        self.assertEqual(entity_types("Returns are guaranteed."), ("RETURN",))

    def test_a_text_without_entities_has_no_hooks(self) -> None:
        self.assertEqual(entity_hooks("Nothing here at all."), ())
        self.assertEqual(entity_types("Nothing here at all."), ())

    def test_a_non_string_is_refused(self) -> None:
        with self.assertRaises(LexiconError):
            entity_hooks(None)

    def test_function_words_are_not_entities(self) -> None:
        for word in ("the", "this", "its", "your"):
            with self.subTest(word=word):
                self.assertNotIn(word, entity_hooks(f"{word} return is safe"))


class SliceTest(unittest.TestCase):
    def test_every_relation_the_evaluator_defines_has_a_frame_slice(self) -> None:
        origins = [item.origin for item in slices()]
        for relation in relation_frames():
            with self.subTest(relation=relation):
                self.assertTrue(
                    any(f".{relation}." in origin for origin in origins),
                    f"no slice is derived from relation {relation}",
                )

    def test_the_four_relations_are_the_ones_the_tables_name(self) -> None:
        self.assertEqual(
            set(relation_frames()),
            {"GUARANTEE", "RISK_REMOVED", "PREDICTION", "ADVICE"},
        )

    def test_the_guarantor_table_is_enumerated(self) -> None:
        self.assertIn("v3.patterns.GUARANTORS", [item.origin for item in slices()])

    def test_the_entity_tables_are_enumerated(self) -> None:
        origins = [item.origin for item in slices()]
        self.assertIn("v3.patterns.ENTITIES.RETURN", origins)
        self.assertIn("v3.patterns.ENTITIES.INSTRUMENT", origins)

    def test_the_guarantor_table_contributes_words(self) -> None:
        guarantee = [item for item in slices() if item.origin == "v3.patterns.GUARANTORS"]
        self.assertEqual(len(guarantee), 1)
        self.assertTrue(guarantee[0].words)

    def test_a_slice_words_property_is_deduplicated_and_lowercased(self) -> None:
        item = LexiconSlice("test", lemmas=("Rise", "rise"), patterns=("rise|fall",))
        self.assertEqual(item.words, ("rise", "fall"))

    def test_origin_of_names_every_declaration_holding_a_word(self) -> None:
        origins = origin_of("assured")
        self.assertIn("v3.patterns.GUARANTEE.copular[3]", origins)

    def test_origin_of_an_unknown_word_is_empty(self) -> None:
        self.assertEqual(origin_of("zzz"), ())

    def test_slices_are_cached_so_the_registry_is_walked_once(self) -> None:
        self.assertIs(slices(), slices())

    def test_the_slice_count_is_recorded(self) -> None:
        self.assertEqual(describe()["slices"], len(slices()))


class TokenTest(unittest.TestCase):
    def test_tokens_are_lowercased(self) -> None:
        self.assertEqual(tokens("Returns Are Guaranteed"), ("returns", "are", "guaranteed"))

    def test_hyphenated_tokens_stay_whole(self) -> None:
        self.assertIn("risk-free", tokens("a risk-free fund"))

    def test_digits_and_punctuation_are_dropped(self) -> None:
        self.assertEqual(tokens("300 cases, 12 words."), ("cases", "words"))


class DescribeTest(unittest.TestCase):
    def test_describe_reports_positive_counts(self) -> None:
        body = describe()
        for key in (
            "slices",
            "declared_lemmas",
            "known_words",
            "generated_forms",
            "entity_words",
        ):
            with self.subTest(key=key):
                self.assertIsInstance(body[key], int)
                self.assertGreater(body[key], 0)

    def test_describe_names_the_four_relations(self) -> None:
        self.assertEqual(
            describe()["relations"],
            ["ADVICE", "GUARANTEE", "PREDICTION", "RISK_REMOVED"],
        )

    def test_describe_states_that_it_is_read_only(self) -> None:
        self.assertIn("read-only", describe()["note"])

    def test_reading_the_lexicon_does_not_extend_the_lemma_index(self) -> None:
        """`register()` mutates the index; the coverage read calls pure functions only."""

        from risk_evaluation.v3 import morphology

        before = morphology.known_lemmas()
        known_words()
        generated_forms()
        form_to_lemma()
        entity_types("Returns are guaranteed on this fund")
        self.assertEqual(morphology.known_lemmas(), before)

    def test_the_evaluators_own_tables_register_their_lemmas_when_imported(self) -> None:
        """Recorded for the report, not asserted as a defect.

        Importing `risk_evaluation.v3.patterns` and `risk_evaluation.v3_1.advice` —
        which `lexicon.slices()` must do to enumerate them — calls the evaluator's own
        `morphology.register()`, so the evaluator's *in-memory* lemma index is populated
        (21 then 97 lemmas) as a side effect of the read. Nothing on disk changes, which
        is what `freeze.guard()` proves and what the phase's prohibition is about; but
        the lexicon docstring's "Nothing in `risk_evaluation/v3*` is written to, in
        memory or on disk" overstates the in-memory half of that claim.
        """

        from risk_evaluation.v3 import morphology

        self.assertTrue(morphology.known_lemmas())

    def test_the_frozen_evaluator_digest_is_unchanged_by_reading_the_lexicon(
        self,
    ) -> None:
        before = freeze.evaluator_digest()
        known_words()
        entity_types("Returns are guaranteed on this fund")
        self.assertEqual(before, freeze.evaluator_digest())


class ModuleSurfaceTest(unittest.TestCase):
    def test_the_module_offers_the_four_functions_the_analyzer_uses(self) -> None:
        for name in ("known", "morphology_hit", "entity_hooks", "entity_types"):
            self.assertTrue(callable(getattr(lexicon, name, None)), name)

    def test_relation_frames_returns_descriptions_per_relation(self) -> None:
        frames = relation_frames()
        for relation, descriptions in frames.items():
            with self.subTest(relation=relation):
                self.assertTrue(descriptions)
                for description in descriptions:
                    self.assertIsInstance(description, str)
