"""The failure taxonomy: nine types, a declared precedence, and enforceable rules.

Two properties are load-bearing here and are asserted directly rather than inferred
from the code: the precedence order, and the rule that a type can never be returned
without the evidence its rule requires.
"""

from __future__ import annotations

import unittest

from risk_evaluation.coverage import taxonomy
from risk_evaluation.coverage.model import Evidence
from risk_evaluation.coverage.taxonomy import (
    ANNOTATION_CONFLICT,
    ATTRIBUTION_GAP,
    AUTO_GENERATABLE,
    FAILURE_TYPES,
    FRAME_GAP,
    HUMAN_REQUIRED,
    LEXICAL_GAP,
    MEANING,
    MORPHOLOGY_GAP,
    PRECEDENCE,
    REPAIR_TYPE,
    REPAIR_TYPES,
    RULES,
    STANCE_GAP,
    SYNONYM_GAP,
    TAXONOMY_CONFLICT,
    UNEXPLAINED,
    UNKNOWN,
    TaxonomyError,
    Rule,
    build_record,
    classify,
    counts_by_type,
    describe,
    repair_for,
    rule_for,
)

from ._support import evidence, failure_record


def names(*items: str) -> tuple[Evidence, ...]:
    return tuple(evidence(name) for name in items)


class TaxonomyShapeTest(unittest.TestCase):
    def test_all_nine_types_are_declared(self) -> None:
        self.assertEqual(
            set(FAILURE_TYPES),
            {
                ANNOTATION_CONFLICT,
                TAXONOMY_CONFLICT,
                ATTRIBUTION_GAP,
                STANCE_GAP,
                MORPHOLOGY_GAP,
                SYNONYM_GAP,
                FRAME_GAP,
                LEXICAL_GAP,
                UNKNOWN,
            },
        )
        self.assertEqual(len(FAILURE_TYPES), 9)

    def test_every_type_has_a_meaning(self) -> None:
        for name in FAILURE_TYPES:
            self.assertTrue(MEANING.get(name), name)

    def test_every_type_has_a_precedence_position(self) -> None:
        self.assertEqual(set(PRECEDENCE), set(FAILURE_TYPES))
        self.assertEqual(sorted(PRECEDENCE.values()), list(range(9)))

    def test_precedence_ranks_the_types_in_first_appearance_order(self) -> None:
        """`PRECEDENCE` is a rank over `RULES`, not over the canonical listing.

        `FAILURE_TYPES` is a listing; `RULES` is the order `classify` walks, and the
        two intentionally differ — the unresolved-label rule runs first and the
        third-reading rule runs ahead of the broader annotation rule. Precedence is
        therefore derived from `RULES`, and this pins the derivation.
        """

        first_appearance: dict[str, int] = {}
        for rule in RULES:
            first_appearance.setdefault(rule.failure_type, len(first_appearance))
        self.assertEqual(PRECEDENCE, first_appearance)

    def test_every_type_implies_a_declared_repair_type(self) -> None:
        self.assertEqual(set(REPAIR_TYPE), set(FAILURE_TYPES))
        for name in FAILURE_TYPES:
            self.assertIn(REPAIR_TYPE[name], REPAIR_TYPES)

    def test_the_unsettled_label_guard_is_tested_first(self) -> None:
        self.assertEqual(RULES[0].failure_type, UNKNOWN)
        self.assertEqual(RULES[0].requires, ("annotation_unresolved",))

    def test_the_applied_rule_order_is_the_declared_one(self) -> None:
        """The exact sequence `classify` walks, pinned as data."""

        self.assertEqual(
            [rule.failure_type for rule in RULES[1:]],
            [
                TAXONOMY_CONFLICT,
                ANNOTATION_CONFLICT,
                ATTRIBUTION_GAP,
                STANCE_GAP,
                MORPHOLOGY_GAP,
                SYNONYM_GAP,
                FRAME_GAP,
                FRAME_GAP,
                LEXICAL_GAP,
                LEXICAL_GAP,
            ],
        )

    def test_declared_precedence_numbers_match_the_applied_rule_order(self) -> None:
        """`PRECEDENCE` is derived from `RULES`, so it cannot contradict `classify`.

        It used to be derived from `FAILURE_TYPES`, whose order is a canonical listing
        rather than an application order. The two diverged as soon as the
        unresolved-label rule ran first and the third-reading rule ran ahead of the
        broader annotation rule, and `Rule.as_dict()["precedence"]` then reported a
        number that disagreed with the order `classify` walks. A consumer sorting rules
        by that field got the wrong order.
        """

        positions = [PRECEDENCE[rule.failure_type] for rule in RULES[1:]]
        self.assertEqual(positions, sorted(positions))

    def test_precedence_ranks_a_third_reading_above_a_disagreement(self) -> None:
        """The ordering the derivation must preserve, stated directly."""

        self.assertLess(
            PRECEDENCE[TAXONOMY_CONFLICT], PRECEDENCE[ANNOTATION_CONFLICT]
        )

    def test_precedence_gives_an_unsettled_label_the_first_position(self) -> None:
        self.assertEqual(PRECEDENCE[UNKNOWN], 0)
        self.assertEqual(RULES[0].failure_type, UNKNOWN)

    def test_every_rule_names_at_least_one_required_evidence_item(self) -> None:
        for rule in RULES:
            self.assertTrue(rule.requires, rule.failure_type)
            self.assertTrue(rule.summary)

    def test_a_rule_serialises_its_precedence_and_repair(self) -> None:
        body = rule_for(LEXICAL_GAP).as_dict()
        self.assertEqual(body["failure_type"], LEXICAL_GAP)
        self.assertEqual(body["repair_type"], "lexical_extension")
        self.assertIn(body["failure_type"], FAILURE_TYPES)
        self.assertIsInstance(body["precedence"], int)
        self.assertTrue(rule_for(LEXICAL_GAP).requires)

    def test_rule_for_unknown_returns_the_fallback_rule(self) -> None:
        rule = rule_for(UNKNOWN)
        self.assertEqual(rule, UNEXPLAINED)
        self.assertEqual(rule.requires, ("no_rule_matched",))
        self.assertEqual(rule.summary, MEANING[UNKNOWN])

    def test_rule_for_rejects_an_undeclared_type(self) -> None:
        with self.assertRaises(TaxonomyError):
            rule_for("VIBE_GAP")

    def test_describe_is_json_ready_and_complete(self) -> None:
        body = describe()
        self.assertEqual(body["types"], list(FAILURE_TYPES))
        self.assertEqual(body["auto_generatable"], list(AUTO_GENERATABLE))
        self.assertEqual(body["human_required"], list(HUMAN_REQUIRED))
        self.assertEqual(len(body["rules"]), len(RULES))
        self.assertTrue(body["meaning"])
        self.assertTrue(body["repair_type"])


class AutoAndHumanTest(unittest.TestCase):
    def test_the_two_sets_are_disjoint(self) -> None:
        self.assertEqual(set(AUTO_GENERATABLE) & set(HUMAN_REQUIRED), set())

    def test_the_two_sets_together_cover_every_type(self) -> None:
        self.assertEqual(
            set(AUTO_GENERATABLE) | set(HUMAN_REQUIRED), set(FAILURE_TYPES)
        )

    def test_the_conflicts_and_unknown_are_never_auto_generatable(self) -> None:
        for name in (TAXONOMY_CONFLICT, ANNOTATION_CONFLICT, UNKNOWN):
            self.assertIn(name, HUMAN_REQUIRED)
            self.assertNotIn(name, AUTO_GENERATABLE)

    def test_attribution_and_stance_need_a_human(self) -> None:
        for name in (ATTRIBUTION_GAP, STANCE_GAP):
            self.assertIn(name, HUMAN_REQUIRED)
            self.assertNotIn(name, AUTO_GENERATABLE)

    def test_the_four_vocabulary_gaps_are_auto_generatable(self) -> None:
        self.assertEqual(
            set(AUTO_GENERATABLE),
            {MORPHOLOGY_GAP, SYNONYM_GAP, FRAME_GAP, LEXICAL_GAP},
        )


class PrecedenceTest(unittest.TestCase):
    """The order the analyzer tests is where the judgement lives."""

    def test_a_third_reading_outranks_a_decision_disagreement(self) -> None:
        failure_type, rule = classify(
            names("annotators_disagreed", "adjudicator_third_reading")
        )
        self.assertEqual(failure_type, TAXONOMY_CONFLICT)
        self.assertIn("adjudicator_third_reading", rule.requires)

    def test_an_unresolved_annotation_outranks_everything(self) -> None:
        failure_type, _ = classify(
            names(
                "annotation_unresolved",
                "adjudicator_third_reading",
                "annotators_disagreed",
                "no_hook_at_all",
            )
        )
        self.assertEqual(failure_type, UNKNOWN)

    def test_an_unresolved_annotation_is_not_the_fallback_unknown(self) -> None:
        _failure_type, rule = classify(names("annotation_unresolved"))
        self.assertEqual(rule, RULES[0])
        self.assertNotEqual(rule, UNEXPLAINED)

    def test_a_decision_disagreement_is_an_annotation_conflict(self) -> None:
        failure_type, _ = classify(names("annotators_disagreed"))
        self.assertEqual(failure_type, ANNOTATION_CONFLICT)

    def test_a_dispute_elsewhere_is_not_an_annotation_conflict(self) -> None:
        failure_type, _ = classify(names("annotators_disagreed_elsewhere"))
        self.assertEqual(failure_type, UNKNOWN)

    def test_attribution_outranks_stance(self) -> None:
        failure_type, _ = classify(
            names("speaker_mismatch", "stance_mismatch", "speaker_match")
        )
        self.assertEqual(failure_type, ATTRIBUTION_GAP)

    def test_a_stance_difference_needs_the_speakers_to_agree(self) -> None:
        failure_type, _ = classify(names("stance_mismatch", "speaker_match"))
        self.assertEqual(failure_type, STANCE_GAP)

    def test_a_stance_difference_without_speaker_agreement_is_unexplained(self) -> None:
        failure_type, rule = classify(names("stance_mismatch"))
        self.assertEqual(failure_type, UNKNOWN)
        self.assertEqual(rule, UNEXPLAINED)

    def test_morphology_outranks_a_frame_gap(self) -> None:
        failure_type, _ = classify(
            names(
                "known_lemma_unmatched_form",
                "hooks_present",
                "no_frame_matched",
                "relation_cue_present",
            )
        )
        self.assertEqual(failure_type, MORPHOLOGY_GAP)

    def test_a_synonym_outranks_a_lexical_gap(self) -> None:
        failure_type, _ = classify(
            names("declared_synonym_present", "no_hook_at_all")
        )
        self.assertEqual(failure_type, SYNONYM_GAP)

    def test_a_frame_gap_outranks_a_lexical_gap(self) -> None:
        failure_type, _ = classify(names("capability_declined", "no_hook_at_all"))
        self.assertEqual(failure_type, FRAME_GAP)

    def test_hooks_and_a_relation_cue_make_a_frame_gap(self) -> None:
        failure_type, rule = classify(
            names("hooks_present", "no_frame_matched", "relation_cue_present")
        )
        self.assertEqual(failure_type, FRAME_GAP)
        self.assertEqual(
            set(rule.requires),
            {"hooks_present", "no_frame_matched", "relation_cue_present"},
        )

    def test_a_hook_without_a_relation_cue_is_a_lexical_gap(self) -> None:
        failure_type, _ = classify(names("hooks_present", "no_relation_cue"))
        self.assertEqual(failure_type, LEXICAL_GAP)

    def test_no_hooks_at_all_is_a_lexical_gap(self) -> None:
        failure_type, _ = classify(names("no_hook_at_all"))
        self.assertEqual(failure_type, LEXICAL_GAP)

    def test_no_evidence_is_an_unexplained_unknown(self) -> None:
        failure_type, rule = classify(())
        self.assertEqual(failure_type, UNKNOWN)
        self.assertEqual(rule, UNEXPLAINED)

    def test_unknown_evidence_is_an_unexplained_unknown(self) -> None:
        failure_type, rule = classify(names("relation_misattributed"))
        self.assertEqual(failure_type, UNKNOWN)
        self.assertEqual(rule, UNEXPLAINED)
        self.assertNotEqual(rule.requires, ("annotation_unresolved",))


class RuleRequiresEvidenceTest(unittest.TestCase):
    """A type can never be returned without the evidence its rule requires."""

    def test_the_returned_rule_only_requires_evidence_that_is_present(self) -> None:
        catalogues = [
            (),
            ("annotators_disagreed",),
            ("adjudicator_third_reading",),
            ("annotation_unresolved",),
            ("speaker_mismatch",),
            ("stance_mismatch", "speaker_match"),
            ("known_lemma_unmatched_form",),
            ("declared_synonym_present",),
            ("hooks_present",),
            ("hooks_present", "no_frame_matched"),
            ("no_hook_at_all",),
            ("capability_declined",),
            ("relation_misattributed", "prediction_outcome"),
        ]
        for catalogue in catalogues:
            with self.subTest(evidence=catalogue):
                present = set(catalogue)
                _failure_type, rule = classify(names(*catalogue))
                if rule is UNEXPLAINED:
                    # The fallback rule's requirement is the *reason* evidence the
                    # caller must add once the taxonomy has admitted it cannot explain
                    # the case; it is by construction absent here.
                    self.assertEqual(_failure_type, UNKNOWN)
                    continue
                self.assertTrue(
                    set(rule.requires) <= present,
                    f"{rule.failure_type} requires {rule.requires} but only {present}",
                )

    def test_a_type_is_never_returned_without_its_required_evidence(self) -> None:
        for rule in RULES:
            with self.subTest(rule=rule.failure_type, requires=rule.requires):
                # Every one of the rule's own requirements, minus one.
                for dropped in rule.requires:
                    catalogue = tuple(
                        name for name in rule.requires if name != dropped
                    )
                    failure_type, fired = classify(names(*catalogue))
                    if failure_type == rule.failure_type:
                        self.assertNotEqual(
                            fired,
                            rule,
                            "a rule fired without one of its requirements",
                        )

    def test_frames_never_fire_on_hooks_alone(self) -> None:
        for catalogue in ((), ("hooks_present",), ("no_frame_matched",)):
            with self.subTest(evidence=catalogue):
                failure_type, _ = classify(names(*catalogue))
                self.assertNotEqual(failure_type, FRAME_GAP)

    def test_synonym_gap_never_fires_without_a_declared_synonym(self) -> None:
        for catalogue in ((), ("no_hook_at_all",), ("hooks_present", "no_relation_cue")):
            with self.subTest(evidence=catalogue):
                failure_type, _ = classify(names(*catalogue))
                self.assertNotEqual(failure_type, SYNONYM_GAP)


class RepairTest(unittest.TestCase):
    def test_each_type_maps_to_its_declared_repair(self) -> None:
        for name in FAILURE_TYPES:
            with self.subTest(failure_type=name):
                built = repair_for(name, risk_category="market_prediction")
                if REPAIR_TYPE[name] == "none":
                    self.assertIsNone(built)
                else:
                    self.assertIsNotNone(built)
                    self.assertEqual(built.type, REPAIR_TYPE[name])
                    self.assertEqual(built.risk_category, "market_prediction")

    def test_unknown_implies_no_repair(self) -> None:
        self.assertIsNone(repair_for(UNKNOWN, risk_category="market_prediction"))

    def test_an_undeclared_type_implies_no_repair(self) -> None:
        self.assertIsNone(repair_for("VIBE_GAP", risk_category="market_prediction"))

    def test_a_repair_carries_its_additions_and_target(self) -> None:
        built = repair_for(
            SYNONYM_GAP,
            risk_category="market_prediction",
            additions=("zoomy",),
            target="axis:movement_direction",
        )
        self.assertEqual(built.additions, ("zoomy",))
        self.assertEqual(built.target, "axis:movement_direction")


class BuildRecordTest(unittest.TestCase):
    def test_build_record_refuses_empty_evidence(self) -> None:
        with self.assertRaises(TaxonomyError) as caught:
            build_record(
                case_id="IND-0001",
                input_text="Returns are assured.",
                expected=(),
                actual=(),
                evidence=(),
            )
        self.assertIn("needs evidence", str(caught.exception))

    def test_build_record_raises_when_the_fired_rule_needs_missing_evidence(
        self,
    ) -> None:
        """The fallback rule requires `no_rule_matched`, and the caller supplied none."""

        with self.assertRaises(TaxonomyError) as caught:
            build_record(
                case_id="IND-0001",
                input_text="Returns are assured.",
                expected=("financial_guarantee",),
                actual=(),
                evidence=(evidence("speaker_match", "inferred"),),
            )
        message = str(caught.exception)
        self.assertIn("UNKNOWN", message)
        self.assertIn("no_rule_matched", message)

    def test_build_record_accepts_the_fallback_evidence(self) -> None:
        record = build_record(
            case_id="IND-0001",
            input_text="Returns are assured.",
            expected=("financial_guarantee",),
            actual=(),
            evidence=(evidence("no_rule_matched", "inferred"),),
        )
        self.assertEqual(record.failure_type, UNKNOWN)
        self.assertEqual(record.required_evidence, ("no_rule_matched",))
        self.assertIsNone(record.repair_candidate)

    def test_build_record_records_the_required_evidence_of_the_fired_rule(self) -> None:
        record = build_record(
            case_id="IND-0002",
            input_text="Turnover will plummet.",
            expected=("market_prediction",),
            actual=(),
            evidence=names("declared_synonym_present"),
        )
        self.assertEqual(record.failure_type, SYNONYM_GAP)
        self.assertEqual(record.required_evidence, ("declared_synonym_present",))
        self.assertEqual(record.confidence, 1.0)

    def test_build_record_defaults_the_risk_category_to_the_expected_one(self) -> None:
        record = build_record(
            case_id="IND-0003",
            input_text="Turnover will plummet.",
            expected=("market_prediction",),
            actual=(),
            evidence=names("declared_synonym_present"),
        )
        self.assertEqual(record.repair_candidate.risk_category, "market_prediction")

    def test_build_record_prefers_an_explicit_risk_category(self) -> None:
        record = build_record(
            case_id="IND-0003",
            input_text="Turnover will plummet.",
            expected=("market_prediction",),
            actual=(),
            evidence=names("declared_synonym_present"),
            risk_category="financial_guarantee",
        )
        self.assertEqual(record.repair_candidate.risk_category, "financial_guarantee")

    def test_build_record_attaches_the_repair_the_type_implies(self) -> None:
        record = build_record(
            case_id="IND-0004",
            input_text="Turnover will plummet.",
            expected=("market_prediction",),
            actual=(),
            evidence=names("known_lemma_unmatched_form"),
            additions=("plummets",),
        )
        self.assertEqual(record.failure_type, MORPHOLOGY_GAP)
        self.assertEqual(record.repair_candidate.type, "morphology_extension")
        self.assertEqual(record.repair_candidate.additions, ("plummets",))

    def test_build_record_carries_the_trace_fields_the_analyzer_supplies(self) -> None:
        record = build_record(
            case_id="IND-0005",
            input_text="Turnover will plummet.",
            expected=("market_prediction",),
            actual=(),
            evidence=names("no_hook_at_all", "no_relation_cue"),
            outcome="false_negative",
            language="en",
            group="market_prediction",
            form="declarative",
        )
        self.assertEqual(record.outcome, "false_negative")
        self.assertEqual(record.language, "en")
        self.assertEqual(record.group, "market_prediction")
        self.assertEqual(record.form, "declarative")


class CountsTest(unittest.TestCase):
    def test_counts_by_type_starts_every_type_at_zero(self) -> None:
        counts = counts_by_type(())
        self.assertEqual(set(counts), set(FAILURE_TYPES))
        self.assertTrue(all(value == 0 for value in counts.values()))

    def test_counts_by_type_counts_the_records(self) -> None:
        counts = counts_by_type(
            [
                failure_record(case_id="IND-1", failure_type=LEXICAL_GAP),
                failure_record(case_id="IND-2", failure_type=LEXICAL_GAP),
                failure_record(case_id="IND-3", failure_type=FRAME_GAP),
            ]
        )
        self.assertEqual(counts[LEXICAL_GAP], 2)
        self.assertEqual(counts[FRAME_GAP], 1)
        self.assertEqual(counts[UNKNOWN], 0)

    def test_a_rule_object_is_hashable(self) -> None:
        self.assertEqual(len({Rule(UNKNOWN, ("a",), "b"), Rule(UNKNOWN, ("a",), "b")}), 1)

    def test_the_module_exports_the_names_the_analyzer_uses(self) -> None:
        for name in ("classify", "build_record", "FAILURE_TYPES", "MEANING"):
            self.assertTrue(hasattr(taxonomy, name), name)
