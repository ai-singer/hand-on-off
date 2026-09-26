# Blank Instance Analysis

## 1. Scope and inspection method

The `blank/` directory was inspected before framework implementation. At the
time of inspection it contained one file only:

```text
blank/
└── openclaw-backup-20260922.tar.gz
```

The archive was listed and its text files were read in place. It was not
extracted or modified during analysis.

## 2. Current structure

The backup contains an OpenClaw workspace seed:

```text
workspace/
├── .openclaw/
│   └── workspace-state.json
├── baidu-search/
│   └── SKILL.md
├── gemini_image/
│   └── SKILL.md
├── ocf_update/
│   └── SKILL.md
├── AGENTS.md
├── BOOTSTRAP.md
├── HEARTBEAT.md
├── IDENTITY.md
├── SOUL.md
├── TOOLS.md
└── USER.md
```

### Agent configuration

- `AGENTS.md` defines the generic OpenClaw workspace startup sequence,
  memory behavior, safety boundaries, group-chat behavior, heartbeat behavior,
  and tool/skill conventions.
- `SOUL.md`, `IDENTITY.md`, and `USER.md` are generic identity and user-context
  templates. They contain no Creator-specific configuration.
- `.openclaw/workspace-state.json` only records bootstrap seed state.

### Skill configuration

- `baidu-search/SKILL.md` describes an internal Baidu search integration.
- `gemini_image/SKILL.md` describes Gemini image generation/editing.
- `ocf_update/SKILL.md` describes OpenClaw Farm skill updates.
- These skills are operational capabilities, not a Creator Agent framework.
  They currently live as top-level workspace folders rather than behind a
  versioned framework skill registry.

### Prompt and workflow

- `SOUL.md`, `BOOTSTRAP.md`, and parts of `AGENTS.md` act as generic behavioral
  prompts.
- No Creator distillation prompt, source-classification prompt, domain plugin
  contract, content-production workflow, or quality gate exists.
- `HEARTBEAT.md` is an empty template and is unrelated to content production.

### Environment and deployment

- No dependency manifest, runtime contract, environment-variable template,
  container definition, packaging script, health check, or deployment guide is
  present.
- The only deployable-looking artifact is the backup archive itself. Its
  creation process and target runtime contract are not documented.

## 3. Reusable parts

1. **OpenClaw workspace convention**: the `workspace/` root and standard
   `AGENTS.md`, `SOUL.md`, `USER.md`, `TOOLS.md`, `HEARTBEAT.md`, and
   `.openclaw/workspace-state.json` layout provide a valid instance envelope.
2. **Skill packaging precedent**: each existing capability has a self-contained
   `SKILL.md` with name, version, description, operating steps, and failure
   behavior. This is a useful compatibility reference for framework skills.
3. **Safety guidance**: the current `SOUL.md` and `AGENTS.md` emphasize privacy,
   explicit confirmation for external actions, and non-destructive behavior.
4. **Backup artifact**: `openclaw-backup-20260922.tar.gz` is a recovery and
   comparison point and should remain immutable.

## 4. Parts to replace or extend

1. Add an explicit Creator Agent package structure for core contracts,
   one-pass distillation, plugin interfaces, domain plugins, workflows,
   schemas, evaluation, and tests.
2. Replace generic bootstrap-only behavior in the deployable template with a
   Creator-oriented `AGENTS.md` that preserves the useful safety boundaries.
3. Move reusable Creator capabilities behind independently versioned skill
   packages rather than coupling them to one account or one domain.
4. Add a machine-readable unified distillation artifact schema and validate all
   core/plugin output against the same contract.
5. Add a plugin loader and registry so changing domains does not require
   changing the common core.
6. Add a deterministic reference workflow and quality gate. Model-backed
   generation remains an adapter boundary, not a hard-coded dependency.
7. Add deployment documentation and a reproducible packaging script for the
   OpenClaw Farm workspace artifact.

## 5. Risks

| Risk | Impact | Mitigation in this task |
| --- | --- | --- |
| Backup-only source provides no executable Creator baseline | Architecture could accidentally be invented without deployment compatibility | Preserve the archive; use its `workspace/` envelope and Skill conventions as compatibility anchors |
| Existing skills may depend on secrets in `~/.openclaw/openclaw.json` | Tests or deployments could leak or require real credentials | Keep framework tests deterministic and offline; do not copy credentials or invoke external services |
| Generic `AGENTS.md` allows broad autonomous behavior | A production Creator could exceed content-production scope | Provide a scoped template agent contract with explicit input/output and side-effect boundaries |
| Domain policy leaking into the core | Every new Creator would require core changes | Define a plugin protocol; keep Xiaolin finance rules inside its plugin package |
| Two-stage distillation reappearing through workflow composition | Error accumulation and incompatible artifacts | Use one engine invocation that combines common extraction and plugin enhancement before producing one artifact |
| Schema drift across plugins | Downstream generation becomes fragile | Require every plugin to return the same `domain_extension` and evaluation contribution shapes; validate at the workflow boundary |
| “Deployment-ready” being confused with production credentials/configuration | Unsafe or false-ready release | Provide packaging and environment contracts only; keep secrets and production activation outside the repository |
| Sample finance plugin being mistaken for investment advice | Compliance and trust risk | Add explicit evidence, prediction, and investment-advice constraints and quality checks |

## 6. Implementation direction

The new template will be created under `blank/workspace/`, matching the backup's
deployable workspace root while keeping `blank/openclaw-backup-20260922.tar.gz`
unchanged. The framework will use a single-pass orchestration model:

```text
RawSource
  -> common classification and extraction
  -> plugin enhancement within the same engine run
  -> UnifiedDistillationArtifact
  -> generation adapter
  -> quality evaluation
```

The first implementation will be dependency-light and deterministic so its
contracts can be tested locally and later connected to production model,
storage, transcription, OCR, and media-processing adapters.
