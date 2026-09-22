# Visual Prompt Templates
# Finance Vertical — XHS Image-Text Posts
# Distilled from: 6 S/A-tier posts visual pattern analysis
# Version: v1.0 | 2026-09-22

---

# Visual Pattern Observations

## Structural Patterns (from metadata analysis)

| Post Type | Image Count | Aspect Ratio | Dominant Visual Type |
|-----------|------------|--------------|----------------------|
| 产业链拆解 | 6–9 张 | 3:4 (1792×2400) | 流程图 + 层级图谱 |
| 反直觉框架 | 7 张 | 3:4 (1242×1660) | 文字卡片 + 图示 |
| 知识大白话 | 4–6 张 | 3:4 (1242×1660) | 知识卡片（术语→解释） |
| 清单框架 | 4 张 | 3:4 (1280×1707) | 分类图表 + 案例列表 |
| 工具实用 | 5 张 | 3:4 (1086×1448) | 截图式/公式展示卡 |

## Universal Visual Constants
- 全部为竖版 3:4 比例
- 背景以纯色或低噪浅色为主（知识类不用复杂背景）
- 文字为主要信息载体，图示辅助说明
- 封面图信息密度最高，后续图递进展开

---

# Prompt Template A: Industry Chain Diagram (产业链图谱型)

**Usage:** Template A — 产业链拆解型内容

## Cover Image (封面/图1)

```
Vertical infographic poster, 3:4 ratio, clean white or very light gray background.

Title text at top: "[行业名称]产业链" in bold Chinese, large font, dark charcoal color.
Subtitle: "上游 / 中游 / 下游" structure label.

Main visual: Three-tier vertical flow diagram.
- Top tier (上游): labeled boxes with arrow pointing down, light blue fill.
- Middle tier (中游): labeled boxes, medium blue fill.
- Bottom tier (下游): labeled boxes, deep blue or teal fill.

Each box contains: role name + 1-line function description.
Arrows between tiers show value/money flow direction.

Style: flat design, no shadows, clean sans-serif Chinese font.
Color palette: white background, #1A1A2E dark text, #4A90D9 blue accent, #E8F4FD light fill.
Bottom: small logo placeholder + series number "NO.{N}".
```

## Detail Images (图2–N，每层详细展开)

```
Vertical card, 3:4 ratio, light background (#F8FAFB).

Header bar: colored stripe at top (matching tier color), tier label in white bold text.
Left side: role/participant name in large bold font.
Right side: bullet list of revenue streams or key functions (3–5 items).
Bottom: one key data point or case name in highlighted box.

Style: structured, grid-aligned, high information density but visually organized.
Font: bold headers, regular body text, consistent hierarchy.
```

---

# Prompt Template B: Knowledge Card Series (知识卡片系列型)

**Usage:** Template C — 知识大白话型 / Template E — 工具实用型

## Cover Image (封面)

```
Vertical poster, 3:4 ratio, warm white or very pale yellow background (#FFFDF5).

Top area: emoji icon (🔥 or ⚡) + main title in bold dark text, 2 lines max.
Tagline below title: value promise in smaller font, contrasting color.

Center area: preview grid showing 4–6 mini card thumbnails arranged in 2×3 layout,
each mini card showing one term + one-word plain language translation.

Bottom strip: "共{N}个概念" count badge + save/bookmark icon hint.

Style: warm, approachable, not corporate. Slight texture on background acceptable.
Color palette: #2D2D2D text, #FF6B35 accent (warm orange), #FFF9F0 background.
```

## Knowledge Card (内容图，每图一个概念)

```
Vertical card, 3:4 ratio, clean white background.

Top left: card number badge "[01]" in colored circle.
Main area, top half: 
  - Term name in large bold font (专业词)
  - Horizontal divider line
Main area, bottom half:
  - Plain language translation in medium font, left-aligned
  - 1–2 line analogy or memory trick in lighter gray text
  - Optional: small icon or simple illustration related to the concept

Bottom strip: light gray bar with topic tags.

Style: textbook-clean but friendly. No complex backgrounds.
Color palette: white background, #1C1C1E primary text, #007AFF blue for term highlight,
#8E8E93 gray for secondary text.
```

---

# Prompt Template C: Framework Card Series (框架卡片系列型)

**Usage:** Template B — 反直觉框架型 / Template D — 清单框架型

## Cover Image (封面)

```
Vertical poster, 3:4 ratio, dark background (#1A1A2E or #0D1B2A).

Large bold title in white, 2 lines, centered or left-aligned.
Subtitle in smaller accent-colored text (orange or cyan) below title.

Center: abstract geometric diagram suggesting framework structure
(e.g., overlapping circles, arrow grid, or matrix preview).
Diagram is decorative — details shown in following cards.

Bottom: horizontal rule + "共{N}维度" or "{N}大模块" label in light text.

Style: premium, editorial, high contrast. Dark mode aesthetic.
Color palette: #0D1B2A background, #FFFFFF primary text, #FF9500 or #00D2FF accent.
```

## Framework Detail Card (维度/模块展开图)

```
Vertical card, 3:4 ratio.

Top: dimension number + dimension title in large bold text.
Large background number (e.g., "01") in very light opacity behind content for depth.

Content area:
  Left column: "闲于 / 避免" label + what to avoid (2–3 bullet points)
  Right column: "忙在 / 专注" label + what to focus on (2–3 bullet points)
  Or: single column flow if not contrast-based.

Bottom: one-line key takeaway in highlighted box or underline.

Style: structured, dual-column where applicable, clean grid.
Color palette: white background, dark headers, accent color for column labels.
Consistent accent color across all cards in series.
```

---

# Prompt Template D: Infographic Summary (信息图汇总型)

**Usage:** Single-image dense content / Template D 图1全景图

## Full Landscape Overview Card

```
Vertical infographic, 3:4 ratio, light gray background (#F5F5F7).

Title at top: large bold text, dark.
Subtitle: classification or scope description.

Main body: grid or matrix layout.
- {N} cells arranged in rows (2–3 per row)
- Each cell: category icon or number + name + 1-line description + 1 example
- Cells separated by thin grid lines

Bottom: summary row highlighting most important pattern or trend.

Style: dense but organized. Magazine infographic style.
Color coding: each category uses a unique accent color for its cell header.
Font: bold for category names, regular for descriptions, small for examples.
```

---

# Universal Visual Rules

## Aspect Ratio
**Always 3:4 vertical.** Recommended pixel sizes:
- Standard: 1242 × 1660
- High-res: 1792 × 2400
- Compact: 1080 × 1440

## Typography Hierarchy
```
Level 1 (Title):     Bold, 48–64px equivalent, dark (#1A1A2E or white on dark)
Level 2 (Section):   SemiBold, 32–40px, accent color or dark
Level 3 (Body):      Regular, 24–28px, mid-gray (#3C3C43)
Level 4 (Caption):   Light, 18–22px, light-gray (#8E8E93)
```

## Color Palette System

### Light Mode (知识/工具型)
```
Background:   #FFFFFF or #F8FAFB
Primary text: #1C1C1E
Accent:       #007AFF (blue) or #FF6B35 (orange)
Secondary:    #8E8E93
Divider:      #E5E5EA
```

### Dark Mode (框架/分析型)
```
Background:   #0D1B2A or #1A1A2E
Primary text: #FFFFFF
Accent:       #FF9500 (orange) or #00D2FF (cyan)
Secondary:    #8E8E93
Highlight:    rgba(255,149,0,0.15)
```

### Industry Chain Mode (产业链型)
```
Background:   #FFFFFF
Tier 1 (上游): #E8F4FD + #4A90D9 text
Tier 2 (中游): #E3F2FD + #1565C0 text
Tier 3 (下游): #E8EAF6 + #283593 text
Arrow:        #90CAF9
```

## Image Count Guidelines

| Template | Recommended Image Count | Logic |
|----------|------------------------|-------|
| 产业链拆解 | 6–9 张 | 1 overview + 1 per tier + detail cards |
| 反直觉框架 | 5–7 张 | 1 cover + 1 per dimension |
| 知识大白话 | 4–8 张 | 1 cover + 1 per concept |
| 清单框架 | 3–5 张 | 1 overview + category details |
| 工具实用 | 3–6 张 | 1 per tool/formula |

## What NOT to Include in Prompts
- Real brand logos or trademarks
- Real person faces or portraits
- Stock market charts or price graphs (risk content)
- Any specific investment return numbers
- News screenshots or media logos
