from __future__ import annotations

import json
import unittest

from risk_evaluation.evidence import (
    EVIDENCE_DESCRIPTIONS,
    EvidenceRequirement,
    assess_evidence,
    derivable_evidence,
    requirements_for,
)
from risk_evaluation.taxonomy import RISK_TAXONOMY, category_names


class EvidenceRequirementTests(unittest.TestCase):
    def test_requirements_follow_the_taxonomy(self) -> None:
        for name in category_names():
            requirements = requirements_for(name)

            self.assertTrue(requirements, name)
            self.assertTrue(
                all(isinstance(item, EvidenceRequirement) for item in requirements),
                name,
            )
            self.assertEqual(
                tuple(item.evidence_id for item in requirements),
                dict((item.name, item) for item in RISK_TAXONOMY)[name].evidence_required,
            )

    def test_every_declared_requirement_has_a_description(self) -> None:
        for name in category_names():
            for requirement in requirements_for(name):
                self.assertIn(requirement.evidence_id, EVIDENCE_DESCRIPTIONS)
                self.assertTrue(requirement.description)

    def test_unknown_category_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            requirements_for("not_a_category")


class EvidenceAssessmentTests(unittest.TestCase):
    def test_source_is_satisfied_when_the_risk_names_its_sources(self) -> None:
        status = assess_evidence("market_prediction", source_ids=("s-1",))

        self.assertIn("source", status.satisfied)
        self.assertNotIn("source", status.unsatisfied)
        self.assertTrue(status.checkable)

    def test_source_is_unsatisfied_when_no_source_is_named(self) -> None:
        status = assess_evidence("market_prediction", source_ids=())

        self.assertIn("source", status.unsatisfied)
        self.assertFalse(status.complete)

    def test_requirements_the_artifact_cannot_express_are_unknown(self) -> None:
        """Unknown is not absent: the artifact simply cannot demonstrate it yet."""

        status = assess_evidence("market_prediction", source_ids=("s-1",))

        self.assertEqual(set(status.unknown), {"data", "time_range"})
        self.assertFalse(status.complete)

    def test_only_source_is_derivable_today(self) -> None:
        self.assertEqual(derivable_evidence(), ("source",))

        for name in category_names():
            for requirement in requirements_for(name):
                if requirement.evidence_id not in derivable_evidence():
                    self.assertIn(
                        requirement.evidence_id,
                        assess_evidence(name, source_ids=("s-1",)).unknown,
                        name,
                    )

    def test_status_serializes(self) -> None:
        # market_prediction requires source, data and time_range; only source is
        # derivable from the artifact today.
        status = assess_evidence("market_prediction", source_ids=("s-1",))

        payload = json.loads(json.dumps(status.as_dict()))

        self.assertEqual(payload["category"], "market_prediction")
        self.assertEqual(payload["satisfied"], ["source"])
        self.assertFalse(payload["complete"])
        self.assertIn("render", dir(status))
        self.assertTrue(status.render())


if __name__ == "__main__":
    unittest.main()
