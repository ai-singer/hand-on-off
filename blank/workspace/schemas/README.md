# Schemas

`unified_distillation_artifact.json` is the public handoff contract between
distillation, generation adapters, evaluation, storage, and deployment. Change
it deliberately and version breaking changes. Plugin-private schemas belong in
their plugin package and cannot weaken this shared contract.
