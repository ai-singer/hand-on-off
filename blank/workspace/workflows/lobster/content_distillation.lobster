{
  "name": "creator-agent-content-distillation",
  "args": {
    "sources_json": {
      "default": "[]"
    },
    "runtime_config": {
      "default": "config/runtime/default.json"
    },
    "format_name": {
      "default": "content_plan"
    }
  },
  "steps": [
    {
      "id": "source_input",
      "command": "python -m workflows.lobster.runtime_adapter source-input"
    },
    {
      "id": "unified_distillation",
      "command": "python -m workflows.lobster.runtime_adapter distill",
      "stdin": "$source_input.json"
    },
    {
      "id": "creator_plugin_enhancement",
      "command": "python -m workflows.lobster.runtime_adapter plugin-check",
      "stdin": "$unified_distillation.json"
    },
    {
      "id": "quality_gate",
      "command": "python -m workflows.lobster.runtime_adapter gate",
      "stdin": "$creator_plugin_enhancement.json"
    },
    {
      "id": "content_generation",
      "command": "python -m workflows.lobster.runtime_adapter generation-handoff",
      "stdin": "$quality_gate.json",
      "condition": "$quality_gate.json.can_continue"
    }
  ]
}
