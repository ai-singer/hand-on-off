"""The candidate registry: the human review queue and its provable rejections.

The asymmetry between the three directories is the design under test. `pending/` is
what the framework writes, `rejected/` only carries rejections provable from the
framework's own tables, and `accepted/` is never written by the framework at all —
including on a re-run over a decision a human has already made.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from risk_evaluation.coverage import registry
from risk_evaluation.coverage.model import (
    ACCEPTED,
    PENDING,
    RECOMMEND_ACCEPT,
    RECOMMEND_DEFER,
    REJECTED,
    CoverageError,
    ReviewDecision,
)
from risk_evaluation.coverage.registry import (
    ACCEPTED_DIR,
    ACCEPTED_README,
    CANDIDATE_PREFIX,
    FROZEN_PREFIXES,
    PENDING_DIR,
    REGISTRY_DIR,
    REJECTED_DIR,
    REASON_ALREADY_KNOWN,
    REASON_EMPTY,
    REASON_FROZEN_TARGET,
    REASON_LITERAL_CASE,
    REJECTION_REASONS,
    RegistryError,
    RegistryReport,
    apply_decision,
    build,
    candidates_from_analysis,
    candidates_from_generated,
    describe,
    load,
    partition,
    rejection_reason,
    sort_candidates,
    write,
)
from risk_evaluation.coverage.taxonomy import AUTO_GENERATABLE, HUMAN_REQUIRED

from ._support import analysis, candidate, candidates, generated, registry_report


class CandidateShapeTest(unittest.TestCase):
    def test_the_analysis_produces_candidates(self) -> None:
        self.assertTrue(candidates_from_analysis(analysis()))

    def test_candidate_ids_are_unique(self) -> None:
        ids = [item.candidate_id for item in candidates()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_candidate_ids_are_stable_across_calls(self) -> None:
        first = [item.candidate_id for item in build(analysis(), generated())]
        second = [item.candidate_id for item in build(analysis(), generated())]
        self.assertEqual(first, second)

    def test_candidate_ids_match_the_declared_prefix(self) -> None:
        pattern = re.compile(rf"^{re.escape(CANDIDATE_PREFIX)}-\d{{4}}$")
        for item in candidates():
            with self.subTest(candidate=item.candidate_id):
                self.assertRegex(item.candidate_id, pattern)

    def test_analysis_candidate_ids_start_at_one_and_are_contiguous(self) -> None:
        ids = [item.candidate_id for item in candidates_from_analysis(analysis())]
        self.assertEqual(ids[0], f"{CANDIDATE_PREFIX}-0001")
        self.assertEqual(
            ids, [f"{CANDIDATE_PREFIX}-{index:04d}" for index in range(1, len(ids) + 1)]
        )

    def test_generated_candidate_ids_are_in_a_separate_block(self) -> None:
        ids = [item.candidate_id for item in candidates_from_generated(generated(), analysis())]
        self.assertTrue(ids)
        for candidate_id in ids:
            with self.subTest(candidate=candidate_id):
                self.assertGreaterEqual(int(candidate_id.rsplit("-", 1)[1]), 9000)

    def test_every_analysis_candidate_covers_at_least_one_case(self) -> None:
        for item in candidates_from_analysis(analysis()):
            with self.subTest(candidate=item.candidate_id):
                self.assertTrue(item.covers_cases)

    def test_a_generated_candidate_may_cover_no_failing_case(self) -> None:
        """Expansion is proactive: an axis may be new to the failure set entirely."""

        unmotivated = [
            item for item in candidates_from_generated(generated(), analysis()) if not item.covers_cases
        ]
        self.assertTrue(unmotivated, "expected at least one proactive candidate")
        for item in unmotivated:
            with self.subTest(candidate=item.candidate_id):
                self.assertFalse(item.is_general)
                self.assertIn("0 existing failing case(s)", item.expected_impact)

    def test_every_candidate_is_grouped_by_what_it_needs(self) -> None:
        """One candidate per (failure type, target, category), not per failing case."""

        for item in candidates_from_analysis(analysis()):
            targets = {
                (record.failure_type, record.repair_candidate.target if record.repair_candidate else "human-review")
                for record in analysis().failures
                if record.case_id in item.covers_cases
            }
            with self.subTest(candidate=item.candidate_id):
                self.assertEqual(len(targets), 1)

    def test_candidate_proposals_never_quote_their_own_cases_literal_text(self) -> None:
        for item in candidates():
            with self.subTest(candidate=item.candidate_id):
                self.assertNotIn(REASON_LITERAL_CASE, str(rejection_reason(item)))
                lowered = item.proposal.lower()
                for case_id in item.covers_cases:
                    self.assertNotIn(case_id.lower(), lowered)

    def test_candidates_for_human_required_types_defer(self) -> None:
        for item in candidates():
            if item.failure_type not in HUMAN_REQUIRED:
                continue
            with self.subTest(candidate=item.candidate_id):
                self.assertEqual(item.recommendation, RECOMMEND_DEFER)

    def test_analysis_candidates_with_a_word_list_are_recommended_for_acceptance(
        self,
    ) -> None:
        recommended = [
            item
            for item in candidates_from_analysis(analysis())
            if item.additions and item.failure_type in AUTO_GENERATABLE
        ]
        self.assertTrue(recommended)
        for item in recommended:
            with self.subTest(candidate=item.candidate_id):
                self.assertEqual(item.recommendation, RECOMMEND_ACCEPT)

    def test_a_generated_candidate_with_no_failing_case_behind_it_defers(self) -> None:
        """Nothing asked for it, so acceptance is not recommended for it."""

        for item in candidates_from_generated(generated(), analysis()):
            if item.covers_cases or not item.is_general:
                continue
            with self.subTest(candidate=item.candidate_id):
                self.assertEqual(item.recommendation, RECOMMEND_DEFER)

    def test_no_candidate_is_recommended_for_acceptance_without_a_word_list(self) -> None:
        for item in candidates():
            if item.additions:
                continue
            with self.subTest(candidate=item.candidate_id):
                self.assertEqual(item.recommendation, RECOMMEND_DEFER)

    def test_build_deduplicates_by_proposal_text(self) -> None:
        raw = candidates_from_analysis(analysis()) + candidates_from_generated(
            generated(), analysis()
        )
        built = build(analysis(), generated())
        proposals = [item.proposal for item in built]
        self.assertEqual(len(proposals), len(set(proposals)))
        self.assertLessEqual(len(built), len(raw))


class SortTest(unittest.TestCase):
    def test_general_candidates_come_first(self) -> None:
        ordered = sort_candidates(
            [
                candidate(candidate_id="CAND-R1-0002", covers_cases=(), additions=()),
                candidate(candidate_id="CAND-R1-0001"),
            ]
        )
        self.assertEqual(ordered[0].candidate_id, "CAND-R1-0001")

    def test_equal_generality_sorts_by_the_number_of_cases_covered(self) -> None:
        ordered = sort_candidates(
            [
                candidate(candidate_id="CAND-R1-0001", covers_cases=("a",)),
                candidate(candidate_id="CAND-R1-0002", covers_cases=("a", "b", "c")),
            ]
        )
        self.assertEqual(
            [item.candidate_id for item in ordered], ["CAND-R1-0002", "CAND-R1-0001"]
        )

    def test_the_sort_is_stable_for_identical_inputs(self) -> None:
        items = candidates()
        self.assertEqual(
            [item.candidate_id for item in sort_candidates(items)],
            [item.candidate_id for item in sort_candidates(items)],
        )


class RejectionReasonTest(unittest.TestCase):
    """Only rejections provable without an opinion are made mechanically."""

    def test_additions_the_evaluator_already_matches_are_rejected(self) -> None:
        item = candidate(additions=("guaranteed", "assured"))
        self.assertEqual(rejection_reason(item), REASON_ALREADY_KNOWN)

    def test_one_unknown_word_is_enough_to_leave_a_candidate_alone(self) -> None:
        item = candidate(additions=("guaranteed", "zoomy"))
        self.assertIsNone(rejection_reason(item))

    def test_a_proposal_naming_the_frozen_v3_patterns_is_rejected(self) -> None:
        item = candidate(
            additions=("zoomy",),
            proposal="add zoomy to risk_evaluation/v3/patterns.py",
            covers_cases=("IND-0007",),
        )
        self.assertEqual(rejection_reason(item), REASON_FROZEN_TARGET)

    def test_a_proposal_naming_production_is_rejected(self) -> None:
        item = candidate(
            additions=("zoomy",),
            proposal="wire the extension into production/ settings",
            covers_cases=("IND-0007",),
        )
        self.assertEqual(rejection_reason(item), REASON_FROZEN_TARGET)

    def test_a_proposal_naming_runtime_or_workflows_or_plugins_is_rejected(self) -> None:
        for prefix in ("runtime/", "workflows/", "plugins/"):
            with self.subTest(prefix=prefix):
                item = candidate(
                    additions=("zoomy",),
                    proposal=f"change {prefix}something",
                    covers_cases=("IND-0007",),
                )
                self.assertEqual(rejection_reason(item), REASON_FROZEN_TARGET)

    def test_a_proposal_quoting_a_failing_cases_id_is_rejected(self) -> None:
        item = candidate(
            additions=("zoomy",),
            proposal="the rule that fixes IND-0001 should fire",
            covers_cases=("IND-0001",),
        )
        self.assertEqual(rejection_reason(item), REASON_LITERAL_CASE)

    def test_a_normal_candidate_is_left_to_a_human(self) -> None:
        item = candidate(
            additions=("zoomy",),
            proposal="extend the movement_direction axis by adding zoomy",
            covers_cases=("IND-0007",),
        )
        self.assertIsNone(rejection_reason(item))

    def test_a_candidate_with_nothing_to_add_is_left_to_a_human(self) -> None:
        item = candidate(additions=(), proposal="the repair is structural")
        self.assertIsNone(rejection_reason(item))

    def test_every_provable_reason_is_declared(self) -> None:
        declared = set(REJECTION_REASONS)
        self.assertEqual(
            declared,
            {REASON_ALREADY_KNOWN, REASON_LITERAL_CASE, REASON_FROZEN_TARGET, REASON_EMPTY},
        )

    def test_the_empty_proposal_reason_is_never_returned_mechanically(self) -> None:
        """A candidate with nothing to add may be a structural finding, not a mistake."""

        for additions in ((), ("zoomy",)):
            with self.subTest(additions=additions):
                self.assertNotEqual(
                    rejection_reason(candidate(additions=additions)), REASON_EMPTY
                )

    def test_the_frozen_prefixes_cover_every_area_this_phase_may_not_touch(self) -> None:
        for prefix in (
            "risk_evaluation/v3/",
            "risk_evaluation/v3_1/",
            "risk_evaluation/v3_independent/",
            "risk_evaluation/benchmarks/",
            "runtime/",
            "production/",
            "workflows/",
            "plugins/",
        ):
            with self.subTest(prefix=prefix):
                self.assertIn(prefix, FROZEN_PREFIXES)


class PartitionTest(unittest.TestCase):
    def test_the_real_candidates_are_all_pending(self) -> None:
        pending, rejected = partition(candidates())
        self.assertEqual(len(pending), len(candidates()))
        self.assertEqual(rejected, ())

    def test_a_provable_rejection_is_split_out(self) -> None:
        good = candidate(candidate_id="CAND-R1-0001", additions=("zoomy",))
        bad = candidate(
            candidate_id="CAND-R1-0002",
            additions=("guaranteed",),
            proposal="extend an axis by adding guaranteed",
        )
        pending, rejected = partition([good, bad])
        self.assertEqual([item.candidate_id for item in pending], ["CAND-R1-0001"])
        self.assertEqual([item.candidate_id for item, _ in rejected], ["CAND-R1-0002"])
        self.assertEqual(rejected[0][1], REASON_ALREADY_KNOWN)

    def test_partition_splits_into_two_disjoint_halves(self) -> None:
        items = [
            candidate(candidate_id="CAND-R1-0001", additions=("zoomy",)),
            candidate(candidate_id="CAND-R1-0002", additions=("guaranteed",)),
        ]
        pending, rejected = partition(items)
        self.assertEqual(len(pending) + len(rejected), len(items))
        self.assertEqual(
            {item.candidate_id for item in pending}
            & {item.candidate_id for item, _ in rejected},
            set(),
        )

    def test_the_report_counts_the_partition(self) -> None:
        report = registry_report()
        self.assertEqual(report.counts["pending"], len(candidates()))
        self.assertEqual(report.counts["rejected"], 0)
        self.assertEqual(report.counts["accepted"], 0)

    def test_the_report_states_the_policy(self) -> None:
        self.assertIn("accepted requires a human decision", registry_report().as_dict()["policy"])


class ApplyDecisionTest(unittest.TestCase):
    """The only path to `accepted`, and it requires a human."""

    def test_a_decision_naming_a_different_candidate_is_refused(self) -> None:
        with self.assertRaises(RegistryError) as caught:
            apply_decision(
                candidate(candidate_id="CAND-R1-0001"),
                ReviewDecision(
                    candidate_id="CAND-R1-0002",
                    decision=ACCEPTED,
                    reviewer="a reviewer",
                    rationale="looks right",
                ),
            )
        self.assertIn("decision names", str(caught.exception))

    def test_an_acceptance_must_name_a_reviewer(self) -> None:
        with self.assertRaises(RegistryError) as caught:
            apply_decision(
                candidate(),
                ReviewDecision(
                    candidate_id="CAND-R1-0001",
                    decision=ACCEPTED,
                    reviewer="",
                    rationale="looks right",
                ),
            )
        self.assertIn("must name a reviewer", str(caught.exception))

    def test_a_rejection_may_be_unattributed(self) -> None:
        """Only acceptance is the claim that needs a signature."""

        updated = apply_decision(
            candidate(),
            ReviewDecision(
                candidate_id="CAND-R1-0001",
                decision=REJECTED,
                reviewer="",
                rationale="the words are already matched",
            ),
        )
        self.assertEqual(updated.status, REJECTED)

    def test_an_acceptance_by_a_named_reviewer_is_applied(self) -> None:
        updated = apply_decision(
            candidate(),
            ReviewDecision(
                candidate_id="CAND-R1-0001",
                decision=ACCEPTED,
                reviewer="reviewer",
                rationale="scored against a later benchmark",
            ),
        )
        self.assertEqual(updated.status, ACCEPTED)
        self.assertEqual(updated.candidate_id, "CAND-R1-0001")
        self.assertEqual(updated.additions, ("zoomy",))

    def test_applying_a_decision_keeps_the_candidate_identity(self) -> None:
        original = candidate(covers_cases=("IND-0001", "IND-0002"))
        updated = apply_decision(
            original,
            ReviewDecision(
                candidate_id=original.candidate_id,
                decision=REJECTED,
                reviewer="reviewer",
                rationale="not now",
            ),
        )
        self.assertEqual(updated.covers_cases, original.covers_cases)
        self.assertEqual(updated.proposal, original.proposal)
        self.assertEqual(updated.generator, original.generator)

    def test_a_pending_decision_cannot_even_be_constructed(self) -> None:
        """So the `PENDING` branch of `apply_decision` is unreachable by construction."""

        with self.assertRaises(CoverageError):
            ReviewDecision(
                candidate_id="CAND-R1-0001",
                decision=PENDING,
                reviewer="reviewer",
                rationale="no ruling yet",
            )


class WriteTest(unittest.TestCase):
    """`write()` writes pending and provable rejections, and never `accepted/`."""

    def _write(self, root: Path) -> RegistryReport:
        return write(analysis(), generated(), registry_dir=root)

    def test_write_creates_the_three_directories(self) -> None:
        with TemporaryDirectory() as raw:
            root = Path(raw) / "coverage_candidates"
            self._write(root)
            self.assertTrue((root / "pending").is_dir())
            self.assertTrue((root / "rejected").is_dir())
            self.assertTrue((root / "accepted").is_dir())

    def test_write_puts_a_file_per_pending_candidate(self) -> None:
        with TemporaryDirectory() as raw:
            root = Path(raw) / "registry"
            report = self._write(root)
            files = sorted(path.name for path in (root / "pending").glob("*.json"))
            self.assertEqual(len(files), len(report.pending))
            self.assertEqual(files, sorted(f"{item.candidate_id}.json" for item in report.pending))

    def test_write_never_writes_into_accepted(self) -> None:
        with TemporaryDirectory() as raw:
            root = Path(raw) / "registry"
            self._write(root)
            self.assertEqual(
                sorted(path.name for path in (root / "accepted").iterdir()),
                ["README.md"],
            )

    def test_the_accepted_readme_states_that_a_human_writes_it(self) -> None:
        with TemporaryDirectory() as raw:
            root = Path(raw) / "registry"
            self._write(root)
            text = (root / "accepted" / "README.md").read_text(encoding="utf-8")
            self.assertIn("written by a human, never by the framework", text)
            self.assertEqual(text, ACCEPTED_README)

    def test_the_report_contains_no_accepted_candidate(self) -> None:
        with TemporaryDirectory() as raw:
            report = self._write(Path(raw) / "registry")
            self.assertEqual(report.accepted, ())
            self.assertEqual(report.counts["accepted"], 0)

    def test_a_written_pending_candidate_reloads_identically(self) -> None:
        with TemporaryDirectory() as raw:
            root = Path(raw) / "registry"
            report = self._write(root)
            first = report.pending[0]
            reloaded = load(root / "pending" / f"{first.candidate_id}.json")
            self.assertEqual(reloaded.candidate_id, first.candidate_id)
            self.assertEqual(reloaded.proposal, first.proposal)
            self.assertEqual(reloaded.additions, first.additions)
            self.assertEqual(reloaded.covers_cases, first.covers_cases)
            self.assertEqual(reloaded.status, PENDING)

    def test_a_re_run_produces_the_same_pending_files(self) -> None:
        with TemporaryDirectory() as raw:
            root = Path(raw) / "registry"
            self._write(root)
            before = {
                path.name: path.read_text(encoding="utf-8")
                for path in (root / "pending").glob("*.json")
            }
            self._write(root)
            after = {
                path.name: path.read_text(encoding="utf-8")
                for path in (root / "pending").glob("*.json")
            }
            self.assertEqual(before, after)

    def test_a_re_run_does_not_touch_a_candidate_a_human_already_accepted(self) -> None:
        with TemporaryDirectory() as raw:
            root = Path(raw) / "registry"
            self._write(root)
            accepted = root / "accepted" / "CAND-R1-0001.json"
            decision = {
                "candidate_id": "CAND-R1-0001",
                "status": ACCEPTED,
                "reviewer": "a reviewer",
                "note": "hand-written decision, must survive a re-run",
            }
            accepted.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
            recorded = accepted.read_text(encoding="utf-8")

            self._write(root)

            self.assertEqual(accepted.read_text(encoding="utf-8"), recorded)
            self.assertEqual(
                sorted(path.name for path in (root / "accepted").iterdir()),
                ["CAND-R1-0001.json", "README.md"],
            )

    def test_write_leaves_the_packaged_registry_alone(self) -> None:
        """A run against a temporary registry must not touch the shipped one."""

        self.assertTrue(REGISTRY_DIR.is_dir())
        self.assertTrue(list(PENDING_DIR.glob("*.json")))

        def snapshot() -> dict[str, tuple[int, int]]:
            return {
                str(path.relative_to(REGISTRY_DIR)): (
                    path.stat().st_mtime_ns,
                    path.stat().st_size,
                )
                for path in sorted(REGISTRY_DIR.rglob("*"))
                if path.is_file()
            }

        before = snapshot()
        with TemporaryDirectory() as raw:
            self._write(Path(raw) / "registry")
        self.assertEqual(snapshot(), before)

    def test_rejected_candidates_are_written_with_their_reason(self) -> None:
        """The real run proves nothing, so the rejection branch is driven directly."""

        reviewable = candidate(candidate_id="CAND-R1-0001", additions=("zoomy",))
        redundant = candidate(
            candidate_id="CAND-R1-0002",
            additions=("guaranteed",),
            proposal="extend an axis by adding guaranteed",
        )
        with TemporaryDirectory() as raw:
            root = Path(raw) / "registry"
            root.mkdir(parents=True)
            with mock.patch.object(registry, "build", return_value=(reviewable, redundant)):
                report = write(analysis(), generated(), registry_dir=root)

            self.assertEqual([item.candidate_id for item in report.pending], ["CAND-R1-0001"])
            self.assertEqual(
                [item.candidate_id for item, _ in report.rejected], ["CAND-R1-0002"]
            )
            rejected_files = sorted((root / "rejected").glob("*.json"))
            self.assertEqual([path.name for path in rejected_files], ["CAND-R1-0002.json"])
            body = json.loads(rejected_files[0].read_text(encoding="utf-8"))
            self.assertEqual(body["status"], REJECTED)
            self.assertEqual(body["rejection_reason"], REASON_ALREADY_KNOWN)
            self.assertIn("provable", body["rejection_basis"])
            self.assertEqual(
                sorted(path.name for path in (root / "pending").glob("*.json")),
                ["CAND-R1-0001.json"],
            )
            self.assertEqual(
                sorted(path.name for path in (root / "accepted").iterdir()), ["README.md"]
            )


class DefaultsAndDescribeTest(unittest.TestCase):
    def test_the_default_directories_live_under_the_package(self) -> None:
        self.assertEqual(REGISTRY_DIR.parent.name, "coverage")
        self.assertEqual(PENDING_DIR.parent, REGISTRY_DIR)
        self.assertEqual(REJECTED_DIR.parent, REGISTRY_DIR)
        self.assertEqual(ACCEPTED_DIR.parent, REGISTRY_DIR)

    def test_describe_without_a_report_describes_the_policy(self) -> None:
        body = describe()
        self.assertIs(body["writes_accepted"], False)
        self.assertEqual(body["directories"], ["pending", "accepted", "rejected"])
        self.assertEqual(body["provable_rejections"], list(REJECTION_REASONS))
        self.assertEqual(body["frozen_prefixes"], list(FROZEN_PREFIXES))

    def test_describe_with_a_report_serialises_the_report(self) -> None:
        report = RegistryReport(pending=(), rejected=(), accepted=())
        self.assertEqual(describe(report), report.as_dict())

    def test_the_report_counts_are_zero_when_empty(self) -> None:
        self.assertEqual(
            RegistryReport(pending=(), rejected=(), accepted=()).counts,
            {"pending": 0, "rejected": 0, "accepted": 0},
        )

    def test_the_accepted_readme_says_ids_are_stable(self) -> None:
        self.assertIn("Candidate ids are stable.", ACCEPTED_README)
