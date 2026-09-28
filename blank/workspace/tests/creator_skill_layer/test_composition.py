"""Composition: finance, sports, mixed bundles, scoring, and verification."""

from __future__ import annotations

import unittest
from copy import deepcopy

from creator_skill import (
    DEFAULT_SKILL_CATALOG,
    REQUIRED_SKILL_TYPES,
    CreatorRequest,
    SkillBundle,
    SkillComposer,
    SkillCompositionError,
    SkillDependency,
    SkillProvenance,
    SkillRegistry,
    SkillSelection,
    compose,
    compose_bundle_id,
    score_skill,
)
from creator_skill.model import CreatorSkill, SkillCompatibility


def _registry() -> SkillRegistry:
    return SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)


class ScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = _registry()

    def test_domain_match_beats_a_platform_only_match(self) -> None:
        request = CreatorRequest(domain="finance", platform="xiaohongshu")
        domain_skill = self.registry.resolve("business-finance-analysis")
        source_skill = self.registry.resolve("xiaohongshu-source")
        self.assertGreater(
            score_skill(domain_skill, request).total,
            score_skill(source_skill, request).total,
        )

    def test_incompatible_domain_scores_negative(self) -> None:
        request = CreatorRequest(domain="sports", platform="xiaohongshu")
        persona = self.registry.resolve("finance-persona")
        score = score_skill(persona, request)
        self.assertFalse(score.compatible)
        self.assertLess(score.total, 0)

    def test_incompatible_platform_scores_negative(self) -> None:
        request = CreatorRequest(domain="finance", platform="bilibili")
        source = self.registry.resolve("xiaohongshu-source")
        self.assertFalse(score_skill(source, request).compatible)

    def test_incompatible_style_scores_negative(self) -> None:
        request = CreatorRequest(domain="finance", platform="web", style="comedy")
        persona = self.registry.resolve("finance-persona")
        self.assertFalse(score_skill(persona, request).compatible)

    def test_score_explains_each_contribution(self) -> None:
        request = CreatorRequest(domain="finance", platform="xiaohongshu")
        score = score_skill(self.registry.resolve("finance-persona"), request)
        joined = " ".join(score.reasons)
        self.assertIn("matched domain finance", joined)
        self.assertIn("matched style education", joined)
        self.assertIn("confidence", joined)

    def test_agnostic_dimensions_are_labelled(self) -> None:
        request = CreatorRequest(domain="finance", platform="web")
        score = score_skill(self.registry.resolve("text-distillation"), request)
        joined = " ".join(score.reasons)
        self.assertIn("domain-agnostic", joined)
        self.assertIn("platform-agnostic", joined)

    def test_score_as_dict_shape(self) -> None:
        record = score_skill(
            self.registry.resolve("text-distillation"),
            CreatorRequest(domain="finance", platform="web"),
        ).as_dict()
        for key in ("skill_id", "skill_type", "total", "compatible", "reasons"):
            self.assertIn(key, record)


class FinanceBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.composer = SkillComposer(_registry())
        cls.result = cls.composer.compose(
            CreatorRequest(domain="finance", platform="xiaohongshu")
        )

    def test_bundle_is_complete(self) -> None:
        self.assertTrue(self.result.complete)

    def test_bundle_selects_seven_skills(self) -> None:
        self.assertEqual(len(self.result.bundle.selections), 7)

    def test_bundle_covers_every_required_type(self) -> None:
        for skill_type in REQUIRED_SKILL_TYPES:
            self.assertIsNotNone(self.result.bundle.by_type(skill_type), skill_type)

    def test_finance_persona_is_selected(self) -> None:
        self.assertEqual(self.result.bundle.by_type("identity").skill_id, "finance-persona")

    def test_finance_domain_skill_is_selected(self) -> None:
        self.assertEqual(
            self.result.bundle.by_type("domain").skill_id, "business-finance-analysis"
        )

    def test_xiaohongshu_source_is_selected(self) -> None:
        self.assertEqual(
            self.result.bundle.by_type("source").skill_id, "xiaohongshu-source"
        )

    def test_finance_risk_review_is_selected(self) -> None:
        self.assertEqual(
            self.result.bundle.by_type("review").skill_id, "finance-risk-review"
        )

    def test_xiaohongshu_publishing_is_selected(self) -> None:
        self.assertEqual(
            self.result.bundle.by_type("publishing").skill_id, "xiaohongshu-publishing"
        )

    def test_verification_passes(self) -> None:
        checks = self.composer.verify(self.result.bundle)
        self.assertTrue(all(value == "PASS" for value in checks.values()))

    def test_verification_document_is_pass(self) -> None:
        self.assertEqual(
            self.composer.verify_document(self.result.bundle)["status"], "PASS"
        )

    def test_every_selection_carries_a_reason(self) -> None:
        for selection in self.result.bundle.selections:
            with self.subTest(skill=selection.skill_id):
                self.assertTrue(selection.reason)
                self.assertIn(selection.skill_id, selection.reason)

    def test_reasons_are_recorded_per_type(self) -> None:
        for skill_type in REQUIRED_SKILL_TYPES:
            self.assertIn(skill_type, self.result.reasons)

    def test_declared_skills_are_marked_in_the_reason(self) -> None:
        source = self.result.bundle.by_type("source")
        self.assertEqual(source.status, "declared")
        self.assertIn("not available", self.result.reasons["source"])

    def test_alternatives_are_recorded(self) -> None:
        self.assertIn("review", self.result.rejected)
        self.assertIn("evidence-review", self.result.rejected["review"])

    def test_bundle_id_is_deterministic(self) -> None:
        again = self.composer.compose(
            CreatorRequest(domain="finance", platform="xiaohongshu")
        )
        self.assertEqual(self.result.bundle.bundle_id, again.bundle.bundle_id)

    def test_bundle_provenance_names_the_skills(self) -> None:
        self.assertIn("finance-persona", self.result.bundle.provenance.note)

    def test_result_is_serialisable(self) -> None:
        import json

        json.dumps(self.result.as_dict())

    def test_composing_twice_is_identical(self) -> None:
        again = self.composer.compose(
            CreatorRequest(domain="finance", platform="xiaohongshu")
        )
        self.assertEqual(self.result.bundle.as_dict(), again.bundle.as_dict())


class VisualExtraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.composer = SkillComposer(_registry())

    def test_visual_skill_is_added_as_an_extra(self) -> None:
        result = self.composer.compose(
            CreatorRequest(
                domain="finance",
                platform="xiaohongshu",
                declared_capabilities=("visual-style-distillation",),
            )
        )
        self.assertEqual(len(result.bundle.extras), 1)
        self.assertEqual(result.bundle.extras[0].skill_id, "visual-style-distillation")

    def test_extra_does_not_break_the_one_per_type_rule(self) -> None:
        result = self.composer.compose(
            CreatorRequest(
                domain="finance",
                platform="xiaohongshu",
                declared_capabilities=("visual-style-distillation",),
            )
        )
        types = [s.skill_type for s in result.bundle.selections]
        self.assertEqual(len(types), len(set(types)))

    def test_bundle_with_an_extra_still_verifies(self) -> None:
        result = self.composer.compose(
            CreatorRequest(
                domain="finance",
                platform="xiaohongshu",
                declared_capabilities=("visual-style-distillation",),
            )
        )
        self.assertTrue(all(v == "PASS" for v in self.composer.verify(result.bundle).values()))

    def test_unregistered_declared_capability_is_noted(self) -> None:
        result = self.composer.compose(
            CreatorRequest(
                domain="finance",
                platform="xiaohongshu",
                declared_capabilities=("ghost-skill",),
            )
        )
        self.assertTrue(any("ghost-skill" in note for note in result.bundle.notes))

    def test_incompatible_declared_capability_is_noted(self) -> None:
        result = self.composer.compose(
            CreatorRequest(
                domain="finance",
                platform="bilibili",
                declared_capabilities=("xiaohongshu-publishing",),
            )
        )
        self.assertTrue(
            any("incompatible" in note for note in result.bundle.notes)
        )


class SportsAndMixedBundleTests(unittest.TestCase):
    """Domains the repository has no skills for must be reported, not invented."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.composer = SkillComposer(_registry())

    def test_sports_bundle_is_partial(self) -> None:
        result = self.composer.compose(
            CreatorRequest(domain="sports", platform="xiaohongshu")
        )
        self.assertFalse(result.complete)

    def test_sports_bundle_reports_identity_and_domain_as_unsatisfied(self) -> None:
        result = self.composer.compose(
            CreatorRequest(domain="sports", platform="xiaohongshu")
        )
        self.assertIn("identity", result.unsatisfied)
        self.assertIn("domain", result.unsatisfied)

    def test_sports_bundle_still_selects_what_exists(self) -> None:
        result = self.composer.compose(
            CreatorRequest(domain="sports", platform="xiaohongshu")
        )
        self.assertGreaterEqual(len(result.bundle.selections), 4)

    def test_sports_bundle_records_the_gap_in_notes(self) -> None:
        result = self.composer.compose(
            CreatorRequest(domain="sports", platform="xiaohongshu")
        )
        self.assertTrue(
            any("unresolved skill types" in note for note in result.bundle.notes)
        )

    def test_sports_bundle_still_verifies(self) -> None:
        result = self.composer.compose(
            CreatorRequest(domain="sports", platform="xiaohongshu")
        )
        self.assertEqual(
            self.composer.verify(result.bundle)["required_types"], "PARTIAL"
        )

    def test_tech_bundle_uses_the_tech_domain_skill(self) -> None:
        result = self.composer.compose(
            CreatorRequest(domain="tech", platform="bilibili")
        )
        self.assertEqual(result.bundle.by_type("domain").skill_id, "technology-analysis")

    def test_tech_bundle_records_identity_as_unsatisfied(self) -> None:
        result = self.composer.compose(
            CreatorRequest(domain="tech", platform="bilibili")
        )
        self.assertIn("identity", result.unsatisfied)

    def test_finance_on_web_uses_the_news_source(self) -> None:
        result = self.composer.compose(CreatorRequest(domain="finance", platform="web"))
        self.assertEqual(result.bundle.by_type("source").skill_id, "news-source")

    def test_finance_on_web_records_generation_and_publishing_gaps(self) -> None:
        result = self.composer.compose(CreatorRequest(domain="finance", platform="web"))
        self.assertIn("generation", result.unsatisfied)
        self.assertIn("publishing", result.unsatisfied)

    def test_mixed_request_with_an_extra_verifies(self) -> None:
        result = self.composer.compose(
            CreatorRequest(
                domain="tech",
                platform="bilibili",
                declared_capabilities=("visual-style-distillation",),
            )
        )
        checks = self.composer.verify(result.bundle)
        # The tech/bilibili bundle has declared gaps, so required_types is PARTIAL
        # rather than PASS; every other check must pass.
        self.assertEqual(checks["required_types"], "PARTIAL")
        for key, value in checks.items():
            if key == "required_types":
                continue
            self.assertEqual(value, "PASS", key)

    def test_visual_extra_is_added_for_a_different_domain(self) -> None:
        result = self.composer.compose(
            CreatorRequest(
                domain="tech",
                platform="bilibili",
                declared_capabilities=("visual-style-distillation",),
            )
        )
        self.assertEqual(
            [e.skill_id for e in result.bundle.extras], ["visual-style-distillation"]
        )


class StrictBundleTests(unittest.TestCase):
    """With allow_unavailable=False, an incomplete bundle must raise."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.composer = SkillComposer(_registry())

    def test_strict_request_rejects_because_declared_skills_are_not_available(self) -> None:
        """No bundle today is fully available: source, generation and publishing
        are declared capabilities without implementations, so a strict request
        must refuse rather than pretend the bundle is complete."""

        with self.assertRaises(SkillCompositionError) as ctx:
            self.composer.compose(
                CreatorRequest(
                    domain="finance", platform="xiaohongshu", allow_unavailable=False
                )
            )
        self.assertIn("source", str(ctx.exception))
        self.assertIn("generation", str(ctx.exception))
        self.assertIn("publishing", str(ctx.exception))

    def test_strict_request_rejects_a_bundle_with_a_missing_type(self) -> None:
        with self.assertRaises(SkillCompositionError):
            self.composer.compose(
                CreatorRequest(
                    domain="sports", platform="xiaohongshu", allow_unavailable=False
                )
            )

    def test_relaxed_request_composes_a_partial_bundle(self) -> None:
        result = self.composer.compose(
            CreatorRequest(domain="sports", platform="xiaohongshu", allow_unavailable=True)
        )
        self.assertFalse(result.complete)

    def test_custom_required_types_narrow_the_bundle(self) -> None:
        result = self.composer.compose(
            CreatorRequest(
                domain="finance",
                platform="xiaohongshu",
                required_skill_types=("identity", "domain"),
            )
        )
        self.assertEqual(len(result.bundle.selections), 2)

    def test_unknown_required_type_is_rejected(self) -> None:
        with self.assertRaises(SkillCompositionError):
            self.composer.compose(
                CreatorRequest(
                    domain="finance",
                    platform="xiaohongshu",
                    required_skill_types=("telepathy",),
                )
            )

    def test_compose_requires_a_request_object(self) -> None:
        with self.assertRaises(SkillCompositionError):
            self.composer.compose({"domain": "finance"})  # type: ignore[arg-type]

    def test_composer_requires_a_registry(self) -> None:
        with self.assertRaises(SkillCompositionError):
            SkillComposer("not a registry")  # type: ignore[arg-type]


class VerificationFailureTests(unittest.TestCase):
    """A bundle that references something absent must fail verification."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = _registry()
        cls.composer = SkillComposer(cls.registry)

    def _bundle(self, selections, notes=()) -> SkillBundle:
        return SkillBundle(
            bundle_id="bundle-manual",
            request=CreatorRequest(domain="finance", platform="xiaohongshu"),
            selections=tuple(selections),
            provenance=SkillProvenance(
                source_kind="projection",
                source_ref="bundle-manual",
                skill_version="1.0.0",
                generated_at="1970-01-01T00:00:00Z",
            ),
            notes=tuple(notes),
        )

    def test_bundle_referencing_an_unknown_skill_fails(self) -> None:
        bundle = self._bundle(
            [
                SkillSelection(
                    skill_type="identity",
                    skill_id="ghost-persona",
                    version="1.0.0",
                    reason="r",
                )
            ]
        )
        with self.assertRaises(Exception):
            self.composer.verify(bundle)

    def test_bundle_referencing_a_wrong_version_fails(self) -> None:
        bundle = self._bundle(
            [
                SkillSelection(
                    skill_type="identity",
                    skill_id="finance-persona",
                    version="9.9.9",
                    reason="r",
                )
            ]
        )
        with self.assertRaises(Exception):
            self.composer.verify(bundle)

    def test_incomplete_bundle_without_notes_fails(self) -> None:
        bundle = self._bundle(
            [
                SkillSelection(
                    skill_type="identity",
                    skill_id="finance-persona",
                    version="1.0.0",
                    reason="r",
                )
            ]
        )
        with self.assertRaises(Exception):
            self.composer.verify(bundle)

    def test_conflicting_pair_fails_verification(self) -> None:
        """A bundle selecting both sides of a conflict edge must be rejected."""

        base = _registry()
        conflicting = CreatorSkill(
            skill_id="conflicting-review",
            skill_type="review",
            version="1.0.0",
            description="conflicts with the finance review skill",
            capabilities=("review.a", "review.b"),
            inputs=("i",),
            outputs=("o",),
            dependencies=(SkillDependency("finance-persona", "conflict"),),
            compatibility=SkillCompatibility(domains=("finance",)),
            provenance=SkillProvenance(
                source_kind="manual",
                source_ref="x",
                skill_version="1.0.0",
                generated_at="1970-01-01T00:00:00Z",
            ),
        )
        registry = SkillRegistry()
        for skill_id in base.ids():
            registry.register(base.resolve(skill_id), validate=False)
        registry.register(conflicting, validate=False)

        # Both sides present: the review slot holds the conflicting skill and the
        # identity slot holds its declared conflict partner.
        bundle = SkillBundle(
            bundle_id="bundle-conflict",
            request=CreatorRequest(domain="finance", platform="xiaohongshu"),
            selections=(
                SkillSelection("identity", "finance-persona", "1.0.0", "r"),
                SkillSelection("review", "conflicting-review", "1.0.0", "r"),
            ),
            provenance=SkillProvenance(
                source_kind="projection",
                source_ref="bundle-conflict",
                skill_version="1.0.0",
                generated_at="1970-01-01T00:00:00Z",
            ),
            notes=("partial",),
        )
        with self.assertRaises(SkillCompositionError) as ctx:
            SkillComposer(registry).verify(bundle)
        self.assertIn("conflict", str(ctx.exception))

    def test_a_conflict_partner_that_is_absent_does_not_fail(self) -> None:
        """A conflict edge only fires when its partner is actually selected."""

        base = _registry()
        conflicting = CreatorSkill(
            skill_id="conflicting-review",
            skill_type="review",
            version="1.0.0",
            description="conflicts with the finance review skill",
            capabilities=("review.a", "review.b"),
            inputs=("i",),
            outputs=("o",),
            dependencies=(SkillDependency("finance-persona", "conflict"),),
            compatibility=SkillCompatibility(),
            provenance=SkillProvenance(
                source_kind="manual",
                source_ref="x",
                skill_version="1.0.0",
                generated_at="1970-01-01T00:00:00Z",
            ),
        )
        registry = SkillRegistry()
        for skill_id in base.ids():
            registry.register(base.resolve(skill_id), validate=False)
        registry.register(conflicting, validate=False)

        bundle = SkillBundle(
            bundle_id="bundle-no-conflict",
            request=CreatorRequest(domain="finance", platform="xiaohongshu"),
            selections=(
                SkillSelection("review", "conflicting-review", "1.0.0", "r"),
            ),
            provenance=SkillProvenance(
                source_kind="projection",
                source_ref="bundle-no-conflict",
                skill_version="1.0.0",
                generated_at="1970-01-01T00:00:00Z",
            ),
            notes=("partial",),
        )
        checks = SkillComposer(registry).verify(bundle)
        self.assertEqual(checks["dependencies"], "PASS")


class BundleIdTests(unittest.TestCase):
    def test_bundle_id_is_stable(self) -> None:
        request = CreatorRequest(domain="finance", platform="xiaohongshu")
        first = compose_bundle_id(request, ())
        second = compose_bundle_id(request, ())
        self.assertEqual(first, second)

    def test_bundle_id_changes_with_the_domain(self) -> None:
        selections = ()
        a = compose_bundle_id(CreatorRequest(domain="finance", platform="web"), selections)
        b = compose_bundle_id(CreatorRequest(domain="tech", platform="web"), selections)
        self.assertNotEqual(a, b)

    def test_bundle_id_changes_with_the_platform(self) -> None:
        a = compose_bundle_id(CreatorRequest(domain="finance", platform="web"), ())
        b = compose_bundle_id(CreatorRequest(domain="finance", platform="bilibili"), ())
        self.assertNotEqual(a, b)

    def test_bundle_id_is_prefixed(self) -> None:
        self.assertTrue(
            compose_bundle_id(CreatorRequest(domain="finance", platform="web"), ()).startswith(
                "bundle-"
            )
        )

    def test_module_level_compose_uses_the_default_registry(self) -> None:
        result = compose(CreatorRequest(domain="finance", platform="xiaohongshu"))
        self.assertTrue(result.bundle.selections)

    def test_module_level_compose_accepts_a_registry(self) -> None:
        result = compose(
            CreatorRequest(domain="finance", platform="xiaohongshu"), registry=_registry()
        )
        self.assertTrue(result.bundle.selections)


if __name__ == "__main__":
    unittest.main()
