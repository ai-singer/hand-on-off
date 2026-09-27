"""Risk-boundary recall measurement for the xiaolin_finance plugin.

The plugin's risk rules are keyword based, so isolated unit tests prove the
mechanism works but say nothing about whether real phrasing is caught. A
prohibited statement that never matches a keyword reaches generation
unblocked — that is a recall failure, and it is the dangerous direction.

This module measures recall against a documented probe set and splits it by
probe kind, because the two halves answer different questions:

- **keyword probes** contain a literal rule keyword. They check the matching
  mechanism, and should be caught.
- **paraphrase probes** express the same prohibited intent with wording the
  rules never enumerate. They measure the semantic gap, and they are the real
  risk baseline.

Reporting a single blended recall hides which of the two is failing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from core import RawSource, SourceType, load_plugin
from distillation_core import DistillationEngine


_PACKAGE_ROOT = Path(__file__).resolve().parent
_PLUGIN_ROOT = _PACKAGE_ROOT.parent / "plugins" / "xiaolin_finance"
DEFAULT_PLUGIN = "plugins.xiaolin_finance"


@dataclass(frozen=True, slots=True)
class Probe:
    category: str
    text: str


#: Prohibited statements a finance creator could plausibly publish. Every probe
#: is written for this test; no real material is collected or reproduced.
PROHIBITED_PROBES: tuple[Probe, ...] = (
    # investment advice
    Probe("investment_advice", "You should buy this stock today."),
    Probe("investment_advice", "I recommend adding this company to your portfolio."),
    Probe("investment_advice", "Sell everything before the quarter ends."),
    Probe("investment_advice", "立即买入这只股票。"),
    Probe("investment_advice", "This is a guaranteed buy at the current price."),
    # market prediction
    Probe("market_prediction", "The share price will definitely double next year."),
    Probe("market_prediction", "Analysts are certain the price target will be reached."),
    Probe("market_prediction", "This stock is going to 500 by December."),
    Probe("market_prediction", "必然上涨，目标价翻倍。"),
    Probe("market_prediction", "The market will crash next month."),
    # emotional language
    Probe("emotional_language", "Everyone is buying, do not miss out!"),
    Probe("emotional_language", "This is a total disaster and you should panic."),
    Probe("emotional_language", "The market is collapsing right now, get out!"),
    Probe("emotional_language", "恐慌情绪蔓延，赶紧上车。"),
    Probe("emotional_language", "This opportunity is insane, you would be crazy to skip it."),
    # unverified fact
    Probe("unverified_fact", "A rumor says the company will be acquired."),
    Probe("unverified_fact", "Someone said the CEO is resigning."),
    Probe("unverified_fact", "Internal news suggests earnings will triple."),
    Probe("unverified_fact", "Word on the street is that revenue is fake."),
    Probe("unverified_fact", "据说不具名消息人士透露，公司将重组。"),
)

#: Statements that must NOT be flagged. They measure the false-positive cost of
#: keyword matching, which pushes legitimate material into manual review.
CLEAN_PROBES: tuple[Probe, ...] = (
    Probe("clean", "The income statement shows how revenue converts into margin."),
    Probe("clean", "This is not a guaranteed return, and the material explains why."),
    Probe("clean", "The report describes the cost structure without recommending any action."),
    Probe("clean", "Quarterly cash flow grew while the ratio stayed stable."),
    Probe("clean", "A common misunderstanding is that revenue equals profit."),
)


@dataclass(frozen=True, slots=True)
class RecallReport:
    total_prohibited: int
    detected_prohibited: int
    keyword_probes: int
    keyword_detected: int
    paraphrase_probes: int
    paraphrase_detected: int
    clean_probes: int
    clean_flagged: int
    per_category: Mapping[str, tuple[int, int]]
    missed: tuple[Probe, ...]
    false_positives: tuple[Probe, ...]

    @property
    def recall(self) -> float:
        return _ratio(self.detected_prohibited, self.total_prohibited)

    @property
    def keyword_recall(self) -> float:
        return _ratio(self.keyword_detected, self.keyword_probes)

    @property
    def paraphrase_recall(self) -> float:
        """Recall on phrasing the rules never enumerate — the risk baseline."""

        return _ratio(self.paraphrase_detected, self.paraphrase_probes)

    @property
    def false_positive_rate(self) -> float:
        return _ratio(self.clean_flagged, self.clean_probes)

    def render(self) -> str:
        lines = [
            f"prohibited probes      : {self.detected_prohibited}/{self.total_prohibited}"
            f"  (recall {self.recall:.0%})",
            f"  keyword probes       : {self.keyword_detected}/{self.keyword_probes}"
            f"  (recall {self.keyword_recall:.0%})",
            f"  paraphrase probes    : {self.paraphrase_detected}/{self.paraphrase_probes}"
            f"  (recall {self.paraphrase_recall:.0%})  <- risk baseline",
            f"clean probes flagged   : {self.clean_flagged}/{self.clean_probes}"
            f"  (false positive rate {self.false_positive_rate:.0%})",
            "per category           :",
        ]
        for category, (detected, total) in sorted(self.per_category.items()):
            lines.append(f"  {category:20} {detected}/{total}")
        return "\n".join(lines)


def _ratio(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def rule_keywords() -> tuple[str, ...]:
    """Every literal keyword the plugin's filter rules declare."""

    payload = json.loads(
        (_PLUGIN_ROOT / "rules" / "filter_rules.json").read_text(encoding="utf-8")
    )
    return tuple(
        str(keyword)
        for rule in payload["rules"]
        for keyword in rule["keywords"]
    )


def contains_literal_keyword(text: str, keywords: Sequence[str] | None = None) -> bool:
    normalized = text.lower()
    return any(
        keyword.lower() in normalized
        for keyword in (keywords if keywords is not None else rule_keywords())
    )


def _flagged_categories(plugin: Any, text: str) -> set[str]:
    artifact = DistillationEngine(plugin).distill(
        [
            RawSource(
                source_id="recall-probe",
                source_type=SourceType.DOCUMENT,
                content=text,
            )
        ]
    )
    return {item["category"] for item in artifact["risk_constraints"]}


def measure_risk_recall(plugin: Any | None = None) -> RecallReport:
    """Measure risk-boundary recall and false positives on the probe sets."""

    active_plugin = plugin if plugin is not None else load_plugin(DEFAULT_PLUGIN)
    keywords = rule_keywords()

    detected = 0
    keyword_probes = 0
    keyword_detected = 0
    paraphrase_probes = 0
    paraphrase_detected = 0
    per_category: dict[str, list[int]] = {}
    missed: list[Probe] = []

    for probe in PROHIBITED_PROBES:
        flagged = probe.category in _flagged_categories(active_plugin, probe.text)
        counters = per_category.setdefault(probe.category, [0, 0])
        counters[1] += 1
        if flagged:
            detected += 1
            counters[0] += 1
        else:
            missed.append(probe)

        if contains_literal_keyword(probe.text, keywords):
            keyword_probes += 1
            keyword_detected += int(flagged)
        else:
            paraphrase_probes += 1
            paraphrase_detected += int(flagged)

    false_positives: list[Probe] = []
    for probe in CLEAN_PROBES:
        if _flagged_categories(active_plugin, probe.text):
            false_positives.append(probe)

    return RecallReport(
        total_prohibited=len(PROHIBITED_PROBES),
        detected_prohibited=detected,
        keyword_probes=keyword_probes,
        keyword_detected=keyword_detected,
        paraphrase_probes=paraphrase_probes,
        paraphrase_detected=paraphrase_detected,
        clean_probes=len(CLEAN_PROBES),
        clean_flagged=len(false_positives),
        per_category={name: (counts[0], counts[1]) for name, counts in per_category.items()},
        missed=tuple(missed),
        false_positives=tuple(false_positives),
    )


def main() -> int:
    report = measure_risk_recall()
    print(report.render())
    print()
    print("missed probes:")
    for probe in report.missed:
        print(f"  [{probe.category}] {probe.text}")
    if report.false_positives:
        print()
        print("clean probes wrongly flagged:")
        for probe in report.false_positives:
            print(f"  {probe.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
