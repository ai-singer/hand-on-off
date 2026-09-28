"""Generate M5 profile artifacts from the M4 benchmark run.

Run from the workspace root: python docs/m5/generate_profiles.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("M3_BENCHMARK_CACHE", "1")

from multimodal_creator.grammar.benchmark_runner import run_benchmark
from multimodal_creator.profile import (
    PROFILE_VERSION,
    factory_config,
    pattern_to_profile,
    validation_summary,
    write_profile_bundle,
    write_schema,
)

OUT = Path(__file__).resolve().parent
CACHE = Path(".m5cache")
CACHE.mkdir(exist_ok=True)
PROFILES = OUT / "profiles"
PROFILES.mkdir(exist_ok=True)

# The schema the profile documents conform to.
schema_path = write_schema(OUT / "visual_creator_profile.schema.json")
print(f"schema written: {schema_path.name}")

report = run_benchmark(workdir=CACHE)
run = report.run
print(f"M4 run: {report.passed}/{report.total} benchmark cases, {len(run.clusters)} clusters")

grammar_by_id = {record.sample_id: record.grammar for record in run.grammars}
summaries: list[dict] = []
written: list[dict] = []

for index, cluster in enumerate(run.clusters):
    creator_ids = sorted(
        {
            run.grammar_for(sample_id).creator_id
            for sample_id in cluster.member_ids
            if run.grammar_for(sample_id).creator_id
        }
    )
    creator_id = creator_ids[0] if creator_ids else f"unattributed-{index:02d}"
    grammars = [
        grammar_by_id[sample_id]
        for sample_id in cluster.member_ids
        if sample_id in grammar_by_id
    ]
    if not grammars:
        continue

    profile = pattern_to_profile(
        creator_id=creator_id,
        patterns=[cluster.strategy],
        grammars=grammars,
        constraints=[cluster.constraints],
    )

    bundle = write_profile_bundle(profile, PROFILES)
    written.append(bundle.as_dict())
    summaries.append(
        {
            "profile_id": profile.profile_id,
            "creator_id": profile.creator_id,
            "support": profile.support,
            "confidence": profile.confidence,
            "style_family": profile.visual_identity.style_family,
            "visual_language": profile.visual_identity.visual_language,
            "complexity": profile.visual_identity.complexity,
            "preferred_layout": list(profile.composition_rules.preferred),
            "forbidden_layout_count": len(profile.composition_rules.forbidden),
            "attention": dict(profile.attention_strategy.order),
            "hierarchy": dict(profile.hierarchy_pattern.tiers),
            "must_have_count": len(profile.constraints.must_have),
            "avoid": list(profile.constraints.avoid),
            "validation": validation_summary(profile)["checks"],
        }
    )
    print(
        f"  {profile.creator_id:<12} {profile.profile_id} "
        f"lang={profile.visual_identity.visual_language:<16} "
        f"complexity={profile.visual_identity.complexity:<7} "
        f"conf={profile.confidence:.2f}"
    )

# One factory config as an illustrative example of the consumption shape.
if summaries:
    example = pattern_to_profile(
        creator_id=run.grammar_for(run.clusters[0].member_ids[0]).creator_id,
        patterns=[run.clusters[0].strategy],
        grammars=[
            grammar_by_id[sid]
            for sid in run.clusters[0].member_ids
            if sid in grammar_by_id
        ],
        constraints=[run.clusters[0].constraints],
    )
    (OUT / "example_factory_config.json").write_text(
        json.dumps(factory_config(example), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print("example factory config written")

report_payload = {
    "schema": "m5_profile_generation/v1",
    "profile_version": PROFILE_VERSION,
    "m4_benchmark": {
        "cases_passed": report.passed,
        "cases_total": report.total,
        "clusters": len(run.clusters),
    },
    "profiles_generated": len(summaries),
    "profiles": summaries,
    "written": written,
}
(OUT / "profile_generation_report.json").write_text(
    json.dumps(report_payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
)
print(f"profiles generated: {len(summaries)}")
print("wrote:", sorted(p.name for p in OUT.iterdir()))
