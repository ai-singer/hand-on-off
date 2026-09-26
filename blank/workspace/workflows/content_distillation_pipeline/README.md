# Content Distillation Pipeline

Logical flow:

```text
raw material input
  -> one engine run [classification + common understanding + plugin enhancement]
  -> unified distillation artifact
  -> quality check
  -> optional content-generation adapter only on PASS
```

The bracketed work is one orchestration boundary and emits no intermediate
generic artifact. QualityGateController turns evaluation into control flow:
FAIL stops before generation, while PASS may invoke the injected adapter. The
adapter boundary allows a deployment to use a model, template renderer, or
human handoff without coupling it to distillation.
