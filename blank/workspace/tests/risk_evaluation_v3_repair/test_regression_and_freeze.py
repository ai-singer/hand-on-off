"""Steps 6 and 7: the regression suite and the new freeze version.

The two tests that matter most here are the negative ones: that the regression
reports `broken` at all, and that the freeze records the Phase 8.6 benchmark hash
unchanged. A suite that could only report improvements and a freeze that could not
tell whether the labels had moved would both pass while proving nothing.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from risk_evaluation.v3_validation.freeze import VERIFIED_KEYS, load_freeze
from risk_evaluation.v3_repair.freeze import (
    FREEZE_KIND,
    FREEZE_PATH,
    FREEZE_SCHEMA_VERSION,
    REPAIRS,
    REPAIR_MODULES,
    RepairFreezeError,
    build_repair_freeze,
    load_repair_freeze,
    repair_hash,
    repair_hashes,
    table_hash,
    verify_repair_freeze,
    write_repair_freeze,
)
from risk_evaluation.v3_repair.freeze import PHASE_86_FREEZE_PATH
from risk_evaluation.v3_repair.regression import (
    BASELINE_PATH,
    BROKEN,
    FIXED,
    REPORT_PATH,
    SET_NAMES,
    STILL_WRONG,
    TRANSITIONS,
    UNCHANGED,
    RegressionError,
    baseline_provenance,
    build_regression,
    load_baseline,
    run,
    summarise,
    write_report,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


class RegressionShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = build_regression()

    def test_all_five_sets_are_covered(self) -> None:
        self.assertEqual(
            tuple(item.set_name for item in self.report.summaries), SET_NAMES
        )

    def test_the_set_sizes_are_the_published_ones(self) -> None:
        sizes = {item.set_name: item.cases for item in self.report.summaries}

        self.assertEqual(
            sizes,
            {
                "phase_8.1": 15,
                "phase_8.3": 9,
                "phase_8.4": 17,
                "phase_8.5": 60,
                "phase_8.6_independent_v2": 99,
            },
        )

    def test_every_case_carries_a_pre_repair_result(self) -> None:
        """Without it, `fixed` and `broken` would be measured against v2."""

        for item in self.report.records:
            self.assertIsNotNone(item.pre_repair, (item.set_name, item.case_id))

    def test_no_case_was_broken(self) -> None:
        """The phase's requirement, as an assertion rather than a printed line."""

        self.assertEqual(
            [item.case_id for item in self.report.broken],
            [],
            [item.as_dict() for item in self.report.broken],
        )

    def test_the_regression_reports_breakage_when_there_is_breakage(self) -> None:
        """The suite must be able to fail. Checked by handing it a false before."""

        baseline = load_baseline()
        broken_baseline = {
            name: [dict(item) for item in items] for name, items in baseline.items()
        }
        # Claim v3 got every Phase 8.6 case right before the repair. It did not,
        # so every case v3 now gets wrong must come back as `broken`.
        for item in broken_baseline["phase_8.6_independent_v2"]:
            item["v3"] = list(item["expected"])

        report = build_regression(baseline=broken_baseline)

        self.assertTrue(report.broken)
        self.assertTrue(all(item.transition == BROKEN for item in report.broken))

    def test_every_transition_is_a_declared_value(self) -> None:
        for item in self.report.records:
            self.assertIn(item.transition, TRANSITIONS)

    def test_fixed_is_not_empty_on_the_two_sets_that_moved(self) -> None:
        """A regression that reported no fixes would not be reporting the repair."""

        self.assertEqual(
            self.report.summary_for("phase_8.6_independent_v2").fixed,
            (
                "IV-014",
                "IV-032",
                "IV-033",
                "IV-035",
                "IV-046",
                "IV-051",
                "IV-055",
                "IV-062",
                "IV-071",
                "IV-075",
                "IV-088",
                "IV-096",
            ),
        )
        self.assertEqual(
            self.report.summary_for("phase_8.5").fixed, ("TQ-04", "TQ-06", "TQ-07")
        )

    def test_the_replay_sets_did_not_move(self) -> None:
        """Phase 8.1, 8.3 and 8.4 are the historically frozen sets."""

        for name in ("phase_8.1", "phase_8.3", "phase_8.4"):
            summary = self.report.summary_for(name)
            self.assertEqual(summary.delta_vs_pre_repair, 0, name)
            self.assertEqual(summary.fixed, (), name)
            self.assertEqual(summary.broken, (), name)

    def test_the_phase_8_6_set_gained_twelve_cases(self) -> None:
        summary = self.report.summary_for("phase_8.6_independent_v2")

        self.assertEqual(
            (summary.pre_repair_correct, summary.v3_correct), (84, 96)
        )

    def test_still_wrong_is_reported_separately_from_unchanged(self) -> None:
        """A defect that survived is not the same finding as a case always right."""

        summary = self.report.summary_for("phase_8.1")
        correct_always = [
            item
            for item in self.report.records
            if item.set_name == "phase_8.1"
            and item.transition == UNCHANGED
        ]

        self.assertEqual(summary.still_wrong, tuple(
            item.case_id
            for item in self.report.records
            if item.set_name == "phase_8.1" and item.transition == STILL_WRONG
        ))
        self.assertTrue(summary.still_wrong)
        self.assertFalse(
            set(summary.still_wrong) & {item.case_id for item in correct_always}
        )

    def test_the_summaries_are_reproducible(self) -> None:
        again = build_regression()

        self.assertEqual(again.as_dict(), self.report.as_dict())

    def test_the_report_is_json_serializable(self) -> None:
        json.dumps(self.report.as_dict(), sort_keys=True)

    def test_the_report_names_where_the_labels_came_from(self) -> None:
        self.assertIn("pre-Phase-8.7", self.report.as_dict()["note"])

    def test_the_baseline_records_its_own_provenance(self) -> None:
        provenance = baseline_provenance()

        self.assertIn("a6d065d", provenance["taken_on"])
        self.assertIn("unmodified", provenance["taken_on"])
        self.assertEqual(provenance["kind"], "pre-repair measurement")
        self.assertEqual(
            provenance["sets"],
            {
                "phase_8.1": 15,
                "phase_8.3": 9,
                "phase_8.4": 17,
                "phase_8.5": 60,
                "phase_8.6_independent_v2": 99,
            },
        )

    def test_a_missing_baseline_is_reported(self) -> None:
        with self.assertRaises(RegressionError):
            load_baseline(Path("/no/such/baseline.json"))

    def test_the_artifact_is_written_and_matches_a_fresh_run(self) -> None:
        self.assertTrue(REPORT_PATH.is_file())
        payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(payload["broken_count"], 0)
        self.assertEqual(payload["v3_correct"], self.report.v3_correct)
        self.assertEqual(
            [item["set_name"] for item in payload["sets"]], list(SET_NAMES)
        )

    def test_writing_is_reproducible(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "r.json"
            write_report(target, report=self.report)
            first = target.read_text(encoding="utf-8")
            write_report(target, report=self.report)

            self.assertEqual(first, target.read_text(encoding="utf-8"))

    def test_the_runner_and_the_summariser_agree(self) -> None:
        records = run()

        self.assertEqual(summarise(records), self.report.summaries)


class RepairFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frozen = load_repair_freeze()

    def test_the_new_freeze_exists_and_the_old_one_is_untouched(self) -> None:
        self.assertTrue(FREEZE_PATH.is_file())
        self.assertTrue(PHASE_86_FREEZE_PATH.is_file())

    def test_it_is_a_new_version_and_not_an_overwrite(self) -> None:
        phase_86 = load_freeze(PHASE_86_FREEZE_PATH)

        self.assertEqual(self.frozen["freeze_schema_version"], FREEZE_SCHEMA_VERSION)
        self.assertEqual(phase_86["freeze_schema_version"], "3.0.0")
        self.assertEqual(self.frozen["freeze_kind"], FREEZE_KIND)
        self.assertEqual(
            self.frozen["supersedes"]["evaluator_hash"], phase_86["evaluator_hash"]
        )

    def test_the_freeze_matches_the_tree(self) -> None:
        result = verify_repair_freeze()

        self.assertTrue(result.matches, result.render())
        self.assertEqual(result.mismatches, ())

    def test_the_phase_8_6_labels_were_not_touched(self) -> None:
        """The phase forbids changing the expected results. This checks it."""

        result = verify_repair_freeze()
        phase_86 = load_freeze(PHASE_86_FREEZE_PATH)

        self.assertTrue(result.labels_unchanged)
        self.assertEqual(self.frozen["benchmark_hash"], phase_86["benchmark_hash"])
        self.assertEqual(self.frozen["case_count"], phase_86["case_count"])
        self.assertEqual(self.frozen["benchmark"], phase_86["benchmark"])

    def test_the_decision_policy_is_unchanged_by_the_repair(self) -> None:
        """No rule was added, removed or reworded, and no category remapped."""

        phase_86 = load_freeze(PHASE_86_FREEZE_PATH)

        self.assertEqual(
            self.frozen["decision_policy_hash"], phase_86["decision_policy_hash"]
        )

    def test_only_the_evaluator_moved_between_the_two_freezes(self) -> None:
        phase_86 = load_freeze(PHASE_86_FREEZE_PATH)
        moved = [
            key for key in VERIFIED_KEYS if self.frozen[key] != phase_86[key]
        ]

        self.assertEqual(moved, ["evaluator_hash"])

    def test_every_repair_layer_is_frozen(self) -> None:
        self.assertEqual(set(self.frozen["repair_hashes"]), set(REPAIR_MODULES))
        for name, digest in self.frozen["repair_hashes"].items():
            self.assertEqual(len(digest), 64, name)
            int(digest, 16)

    def test_a_repair_layer_that_changes_moves_its_hash(self) -> None:
        """The hashes are over source bytes, so the check is not a formality."""

        self.assertEqual(self.frozen["repair_hashes"], repair_hashes())
        self.assertEqual(repair_hash("risk_evaluation.v3.morphology"), repair_hashes()["morphology"])

    def test_the_declared_tables_are_frozen_too(self) -> None:
        self.assertEqual(self.frozen["repair_table_hash"], table_hash())

    def test_the_repairs_are_named(self) -> None:
        self.assertEqual(len(REPAIRS), 3)
        self.assertEqual(
            set(self.frozen["repairs"]),
            {
                "R1-intent-pattern-inflection-coverage",
                "R2-attribution-source-and-rejection-coverage",
                "R3-fallback-propagation",
            },
        )

    def test_a_tampered_repair_hash_is_detected(self) -> None:
        import tempfile

        tampered = dict(self.frozen)
        tampered["repair_hashes"] = dict(tampered["repair_hashes"], sources="0" * 64)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "freeze.json"
            target.write_text(json.dumps(tampered), encoding="utf-8")

            result = verify_repair_freeze(target)

        self.assertFalse(result.matches)
        self.assertIn("repair_hashes.sources", result.mismatches)

    def test_a_moved_benchmark_hash_is_detected(self) -> None:
        """A label edit would show up here rather than in a report."""

        import tempfile

        tampered = dict(self.frozen)
        tampered["supersedes"] = dict(tampered["supersedes"], benchmark_hash="0" * 64)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "freeze.json"
            target.write_text(json.dumps(tampered), encoding="utf-8")

            result = verify_repair_freeze(target)

        self.assertFalse(result.matches)
        self.assertFalse(result.labels_unchanged)

    def test_building_twice_gives_the_same_hashes(self) -> None:
        first = {k: v for k, v in build_repair_freeze().items() if k != "timestamp"}
        second = {k: v for k, v in build_repair_freeze().items() if k != "timestamp"}

        self.assertEqual(first, second)

    def test_a_missing_freeze_is_reported(self) -> None:
        import tempfile

        with self.assertRaises(RepairFreezeError):
            load_repair_freeze(Path(tempfile.gettempdir()) / "no-such-repair-freeze.json")

    def test_the_freeze_is_json_serializable(self) -> None:
        json.dumps(self.frozen, sort_keys=True)

    def test_writing_is_reproducible(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "f.json"
            write_repair_freeze(target)
            first = target.read_text(encoding="utf-8")
            write_repair_freeze(target)

            self.assertEqual(
                json.loads(first)["repair_hashes"],
                json.loads(target.read_text(encoding="utf-8"))["repair_hashes"],
            )


class TestPackageNamingTests(unittest.TestCase):
    def test_the_test_package_does_not_shadow_a_workspace_package(self) -> None:
        top_level = {
            path.name
            for path in WORKSPACE_ROOT.iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        }

        self.assertNotIn("risk_evaluation_v3_repair", top_level)


if __name__ == "__main__":
    unittest.main()
