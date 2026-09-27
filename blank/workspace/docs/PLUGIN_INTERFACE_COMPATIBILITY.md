# Plugin Interface Compatibility

Phase 6.1 reference for the Creator Distillation Plugin contract as it exists in
this template. It records what a plugin may rely on, what it must produce, and
what must not change.

Sources of truth:

| Artifact | Role |
| --- | --- |
| `plugin_interface/base.py` | Runtime-checkable protocol |
| `plugin_interface/creator_distillation_plugin_spec.md` | Normative specification, version `1.0` |
| `distillation_core/engine.py` | The only caller of a plugin |
| `schemas/unified_distillation_artifact.json` | The shared output contract |

## 1. Plugin lifecycle

```text
load_plugin(module_path)                 core/plugin_loader.py
  |-- importlib.import_module(module_path)
  |-- module.create_plugin()             zero-argument factory
  |-- isinstance(plugin, CreatorDistillationPlugin)   runtime-checkable
  |-- identity completeness check (name, version, domain, creator_target)
  v
plugin instance
  |
  |-- identity                          read by the engine and by the runtime adapter
  |-- enhance(raw_sources, common_signals)   called once per distillation run
  v
PluginContribution -> merged into one artifact -> schema validation -> quality gate
```

Key lifecycle facts:

1. **One invocation, one artifact.** `DistillationEngine.distill()` calls
   `enhance()` exactly once. A plugin is not a second distillation stage and
   must never receive a serialized artifact as a new source.
2. **Construction is an integration boundary.** Anything raised from
   `create_plugin()` is wrapped into `PluginLoadError` by the loader.
3. **The plugin is not asked to validate itself.** The engine validates the
   merged artifact against the shared schema and, when
   `plugins/<name>/schemas/domain_extension.schema.json` exists, against the
   plugin's private schema.
4. **Failure is explicit.** A plugin failure fails the run; it must not fall
   back to a generic result.
5. **No side effects.** Distillation plugins are deterministic and side-effect
   free by default. Network or model calls require a separately injected adapter
   with a documented timeout and error contract.

## 2. Input format

`enhance(raw_sources, common_signals)` receives two arguments.

### 2.1 `raw_sources: Sequence[RawSource]`

The original inputs, unchanged. `RawSource` (in `core/models.py`) carries
`source_id`, `source_type` (`video` | `document` | `data` | `image`), `content`,
and `metadata`.

### 2.2 `common_signals: Mapping[str, Sequence[Mapping[str, Any]]]`

A **deep copy** of the common extraction, keyed by the four artefact families:

| Family | Item shape |
| --- | --- |
| `topic_candidate` | `label`, `rationale`, `source_ids`, `confidence`, `origin` |
| `content_template` | `name`, `sections`, `source_ids`, `origin` |
| `knowledge_unit` | `statement`, `evidence_refs[{source_id, source_type}]`, `confidence`, `origin` |
| `style_pattern` | `name`, `attributes`, `source_ids`, `origin` |

The copy is read-only in effect: mutating it does not change the artifact. The
plugin reads it for context and must not depend on being able to write it.

**This is where "RawSource classification results" reach the plugin.** The
common extractor has already classified the material into those four families;
the plugin adds domain judgement on top rather than re-classifying from scratch.

## 3. Output format

`enhance()` returns `PluginContribution` (in `plugin_interface/base.py`):

| Field | Type | Contract |
| --- | --- | --- |
| `domain_extension` | `Mapping[str, Any]` | Plugin-owned structured values. Merged verbatim into `artifact.domain_extension`. |
| `risk_constraints` | `Sequence[Mapping]` | Explicit risk decisions. Each item requires `rule_id`, `severity` (`info`/`warning`/`block`), `action` (`downrank`/`require_evidence`/`require_review`/`block`), `message`, `source_ids`. |
| `evaluation_result` | `Mapping[str, Any]` | Domain quality evidence. Merged into `artifact.evaluation_result.domain`. |
| `field_enhancements` | `Mapping[str, Sequence[Mapping]]` | **Optional additions** to `topic_candidate`, `content_template`, `knowledge_unit`, or `style_pattern`. |

Hard rules enforced by the engine:

- `field_enhancements` keys outside the four families raise `ValueError`;
- additions are **appended** to the common lists — a plugin cannot remove or
  replace a common signal;
- the merged artifact must satisfy `schemas/unified_distillation_artifact.json`;
- when a private schema exists it is applied to `domain_extension` after the
  shared schema passes, and a failure stops the run before the quality gate.

## 4. Extension points

| Extension point | Location | Freedom |
| --- | --- | --- |
| Domain value judgement | plugin `rules/` | Which signals deserve more weight |
| Domain risk rules | plugin `rules/` | Which claims are constrained, reviewed or blocked |
| Structure templates | plugin `rules/` | How content is organised (never finished prose) |
| `domain_extension` | plugin `schemas/domain_extension.schema.json` | Any shape; it is an open object in the shared schema |
| Domain evaluation | plugin `evaluation/rubric.json` | Deterministic scoring policy |
| Field additions | `field_enhancements` | Append-only additions to the four common families |

A plugin may only **add**. The shared artifact's common families, the quality
gate, the distillation engine and the runtime bootstrap are not extension
points.

## 5. Areas that must not be modified by a plugin

| Area | Why |
| --- | --- |
| `distillation_core/` | Common extraction and the single-run engine are domain-neutral |
| `plugin_interface/` | Changing the protocol breaks every other plugin |
| `schemas/unified_distillation_artifact.json` | The shared contract is what makes artifacts interchangeable |
| `evaluation/` | Quality policy shared by all plugins |
| `runtime/`, `artifact/`, `workflows/`, `security/` | Framework services outside the plugin boundary |
| `core/` | Plugins may import its public contracts (`core.models.RawSource`) and nothing else |

A plugin declares its own semantic version. A breaking change to the plugin
specification requires a new major specification version.

## 6. Compatibility statement for this template

```text
Specification version : 1.0
Implemented by        : plugins/xiaolin_finance (plugin 1.1.0)
Private schema        : schemas/domain_extension.schema.json (1.1.0)
Conformance           : tests/test_framework.py, tests/stabilization/, tests/finance_plugin/
```

Adding or removing `plugins/xiaolin_finance` requires no change to `core/`,
`distillation_core/`, `evaluation/` or the shared schema. This is verified
behaviourally: `tests/finance_plugin/test_xiaolin_finance_contract.py` runs the
same sources through the finance plugin and through a domain-free plugin and
asserts that `knowledge_unit`, `content_template` and `style_pattern` are
identical, and that `topic_candidate` is only appended to.
