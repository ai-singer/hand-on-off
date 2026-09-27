"""The experiment dataset: shape, composition, and the Phase 8.1 replay set."""

from __future__ import annotations

import json
import unittest

from risk_evaluation.attribution_experiment.cases import (
    ATTRIBUTION_GROUPS,
    AUTHOR_REJECTION,
    AUTHOR_RISK,
    DATASET_PATH,
    DATASET_VERSION,
    EXPERIMENT_CASES,
    GROUP_NAMES,
    MIXED_CLAIM,
    NO_RISK_EDUCATION,
    REPLAY_CASES,
    REQUIRED_GROUP_SIZES,
    THIRD_PARTY_CITATION,
    ExperimentCase,
    case_index,
    dataset_payload,
    group_cases,
    group_sizes,
    write_dataset,
)
from risk_evaluation.taxonomy import RISK_TAXONOMY


class DatasetShapeTests(unittest.TestCase):
    def test_the_dataset_has_at_least_sixty_cases(self) -> None:
        self.assertGreaterEqual(len(EXPERIMENT_CASES), 60)

    def test_every_group_meets_its_required_size(self) -> None:
        sizes = group_sizes()

        for group, required in REQUIRED_GROUP_SIZES.items():
            self.assertGreaterEqual(sizes[group], required, group)

    def test_the_group_sizes_are_exactly_as_specified(self) -> None:
        self.assertEqual(
            group_sizes(),
            {
                AUTHOR_RISK: 15,
                THIRD_PARTY_CITATION: 10,
                AUTHOR_REJECTION: 10,
                MIXED_CLAIM: 10,
                NO_RISK_EDUCATION: 15,
            },
        )

    def test_case_ids_are_unique(self) -> None:
        ids = [case.case_id for case in EXPERIMENT_CASES]

        self.assertEqual(len(ids), len(set(ids)))

    def test_every_group_name_is_declared(self) -> None:
        self.assertEqual(set(GROUP_NAMES), set(REQUIRED_GROUP_SIZES))

    def test_group_lookup_returns_the_whole_group(self) -> None:
        for group, size in REQUIRED_GROUP_SIZES.items():
            self.assertEqual(len(group_cases(group)), size, group)

    def test_case_index_maps_every_id(self) -> None:
        self.assertEqual(len(case_index()), len(EXPERIMENT_CASES))

    def test_every_case_records_a_note(self) -> None:
        for case in EXPERIMENT_CASES:
            self.assertTrue(case.note.strip(), case.case_id)


class DatasetValidationTests(unittest.TestCase):
    def test_an_unknown_group_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ExperimentCase("X-1", "Z", "text", ())

    def test_empty_text_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ExperimentCase("X-1", AUTHOR_RISK, "  ", ())

    def test_an_unknown_expected_category_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ExperimentCase("X-1", AUTHOR_RISK, "text", ("not_a_category",))

    def test_every_expected_category_is_a_taxonomy_category(self) -> None:
        known = {entry.name for entry in RISK_TAXONOMY}
        for case in EXPERIMENT_CASES:
            for name in case.expected_categories:
                self.assertIn(name, known, case.case_id)

    def test_the_group_sets_the_attribution_flag(self) -> None:
        for case in EXPERIMENT_CASES:
            self.assertEqual(
                case.is_attribution_case, case.group in ATTRIBUTION_GROUPS
            )

    def test_expects_risk_matches_the_expected_categories(self) -> None:
        for case in EXPERIMENT_CASES:
            self.assertEqual(case.expects_risk, bool(case.expected_categories))


class GroupSemanticsTests(unittest.TestCase):
    """Each group's expectations follow the guide, checked as a property."""

    def test_group_a_expects_risk_everywhere(self) -> None:
        for case in group_cases(AUTHOR_RISK):
            self.assertTrue(case.expects_risk, case.case_id)

    def test_group_b_expects_no_author_voice_category(self) -> None:
        """A borrowed claim is not the article's, so no author-voice category."""

        author_voice = {"investment_advice", "market_prediction", "financial_guarantee", "emotional_manipulation"}
        for case in group_cases(THIRD_PARTY_CITATION):
            self.assertEqual(set(case.expected_categories) & author_voice, set(), case.case_id)

    def test_group_c_never_expects_an_author_voice_category(self) -> None:
        """A rejected claim is not the article's, so no author-voice category.

        One case does expect `unverified_information`: rejecting a claim does not
        make its uncheckable source checkable, and `taxonomy_v2` reports that
        category whatever the voice.
        """

        author_voice = {
            "investment_advice",
            "market_prediction",
            "financial_guarantee",
            "emotional_manipulation",
        }
        for case in group_cases(AUTHOR_REJECTION):
            self.assertEqual(set(case.expected_categories) & author_voice, set(), case.case_id)

    def test_group_c_keeps_the_agnostic_category_where_it_applies(self) -> None:
        case = case_index()["C-04"]

        self.assertEqual(case.expected_categories, ("unverified_information",))

    def test_group_d_expects_the_authors_category(self) -> None:
        for case in group_cases(MIXED_CLAIM):
            self.assertTrue(case.expects_risk, case.case_id)

    def test_group_e_never_expects_risk(self) -> None:
        for case in group_cases(NO_RISK_EDUCATION):
            self.assertFalse(case.expects_risk, case.case_id)

    def test_group_d_cases_carry_two_sentences(self) -> None:
        """The defect needs a borrowed attribution and the author's own claim."""

        for case in group_cases(MIXED_CLAIM):
            self.assertGreaterEqual(case.text.count("."), 2, case.case_id)


class ReplaySetTests(unittest.TestCase):
    def test_the_replay_set_meets_the_minimum(self) -> None:
        self.assertGreaterEqual(len(REPLAY_CASES), 10)

    def test_the_replay_set_includes_the_phase_8_1_family(self) -> None:
        origins = {case.origin for case in REPLAY_CASES}

        self.assertIn("phase-8.1", origins)

    def test_the_replay_set_carries_the_three_recorded_failures(self) -> None:
        texts = {case.text for case in REPLAY_CASES}

        for failure in (
            "Analysts say the sector is volatile this year. Buy this stock before the quarter ends.",
            "Economists forecast slower growth in Europe. This fund cannot lose money.",
            "Regulators published the revised disclosure rules. Do not miss this opportunity.",
        ):
            self.assertIn(failure, texts)

    def test_the_replay_set_carries_the_phase_8_1_controls(self) -> None:
        ids = {case.case_id for case in REPLAY_CASES}

        self.assertTrue({"CTL-01", "CTL-02", "CTL-03", "CTL-04"} <= ids)

    def test_fresh_replay_cases_are_marked_as_such(self) -> None:
        """Three cases were authored here to reach the minimum of ten."""

        fresh = [case for case in REPLAY_CASES if case.origin == "phase-8.3"]

        self.assertEqual(len(fresh), 3)

    def test_replay_ids_are_unique(self) -> None:
        ids = [case.case_id for case in REPLAY_CASES]

        self.assertEqual(len(ids), len(set(ids)))


class DatasetArtifactTests(unittest.TestCase):
    def test_the_dataset_file_exists(self) -> None:
        self.assertTrue(DATASET_PATH.is_file())

    def test_the_version_is_recorded(self) -> None:
        self.assertEqual(DATASET_VERSION, "v1")
        self.assertEqual(dataset_payload()["version"], "v1")

    def test_the_payload_is_json_serializable(self) -> None:
        json.dumps(dataset_payload(), sort_keys=True)

    def test_the_file_matches_the_payload(self) -> None:
        on_disk = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

        self.assertEqual(on_disk["case_count"], len(EXPERIMENT_CASES))
        self.assertEqual(len(on_disk["cases"]), len(EXPERIMENT_CASES))
        self.assertEqual(len(on_disk["replay_cases"]), len(REPLAY_CASES))

    def test_the_file_records_the_required_sizes(self) -> None:
        on_disk = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

        self.assertEqual(
            on_disk["required_group_sizes"], dict(REQUIRED_GROUP_SIZES)
        )

    def test_writing_is_reproducible(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "dataset.json"
            write_dataset(target)
            first = target.read_text(encoding="utf-8")
            write_dataset(target)

            self.assertEqual(first, target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
