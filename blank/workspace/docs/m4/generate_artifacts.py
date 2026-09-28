"""Generate M4 measurement artifacts: manifest, benchmark report, agreement report.

Run from the workspace root::

    python _m4_artifacts.py
"""

from __future__ import annotations

import json
from pathlib import Path

from multimodal_creator.dataset.human_eval import (
    Rating,
    Rater,
    build_rating_packet,
    compute_agreement,
    write_agreement_report,
)
from multimodal_creator.dataset.provenance import (
    DatasetManifest,
    synthetic_manifest,
    write_manifest,
)
from multimodal_creator.grammar.benchmark_runner import run_benchmark, write_report

OUT = Path("_m4_artifacts")
OUT.mkdir(exist_ok=True)

# ---------------------------------------------------------------- benchmark
report = run_benchmark(workdir=Path(".m4cache"))
write_report(report, OUT / "m4_benchmark_report.json")
print(f"benchmark: {report.passed}/{report.total} cases")
print(report.run.evaluation.render())

# ---------------------------------------------------------------- manifest
dataset = report.run.dataset
creator_by_sample = {
    sample.sample_id: sample.creator_id for sample in dataset.samples
}
manifest = synthetic_manifest(
    [sample.sample_id for sample in dataset.samples],
    creator_ids=creator_by_sample,
    dataset_id="m4-synthetic-grammar-corpus",
)
write_manifest(manifest, OUT / "dataset_manifest.json")
print()
print(manifest.render())

# Real-collection check must fail on a synthetic manifest. This is the guard
# that stops the report claiming real-world validation it does not have.
try:
    manifest.assert_real_collection(minimum=20)
except Exception as exc:  # noqa: BLE001 - the failure is the expected outcome
    print(f"real-collection check correctly refused: {type(exc).__name__}")
    print(f"  reason: {exc}")
else:
    raise SystemExit("ERROR: synthetic manifest passed the real-collection check")

# ------------------------------------------------------- rating packet
items = []
for cluster in report.run.clusters[:8]:
    record = report.run.grammar_for(cluster.member_ids[0])
    items.append(
        {
            "item_id": cluster.cluster_id[:60],
            "image_reference": record.sample_id,
            "grammar_summary": " | ".join(
                f"{r.region_type}@{r.position_band}/{r.column_band}"
                for r in record.grammar.regions
            ),
            "strategy_summary": (
                f"attention={cluster.strategy.attention_strategy} "
                f"hierarchy={list(cluster.strategy.information_hierarchy)} "
                f"composition={list(cluster.strategy.composition_strategy)}"
            ),
        }
    )
packet = build_rating_packet(items, output_path=OUT / "rating_packet.json")
print()
print(f"rating packet: {len(packet['items'])} items written")

# --------------------------------------------------- provisional agreement
# PROVISIONAL FIXTURE RATERS. These are not humans. They exist so the agreement
# machinery is exercised and its output shape is checked; the report must not
# present this as human agreement.
fixture_raters = [
    Rater("fixture-a", "synthetic_fixture", "placeholder for a real human rater"),
    Rater("fixture-b", "synthetic_fixture", "placeholder for a real human rater"),
]
ratings: list[Rating] = []
for index, item in enumerate(items):
    # Deterministic, mildly disagreeing fixture so both metrics and
    # disagreement cases are exercised.
    first = "yes" if index % 3 != 0 else "no"
    second = "yes" if index % 4 != 0 else "no"
    ratings.append(
        Rating("fixture-a", item["item_id"], first, "yes", "fixture")
    )
    ratings.append(
        Rating("fixture-b", item["item_id"], second, "yes", "fixture")
    )

fixture_report = compute_agreement(
    ratings, fixture_raters, require_human=False
)
write_agreement_report(fixture_report, OUT / "agreement_report.json")
print()
print(f"fixture agreement (NOT human): {fixture_report.overall_agreement:.3f}")
print(f"is_human_agreement: {fixture_report.is_human_agreement}")

# And prove the human requirement actually bites.
try:
    compute_agreement(ratings, fixture_raters, require_human=True)
except Exception as exc:  # noqa: BLE001 - expected
    print(f"human requirement correctly refused fixture raters: {type(exc).__name__}")
else:
    raise SystemExit("ERROR: fixture raters were accepted as human evidence")

print()
print("wrote:", sorted(p.name for p in OUT.iterdir()))
