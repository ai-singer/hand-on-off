"""The adversarial expansion generator: declared substitution, never random text.

The bugs this module was built through are all grammatical, so the tests here assert
the shapes of the sentences it produces: a participle where the frame is copular, a
third person form where the frame is a bare present, and never a doubled suffix.
"""

from __future__ import annotations

import json
import re
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from tempfile import TemporaryDirectory

from risk_evaluation.coverage import generator, synonyms
from risk_evaluation.coverage.generator import (
    CASE_PREFIX,
    FORMS,
    GENERATED_DIR,
    GENERATED_PATH,
    LEMMA,
    PARTICIPLE,
    TEMPLATES,
    THIRD,
    GeneratedCase,
    GeneratorError,
    Template,
    axis_cases,
    chain_cases,
    describe,
    frame_cases,
    generate,
    observe,
    payload,
    template,
)
from risk_evaluation.coverage.taxonomy import FAILURE_TYPES

from ._support import generated, generated_payload


def rule_word(rule: str) -> str:
    """The substituted word a case's generation rule names."""

    return rule.rsplit(":", 1)[-1]


class DeterminismTest(unittest.TestCase):
    """Structured substitution is reproducible or it is not reviewable."""

    def test_two_calls_produce_identical_case_ids(self) -> None:
        self.assertEqual([c.case_id for c in generate()], [c.case_id for c in generate()])

    def test_two_calls_produce_identical_texts(self) -> None:
        self.assertEqual([c.text for c in generate()], [c.text for c in generate()])

    def test_the_cached_fixture_matches_a_fresh_call(self) -> None:
        self.assertEqual([c.case_id for c in generated()], [c.case_id for c in generate()])

    def test_the_order_is_stable_by_length_then_text(self) -> None:
        keys = [(len(case.text), case.text) for case in generate()]
        self.assertEqual(keys, sorted(keys))

    def test_case_ids_are_unique(self) -> None:
        ids = [case.case_id for case in generate()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_case_id_carries_the_generated_prefix(self) -> None:
        for case in generate():
            with self.subTest(case=case.case_id):
                self.assertTrue(case.case_id.startswith(CASE_PREFIX))


class ContractTest(unittest.TestCase):
    def test_at_least_fifty_cases_are_generated(self) -> None:
        self.assertGreaterEqual(len(generate()), 50)

    def test_every_case_says_why_it_was_generated(self) -> None:
        for case in generate():
            with self.subTest(case=case.case_id):
                self.assertTrue(case.generation_reason.strip())

    def test_every_case_declares_the_categories_the_guide_gives_it(self) -> None:
        controls = {
            variant.variant_id
            for variant in synonyms.FRAME_VARIANTS
            if not variant.expects_finding
        }
        self.assertTrue(controls)
        for case in generate():
            with self.subTest(case=case.case_id):
                if case.parent_case in controls:
                    # The declared negative control: it exists so the set can detect a
                    # detector that catches everything, so it claims no category.
                    self.assertEqual(case.expected_categories, ())
                    self.assertFalse(case.expects_risk)
                    continue
                self.assertTrue(case.expected_categories)
                self.assertTrue(case.expects_risk)

    def test_exactly_one_generated_case_claims_no_category(self) -> None:
        silent = [case.case_id for case in generate() if not case.expected_categories]
        self.assertEqual(silent, ["GEN-R1-FRAME-0003"])

    def test_every_case_is_excluded_from_every_benchmark(self) -> None:
        for case in generate():
            with self.subTest(case=case.case_id):
                self.assertIs(case.excludes_from_benchmark, True)

    def test_every_case_names_the_table_it_came_from(self) -> None:
        for case in generate():
            with self.subTest(case=case.case_id):
                self.assertTrue(case.source_table)
                self.assertTrue(case.source_table.startswith("synonyms."))

    def test_every_case_carries_a_declared_failure_type(self) -> None:
        for case in generate():
            with self.subTest(case=case.case_id):
                self.assertIn(case.failure_type, FAILURE_TYPES)

    def test_every_case_carries_a_declared_risk_category(self) -> None:
        declared = set(synonyms.categories())
        for case in generate():
            with self.subTest(case=case.case_id):
                self.assertIn(case.risk_category, declared)

    def test_every_case_is_english(self) -> None:
        for case in generate():
            with self.subTest(case=case.case_id):
                self.assertEqual(case.language, "en")


class GrammarTest(unittest.TestCase):
    """The specific ways the first drafts produced ungrammatical sentences."""

    def test_no_generated_text_contains_a_doubled_ed(self) -> None:
        offenders = [case.text for case in generate() if "eded" in case.text]
        self.assertEqual(offenders, [])

    def test_no_generated_text_contains_a_doubled_ing(self) -> None:
        offenders = [case.text for case in generate() if "inging" in case.text]
        self.assertEqual(offenders, [])

    def test_the_participle_template_yields_the_participle(self) -> None:
        self.assertIn("Returns are promised.", {case.text for case in generate()})

    def test_no_copular_case_substitutes_a_bare_lemma(self) -> None:
        lemmas = set(synonyms.axis("guarantee_predicate").synonyms)
        for case in generate():
            match = re.fullmatch(r"Returns are (\S+)\.", case.text)
            if not match:
                continue
            with self.subTest(case=case.case_id):
                self.assertNotIn(match.group(1), lemmas)

    def test_the_movement_template_yields_a_third_person_form(self) -> None:
        self.assertIn("Turnover plummets next quarter.", {case.text for case in generate()})

    def test_the_copular_template_is_the_documented_worked_example(self) -> None:
        item = template("TPL-GUAR-COPULAR")
        self.assertEqual(item.form, PARTICIPLE)
        self.assertEqual(item.render("promise"), "Returns are promised.")
        self.assertEqual(item.render_verbatim("promised"), "Returns are promised.")

    def test_the_movement_template_is_third_person(self) -> None:
        item = template("TPL-PRED-MOVEMENT")
        self.assertEqual(item.form, THIRD)
        self.assertEqual(item.render("plummet"), "Turnover plummets next quarter.")

    def test_every_template_substituted_case_renders_from_its_rule(self) -> None:
        """Each axis case is exactly its template's rendering of the declared word."""

        checked = 0
        for case in generate():
            if not case.generation_rule.startswith("template:"):
                continue
            _marker, template_id, _axis_marker, axis_name, word = case.generation_rule.split(
                ":", 4
            )
            with self.subTest(case=case.case_id):
                self.assertEqual(
                    template(template_id).render(word),
                    case.text,
                    f"{axis_name} case is not its template's rendering",
                )
            checked += 1
        self.assertGreater(checked, 40)

    def test_a_multi_word_substitution_is_never_inflected(self) -> None:
        """The morphology layer inflects tokens, not phrases."""

        item = template("TPL-PRED-MOVEMENT")
        self.assertEqual(item.shape("snap up"), "snap up")
        self.assertEqual(item.shape("loss-proof"), "loss-proof")

    def test_the_movement_chain_cases_are_third_person_too(self) -> None:
        """A lemma chain is shaped by its template; a surface chain is not.

        `chain_cases()` used to render every step verbatim, which is right for a chain
        whose steps are surface forms (`guaranteed`, `assured`, `promised`) and wrong
        for the `movement_lexical` chain, whose steps are lemmas. Rendering that chain
        verbatim produced bare-lemma sentences:

            'Turnover skyrocket next quarter.'   # wrong
            'Turnover skyrockets next quarter.'  # right

        `synonyms.Chain` now declares `forms`, so the generator knows which path to
        take.
        """

        item = template("TPL-PRED-MOVEMENT")
        checked = 0
        for case in generate():
            if not case.generation_rule.startswith("chain:movement_lexical:"):
                continue
            checked += 1
            with self.subTest(case=case.case_id):
                self.assertEqual(case.text, item.render(rule_word(case.generation_rule)))
        self.assertTrue(checked, "the movement chain produced no cases to check")

    def test_a_surface_form_chain_is_not_inflected_again(self) -> None:
        """The other half of the distinction: `promised` keeps its spelling.

        Shaping a surface form through the participle builder produced
        `Returns are promiseded.`, so a surface chain is rendered verbatim.
        """

        surfaces = {
            case.text
            for case in generate()
            if case.generation_rule.startswith("chain:guarantee_weakening:")
        }
        self.assertIn("Returns are promised.", surfaces)
        for text in surfaces:
            with self.subTest(text=text):
                self.assertNotIn("promiseded", text)


class WithheldTest(unittest.TestCase):
    def test_the_withheld_wordings_are_declared(self) -> None:
        self.assertTrue(synonyms.WITHHELD)

    def test_a_generated_withheld_wording_never_claims_a_risk_category(self) -> None:
        """The refusal is about *claiming*, and the control case is labelled as one."""

        withheld = {item.text for item in synonyms.WITHHELD}
        seen = [case for case in generate() if case.text in withheld]
        for case in seen:
            with self.subTest(case=case.case_id):
                self.assertEqual(case.expected_categories, ())
                self.assertFalse(case.expects_risk)

    def test_a_withheld_wording_is_generated_only_as_a_negative_control(self) -> None:
        """`WITHHELD` refuses a *candidate*, not a case, and the control proves it.

        `synonyms.WITHHELD` records "Returns cannot be guaranteed." as a wording this
        framework "does not turn into candidates", and `frame_cases()` does emit it —
        as `GEN-R1-FRAME-0003`, with no expected category. The two are consistent once
        the distinction is stated: the wording is generated precisely so that the
        expansion set contains something a detector must not fire on, and it is never
        the basis of a repair proposal.

        An earlier version of this test asserted that no generated text may equal a
        withheld text, which contradicted the design rather than checking it.
        """

        withheld = {item.text for item in synonyms.WITHHELD}
        seen = [case for case in generate() if case.text in withheld]
        self.assertTrue(seen, "the negative control is missing from the expansion set")
        for case in seen:
            with self.subTest(case=case.case_id):
                self.assertEqual(case.expected_categories, ())
                self.assertFalse(case.expects_risk)
                self.assertEqual(case.failure_type, "LEXICAL_GAP")


class DedupTest(unittest.TestCase):
    def test_no_two_cases_share_a_text(self) -> None:
        texts = [case.text for case in generate()]
        self.assertEqual(len(texts), len(set(texts)))

    def test_dedup_actually_removed_duplicates(self) -> None:
        raw = len(frame_cases()) + len(chain_cases()) + len(axis_cases())
        self.assertLess(len(generate()), raw)

    def test_dedup_keeps_the_first_case_for_a_text(self) -> None:
        """Frame cases come first, then chain cases, then axis cases."""

        first_for_text = {
            case.text: case
            for case in reversed(frame_cases() + chain_cases() + axis_cases())
        }
        for case in generate():
            with self.subTest(case=case.case_id):
                self.assertEqual(case.case_id, first_for_text[case.text].case_id)

    def test_the_dropped_duplicates_are_the_axis_cases(self) -> None:
        surviving = {case.text: case for case in generate()}
        dropped = [
            case
            for case in axis_cases()
            if surviving[case.text].case_id != case.case_id
        ]
        self.assertTrue(dropped, "dedup removed nothing, so this test proves nothing")
        for case in dropped:
            with self.subTest(case=case.case_id):
                self.assertNotEqual(surviving[case.text].case_id, case.case_id)


class StageTest(unittest.TestCase):
    def test_frame_cases_cover_the_declared_variants(self) -> None:
        self.assertEqual(len(frame_cases()), len(synonyms.FRAME_VARIANTS))

    def test_the_negative_control_frame_case_expects_nothing(self) -> None:
        control = next(
            case for case in frame_cases() if case.generation_rule == "FRAME-GUAR-NEGATED"
        )
        self.assertEqual(control.expected_categories, ())
        self.assertEqual(control.text, "Returns cannot be guaranteed.")

    def test_a_positive_frame_case_carries_its_category(self) -> None:
        case = next(
            case for case in frame_cases() if case.generation_rule == "FRAME-GUAR-GUARANTEED"
        )
        self.assertEqual(case.expected_categories, ("financial_guarantee",))

    def test_chain_cases_skip_the_steps_the_evaluator_already_accepts(self) -> None:
        ids = [case.case_id for case in chain_cases()]
        self.assertEqual(len(ids), 6)
        self.assertTrue(
            all("GUARANTEE_WEAKENING-04" in case_id for case_id in ids if "GUARANTEE" in case_id)
        )
        self.assertFalse(any("MOVEMENT_INFLECTION" in case_id for case_id in ids))

    def test_the_guarantee_chain_case_is_the_first_missing_step(self) -> None:
        case = next(c for c in chain_cases() if "GUARANTEE_WEAKENING" in c.case_id)
        self.assertIn("promised", case.generation_rule)
        self.assertEqual(case.text, "Returns are promised.")

    def test_axis_cases_cover_every_novel_synonym_of_every_template_axis(self) -> None:
        produced = set()
        for case in axis_cases():
            if case.generation_rule.startswith("template:"):
                produced.add(rule_word(case.generation_rule))
        expected = {
            word
            for item in TEMPLATES
            for word in synonyms.axis(item.axis).novel
        }
        self.assertEqual(produced, expected)

    def test_axis_cases_flag_the_axes_with_no_relation_for_review(self) -> None:
        review_only = [
            case
            for case in axis_cases()
            if case.generation_rule.startswith("template:TPL-PRESSURE-URGENCY")
        ]
        self.assertTrue(review_only)
        for case in review_only:
            with self.subTest(case=case.case_id):
                self.assertIn("human review", case.generation_reason)

    def test_a_case_from_an_axis_with_no_relation_is_not_a_vocabulary_proposal(
        self,
    ) -> None:
        self.assertFalse(synonyms.axis("reported_source").auto_generatable)
        for case in axis_cases():
            if not case.generation_rule.startswith("template:TPL-SOURCE-REPORTED"):
                continue
            with self.subTest(case=case.case_id):
                self.assertEqual(case.failure_type, "LEXICAL_GAP")
                self.assertIn("human review", case.generation_reason)


class TemplateTest(unittest.TestCase):
    def test_every_declared_template_is_looked_up_by_id(self) -> None:
        for item in TEMPLATES:
            with self.subTest(template=item.template_id):
                self.assertEqual(template(item.template_id), item)

    def test_an_undeclared_template_id_raises(self) -> None:
        with self.assertRaises(GeneratorError) as caught:
            template("TPL-NOPE")
        self.assertIn("no template named", str(caught.exception))

    def test_every_template_names_a_declared_axis_and_a_guide_basis(self) -> None:
        for item in TEMPLATES:
            with self.subTest(template=item.template_id):
                self.assertIn(item.form, FORMS)
                self.assertTrue(item.guide_basis)
                self.assertEqual(synonyms.axis(item.axis).name, item.axis)

    def test_an_undeclared_form_is_refused(self) -> None:
        with self.assertRaises(GeneratorError):
            Template(
                template_id="T",
                category="c",
                relation="GUARANTEE",
                pattern="Returns are {word}.",
                axis="guarantee_predicate",
                guide_basis="b",
                form="plural",
            )

    def test_every_template_pattern_consumes_a_word_placeholder(self) -> None:
        for item in TEMPLATES:
            with self.subTest(template=item.template_id):
                self.assertTrue(
                    "{word}" in item.pattern or "{Word}" in item.pattern,
                    item.pattern,
                )

    def test_the_upper_placeholder_capitalises(self) -> None:
        item = template("TPL-ADVICE-IMPERATIVE")
        self.assertEqual(item.render("snap up"), "Snap up this fund.")

    def test_shaping_every_declared_word_produces_no_doubled_suffix(self) -> None:
        """`promised` passed through the participle rule produced `promiseded`."""

        for item in TEMPLATES:
            for word in synonyms.axis(item.axis).novel:
                with self.subTest(template=item.template_id, word=word):
                    shaped = item.shape(word)
                    self.assertNotIn("eded", shaped)
                    self.assertNotIn("inging", shaped)

    def test_shaping_a_word_that_cannot_inflect_never_errors(self) -> None:
        """Observation recorded for the report.

        `Template.shape` declares a `GeneratorError` for "a word that cannot inflect"
        (generator.py lines 101-109), but `past_participle` and `third_person` are total
        functions over `str` — `third_person("123")` is `"123s"` and
        `past_participle("-")` is `"-ed"` — so that branch is unreachable and the guard
        never fires. Not asserted as a defect: the branch is defensive, and the frame
        templates are only ever handed words from the declared axes.
        """

        item = template("TPL-PRED-MOVEMENT")
        for word in ("123", "", "-", "zzz"):
            with self.subTest(word=word):
                self.assertIsInstance(item.shape(word), str)

    def test_the_lemma_form_never_inflects(self) -> None:
        item = template("TPL-GUAR-ACTIVE")
        self.assertEqual(item.form, LEMMA)
        self.assertEqual(item.render("promise"), "We promise that your capital is returned in full.")


class ObserveAndPayloadTest(unittest.TestCase):
    def test_observe_reports_one_verdict_per_case(self) -> None:
        cases = generate()
        observed = observe(cases)
        self.assertEqual(set(observed), {case.case_id for case in cases})

    def test_every_verdict_is_one_of_the_declared_four(self) -> None:
        for case_id, entry in observe(generate()).items():
            with self.subTest(case=case_id):
                self.assertIn(
                    entry["verdict"],
                    {"already_handled", "over_triggered", "missed", "unclear"},
                )

    def test_an_already_handled_case_has_matching_sets(self) -> None:
        for entry in observe(generate()).values():
            if entry["verdict"] == "already_handled":
                self.assertEqual(entry["expected"], entry["predicted"])

    def test_the_payload_counts_every_case(self) -> None:
        body = generated_payload()
        self.assertEqual(body["count"], len(generate()))
        self.assertEqual(len(body["cases"]), len(generate()))

    def test_the_payload_verdicts_sum_to_the_case_count(self) -> None:
        body = generated_payload()
        self.assertEqual(sum(body["verdicts"].values()), body["count"])

    def test_the_payload_records_the_declared_templates_and_refusals(self) -> None:
        body = generated_payload()
        self.assertEqual(len(body["templates"]), len(TEMPLATES))
        self.assertEqual(len(body["withheld"]), len(synonyms.WITHHELD))

    def test_the_payload_states_that_the_cases_are_not_a_benchmark(self) -> None:
        self.assertIn("excluded from", generated_payload()["not_a_benchmark"])

    def test_the_payload_excludes_every_case_from_every_benchmark(self) -> None:
        for case in generated_payload()["cases"]:
            with self.subTest(case=case["case_id"]):
                self.assertIs(case["excludes_from_benchmark"], True)

    def test_the_payload_carries_the_three_freeze_digests(self) -> None:
        body = generated_payload()
        for key in ("source_hash", "benchmark_hash", "evaluator_hash"):
            with self.subTest(key=key):
                self.assertTrue(body[key])


class WriteTest(unittest.TestCase):
    def test_write_creates_the_artifact_where_it_is_asked_to(self) -> None:
        with TemporaryDirectory() as raw:
            target = Path(raw) / "generated" / "generated_cases_r1.json"
            written = generator.write(target, generated())
            self.assertEqual(written, target)
            body = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(body["count"], len(generate()))
            self.assertEqual(body["artifact"], "adversarial-expansion-set")

    def test_the_default_output_lives_under_the_package(self) -> None:
        self.assertEqual(GENERATED_DIR, GENERATED_PATH.parent)
        self.assertTrue(
            str(GENERATED_PATH).replace("\\", "/").endswith(
                "risk_evaluation/coverage/generated_cases/generated_cases_r1.json"
            )
        )

    def test_the_written_artifact_never_marks_a_case_as_benchmark_eligible(self) -> None:
        with TemporaryDirectory() as raw:
            target = Path(raw) / "cases.json"
            generator.write(target, generated())
            body = json.loads(target.read_text(encoding="utf-8"))
            leaks = [
                case["case_id"]
                for case in body["cases"]
                if case.get("excludes_from_benchmark") is not True
            ]
            self.assertEqual(leaks, [])


class DescribeTest(unittest.TestCase):
    def test_describe_reports_the_tables_and_the_case_count(self) -> None:
        body = describe()
        self.assertEqual(body["templates"], len(TEMPLATES))
        self.assertEqual(body["cases"], len(generate()))
        self.assertEqual(body["withheld"], len(synonyms.WITHHELD))

    def test_describe_names_the_declared_source_tables(self) -> None:
        sources = describe()["sources"]
        self.assertIn("synonyms.CHAINS", sources)
        self.assertIn("synonyms.FRAME_VARIANTS", sources)
        for source in sources:
            with self.subTest(source=source):
                self.assertTrue(
                    source in {"synonyms.CHAINS", "synonyms.FRAME_VARIANTS"}
                    or source.startswith("synonyms.AXES["),
                    source,
                )

    def test_describe_states_that_nothing_random_is_involved(self) -> None:
        self.assertIn("no random text", describe()["note"])

    def test_generated_cases_are_frozen_records(self) -> None:
        case = generate()[0]
        with self.assertRaises(FrozenInstanceError):
            case.text = "changed"  # type: ignore[misc]

    def test_a_generated_case_is_a_generated_case(self) -> None:
        self.assertIsInstance(generate()[0], GeneratedCase)
