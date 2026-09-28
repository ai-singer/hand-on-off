"""M4 benchmark: 80+ labeled cases over the grammar pipeline (phase 8).

Labels are produced **before** the algorithm runs and are independent of it:

* grammar and relation labels are declared alongside the corpus template that
  generated the image,
* invariant and strategy labels are declared per template family,
* negative labels state what must *not* happen.

Nothing here imports the extractor, the clustering package, or the strategy
module. A test checks that on the parsed syntax tree, because a benchmark that
inspects its own subject stops being a benchmark.

Five groups, as the brief requires: grammar extraction, relation extraction,
invariant discovery, creator strategy extraction, negative cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

#: Group names, fixed so reports compare across runs.
CASE_GROUPS: tuple[str, ...] = (
    "grammar_extraction",
    "relation_extraction",
    "invariant_discovery",
    "creator_strategy",
    "negative_cases",
)

#: Template id prefix -> the grammar regions and relations it must produce.
#:
#: Declared from the *template specification*, not from a pipeline run. These are
#: what the corpus paints, so they are ground truth by construction.
TEMPLATE_GRAMMAR_LABELS: Mapping[str, Mapping[str, Any]] = {
    "T01": {
        "regions": [
            {"region_type": "headline", "position_band": "top"},
            {"region_type": "supporting_information", "position_band": "center"},
            {"region_type": "subject", "position_band": "center"},
            {"region_type": "background", "position_band": "center"},
        ],
        "relations": [
            "background_encloses_all",
            "support_below_headline",
        ],
        "attention_lead": "headline",
    },
    "T02": {
        "regions": [
            {"region_type": "subject", "position_band": "top"},
            {"region_type": "headline", "position_band": "bottom"},
            {"region_type": "supporting_information", "position_band": "bottom"},
            {"region_type": "background", "position_band": "center"},
        ],
        "relations": [
            "background_encloses_all",
            "headline_below_subject",
        ],
        "attention_lead": "subject",
    },
    "T03": {
        "regions": [
            {"region_type": "headline", "position_band": "top"},
            {"region_type": "data_display", "position_band": "center"},
            {"region_type": "supporting_information", "position_band": "center"},
            {"region_type": "background", "position_band": "center"},
        ],
        "relations": ["background_encloses_all"],
        "attention_lead": "headline",
    },
    "T04": {
        "regions": [
            {"region_type": "subject", "position_band": "center"},
            {"region_type": "background", "position_band": "center"},
        ],
        "relations": ["subject_full_bleed"],
        "attention_lead": "subject",
    },
    "T05": {
        "regions": [
            {"region_type": "headline", "position_band": "top"},
            {"region_type": "data_display", "position_band": "center"},
            {"region_type": "supporting_information", "position_band": "bottom"},
            {"region_type": "background", "position_band": "center"},
        ],
        "relations": ["background_encloses_all"],
        "attention_lead": "headline",
    },
    "T06": {
        "regions": [
            {"region_type": "subject", "position_band": "top"},
            {"region_type": "branding", "position_band": "bottom"},
            {"region_type": "background", "position_band": "center"},
        ],
        "relations": ["subject_full_bleed"],
        "attention_lead": "subject",
    },
    "T07": {
        "regions": [
            {"region_type": "headline", "position_band": "top"},
            {"region_type": "data_display", "position_band": "center"},
            {"region_type": "supporting_information", "position_band": "bottom"},
            {"region_type": "background", "position_band": "center"},
        ],
        # The data block sits directly beneath the headline in this template; the
        # caption band is a supporting_information region, not a subtitle, so
        # ``data_above_caption`` — which requires a subtitle anchor — does not
        # hold. An earlier label asserted a relation the corpus geometry cannot
        # produce, which is a benchmark defect, not a detector failure.
        "relations": ["background_encloses_all"],
        "attention_lead": "headline",
    },
    "T08": {
        "regions": [
            {"region_type": "headline", "position_band": "top"},
            {"region_type": "supporting_information", "position_band": "center"},
            {"region_type": "background", "position_band": "center"},
        ],
        "relations": ["background_encloses_all", "support_below_headline"],
        "attention_lead": "headline",
    },
    "T09": {
        "regions": [
            {"region_type": "headline", "position_band": "top"},
            {"region_type": "supporting_information", "position_band": "center"},
            {"region_type": "background", "position_band": "center"},
        ],
        "relations": ["background_encloses_all", "support_below_headline"],
        "attention_lead": "headline",
    },
    "T10": {
        "regions": [
            {"region_type": "supporting_information", "position_band": "center"},
            {"region_type": "background", "position_band": "center"},
        ],
        "relations": ["background_encloses_all"],
        "attention_lead": "supporting_information",
    },
}

#: Template -> the strategy elements its family must distil.
TEMPLATE_STRATEGY_LABELS: Mapping[str, Mapping[str, Any]] = {
    "T01": {
        "attention_strategy": "headline_first",
        "information_hierarchy": ["hook", "explanation"],
        "composition_strategy": ["split_columns", "top_entry"],
    },
    "T02": {
        "attention_strategy": "subject_first",
        "information_hierarchy": ["hook", "explanation"],
        "composition_strategy": ["split_columns"],
    },
    "T03": {
        "attention_strategy": "headline_first",
        "information_hierarchy": ["hook", "evidence"],
        "composition_strategy": ["split_columns", "top_entry"],
    },
    "T04": {
        "attention_strategy": "subject_first",
        "information_hierarchy": ["hook"],
        "composition_strategy": ["full_bleed_subject"],
    },
    "T05": {
        "attention_strategy": "headline_first",
        "information_hierarchy": ["hook", "evidence"],
        "composition_strategy": ["top_entry"],
    },
    "T06": {
        "attention_strategy": "subject_first",
        "information_hierarchy": ["action"],
        "composition_strategy": ["full_bleed_subject"],
    },
    "T07": {
        "attention_strategy": "headline_first",
        "information_hierarchy": ["hook", "evidence"],
        "composition_strategy": ["top_entry"],
    },
    "T08": {
        "attention_strategy": "headline_first",
        "information_hierarchy": ["hook", "explanation"],
        "composition_strategy": ["top_entry"],
    },
    "T09": {
        "attention_strategy": "headline_first",
        "information_hierarchy": ["hook", "explanation"],
        "composition_strategy": ["top_entry", "stacked_information"],
    },
    "T10": {
        "attention_strategy": "headline_first",
        "information_hierarchy": ["explanation"],
        "composition_strategy": ["centred_information"],
    },
}

#: Invariants each template family must exhibit, with the minimum frequency the
#: label asserts. Declared from the template spec, before any run.
#:
#: Keys are ``<feature_family>:<feature>``, matching
#: :meth:`InvariantSet.frequency_of` exactly. An earlier version used bare feature
#: names, so every lookup returned 0.0 and ten cases failed for a labelling
#: mistake rather than a pipeline defect.
TEMPLATE_INVARIANT_LABELS: Mapping[str, tuple[tuple[str, float], ...]] = {
    "T01": (
        ("region_presence:background_present", 1.0),
        ("relation_presence:background_encloses_all", 1.0),
    ),
    "T02": (
        ("region_presence:background_present", 1.0),
        ("region_presence:subject_present", 1.0),
    ),
    "T03": (
        ("region_presence:background_present", 1.0),
        ("region_presence:data_display_present", 0.6),
    ),
    "T04": (
        ("region_presence:subject_present", 1.0),
        ("region_presence:background_present", 1.0),
    ),
    "T05": (
        ("region_presence:background_present", 1.0),
        ("region_presence:data_display_present", 0.6),
    ),
    "T06": (
        ("region_presence:subject_present", 1.0),
        ("region_presence:background_present", 1.0),
    ),
    "T07": (
        ("region_presence:background_present", 1.0),
        ("region_presence:data_display_present", 0.6),
    ),
    "T08": (
        ("region_presence:background_present", 1.0),
        ("region_presence:supporting_information_present", 0.6),
    ),
    "T09": (
        ("region_presence:background_present", 1.0),
        ("region_presence:supporting_information_present", 0.6),
    ),
    "T10": (
        ("region_presence:background_present", 1.0),
        ("region_presence:supporting_information_present", 0.6),
    ),
}

#: Negative assertions: things that must not happen.
NEGATIVE_EXPECTATIONS: tuple[Mapping[str, Any], ...] = (
    {
        "case_id": "negative-absent-region-is-not-invented",
        "assertion": "a grammar must not contain a region type absent from the image",
        "expectation": "no_invented_regions",
    },
    {
        "case_id": "negative-relation-is-not-invented",
        "assertion": "a grammar must not emit a relation between regions that do not both exist",
        "expectation": "no_dangling_relations",
    },
    {
        "case_id": "negative-no-single-score",
        "assertion": "a similarity vector must not expose a combined score field",
        "expectation": "no_combined_score",
    },
    {
        "case_id": "negative-pattern-carries-no-material",
        "assertion": "a strategy pattern must carry no colour value, path, or pixel data",
        "expectation": "no_material_in_pattern",
    },
    {
        "case_id": "negative-invariants-not-hand-specified",
        "assertion": "invariant discovery must not consult a hand-written pattern list",
        "expectation": "invariants_are_mined",
    },
    {
        "case_id": "negative-no-human-agreement-claim",
        "assertion": "agreement must refuse to compute with fewer than two human raters",
        "expectation": "agreement_requires_two_humans",
    },
    {
        "case_id": "negative-synthetic-not-real",
        "assertion": "a synthetic manifest must fail real-collection validation",
        "expectation": "synthetic_fails_real_check",
    },
    {
        "case_id": "negative-constraint-is-not-generative",
        "assertion": "the constraint prototype must not be generative",
        "expectation": "constraint_not_generative",
    },
    {
        "case_id": "negative-no-runtime-integration",
        "assertion": "no M4 module may import the distillation engine or runtime",
        "expectation": "no_runtime_integration",
    },
    {
        "case_id": "negative-layout-label-not-needed",
        "assertion": "strategy distillation must not read a layout class label",
        "expectation": "strategy_ignores_layout_label",
    },
)


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One labeled assertion about the M4 pipeline."""

    case_id: str
    group: str
    kind: str
    template_id: str
    sample_ids: tuple[str, ...]
    expected: Mapping[str, Any]
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "group": self.group,
            "kind": self.kind,
            "template_id": self.template_id,
            "sample_ids": list(self.sample_ids),
            "expected": dict(self.expected),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkDataset:
    """Corpus samples, their labels, and every benchmark case.

    ``width``/``height`` are carried so the M3 observation helper can render the
    corpus without M4 re-stating the frame size.
    """

    samples: tuple[Any, ...]
    templates: Mapping[str, Any]
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

    def describe(self) -> str:
        counts = ", ".join(
            f"{name}={count}" for name, count in sorted(self.group_counts().items())
        )
        return (
            f"M4 benchmark: {self.case_count} cases ({counts}) over "
            f"{len(self.samples)} rendered images and {len(self.templates)} templates"
        )


def build_dataset() -> BenchmarkDataset:
    """Assemble the labeled dataset and its cases.

    The corpus is M3's, reused deliberately: M4's claim is a *representation*
    change, so holding the images fixed isolates the effect of the representation
    from any change in the pictures.
    """

    from ..observation.corpus import CALIBRATION_REPEAT_PLAN, build_templates

    templates = build_templates()
    samples: list[Any] = []

    from ..observation.corpus import SampleSpec

    seed = 40000
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

    labels: dict[str, dict[str, Any]] = {}
    for sample in samples:
        prefix = sample.template_id[:3]
        labels[sample.sample_id] = {
            "sample_id": sample.sample_id,
            "template_id": sample.template_id,
            "template_prefix": prefix,
            "creator_id": sample.creator_id,
            "batch_id": sample.batch_id,
            "grammar": TEMPLATE_GRAMMAR_LABELS.get(prefix, {}),
            "strategy": TEMPLATE_STRATEGY_LABELS.get(prefix, {}),
            "invariants": TEMPLATE_INVARIANT_LABELS.get(prefix, ()),
        }

    cases = _build_cases(samples, labels)
    return BenchmarkDataset(
        samples=tuple(samples),
        templates=templates,
        labels=labels,
        cases=cases,
    )


def _by_prefix(samples: Sequence[Any], prefix: str) -> list[Any]:
    return [sample for sample in samples if sample.template_id.startswith(prefix)]


def _build_cases(
    samples: Sequence[Any], labels: Mapping[str, Mapping[str, Any]]
) -> tuple[BenchmarkCase, ...]:
    cases: list[BenchmarkCase] = []
    prefixes = sorted(TEMPLATE_GRAMMAR_LABELS)

    # -- group 1: grammar extraction (30) ---------------------------------
    # Three assertions per template: region set, region placement, region types.
    for index, prefix in enumerate(prefixes, start=1):
        pool = _by_prefix(samples, prefix)
        if not pool:
            continue
        grammar = TEMPLATE_GRAMMAR_LABELS[prefix]
        cases.append(
            BenchmarkCase(
                case_id=f"grammar-{index:02d}-{prefix}-regions",
                group="grammar_extraction",
                kind="grammar_regions",
                template_id=prefix,
                sample_ids=tuple(s.sample_id for s in pool),
                expected={"regions": list(grammar["regions"])},
                note="region types and vertical placement must be recovered",
            )
        )
        cases.append(
            BenchmarkCase(
                case_id=f"grammar-{index:02d}-{prefix}-types",
                group="grammar_extraction",
                kind="grammar_region_types",
                template_id=prefix,
                sample_ids=tuple(s.sample_id for s in pool),
                expected={
                    "region_types": sorted(
                        {item["region_type"] for item in grammar["regions"]}
                    )
                },
                note="every declared region type must appear",
            )
        )
        cases.append(
            BenchmarkCase(
                case_id=f"grammar-{index:02d}-{prefix}-no-invention",
                group="grammar_extraction",
                kind="grammar_no_invention",
                template_id=prefix,
                sample_ids=tuple(s.sample_id for s in pool),
                expected={
                    "allowed_types": sorted(
                        {item["region_type"] for item in grammar["regions"]}
                        | {"cta", "branding", "subtitle"}
                    )
                },
                note="the extractor may not invent region types outside the declared set",
            )
        )

    # -- group 2: relation extraction (20) --------------------------------
    # Two per template: required relations present, no dangling endpoints.
    for index, prefix in enumerate(prefixes, start=1):
        pool = _by_prefix(samples, prefix)
        if not pool:
            continue
        grammar = TEMPLATE_GRAMMAR_LABELS[prefix]
        cases.append(
            BenchmarkCase(
                case_id=f"relation-{index:02d}-{prefix}-expected",
                group="relation_extraction",
                kind="relation_expected",
                template_id=prefix,
                sample_ids=tuple(s.sample_id for s in pool),
                expected={"relations": list(grammar["relations"])},
                note="declared relations must be recovered",
            )
        )
        cases.append(
            BenchmarkCase(
                case_id=f"relation-{index:02d}-{prefix}-valid",
                group="relation_extraction",
                kind="relation_valid",
                template_id=prefix,
                sample_ids=tuple(s.sample_id for s in pool),
                expected={"relations": list(grammar["relations"])},
                note="endpoints must exist and types must come from the vocabulary",
            )
        )

    # -- group 3: invariant discovery (20) --------------------------------
    # Two per template: asserted frequencies met, and nothing hand-specified.
    for index, prefix in enumerate(prefixes, start=1):
        pool = _by_prefix(samples, prefix)
        if not pool:
            continue
        invariants = TEMPLATE_INVARIANT_LABELS[prefix]
        cases.append(
            BenchmarkCase(
                case_id=f"invariant-{index:02d}-{prefix}-frequencies",
                group="invariant_discovery",
                kind="invariant_frequency",
                template_id=prefix,
                sample_ids=tuple(s.sample_id for s in pool),
                expected={
                    "invariants": [
                        {"feature": feature, "min_frequency": frequency}
                        for feature, frequency in invariants
                    ]
                },
                note="mined frequencies must meet the declared minimum",
            )
        )
        cases.append(
            BenchmarkCase(
                case_id=f"invariant-{index:02d}-{prefix}-mined",
                group="invariant_discovery",
                kind="invariant_is_mined",
                template_id=prefix,
                sample_ids=tuple(s.sample_id for s in pool),
                expected={"must_be_mined": True},
                note="invariants must come from counting, not from a declared list",
            )
        )

    # -- group 4: creator strategy (20) -----------------------------------
    # Two per template: attention lead, and hierarchy subset.
    for index, prefix in enumerate(prefixes, start=1):
        pool = _by_prefix(samples, prefix)
        if not pool:
            continue
        strategy = TEMPLATE_STRATEGY_LABELS[prefix]
        cases.append(
            BenchmarkCase(
                case_id=f"strategy-{index:02d}-{prefix}-attention",
                group="creator_strategy",
                kind="strategy_attention",
                template_id=prefix,
                sample_ids=tuple(s.sample_id for s in pool),
                expected={"attention_strategy": strategy["attention_strategy"]},
                note="attention lead must match the declared strategy",
            )
        )
        cases.append(
            BenchmarkCase(
                case_id=f"strategy-{index:02d}-{prefix}-hierarchy",
                group="creator_strategy",
                kind="strategy_hierarchy",
                template_id=prefix,
                sample_ids=tuple(s.sample_id for s in pool),
                expected={
                    "required_stages": list(strategy["information_hierarchy"]),
                    "required_moves_any": list(strategy["composition_strategy"]),
                },
                note="hierarchy stages and at least one composition move must appear",
            )
        )

    # -- group 5: negative cases (10) -------------------------------------
    for expectation in NEGATIVE_EXPECTATIONS:
        cases.append(
            BenchmarkCase(
                case_id=str(expectation["case_id"]),
                group="negative_cases",
                kind=str(expectation["expectation"]),
                template_id="*",
                sample_ids=(),
                expected={"assertion": expectation["assertion"]},
                note="must not happen",
            )
        )

    return tuple(cases)


__all__ = [
    "CASE_GROUPS",
    "NEGATIVE_EXPECTATIONS",
    "TEMPLATE_GRAMMAR_LABELS",
    "TEMPLATE_INVARIANT_LABELS",
    "TEMPLATE_STRATEGY_LABELS",
    "BenchmarkCase",
    "BenchmarkDataset",
    "build_dataset",
]
