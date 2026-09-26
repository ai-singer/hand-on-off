# Content Distillation Pipeline

Logical flow:

```text
raw material input
  -> one engine run [classification + common understanding + plugin enhancement]
  -> unified distillation artifact
  -> optional content-generation adapter
  -> quality check
```

The bracketed work is one orchestration boundary and emits no intermediate
generic artifact. The optional adapter allows a deployment to use a model,
template renderer, or human handoff without coupling it to distillation.
