# Lobster deployment workflow

The content_distillation.lobster file is the executable OpenClaw/Lobster
mapping. node_contracts.json records the required purpose, input, output,
dependency, and failure behavior for the same ordered nodes.

The creator_plugin_enhancement node is a checkpoint, not a second distillation
pass. Plugin enhancement is produced inside the preceding single
DistillationEngine invocation, preserving the framework protocol.

The template has no production generation implementation. Its final node emits
a validated GenerationRequest handoff only after the quality gate returns PASS;
an instance-owned adapter consumes that request.
