# Creator Production Loop

Phase 6.5.1. The end-to-end path a Creator Agent instance runs to turn raw
material into production-ready output, and which layer owns each stage.

```text
Raw Material
   |
   v  [Runtime]        ingestion adapter (instance-owned)
Source Adapter
   |
   v  [Universal]      core.models.RawSource contract
RawSource
   |
   v  [Universal]      distillation_core: classifier + CommonExtractor
Universal Distillation  -> topic_candidate, content_template,
   |                       knowledge_unit, style_pattern
   v  [Creator Specific]  plugins/<name>: rules + rubric
Creator Plugin Enhancement -> domain_extension, risk_constraints,
   |                          evaluation_result, field_enhancements
   v  [Universal + Domain] schema_validation
Artifact Validation  -> one UnifiedDistillationArtifact
   |
   v  [Universal + Domain] evaluation/ + plugin rubric
Quality Evaluation   -> common score, domain score, risk constraints
   |
   v  [Runtime]        quality gate decides
Generation Contract  -> GenerationRequest
   |
   v  [Runtime]        injected generation adapter
Content Production
```

## 1. Stage ownership

| # | Stage | Layer | Owner in this template |
| --- | --- | --- | --- |
| 1 | Raw Material | outside the template | instance |
| 2 | Source Adapter | **Runtime** (implementation) / **Universal** (contract) | ingestion is instance-owned; the contract is `core/models.py` |
| 3 | RawSource | **Universal** | `core/models.py` |
| 4 | Universal Distillation | **Universal** | `distillation_core/` (`classifier.py`, `extractor.py`, `engine.py`) |
| 5 | Creator Plugin Enhancement | **Creator Specific** | `plugins/<name>/` (`plugin.py` + `rules/` + `evaluation/`) |
| 6 | Artifact Validation | **Universal** + **Creator Specific** | `schema_validation/`, `core/schema_validation.py`, plugin private schema |
| 7 | Quality Evaluation | **Universal** + **Creator Specific** | `evaluation/` (common) + plugin `evaluation/rubric.json` (domain) |
| 8 | Generation Contract | **Runtime** | `workflows/content_distillation_pipeline/generation_interface.py` |
| 9 | Content Production | **Runtime** | an injected `GenerationAdapter`; the template ships none |

### Universal Layer

Domain-neutral and must never require a domain change:

- the `RawSource` contract and its four source kinds (`video`, `document`,
  `data`, `image`);
- classification and the four common signal families;
- the single-run distillation engine and artifact assembly;
- the shared artifact schema;
- the common evaluation and the quality gate.

### Creator Specific Layer

Owns domain judgement only, and only inside `plugins/<name>/`:

- which material deserves amplification (`rules/value_rules.json`);
- which claims are constrained, reviewed or blocked (`rules/filter_rules.json`);
- how content is organised (`rules/structure_templates.json`);
- the private `domain_extension` shape and its schema;
- domain scoring policy and checks (`evaluation/rubric.json`).

The Creator layer **adds**. It cannot remove or replace a common signal, and it
never runs a second distillation pass.

### Runtime Layer

Owns instance identity and wiring, not domain judgement:

- `runtime/` — bootstrap, config validation, plugin/skill/workflow selection;
- `workflows/lobster/` — the executable workflow and its JSON command adapter;
- `artifact/` — deployment artifact manifest and validation;
- `production/` — generation-input projection and risk-recall measurement;
- the generation adapter itself, which is injected per instance.

## 2. What "one loop" means

Four properties make this a single loop rather than parallel pipelines:

1. **One input contract.** Every source kind enters as `RawSource`. There is no
   text pipeline, video pipeline or data pipeline — the kind is data on one
   envelope, and the adapter kind called "text" maps to `document`.
2. **One distillation run.** `DistillationEngine.distill()` calls the plugin
   once and returns exactly one artifact. A completed artifact is never fed
   into a second domain pass.
3. **One artifact.** Every run produces the same nine sections regardless of
   source kind.
4. **One gate.** Content generation can only run after the quality gate returns
   PASS. There is no path that bypasses it.

## 3. Where a stage can fail, and what happens

| Stage | Failure | Behaviour |
| --- | --- | --- |
| Source Adapter | unknown `source_type` | `InvalidSourceError`; the run does not start |
| Universal Distillation | no sources, duplicate `source_id` | `ValueError`; no artifact |
| Creator Plugin | bad rules, failed construction | explicit failure; no generic fallback |
| Artifact Validation | shared or private schema violation | `ArtifactValidationError` before the gate |
| Quality Evaluation | domain score below `pass_score`, or a blocking risk | `review_required`; generation is not invoked |
| Generation Contract | artifact missing an addressed input | reported as incomplete before generating |
| Content Production | adapter error | surfaces to the caller; the template has no adapter of its own |

## 4. Reading the loop with the runtime

```python
from runtime import bootstrap
from distillation_core import DistillationEngine
from workflows.content_distillation_pipeline import ContentDistillationPipeline
from production.generation_input import resolve_generation_input

context = bootstrap()                                    # Runtime layer
pipeline = ContentDistillationPipeline(
    DistillationEngine(context.default_plugin)           # Universal + Creator
)
result = pipeline.run(sources)                           # -> one artifact
inputs = resolve_generation_input(result.artifact)       # Generation contract
```

`RuntimeContext` already resolved the plugin, skills and workflow from the
instance configuration, so nothing in the loop re-reads configuration.

## 5. Related documents

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — framework boundaries
- [`CREATOR_SPECIFIC_PLUGIN_CONTRACT.md`](CREATOR_SPECIFIC_PLUGIN_CONTRACT.md) — plugin contract
- [`PLUGIN_INTERFACE_COMPATIBILITY.md`](PLUGIN_INTERFACE_COMPATIBILITY.md) — interface and forbidden areas
- [`CREATOR_PRODUCTION_READINESS_REPORT.md`](CREATOR_PRODUCTION_READINESS_REPORT.md) — validation evidence, readiness and limits
