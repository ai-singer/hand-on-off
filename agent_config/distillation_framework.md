# Distillation Framework

Version: v1.0
Scope: Creator Agent System Layer
Status: Active

---

# Purpose

Define a universal distillation protocol for all virtual Creator Agents.

This framework is not specific to any industry, platform, or account style.
Individual Creators inherit this framework and extend it with domain-specific rules.

The framework answers three questions:

- What can be distilled from raw content?
- How should distillation be executed?
- What must the output look like?

---

# Distillation Philosophy

## Core Principle

Distillation extracts reusable patterns from raw content.
It does not replicate original content.

```
Raw Content
↓
Pattern Extraction
↓
Reusable Template
↓
Generation Rule
```

## What Distillation Learns

Allowed:

- Content structure and narrative order
- Hook mechanisms and opening strategies
- Explanation models and reasoning chains
- Information organization patterns
- Audience engagement methods
- Visual expression logic

Forbidden:

- Copying original sentences or paragraphs
- Reproducing creator personal experiences or opinions
- Extracting unverified facts as knowledge
- Imitating a single viral post without structural analysis
- Copying identity-specific content as transferable pattern

## Boundary Definition

| Layer | Belongs To | Distillation Allowed |
|-------|-----------|---------------------|
| Raw text / video | Source material | No — preserve original |
| Structural pattern | Distillation output | Yes — extract and abstract |
| Verified facts | Knowledge unit | Yes — with source attribution |
| Personal opinion | Creator identity | No — cannot be distilled |
| Platform-specific rules | Platform layer | No — defined separately |

---

# Source Classification

All input materials are classified into four types before distillation.

## A. Topic Source

Purpose:

- Discover user interest signals
- Extract high-distribution themes
- Identify user questions and cognitive conflicts

Typical inputs:

- Video titles with high engagement
- Comment threads with recurring questions
- Search keyword clusters
- Trending topic pools

Output:

```yaml
topic_candidate:
  topic:
  user_problem:
  cognitive_conflict:
  hook_signal:
  performance_signal:
```

## B. Structure Source

Purpose:

- Extract content frameworks
- Analyze narrative sequencing
- Analyze information organization patterns

Typical inputs:

- Long-form articles
- Image-text posts with high save rates
- Educational explainer content

Output:

```yaml
content_template:
  hook_pattern:
  opening_method:
  information_flow:
  section_organization:
  ending_strategy:
```

## C. Knowledge Source

Purpose:

- Provide verified facts
- Supply case references
- Deliver authoritative data

Typical inputs:

- Official reports and statistics
- Academic papers and research
- Institutional publications
- Verified industry data

Output:

```yaml
knowledge_unit:
  claim:
  source_url:
  source_type:
  verification_status:
  usable_as_evidence: true/false
```

## D. Style Source

Purpose:

- Analyze expression style
- Analyze language rhythm
- Analyze visual language

Typical inputs:

- Creator posts with consistent style signals
- High-engagement writing samples
- Visual content with strong format identity

Output:

```yaml
style_pattern:
  sentence_rhythm:
  paragraph_density:
  tone:
  visual_language:
  audience_address_mode:
```

---

# Distillation Pipeline

## Dual-Track System

All input materials follow one of two distillation tracks based on content type.

### Track 1: Topic Discovery (Video / Short-form)

Goal: `topic_candidate`

Input signals:

- Title
- Tags
- Comment themes
- Engagement distribution (liked / collected / share ratio)

Extraction targets:

| Signal | Extract |
|--------|---------|
| Title | Core topic, user pain point |
| Tags | Topic cluster, platform distribution context |
| Engagement | Transmission mechanism (which metric leads) |
| Comments | User questions, cognitive conflicts, knowledge gaps |

Do not extract:

- Factual claims from video content (not verified)
- Creator personal opinion or conclusions
- Platform trend signals as topic truth

Output:

```yaml
topic_candidate:
  topic:
  angle:
  mechanism:
  user_problem:
  cognitive_conflict:
  content_hook:
  transmission_driver: liked / collected / share / comment
  performance_tier: S / A / B / C
  source_note_id:
  extracted_at:
```

### Track 2: Knowledge + Structure Distillation (Image-Text / Long-form)

Goal: `content_template` + `knowledge_unit`

Input signals:

- Full text body
- Image organization
- Section structure
- Opening and closing patterns

Extraction targets:

| Layer | Extract |
|-------|---------|
| Structure | Opening method, section count, information order |
| Explanation | Reasoning chain, analogy usage, step-by-step logic |
| Cases | Case type, case function in argument, case position |
| Visual | Chart type, text overlay strategy, image-copy relationship |
| Ending | CTA type, emotion close, question close |

Output:

```yaml
content_template:
  hook_pattern:
    type: question / conflict / data / story / contrarian
    structure:
    example:

  content_structure:
    opening:
    main_sections:
    transitions:
    ending:

  information_flow:
    order: problem_first / solution_first / story_first
    density: high / medium / low
    cognitive_load: heavy / medium / light

  explanation_method:
    primary: analogy / mechanism / step-by-step / comparison
    secondary:

  case_strategy:
    case_type: real / hypothetical / historical
    case_position: opening / supporting / closing
    case_function: trust / illustration / proof

  visual_strategy:
    chart_type:
    text_overlay: title_only / caption / full_annotation
    image_copy_relationship: complement / repeat / independent

  ending_strategy:
    type: question / summary / action / emotional
    interaction_design:
```

---

# Extraction Rules

## Rule 1: Structural Abstraction

Every extracted pattern must be abstracted one level above the original content.

Wrong:
> "开头问'宁德时代为什么要上市？'"

Correct:
> "以用户正在思考的行业问题作为开篇 Hook"

## Rule 2: Pattern vs. Instance

Distillation captures the pattern, not the instance.

| Original | Distilled Pattern |
|----------|------------------|
| "我花了两年才明白..." | First-person experience opening that creates credibility gap |
| "90%的人都不知道..." | Contrarian knowledge gap hook |
| "先说结论：..." | Conclusion-first structure with delayed explanation |

## Rule 3: Minimum Sample Size

A structural pattern requires at least 3 independent observations before being recorded as a template.

Single viral post → observation, not template.
Three consistent patterns across different posts → template candidate.

## Rule 4: Source Tagging

Every distilled item must trace back to its source material.

```yaml
source_ref:
  note_ids: []
  collected_at:
  distilled_at:
  distiller: agent / human
```

## Rule 5: Fact Separation

Facts extracted during distillation must be immediately classified:

- Verified (source URL + institutional origin) → `knowledge_unit`, usable in generation
- Unverified (creator claim, no source) → discarded, not entered into knowledge base
- Contested → flagged, requires manual review before use

---

# Output Schema

All distillation results, regardless of track, must be stored in this unified schema.

```yaml
template_id: <uuid or slug>

source_type: video / image_text / article / transcript

content_goal: topic_discovery / knowledge_distillation / structure_distillation

target_audience:
  description:
  knowledge_level: general / intermediate / expert
  pain_point:

user_problem:
  surface:
  underlying:

core_insight:
  claim:
  mechanism:
  evidence_required: true / false

hook_pattern:
  type:
  structure:
  trigger_mechanism:

content_structure:
  opening:
  main_points: []
  transitions:
  ending:

information_flow:
  order:
  density:

explanation_method:
  primary:
  secondary:

case_strategy:
  type:
  position:
  function:

visual_strategy:
  chart_type:
  text_overlay:
  image_copy_relationship:

ending_strategy:
  type:
  interaction_design:

applicable_scenarios: []

limitations:
  do_not_use_when: []
  known_weaknesses: []

confidence: high / medium / low

source_ref:
  note_ids: []
  collected_at:
  distilled_at:
```

---

# Quality Evaluation

## Three-Dimensional Evaluation

High traffic alone does not qualify content for distillation.
Every distillation candidate is evaluated across three dimensions.

### Dimension 1: Performance Signal

Measures audience response.

| Metric | Weight | Notes |
|--------|--------|-------|
| Collected (saves) | High | Indicates lasting value |
| Shared | High | Indicates transmission potential |
| Comments | Medium | Quality weighted over quantity |
| Liked | Low | Passive engagement, lowest signal |

Account normalization required before cross-account comparison.
Use adjusted performance = raw performance ÷ account factor.

### Dimension 2: Structure Quality

Measures whether the content has intrinsic structural merit.

| Check | Pass Condition |
|-------|---------------|
| Cognitive conflict | Clear problem or tension established in opening |
| Explanation chain | Mechanism explained, not just described |
| Information organization | Logical flow, not random bullet list |
| Transferability signal | Structure could work for a different topic |

### Dimension 3: Transferability

Measures whether the pattern can be reused.

| Check | Pass Condition |
|-------|---------------|
| Topic independence | Pattern works beyond the original topic |
| Template formability | Can be expressed as a reusable rule |
| Long-term value | Pattern is not trend-dependent |

## Distillation Value Tiers

| Tier | Condition |
|------|-----------|
| High Value | Strong on all 3 dimensions |
| Medium Value | Strong on 2 of 3 dimensions |
| Low Value | Strong on 1 or fewer dimensions |

Low Value distillations are recorded for observation only.
They do not enter the active template library.

---

# Transfer Rules

## What Can Be Transferred

- Hook type and trigger mechanism
- Content structure and section logic
- Explanation method and reasoning chain
- Case type and positioning strategy
- Visual organization pattern
- Ending and interaction design

## What Cannot Be Transferred

- Creator's personal story or identity
- Platform-specific algorithm assumptions
- Topic-specific facts without source verification
- Emotional resonance tied to a specific cultural moment
- Any pattern observed only once

## Cross-Creator Transfer

A template distilled from Creator A can be used by Creator B if:

- The template is fully abstracted (no A-specific content)
- The template has been validated on minimum 3 observations
- Creator B's domain rules do not prohibit the pattern

---

# Limitations

## Known Constraints

- Distillation cannot replace evidence sourcing. Structural patterns do not generate facts.
- High-save content from niche accounts may not transfer to general audiences.
- Video distillation without transcript is limited to title + tag signal only.
- Style patterns are the most fragile — they degrade fastest across cultural contexts.

## Scope Boundaries

This framework does not define:

- Industry-specific content rules (defined in Creator domain config)
- Platform-specific formatting (defined in platform review rules)
- Publishing permissions and review requirements
- Visual generation rules
- Specific account voice or persona

---

# Integration Interface

## Upstream Input

```
source_material/
  xhs/{category}/video/{note_id}/meta.json      → Track 1 (Topic Discovery)
  xhs/{category}/image_text/{note_id}.json      → Track 2 (Structure + Knowledge)
  evidence-sources/{vertical}.md                → Knowledge Source
```

## Downstream Output

```
template_library/
  content_templates/{template_id}.yaml          → content_template
  metadata/topic_candidates/{note_id}.yaml      → topic_candidate
  metadata/knowledge_units/{unit_id}.yaml       → knowledge_unit
  metadata/style_patterns/{pattern_id}.yaml     → style_pattern
```

## Interface Contract with text_generation.md

`text_generation.md` consumes:

```yaml
# Required inputs from distillation
topic_candidate:        # From Track 1 — defines what to write about
  topic:
  angle:
  user_problem:
  content_hook:

content_template:       # From Track 2 — defines how to write it
  hook_pattern:
  content_structure:
  explanation_method:
  case_strategy:
  ending_strategy:

knowledge_unit[]:       # From Knowledge Source — provides evidence
  claim:
  source_url:
  verification_status:
```

`text_generation.md` must not proceed to final draft without:

- At least one `topic_candidate` (defines direction)
- At least one `content_template` (defines structure)
- At least one verified `knowledge_unit` (provides evidence base)

If any input is missing, the generation step produces outline only, not publishable content.

---

# Version

v1.0 — 2026-09-22

Scope: Creator Agent System Layer
Creator-specific extensions: defined in `agent_config/` per Creator
