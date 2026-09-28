"""The freeze, the sampling frame, and the claim that the agents never saw the evaluator."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from risk_evaluation.v3_validation.freeze import VERIFIED_KEYS
from risk_evaluation.v3_independent import build as build_module
from risk_evaluation.v3_independent import frame as frame_module
from risk_evaluation.v3_independent.build import (
    ANNOTATION_PROMPT,
    GENERATION_PROMPT,
    GUIDE_DIGEST,
    ANNOTATION_SEEDS,
    CATEGORIES,
    CERTAINTIES,
    INTENTS,
    SEVERITIES,
    SPEAKERS,
    STANCES,
    BuildError,
    GeneratedCase,
    Annotation,
    _annotation_from,
    annotation_prompt,
    describe as describe_build,
    generation_prompt,
)
from risk_evaluation.v3_independent.frame import (
    BOUNDARY_KINDS,
    CATEGORY_QUOTA,
    FORMS,
    FrameDescriptor,
    FrameError,
    GROUP_BOUNDARY,
    GROUP_RISK_POSITIVE,
    GROUP_SAFE,
    GROUP_SIZES,
    LANGUAGES,
    SOURCE_TYPES,
    TOPICS,
    build_frame,
    load_slots,
    quota_summary,
    write_frame,
)
from risk_evaluation.v3_independent.freeze import (
    FREEZE_PATH,
    FREEZE_SCHEMA_VERSION,
    FROZEN_PATHS,
    FreezeError,
    build_freeze_v3_2,
    describe as describe_freeze,
    frozen_source_digests,
    guard,
    load_freeze_v3_2,
    verify_freeze_v3_2,
    write_freeze_v3_2,
)


class FreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frozen = load_freeze_v3_2()

    def test_the_freeze_exists_and_is_the_declared_version(self) -> None:
        self.assertTrue(FREEZE_PATH.is_file())
        self.assertEqual(
            self.frozen["freeze_schema_version"], FREEZE_SCHEMA_VERSION
        )
        self.assertEqual(self.frozen["freeze_kind"], "independent-validation")

    def test_the_freeze_carries_all_five_components(self) -> None:
        for key in VERIFIED_KEYS:
            self.assertIn(key, self.frozen, key)
            self.assertEqual(len(self.frozen[key]), 64, key)

    def test_the_freeze_matches_the_tree(self) -> None:
        result = verify_freeze_v3_2()
        self.assertTrue(result.matches, result.render())
        self.assertEqual(result.moved_sources, ())

    def test_the_guard_does_not_raise(self) -> None:
        guard()

    def test_every_frozen_source_is_recorded(self) -> None:
        digests = frozen_source_digests()
        self.assertTrue(digests)
        self.assertEqual(len(digests), self.frozen["frozen_source_count"])
        for path, digest in digests.items():
            self.assertEqual(len(digest), 64, path)
            self.assertTrue(path.endswith(".py"), path)

    def test_the_frozen_paths_cover_the_evaluator_and_the_taxonomy(self) -> None:
        for required in (
            "risk_evaluation/v3",
            "risk_evaluation/v3_1",
            "risk_evaluation/taxonomy.py",
            "risk_evaluation/taxonomy_v2.py",
        ):
            self.assertIn(required, FROZEN_PATHS)

    def test_a_tampered_component_is_detected(self) -> None:
        tampered = dict(self.frozen)
        tampered["evaluator_hash"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "f.json"
            target.write_text(json.dumps(tampered), encoding="utf-8")
            result = verify_freeze_v3_2(target)

        self.assertFalse(result.matches)
        self.assertIn("evaluator_hash", result.mismatches)

    def test_a_moved_source_is_detected(self) -> None:
        tampered = dict(self.frozen)
        recorded = dict(tampered["frozen_sources"])
        first = sorted(recorded)[0]
        recorded[first] = "0" * 64
        tampered["frozen_sources"] = recorded
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "f.json"
            target.write_text(json.dumps(tampered), encoding="utf-8")
            result = verify_freeze_v3_2(target)

        self.assertFalse(result.matches)
        self.assertIn(first, result.moved_sources)

    def test_a_removed_source_is_detected(self) -> None:
        tampered = dict(self.frozen)
        recorded = dict(tampered["frozen_sources"])
        removed = sorted(recorded)[0]
        del recorded[removed]
        tampered["frozen_sources"] = recorded
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "f.json"
            target.write_text(json.dumps(tampered), encoding="utf-8")
            result = verify_freeze_v3_2(target)

        self.assertFalse(result.matches)
        self.assertTrue(any(removed in item for item in result.moved_sources))

    def test_the_guard_raises_on_a_moved_source(self) -> None:
        tampered = dict(self.frozen)
        recorded = dict(tampered["frozen_sources"])
        recorded[sorted(recorded)[0]] = "0" * 64
        tampered["frozen_sources"] = recorded
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "f.json"
            target.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaises(FreezeError):
                guard(target)

    def test_a_missing_freeze_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FreezeError):
                load_freeze_v3_2(Path(directory) / "nope.json")

    def test_the_freeze_declares_its_invariants(self) -> None:
        invariants = self.frozen["invariants"]
        self.assertTrue(invariants["evaluator_frozen_during_run"])
        self.assertTrue(invariants["repairs_require_a_proposal"])

    def test_the_freeze_names_what_it_supersedes(self) -> None:
        self.assertEqual(
            set(self.frozen["supersedes"]), {"phase_8_6", "phase_8_7", "phase_8_8"}
        )

    def test_building_twice_gives_the_same_hashes(self) -> None:
        first = {k: v for k, v in build_freeze_v3_2().items() if k != "timestamp"}
        second = {k: v for k, v in build_freeze_v3_2().items() if k != "timestamp"}
        self.assertEqual(first, second)

    def test_writing_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "f.json"
            write_freeze_v3_2(target)
            first = json.loads(target.read_text(encoding="utf-8"))
            write_freeze_v3_2(target)
            second = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(first["frozen_sources"], second["frozen_sources"])

    def test_the_freeze_describes_itself(self) -> None:
        described = describe_freeze()
        self.assertIn("frozen_paths", described)
        self.assertGreater(described["frozen_source_count"], 10)

    def test_the_freeze_is_json_serializable(self) -> None:
        json.dumps(self.frozen, sort_keys=True)


class FrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.slots = build_frame()

    def test_the_frame_has_three_hundred_slots(self) -> None:
        self.assertEqual(len(self.slots), 300)

    def test_the_group_sizes_are_the_required_ones(self) -> None:
        summary = quota_summary()
        self.assertEqual(
            summary["group"],
            {GROUP_BOUNDARY: 75, GROUP_RISK_POSITIVE: 150, GROUP_SAFE: 75},
        )
        self.assertEqual(sum(GROUP_SIZES.values()), 300)

    def test_every_category_has_thirty_slots(self) -> None:
        summary = quota_summary()
        self.assertEqual(len(summary["category"]), 5)
        for name, count in summary["category"].items():
            self.assertEqual(count, 30, name)
        self.assertEqual(sum(CATEGORY_QUOTA.values()), 150)

    def test_the_languages_are_balanced(self) -> None:
        summary = quota_summary()
        self.assertEqual(summary["language"], {"en": 150, "zh": 150})

    def test_every_boundary_kind_appears_five_times(self) -> None:
        summary = quota_summary()
        self.assertEqual(len(summary["boundary_kind"]), len(BOUNDARY_KINDS))
        for name, count in summary["boundary_kind"].items():
            self.assertEqual(count, 5, name)

    def test_the_frame_uses_every_declared_dimension_value(self) -> None:
        summary = quota_summary()
        for name in SOURCE_TYPES:
            self.assertGreater(summary["source_type"][name], 0, name)
        for name in FORMS:
            self.assertGreater(summary["form"][name], 0, name)

    def test_case_ids_are_unique_and_ordered(self) -> None:
        ids = [item.case_id for item in self.slots]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[0], "IND-0001")
        self.assertEqual(ids[-1], "IND-0300")

    def test_ids_are_zero_padded_to_four_digits(self) -> None:
        for item in self.slots:
            self.assertEqual(len(item.case_id), 8, item.case_id)
            self.assertTrue(item.case_id.startswith("IND-"), item.case_id)

    def test_the_frame_is_reproducible(self) -> None:
        again = build_frame()
        self.assertEqual(
            [item.as_dict() for item in again],
            [item.as_dict() for item in self.slots],
        )

    def test_risk_positive_slots_carry_an_intent_and_safe_ones_do_not(self) -> None:
        for item in self.slots:
            if item.group == GROUP_RISK_POSITIVE:
                self.assertTrue(item.intent, item.case_id)
            else:
                self.assertEqual(item.intent, "", item.case_id)

    def test_only_boundary_slots_carry_a_boundary_kind(self) -> None:
        for item in self.slots:
            if item.group == GROUP_BOUNDARY:
                self.assertTrue(item.boundary_kind, item.case_id)
                self.assertTrue(item.boundary_basis, item.case_id)
            else:
                self.assertEqual(item.boundary_kind, "", item.case_id)

    def test_a_risk_positive_slot_without_an_intent_is_rejected(self) -> None:
        with self.assertRaises(FrameError):
            FrameDescriptor(
                case_id="X-1",
                order=0,
                group=GROUP_RISK_POSITIVE,
                source_type=SOURCE_TYPES[0],
                language="en",
                form=FORMS[0],
                topic=TOPICS[0],
            )

    def test_a_safe_slot_with_an_intent_is_rejected(self) -> None:
        with self.assertRaises(FrameError):
            FrameDescriptor(
                case_id="X-2",
                order=0,
                group=GROUP_SAFE,
                source_type=SOURCE_TYPES[0],
                language="en",
                form=FORMS[0],
                topic=TOPICS[0],
                intent="investment_advice",
            )

    def test_a_boundary_slot_without_a_kind_is_rejected(self) -> None:
        with self.assertRaises(FrameError):
            FrameDescriptor(
                case_id="X-3",
                order=0,
                group=GROUP_BOUNDARY,
                source_type=SOURCE_TYPES[0],
                language="en",
                form=FORMS[0],
                topic=TOPICS[0],
            )

    def test_an_unknown_dimension_value_is_rejected(self) -> None:
        with self.assertRaises(FrameError):
            FrameDescriptor(
                case_id="X-4",
                order=0,
                group=GROUP_SAFE,
                source_type="not_a_register",
                language="en",
                form=FORMS[0],
                topic=TOPICS[0],
            )

    def test_the_frame_file_matches_the_builder(self) -> None:
        loaded = load_slots()
        self.assertEqual(len(loaded), 300)
        self.assertEqual(
            [item.as_dict() for item in loaded],
            [item.as_dict() for item in self.slots],
        )

    def test_writing_the_frame_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "f.json"
            write_frame(target)
            first = target.read_text(encoding="utf-8")
            write_frame(target)
            self.assertEqual(first, target.read_text(encoding="utf-8"))

    def test_every_boundary_kind_cites_the_guide(self) -> None:
        for name, meaning, basis in BOUNDARY_KINDS:
            self.assertTrue(meaning)
            self.assertIn("guide", basis.lower(), name)

    def test_the_frame_declares_no_evaluator_vocabulary(self) -> None:
        """The frame names categories and syntactic shapes, nothing internal."""

        payload = json.dumps(frame_module.frame_payload(), ensure_ascii=False)
        for term in EVALUATOR_TERMS:
            self.assertNotIn(term, payload, term)


#: Terms that exist only inside the evaluator. Neither the frame nor any prompt an
#: agent receives may contain one: that is what "the text authors never saw the
#: evaluator" has to mean to be checkable.
EVALUATOR_TERMS: tuple[str, ...] = (
    "IntentPattern",
    "PatternSet",
    "RelationMatcher",
    "EntityLexicon",
    "semantic_evaluator",
    "taxonomy_v2",
    "MOVEMENT_LEMMAS",
    "MOVEMENT_VERBS",
    "RELATION_CATEGORY",
    "RELATION_REQUIRED",
    "negation_scope",
    "HEDGE_MARKERS",
    "REPORTING_VERBS",
    "ADVISORY_FRAMES",
    "non_directional",
    "weak_prediction",
    "D1-negated-intent",
    "D8-semantic-fallback",
    "signal:",
    "capability:",
    "v3_repair",
    "v3_validation",
)

#: Package paths. These must not appear in the *frame*, because the frame is data an
#: agent reads, but the prompts have to name `risk_evaluation/` in order to forbid
#: reading it, so they are checked separately.
PACKAGE_TERMS: tuple[str, ...] = ("risk_evaluation", "v3_1", "v3_repair", "v3_validation")


def flat(text: str) -> str:
    """Lowercased with runs of whitespace collapsed, for substring checks."""

    return " ".join(text.lower().split())


class IndependenceTests(unittest.TestCase):
    """What the agents were given, and what they were not."""

    def test_the_generation_prompt_contains_no_evaluator_vocabulary(self) -> None:
        for term in EVALUATOR_TERMS:
            self.assertNotIn(term, GENERATION_PROMPT, term)

    def test_the_annotation_prompt_contains_no_evaluator_vocabulary(self) -> None:
        for term in EVALUATOR_TERMS:
            self.assertNotIn(term, ANNOTATION_PROMPT, term)

    def test_the_guide_digest_contains_no_evaluator_vocabulary(self) -> None:
        for term in EVALUATOR_TERMS:
            self.assertNotIn(term, GUIDE_DIGEST, term)

    def test_the_prompts_forbid_reading_the_evaluator(self) -> None:
        for prompt in (GENERATION_PROMPT, ANNOTATION_PROMPT):
            self.assertIn("do not read anything under risk_evaluation/", flat(prompt))

    def test_the_annotation_prompt_forbids_reading_other_labels(self) -> None:
        self.assertIn(
            "do not read any labels written by anyone else", flat(ANNOTATION_PROMPT)
        )

    def test_the_prompts_name_the_package_only_to_forbid_it(self) -> None:
        """A path in a prohibition is not leaked vocabulary, and this pins that."""

        for prompt in (GENERATION_PROMPT, ANNOTATION_PROMPT):
            for term in PACKAGE_TERMS:
                if term not in prompt:
                    continue
                self.assertIn(
                    f"do not read anything under {term}",
                    flat(prompt),
                    f"{term} appears outside the prohibition",
                )

    def test_the_frame_names_no_package_path_at_all(self) -> None:
        payload = json.dumps(frame_module.frame_payload(), ensure_ascii=False)
        for term in PACKAGE_TERMS:
            self.assertNotIn(term, payload, term)

    def test_the_rendered_prompts_carry_their_paths(self) -> None:
        prompt = generation_prompt(Path("slots.json"), Path("out.json"))
        self.assertIn("slots.json", prompt)
        self.assertIn("out.json", prompt)
        prompt = annotation_prompt(Path("cases.json"), Path("labels.json"))
        self.assertIn("cases.json", prompt)
        self.assertIn("labels.json", prompt)

    def test_the_two_annotators_do_not_share_a_shuffle_seed(self) -> None:
        self.assertEqual(len(set(ANNOTATION_SEEDS.values())), len(ANNOTATION_SEEDS))

    def test_the_prompts_name_every_allowed_value(self) -> None:
        for value in (*SPEAKERS, *STANCES, *INTENTS, *CERTAINTIES, *SEVERITIES):
            self.assertIn(value, ANNOTATION_PROMPT, value)
        for name in CATEGORIES:
            self.assertIn(name, ANNOTATION_PROMPT, name)

    def test_the_build_describes_itself(self) -> None:
        described = describe_build()
        self.assertEqual(described["annotators"], ["A", "B"])
        self.assertEqual(len(described["label_fields"]), 5)


class AnnotationSchemaTests(unittest.TestCase):
    def _item(self, **overrides) -> dict:
        base = {
            "id": "IND-0001",
            "claim": "text",
            "speaker": "author",
            "stance": "endorsed",
            "intent": "PREDICTION",
            "certainty": "certain",
            "severity": "warning",
            "decision": ["market_prediction"],
            "reason": "guide 2",
        }
        base.update(overrides)
        return base

    def test_a_valid_item_parses(self) -> None:
        found = _annotation_from(self._item(), "A")
        self.assertEqual(found.case_id, "IND-0001")
        self.assertEqual(found.decision, ("market_prediction",))
        self.assertEqual(found.annotator, "A")

    def test_an_unknown_value_is_rejected(self) -> None:
        for field, value in (
            ("speaker", "nobody"),
            ("stance", "shrugged"),
            ("intent", "VIBES"),
            ("certainty", "fairly"),
            ("severity", "critical"),
        ):
            with self.assertRaises(BuildError, msg=field):
                _annotation_from(self._item(**{field: value}), "A")

    def test_an_unknown_category_is_rejected(self) -> None:
        with self.assertRaises(BuildError):
            _annotation_from(self._item(decision=["market_prediction", "vibes"]), "A")

    def test_a_non_list_decision_is_rejected(self) -> None:
        with self.assertRaises(BuildError):
            _annotation_from(self._item(decision="market_prediction"), "A")

    def test_a_missing_reason_is_rejected(self) -> None:
        with self.assertRaises(BuildError):
            _annotation_from(self._item(reason="  "), "A")

    def test_a_missing_id_is_rejected(self) -> None:
        with self.assertRaises(BuildError):
            _annotation_from(self._item(id=""), "A")

    def test_duplicate_categories_are_collapsed(self) -> None:
        found = _annotation_from(
            self._item(decision=["market_prediction", "market_prediction"]), "A"
        )
        self.assertEqual(found.decision, ("market_prediction",))

    def test_an_empty_decision_is_allowed(self) -> None:
        found = _annotation_from(
            self._item(decision=[], severity="none", intent="NONE", certainty="n/a"), "A"
        )
        self.assertEqual(found.decision, ())

    def test_the_field_accessor_is_stable(self) -> None:
        found = _annotation_from(self._item(), "A")
        self.assertEqual(found.field("speaker"), "author")
        self.assertEqual(found.field("decision"), "market_prediction")

    def test_an_annotation_serialises(self) -> None:
        payload = _annotation_from(self._item(), "A").as_dict()
        self.assertEqual(payload["annotator"], "A")
        self.assertEqual(payload["decision"], ["market_prediction"])

    def test_an_annotation_can_be_built_directly(self) -> None:
        found = Annotation(
            case_id="IND-0002",
            claim="none",
            speaker="unknown",
            stance="uncertain",
            intent="NONE",
            certainty="n/a",
            severity="none",
            decision=(),
            reason="guide 4",
        )
        self.assertEqual(found.field("decision"), "")


class GeneratedCaseTests(unittest.TestCase):
    def test_a_generated_case_exposes_its_slot_dimensions(self) -> None:
        case = GeneratedCase(
            case_id="IND-0001",
            text="text",
            slot={
                "group": GROUP_SAFE,
                "language": "zh",
                "source_type": "news_report",
                "form": "nominal",
            },
        )
        self.assertEqual(case.language, "zh")
        self.assertEqual(case.group, GROUP_SAFE)
        self.assertEqual(case.source_type, "news_report")
        self.assertEqual(case.form, "nominal")

    def test_a_generated_case_serialises(self) -> None:
        case = GeneratedCase("IND-0001", "text", {"group": GROUP_SAFE})
        payload = case.as_dict()
        self.assertEqual(payload["id"], "IND-0001")
        self.assertIn("slot", payload)


class LanguageCoverageTests(unittest.TestCase):
    """The frame declares two languages, and both actually occur."""

    def test_the_language_list_is_en_and_zh(self) -> None:
        self.assertEqual(LANGUAGES, ("en", "zh"))

    def test_every_source_type_has_a_declared_meaning(self) -> None:
        from risk_evaluation.v3_independent.frame import SOURCE_TYPE_MEANING

        self.assertEqual(set(SOURCE_TYPE_MEANING), set(SOURCE_TYPES))

    def test_every_form_has_a_declared_meaning(self) -> None:
        from risk_evaluation.v3_independent.frame import FORM_MEANING

        self.assertEqual(set(FORM_MEANING), set(FORMS))

    def test_the_phase_named_source_types_are_present(self) -> None:
        for name in ("news_report", "analyst_note", "forum_post", "educational_article"):
            self.assertIn(name, SOURCE_TYPES)

    def test_the_topics_are_ten_distinct_subjects(self) -> None:
        self.assertEqual(len(TOPICS), 10)
        self.assertEqual(len(set(TOPICS)), 10)


if __name__ == "__main__":
    unittest.main()
