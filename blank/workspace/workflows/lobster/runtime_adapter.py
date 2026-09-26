"""JSON command adapter used by the executable Lobster workflow."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from config.runtime import load_runtime_config
from core import RawSource, load_plugin
from distillation_core import DistillationEngine
from evaluation import QualityGateController, evaluate_pipeline_output
from workflows.content_distillation_pipeline.generation_interface import (
    GenerationRequest,
)


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
    payload: Mapping[str, Any], config_path: str | Path | None = None
) -> dict[str, Any]:
    runtime = load_runtime_config(config_path)
    plugin = load_plugin(runtime.plugins.default)
    sources = [_raw_source(item) for item in payload.get("sources", [])]
    artifact = DistillationEngine(plugin).distill(sources)
    return {"artifact": artifact}


def verify_plugin_checkpoint(
    payload: Mapping[str, Any], config_path: str | Path | None = None
) -> dict[str, Any]:
    runtime = load_runtime_config(config_path)
    expected = load_plugin(runtime.plugins.default).identity
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
        _write_error("usage: runtime_adapter <source-input|distill|plugin-check|gate|generation-handoff>")
        return 2
    command = arguments[0]
    try:
        config_path = (
            os.environ.get("LOBSTER_ARG_RUNTIME_CONFIG")
            or os.environ.get("CREATOR_RUNTIME_CONFIG")
            or "config/runtime/default.json"
        )
        if command == "source-input":
            raw = os.environ.get("LOBSTER_ARG_SOURCES_JSON")
            payload = json.loads(raw) if raw else _read_stdin()
            result = normalize_source_input(payload)
        elif command == "distill":
            result = distill_payload(_read_stdin(), config_path)
        elif command == "plugin-check":
            result = verify_plugin_checkpoint(_read_stdin(), config_path)
        elif command == "gate":
            result = evaluate_gate(_read_stdin())
        elif command == "generation-handoff":
            result = build_generation_handoff(
                _read_stdin(),
                os.environ.get("LOBSTER_ARG_FORMAT_NAME", "content_plan"),
            )
        else:
            raise ValueError(f"unknown runtime adapter command: {command}")
    except Exception as exc:
        _write_error(f"{type(exc).__name__}: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


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
