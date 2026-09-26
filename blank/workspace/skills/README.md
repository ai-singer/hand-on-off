# Versioned skills

Every skill is a self-contained directory with:

- `SKILL.md`: human/agent operating instructions;
- `manifest.json`: stable name, semantic version, entrypoint, capabilities, and
  focused test command;
- optional implementation and fixture files owned by that skill.

`core.skill_registry.discover_skills()` loads metadata only. This keeps skill
discovery side-effect free and lets a deployment select capabilities without
importing unrelated tools. Shared farm skills may be mounted or packaged here
as long as they satisfy the same manifest contract.

## Deployment adapter layers

- internal/ contains a catalog that points to the unchanged framework Skills.
- openclaw/ contains OpenClaw-compatible wrappers with hyphenated names,
  dependency metadata, runtime requirements, entrypoints, and test commands.

The wrappers translate deployment conventions only. They do not change the
internal Skill instructions or the distillation and plugin contracts.
