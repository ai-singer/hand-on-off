"""The reporter: the coverage dashboard and the five-question expansion report.

Both documents are rendered from the artifacts a run produced, so the tests here check
that every mandated heading, question and figure actually reaches the page — including
on the degenerate input where nothing failed at all.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from risk_evaluation.coverage import reporter
from risk_evaluation.coverage.reporter import (
    DASHBOARD_NAME,
    EXPANSION_NAME,
    NOT_FIXED,
    REQUIRED_BENCHMARK,
    STATUS_HEADER,
    dashboard,
    expansion_report,
    write,
)

from ._support import (
    analysis,
    failure_analysis,
    generated_payload,
    metrics,
    registry_payload,
    summary,
)

QUESTIONS = (
    "What is the largest coverage gap right now?",
    "Which failures can generate a candidate automatically?",
    "Which failures require a human decision?",
    "Is it worth modifying the evaluator in the next phase?",
    "Which risks remain barred from production?",
)


def render_dashboard() -> str:
    return dashboard(
        analysis(),
        metrics(),
        registry_payload(),
        generated_payload(),
        summary(),
        NOT_FIXED,
    )


def render_expansion() -> str:
    return expansion_report(
        analysis(),
        metrics(),
        registry_payload(),
        generated_payload(),
        summary(),
        NOT_FIXED,
    )


class StatusHeaderTest(unittest.TestCase):
    def test_the_header_marks_production_not_ready(self) -> None:
        self.assertIn("Production: NOT READY", STATUS_HEADER)

    def test_the_header_carries_all_five_dimensions(self) -> None:
        for dimension in (
            "Architecture:",
            "Measurement:",
            "Governance:",
            "Capability:",
            "Production:",
        ):
            with self.subTest(dimension=dimension):
                self.assertIn(dimension, STATUS_HEADER)

    def test_the_dashboard_carries_the_status_header(self) -> None:
        self.assertIn(STATUS_HEADER, render_dashboard())

    def test_the_expansion_report_carries_the_status_header(self) -> None:
        self.assertIn(STATUS_HEADER, render_expansion())


class DashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = render_dashboard()
        cls.headings = re.findall(r"^#{1,3} .*$", cls.document, re.M)

    def test_the_mandated_headings_are_present(self) -> None:
        for heading in (
            "Current coverage",
            "Failure distribution",
            "Not fixed",
            "Evaluation requirements",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, self.document)

    def test_the_numbered_sections_are_present(self) -> None:
        for heading in (
            "## 1. Current coverage",
            "## 2. Failure distribution",
            "## 3. Top missing patterns",
            "## 4. Candidate growth",
            "## 5. Not fixed",
            "## 6. Evaluation requirements",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, self.headings)

    def test_the_document_has_a_title(self) -> None:
        self.assertTrue(self.document.startswith("# Phase R1"))

    def test_the_current_coverage_section_states_the_benchmark(self) -> None:
        self.assertIn("risk/independent", self.document)
        self.assertIn("v1", self.document)
        self.assertIn("300 cases", self.document)

    def test_the_current_coverage_section_reports_the_phase_figures(self) -> None:
        for figure in ("0.9062", "0.1758", "0.2945", "0.4949"):
            with self.subTest(figure=figure):
                self.assertIn(figure, self.document)

    def test_the_metrics_table_has_the_four_rows(self) -> None:
        for row in ("| precision |", "| recall |", "| F1 |", "| accuracy |"):
            with self.subTest(row=row):
                self.assertIn(row, self.document)

    def test_the_failure_section_states_the_failure_count(self) -> None:
        self.assertIn("151 of 300 cases fail exact-set match", self.document)

    def test_the_failure_section_names_every_type_it_reports(self) -> None:
        for name in analysis().types():
            with self.subTest(failure_type=name):
                self.assertIn(f"| {name} |", self.document)

    def test_the_failure_section_reports_the_outcome_shape(self) -> None:
        self.assertIn("Outcome shape:", self.document)
        for outcome in ("false_negative", "false_positive"):
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, self.document)

    def test_the_failure_section_reports_the_language_spread(self) -> None:
        self.assertIn("By language:", self.document)
        self.assertIn("The failure is not language-specific.", self.document)

    def test_the_top_missing_patterns_table_is_ranked(self) -> None:
        self.assertIn("| rank | pattern the evaluator lacks | failure type | cases |", self.document)
        self.assertIn("| 1 |", self.document)

    def test_the_candidate_growth_section_counts_the_queue(self) -> None:
        counts = registry_payload()["counts"]
        self.assertIn(f"{counts['pending']} candidates are in the", self.document)
        self.assertIn(f"{counts['rejected']} ", self.document)
        self.assertIn("Nothing was accepted", self.document)

    def test_the_candidate_growth_section_lists_the_pending_candidates(self) -> None:
        for item in registry_payload()["pending"]:
            with self.subTest(candidate=item["candidate_id"]):
                self.assertIn(item["candidate_id"], self.document)

    def test_the_candidate_growth_section_reports_the_expansion_set(self) -> None:
        payload = generated_payload()
        self.assertIn(f"produced {payload['count']} cases from", self.document)
        self.assertIn(f"{len(payload['templates'])} declared templates", self.document)
        for verdict in payload["verdicts"]:
            with self.subTest(verdict=verdict):
                self.assertIn(verdict, self.document)

    def test_the_not_fixed_section_lists_every_item(self) -> None:
        for entry in NOT_FIXED:
            with self.subTest(item=entry["item"]):
                self.assertIn(entry["item"].replace("`", ""), self.document.replace("`", ""))

    def test_the_not_fixed_section_states_why(self) -> None:
        self.assertIn("cannot mistake silence for resolution", self.document)

    def test_the_evaluation_requirements_state_the_needed_benchmark(self) -> None:
        self.assertIn(REQUIRED_BENCHMARK.rstrip("."), self.document)

    def test_the_evaluation_requirements_name_the_regression_sets_and_the_freeze(self) -> None:
        self.assertIn("six registered regression sets", self.document)
        self.assertIn("coverage_freeze_r1.json", self.document)

    def test_the_dashboard_makes_no_accuracy_claim(self) -> None:
        self.assertIn("No accuracy claim is made here", self.document)

    def test_the_dashboard_is_a_markdown_document_with_tables(self) -> None:
        self.assertGreater(len(self.headings), 5)
        self.assertIn("| metric | value |", self.document)
        self.assertIn("|---|---|", self.document)


class ExpansionReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = render_expansion()
        cls.headings = re.findall(r"^#{1,3} .*$", cls.document, re.M)

    def test_all_five_questions_are_asked(self) -> None:
        for question in QUESTIONS:
            with self.subTest(question=question):
                self.assertIn(question, self.document)

    def test_the_questions_are_numbered_in_order(self) -> None:
        for index, question in enumerate(QUESTIONS, start=1):
            with self.subTest(index=index):
                self.assertIn(f"### {index}. {question}", self.headings)

    def test_the_five_questions_section_is_named(self) -> None:
        self.assertIn("## The five questions", self.headings)

    def test_every_question_has_an_answer(self) -> None:
        for question in QUESTIONS:
            marker = f"### {QUESTIONS.index(question) + 1}. {question}\n\n"
            with self.subTest(question=question):
                start = self.document.index(marker) + len(marker)
                answer = self.document[start : self.document.index("\n\n", start)]
                self.assertTrue(answer.strip())

    def test_the_largest_gap_answer_names_the_largest_type(self) -> None:
        biggest = next(iter(analysis().types().items()))
        self.assertIn(f"The largest single gap is {biggest[0]} at {biggest[1]}", self.document)

    def test_the_auto_generatable_answer_counts_the_failures(self) -> None:
        body = summary()
        self.assertIn(
            f"{body['auto_generatable']} of {len(analysis().failures)} failures", self.document
        )

    def test_the_human_decision_answer_counts_the_failures(self) -> None:
        body = summary()
        self.assertIn(f"{body['human_required']} of", self.document)

    def test_the_production_answer_states_the_phase_figures(self) -> None:
        self.assertIn("Precision on the independent set is 0.9062", self.document)
        self.assertIn("recall 0.1758", self.document)

    def test_the_production_answer_keeps_every_category_barred(self) -> None:
        self.assertIn("All five categories remain barred from production", self.document)
        self.assertIn("the status remains Production: NOT READY.", self.document)

    def test_the_corroboration_section_compares_with_phase_8_9(self) -> None:
        self.assertIn("## Independent corroboration", self.headings)
        self.assertIn("106", self.document)
        self.assertIn("151", self.document)

    def test_the_corroboration_section_says_what_it_does_not_prove(self) -> None:
        self.assertIn("says nothing about whether any", self.document)

    def test_the_not_fixed_section_lists_every_item(self) -> None:
        for entry in NOT_FIXED:
            with self.subTest(item=entry["item"]):
                self.assertIn(entry["item"].replace("`", ""), self.document.replace("`", ""))

    def test_the_report_states_what_it_does_not_claim(self) -> None:
        for claim in (
            "It does not claim any accuracy improvement.",
            "It does not claim production readiness, in whole or in part.",
            "It does not claim that its candidates are correct.",
            "It does not claim the failure taxonomy is complete.",
        ):
            with self.subTest(claim=claim):
                self.assertIn(claim, self.document)

    def test_the_report_describes_what_the_phase_did(self) -> None:
        self.assertIn("It introduces no LLM, no", self.document)
        self.assertIn("network call and no production integration.", self.document)


class WriteTest(unittest.TestCase):
    def test_write_creates_both_documents_in_an_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            docs = Path(raw) / "docs"
            paths = write(
                analysis(),
                metrics(),
                registry_payload(),
                generated_payload(),
                summary(),
                docs_dir=docs,
            )
            self.assertEqual(set(paths), {DASHBOARD_NAME, EXPANSION_NAME})
            for name, path in paths.items():
                with self.subTest(document=name):
                    self.assertTrue(path.is_file(), name)
            self.assertEqual(
                sorted(path.name for path in docs.iterdir()),
                sorted([DASHBOARD_NAME, EXPANSION_NAME]),
            )

    def test_the_written_dashboard_is_the_rendered_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            paths = write(
                analysis(),
                metrics(),
                registry_payload(),
                generated_payload(),
                summary(),
                docs_dir=raw,
            )
            self.assertEqual(
                paths[DASHBOARD_NAME].read_text(encoding="utf-8"), render_dashboard()
            )

    def test_the_written_expansion_report_is_the_rendered_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            paths = write(
                analysis(),
                metrics(),
                registry_payload(),
                generated_payload(),
                summary(),
                docs_dir=raw,
            )
            self.assertEqual(
                paths[EXPANSION_NAME].read_text(encoding="utf-8"), render_expansion()
            )

    def test_write_leaves_an_existing_directory_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            docs = Path(raw) / "docs"
            docs.mkdir()
            keep = docs / "unrelated.md"
            keep.write_text("someone else's document\n", encoding="utf-8")
            write(
                analysis(),
                metrics(),
                registry_payload(),
                generated_payload(),
                summary(),
                docs_dir=docs,
            )
            self.assertEqual(keep.read_text(encoding="utf-8"), "someone else's document\n")
            self.assertEqual(len(list(docs.iterdir())), 3)

    def test_both_documents_carry_the_status_header(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            paths = write(
                analysis(),
                metrics(),
                registry_payload(),
                generated_payload(),
                summary(),
                docs_dir=raw,
            )
            for name, path in paths.items():
                with self.subTest(document=name):
                    self.assertIn(STATUS_HEADER, path.read_text(encoding="utf-8"))

    def test_the_default_document_names_are_documented(self) -> None:
        self.assertEqual(DASHBOARD_NAME, "PHASE_R1_COVERAGE_REPORT.md")
        self.assertEqual(EXPANSION_NAME, "PHASE_R1_COVERAGE_EXPANSION_REPORT.md")

    def test_the_default_docs_directory_is_the_repository_one(self) -> None:
        from risk_evaluation.coverage import freeze

        self.assertEqual(reporter.DOCS_DIR, freeze.repository_root() / "docs")


class DegenerateInputTest(unittest.TestCase):
    """An analysis with no failures must still render, rather than dividing by zero."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.empty = failure_analysis((), cases=0)
        cls.empty_registry = {
            "counts": {"pending": 0, "rejected": 0, "accepted": 0},
            "pending": [],
            "rejected": [],
            "accepted": [],
            "policy": "",
        }
        cls.empty_generated = {"count": 0, "templates": [], "verdicts": {}}
        cls.dashboard = dashboard(
            cls.empty,
            metrics(),
            cls.empty_registry,
            cls.empty_generated,
            {"auto_generatable": 0, "human_required": 0},
            NOT_FIXED,
        )
        cls.expansion = expansion_report(
            cls.empty,
            metrics(),
            cls.empty_registry,
            cls.empty_generated,
            {"auto_generatable": 0, "human_required": 0},
            NOT_FIXED,
        )

    def test_the_dashboard_still_renders_its_headings(self) -> None:
        self.assertIn("## 5. Not fixed", self.dashboard)
        self.assertIn("## 6. Evaluation requirements", self.dashboard)

    def test_the_dashboard_reports_zero_failures_without_inventing_a_share(self) -> None:
        self.assertIn("0 of 0 cases fail exact-set match", self.dashboard)
        self.assertIsNone(re.search(r"\bnan\b", self.dashboard, re.IGNORECASE))
        self.assertIsNone(re.search(r"\binf\b", self.dashboard, re.IGNORECASE))

    def test_the_expansion_report_still_asks_five_questions(self) -> None:
        for index, question in enumerate(QUESTIONS, start=1):
            with self.subTest(index=index):
                self.assertIn(f"### {index}. {question}", self.expansion)

    def test_the_expansion_report_handles_an_empty_distribution(self) -> None:
        self.assertIn("The largest single gap is (none) at 0", self.expansion)
        self.assertIsNone(re.search(r"\bnan\b", self.expansion, re.IGNORECASE))
