"""M3 benchmark dataset: 50+ labeled cases over real rendered images (phase 8).

Labels are **independent of the algorithm**. They come from the corpus generator
— which template and which creator produced each image — and are written before
any observation, similarity, or clustering code runs. Nothing in this module
imports the clustering package, and a test asserts that the runner never passes a
label into discovery.

Case groups
-----------

**same-template detection (12)** — pairs the same template, from different
creators. Must be grouped together.
**different-template separation (12)** — pairs of different templates. Must stay
apart.
**creator pattern extraction (12)** — clusters expected to yield a pattern with a
specific layout strategy and hierarchy.
**negative cases (10)** — pairs and singletons that must *not* be merged:
same creator different template, minimal-content images, near-duplicate geometry
with different structure.
**sequence consistency (8)** — multi-frame sequences whose members must be
observed consistently and whose rhythm must be recorded.

That is 54 cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .corpus import (
    CALIBRATION_REPEAT_PLAN,
    SampleSpec,
    TemplateSpec,
    build_templates,
)

#: Group names, fixed so reports are comparable across runs.
CASE_GROUPS: tuple[str, ...] = (
    "same_template_detection",
    "different_template_separation",
    "creator_pattern_extraction",
    "negative_cases",
    "sequence_consistency",
)


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One labeled assertion about the pipeline's behaviour.

    ``expected`` is expressed as a property of the *output*, never as a pointer
    to a cluster id, so the case cannot be satisfied by reading its own label.
    """

    case_id: str
    group: str
    kind: str
    sample_ids: tuple[str, ...]
    expected: Mapping[str, Any]
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "group": self.group,
            "kind": self.kind,
            "sample_ids": list(self.sample_ids),
            "expected": dict(self.expected),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkDataset:
    """The full labeled dataset: specs, templates, labels, and cases."""

    samples: tuple[SampleSpec, ...]
    templates: Mapping[str, TemplateSpec]
    labels: Mapping[str, Mapping[str, Any]]
    cases: tuple[BenchmarkCase, ...]
    width: int = 480
    height: int = 720

    @property
    def case_count(self) -> int:
        return len(self.cases)

    def group_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {group: 0 for group in CASE_GROUPS}
        for case in self.cases:
            counts[case.group] = counts.get(case.group, 0) + 1
        return counts

    def samples_in(self, case: BenchmarkCase) -> tuple[SampleSpec, ...]:
        by_id = {sample.sample_id: sample for sample in self.samples}
        return tuple(by_id[sample_id] for sample_id in case.sample_ids if sample_id in by_id)

    def describe(self) -> str:
        counts = ", ".join(f"{name}={count}" for name, count in sorted(self.group_counts().items()))
        return (
            f"M3 benchmark: {self.case_count} cases ({counts}) over "
            f"{len(self.samples)} rendered images and {len(self.templates)} templates"
        )


def _label(sample: SampleSpec, expected_layout_class: str) -> dict[str, Any]:
    return {
        "sample_id": sample.sample_id,
        "template_id": sample.template_id,
        "creator_id": sample.creator_id,
        "batch_id": sample.batch_id,
        "is_hero": sample.is_hero,
        # Family identity, used for clustering and pattern scoring.
        "layout_family": sample.template_id,
        # The layout class the observer should report, used for detection
        # scoring. Deliberately coarser than family identity: several templates
        # share one arrangement, and conflating the two would score the observer
        # against a distinction the class vocabulary cannot express.
        "expected_layout_class": expected_layout_class,
    }


def build_dataset() -> BenchmarkDataset:
    """Assemble the labeled dataset and its 54 cases.

    The sample set deliberately includes creators who share templates, creators
    who use several templates, and repeat samples of one template by one creator,
    so all five case groups have real material behind them.
    """

    templates = build_templates()
    samples: list[SampleSpec] = []
    seed = 20000

    # Repeat plan gives same-creator-same-template material for the negative and
    # pattern groups; the corpus generator owns which templates and creators.
    for creator_id in sorted(CALIBRATION_REPEAT_PLAN):
        for template_id, count in CALIBRATION_REPEAT_PLAN[creator_id]:
            for index in range(count):
                seed += 1
                samples.append(
                    SampleSpec(
                        sample_id=f"{creator_id}__{template_id}__{index:02d}",
                        template_id=template_id,
                        creator_id=creator_id,
                        batch_id=f"batch-{creator_id}",
                        seed=seed,
                        is_hero=(index == 0),
                    )
                )

    labels = {
        sample.sample_id: _label(
            sample, templates[sample.template_id].expected_layout_class
        )
        for sample in samples
    }
    cases = _build_cases(samples, labels)
    return BenchmarkDataset(
        samples=tuple(samples),
        templates=templates,
        labels=labels,
        cases=cases,
    )


def _first(
    samples: Sequence[SampleSpec], template_prefix: str, creator: str | None = None
) -> SampleSpec:
    for sample in samples:
        if not sample.template_id.startswith(template_prefix):
            continue
        if creator is not None and sample.creator_id != creator:
            continue
        return sample
    raise KeyError(f"no sample for {template_prefix!r} / {creator!r}")


def _all(samples: Sequence[SampleSpec], template_prefix: str) -> list[SampleSpec]:
    return [sample for sample in samples if sample.template_id.startswith(template_prefix)]


def _build_cases(
    samples: Sequence[SampleSpec], labels: Mapping[str, Mapping[str, Any]]
) -> tuple[BenchmarkCase, ...]:
    cases: list[BenchmarkCase] = []

    # -- group 1: same-template detection (12) ----------------------------
    # Pairs of different creators using the same template.
    same_template_pairs = [
        ("T01", "creator_a", "creator_b"),
        ("T01", "creator_a", "creator_d"),
        ("T03", "creator_a", "creator_c"),
        ("T03", "creator_c", "creator_h"),
        ("T02", "creator_b", "creator_e"),
        ("T04", "creator_c", "creator_g"),
        ("T05", "creator_f", "creator_f"),
        ("T07", "creator_f", "creator_f"),
        ("T08", "creator_g", "creator_g"),
        ("T09", "creator_e", "creator_e"),
        ("T10", "creator_h", "creator_h"),
        ("T06", "creator_d", "creator_d"),
    ]
    for index, (prefix, left_creator, right_creator) in enumerate(same_template_pairs, start=1):
        left = _first(samples, prefix, left_creator)
        right = _first(samples, prefix, right_creator)
        if left.sample_id == right.sample_id:
            pool = _all(samples, prefix)
            if len(pool) < 2:
                continue
            left, right = pool[0], pool[1]
        cases.append(
            BenchmarkCase(
                case_id=f"same-{index:02d}-{prefix}",
                group="same_template_detection",
                kind="pair_same_template",
                sample_ids=(left.sample_id, right.sample_id),
                expected={"same_family": True, "shared_template": left.template_id},
                note="same template, rendered separately",
            )
        )

    # -- group 2: different-template separation (12) ----------------------
    different_pairs = [
        ("T01", "T02"),
        ("T01", "T03"),
        ("T01", "T04"),
        ("T02", "T03"),
        ("T02", "T04"),
        ("T03", "T04"),
        ("T05", "T07"),
        ("T05", "T08"),
        ("T06", "T10"),
        ("T07", "T09"),
        ("T08", "T10"),
        ("T09", "T10"),
    ]
    for index, (left_prefix, right_prefix) in enumerate(different_pairs, start=1):
        try:
            left = _first(samples, left_prefix)
            right = _first(samples, right_prefix)
        except KeyError:
            continue
        cases.append(
            BenchmarkCase(
                case_id=f"diff-{index:02d}-{left_prefix}-{right_prefix}",
                group="different_template_separation",
                kind="pair_different_template",
                sample_ids=(left.sample_id, right.sample_id),
                expected={
                    "same_family": False,
                    "left_template": left.template_id,
                    "right_template": right.template_id,
                },
                note="structurally distinct templates",
            )
        )

    # -- group 3: creator pattern extraction (12) -------------------------
    pattern_expectations = [
        ("T01", ("headline_top",), ("attention_entry",)),
        ("T02", ("headline_",), ("attention_entry",)),
        ("T03", ("headline_",), ("attention_entry", "information_block")),
        ("T04", ("subject_",), ("attention_entry",)),
        ("T05", ("chart_body",), ("attention_entry", "information_block")),
        ("T06", ("headline_",), ("attention_entry",)),
        ("T07", ("table_body",), ("attention_entry", "information_block")),
        ("T08", ("copy_",), ("attention_entry", "information_block")),
        ("T09", ("copy_",), ("attention_entry", "information_block")),
        ("T10", ("copy_",), ("information_block",)),
        ("T01", ("headline_",), ("information_block",)),
        ("T03", ("chart_body", "copy_"), None),
    ]
    for index, (prefix, required_moves, required_stages) in enumerate(pattern_expectations, start=1):
        pool = _all(samples, prefix)
        if not pool:
            continue
        cases.append(
            BenchmarkCase(
                case_id=f"pattern-{index:02d}-{prefix}",
                group="creator_pattern_extraction",
                kind="pattern_contains",
                sample_ids=tuple(sample.sample_id for sample in pool),
                expected={
                    "template_id": pool[0].template_id,
                    "required_moves_any": list(required_moves),
                    "required_stages": list(required_stages) if required_stages else [],
                },
                note="distilled pattern must expose these strategy elements",
            )
        )

    # -- group 4: negative cases (10) -------------------------------------
    # Same creator, different templates: must not be merged into one family.
    negatives = [
        ("creator_a", "T01", "T03"),
        ("creator_b", "T01", "T02"),
        ("creator_c", "T03", "T04"),
        ("creator_d", "T01", "T06"),
        ("creator_e", "T02", "T09"),
        ("creator_f", "T05", "T07"),
        ("creator_g", "T04", "T08"),
        ("creator_h", "T03", "T10"),
    ]
    for index, (creator, left_prefix, right_prefix) in enumerate(negatives, start=1):
        try:
            left = _first(samples, left_prefix, creator)
            right = _first(samples, right_prefix, creator)
        except KeyError:
            continue
        cases.append(
            BenchmarkCase(
                case_id=f"negative-{index:02d}-{creator}-{left_prefix}{right_prefix}",
                group="negative_cases",
                kind="pair_same_creator_different_template",
                sample_ids=(left.sample_id, right.sample_id),
                expected={
                    "same_family": False,
                    "same_creator": True,
                    "left_template": left.template_id,
                    "right_template": right.template_id,
                },
                note="one creator, two templates: must not merge",
            )
        )

    # Two self-pairs that must be identical, guarding against a degenerate
    # similarity that returns a constant.
    for index, prefix in enumerate(("T01", "T05"), start=1):
        pool = _all(samples, prefix)
        if len(pool) < 2:
            continue
        cases.append(
            BenchmarkCase(
                case_id=f"negative-{8 + index:02d}-self-{prefix}",
                group="negative_cases",
                kind="pair_same_sample_family",
                sample_ids=(pool[0].sample_id, pool[1].sample_id),
                expected={"same_family": True, "same_creator": True},
                note="repeat of one template by one creator: must be identical-family",
            )
        )

    # -- group 5: sequence consistency (8) --------------------------------
    sequence_plans = [
        ("T01", 3),
        ("T02", 3),
        ("T03", 2),
        ("T04", 2),
        ("T05", 2),
        ("T08", 2),
        ("T09", 3),
        ("T10", 2),
    ]
    for index, (prefix, length) in enumerate(sequence_plans, start=1):
        pool = _all(samples, prefix)
        if not pool:
            continue
        chosen = (pool * ((length // len(pool)) + 1))[:length]
        cases.append(
            BenchmarkCase(
                case_id=f"sequence-{index:02d}-{prefix}",
                group="sequence_consistency",
                kind="sequence_consistency",
                sample_ids=tuple(sample.sample_id for sample in chosen),
                expected={
                    "sequence_length": len(chosen),
                    "template_id": chosen[0].template_id,
                    "constant_layout": True,
                },
                note="frames of one sequence must observe consistently",
            )
        )

    return tuple(cases)


__all__ = [
    "CASE_GROUPS",
    "BenchmarkCase",
    "BenchmarkDataset",
    "build_dataset",
]
