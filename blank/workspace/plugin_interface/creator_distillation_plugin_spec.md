# Creator Distillation Plugin Specification

Specification version: `1.0`

## Purpose

A Creator plugin contributes domain judgment to the framework's single
distillation run. It is not a second distillation stage and must not consume a
serialized generic artifact as a new source. The engine provides both the
original `RawSource` values and read-only common extraction signals, then merges
the contribution into one `UnifiedDistillationArtifact`.

## Required Python entrypoint

The plugin package must expose:

```python
def create_plugin() -> CreatorDistillationPlugin: ...
```

The returned object must implement the runtime-checkable protocol in
`plugin_interface.base`.

## 1. Plugin identity

`identity` returns `PluginIdentity` with four non-empty strings:

- `name`: stable machine-readable package name;
- `version`: plugin contract version (semantic versioning is recommended);
- `domain`: domain classification, such as `finance` or `education`;
- `creator_target`: Creator profile or reusable audience target. It must not
  encode credentials or account secrets.

## 2. Domain value judgment

The plugin declares and applies signals that deserve greater weight. The rules
must be inspectable under the plugin's `rules/` directory. Each enhancement
must retain source references and explain its matched rule.

For finance, examples include business mechanisms, data interpretation, and
company cases. These examples are plugin policy and are not core behavior.

## 3. Domain filtering rules

The plugin identifies content that should be down-ranked, constrained, or sent
to review. It must not silently delete a material claim. Each risk constraint
uses this minimum shape:

```json
{
  "rule_id": "stable-id",
  "severity": "info | warning | block",
  "action": "downrank | require_evidence | require_review | block",
  "message": "human-readable reason",
  "source_ids": ["source-id"]
}
```

For finance, investment instructions and unsupported predictions are expected
risks. The plugin does not provide investment advice.

## 4. Domain structure templates

Structure templates describe content organization, not finished content. A
template has a stable ID, ordered section intents, applicability conditions,
and optional required evidence. It belongs under the plugin's `rules/`
directory and is returned through `domain_extension` when selected.

## 5. Domain evaluation rules

Evaluation rules live under the plugin's `evaluation/` directory. The plugin
returns rule-level results in `evaluation_result`, including a numeric score,
checks, and any review requirement. Scores must be deterministic for identical
inputs unless the plugin explicitly documents an external evaluator.

## Contribution contract

`enhance(raw_sources, common_signals)` returns `PluginContribution`:

- `domain_extension`: plugin-owned structured values;
- `risk_constraints`: explicit risk decisions;
- `evaluation_result`: plugin quality evidence;
- `field_enhancements`: optional additions to `topic_candidate`,
  `content_template`, `knowledge_unit`, or `style_pattern`.

The plugin cannot remove or replace common signals. The engine rejects unknown
enhancement fields and validates the merged artifact against
`schemas/unified_distillation_artifact.json`.

## Side effects and failure behavior

- Distillation plugins must be deterministic and side-effect free by default.
- Network or model calls require a separately injected adapter and documented
  timeout/error contract.
- A plugin failure fails the run explicitly; it must not silently fall back to
  a misleading generic result.
- Plugins never publish content or mutate production accounts.

## Compatibility

- Plugins declare their own semantic version.
- Breaking changes to this specification require a new major specification
  version.
- A plugin must pass the shared conformance tests plus its domain tests before
  deployment.
