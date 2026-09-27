"""JSON command adapter used by the executable Lobster workflow.

Initialization is owned entirely by :mod:`runtime.bootstrap`. This adapter no
longer parses the runtime configuration, constructs a plugin or discovers a
skill: it resolves a :class:`RuntimeContext` once per invocation and reads the
selected components from it, so there is exactly one initialization path.

The workflow schema, node order, command names and every input/output payload
shape are unchanged.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from core import RawSource
from distillation_core import DistillationEngine
from evaluation import QualityGateController, evaluate_pipeline_output
from runtime import RuntimeBootstrapError, RuntimeContext, bootstrap
from workflows.content_distillation_pipeline.generation_interface import (
    GenerationRequest,
)

#: Adapter command -> workflow node it implements. Used to fail closed when an
#: instance binds a workflow that does not declare the node being executed.
_COMMAND_NODES = {
    "source-input": "source_input",
    "distill": "unified_distillation",
    "plugin-check": "creator_plugin_enhancement",
    "gate": "quality_gate",
    "generation-handoff": "content_generation",
}

_USAGE = (
    "usage: runtime_adapter "
    "<source-input|distill|plugin-check|gate|generation-handoff>"
)


def resolve_context(
    config_path: str | Path | None = None,
    context: RuntimeContext | None = None,
) -> RuntimeContext:
    """Return the runtime context for this invocation.

    An explicitly supplied context is used as-is, so a caller that already
    initialized the runtime never re-reads configuration. Otherwise the
    runtime configuration is initialized through `bootstrap()`. This is the
    single place the adapter obtains components from.
    """

    if context is not None:
        return context
    return bootstrap(config_path)


def normalize_source_input(payload: Any) -> dict[str, Any]:
    values = payload.get("sources") if isinstance(payload, dict) else payload
    if not isinstance(values, list) or not values:
        raise ValueError("source input must be a non-empty array or sources envelope")
    sources = [_raw_source(item) for item in values]
    return {
        "sources": [
            {
                "source_id": source.source_id,
                "source_type": source.source_type.value,
                "content": source.content,
                "metadata": dict(source.metadata),
            }
            for source in sources
        ]
    }


def distill_payload(
    payload: Mapping[str, Any],
    config_path: str | Path | None = None,
    *,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime = resolve_context(config_path, context)
    # The plugin comes from the runtime context, so plugin selection is exactly
    # what the runtime configuration enabled and validated.
    plugin = runtime.default_plugin
    sources = [_raw_source(item) for item in payload.get("sources", [])]
    artifact = DistillationEngine(plugin).distill(sources)
    return {"artifact": artifact}


def verify_plugin_checkpoint(
    payload: Mapping[str, Any],
    config_path: str | Path | None = None,
    *,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime = resolve_context(config_path, context)
    expected = runtime.default_plugin.identity
    artifact = _artifact(payload)
    actual = artifact.get("plugin", {})
    if actual.get("name") != expected.name or actual.get("version") != expected.version:
        raise ValueError("artifact plugin identity does not match runtime configuration")
    return {"artifact": artifact}


def evaluate_gate(payload: Mapping[str, Any]) -> dict[str, Any]:
    artifact = _artifact(payload)
    report = evaluate_pipeline_output(artifact, None)
    gate = QualityGateController().decide(report)
    return {
        "artifact": artifact,
        "quality_report": gate.quality_report,
        "decision": gate.decision.value,
        "can_continue": gate.can_continue,
    }


def build_generation_handoff(
    payload: Mapping[str, Any], format_name: str = "content_plan"
) -> dict[str, Any]:
    if not payload.get("can_continue") or payload.get("decision") != "PASS":
        raise ValueError("generation handoff requires a PASS quality gate")
    request = GenerationRequest(
        artifact=_artifact(payload),
        format_name=format_name,
        constraints={},
    )
    return {
        "status": "ready_for_generation",
        "generation_request": {
            "artifact": dict(request.artifact),
            "format_name": request.format_name,
            "constraints": dict(request.constraints),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv or sys.argv[1:])
    if len(arguments) != 1:
        _write_error(_USAGE)
        return 2
    command = arguments[0]
    try:
        if command not in _COMMAND_NODES:
            raise ValueError(f"unknown runtime adapter command: {command}")
        config_path = (
            os.environ.get("LOBSTER_ARG_RUNTIME_CONFIG")
            or os.environ.get("CREATOR_RUNTIME_CONFIG")
            or "config/runtime/default.json"
        )
        # One initialization path: every command runs against a bootstrapped
        # context, so a broken runtime configuration stops the workflow at the
        # first node instead of half-running against defaults.
        context = bootstrap(config_path)
        _verify_workflow_binding(context, command)
        if command == "source-input":
            raw = os.environ.get("LOBSTER_ARG_SOURCES_JSON")
            payload = json.loads(raw) if raw else _read_stdin()
            result = normalize_source_input(payload)
        elif command == "distill":
            result = distill_payload(_read_stdin(), context=context)
        elif command == "plugin-check":
            result = verify_plugin_checkpoint(_read_stdin(), context=context)
        elif command == "gate":
            result = evaluate_gate(_read_stdin())
        else:
            result = build_generation_handoff(
                _read_stdin(),
                os.environ.get("LOBSTER_ARG_FORMAT_NAME", "content_plan"),
            )
    except Exception as exc:
        _write_error(f"{type(exc).__name__}: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def _verify_workflow_binding(context: RuntimeContext, command: str) -> None:
    """Fail closed when the bound workflow does not serve this command.

    The adapter implements specific nodes of the workflow selected by the
    runtime configuration. Executing a node the bound workflow never declares
    would mean running outside the workflow the runtime chose.
    """

    node_id = _COMMAND_NODES[command]
    if node_id not in context.workflow.steps:
        raise RuntimeBootstrapError(
            f"instance {context.instance!r} binds workflow "
            f"{context.workflow.name!r}, which does not declare node {node_id!r} "
            f"required by command {command!r}"
        )


def _raw_source(payload: Any) -> RawSource:
    if not isinstance(payload, dict):
        raise ValueError("each source must be an object")
    return RawSource(
        source_id=payload.get("source_id", ""),
        source_type=payload.get("source_type", ""),
        content=payload.get("content"),
        metadata=payload.get("metadata", {}),
    )


def _artifact(payload: Mapping[str, Any]) -> dict[str, Any]:
    artifact = payload.get("artifact")
    if not isinstance(artifact, dict):
        raise ValueError("payload must contain an artifact object")
    return dict(artifact)


def _read_stdin() -> Any:
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("expected JSON input on stdin")
    return json.loads(raw)


def _write_error(message: str) -> None:
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
