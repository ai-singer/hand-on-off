# OpenClaw Runtime 能力分析文档

> 生成时间：2026-09-28 07:59 UTC
> 分析范围：OpenClaw Runtime 完整能力矩阵、三层架构分类、自动配置可行性评估

---

## A. Runtime 能力清单

以下列出 OpenClaw Runtime 当前具备的全部核心能力。

### 1. 会话与生命周期管理

| 能力 | 说明 |
|------|------|
| 多 Session 管理 | 每个 Agent 拥有独立 sessions 目录，存储为 `.jsonl` 格式 |
| Session 压缩 | 支持 `session:compact:before/after` hook，自动在 Token 上限前压缩上下文 |
| 自动 Memory Flush | Compaction 前自动触发记忆刷写，防止上下文丢失 |
| Session 持久化 | SQLite 存储 sessions.json，重启不丢失 |
| 命名 Session | 支持 `session:<id>` 指定执行目标 |

### 2. 调度与自动化

| 能力 | 说明 |
|------|------|
| Cron 调度 | 三种调度类型：at（一次性）、every（固定间隔）、cron（表达式） |
| 心跳机制 | 默认间隔 30 分钟，支持 tasks 块独立 interval |
| 执行模式 | main / isolated / current / session:<id> 四种模式 |
| Webhook 触发 | Cron 任务可配置 webhook 外部触发 |
| Command Payload | 支持非模型执行的直接脚本命令 |
| 持久化存储 | SQLite 持久化，gateway 重启后自动恢复 |

### 3. 记忆系统

| 能力 | 说明 |
|------|------|
| 三层记忆结构 | MEMORY.md（长期精炼）+ memory/YYYY-MM-DD.md（每日工作）+ DREAMS.md（可选梦境） |
| 自动记忆刷写 | Compaction 前自动触发 memory flush |
| Dreaming 后台整合 | 可选后台进程，自动促进高质量记忆到 MEMORY.md |
| 语义搜索 | `memory_search` 工具，支持 hybrid（向量 + 关键词） |
| 多后端支持 | builtin(SQLite)、QMD（本地first）、Honcho（跨 session AI 记忆）、LanceDB |
| Memory Wiki 插件 | 结构化知识库层 |

### 4. Skill 系统

| 能力 | 说明 |
|------|------|
| 6 层加载优先级 | workspace → .agents/skills → ~/.agents/skills → ~/.openclaw/skills → bundled → extraDirs |
| Bundled Skills | 52 个内置技能，覆盖开发调试、媒体处理、任务管理等 |
| Managed Skills | 用户通过 clawhub 安装的技能，存放于 ~/.openclaw/skills/ |
| Workspace Skills | 最高优先级，直接在工作区 skills/ 目录 |
| Skill Workshop | 提案/审批/变更/废弃流程，支持 proposal 生命周期管理 |
| 按需加载 | 匹配描述时自动读取 SKILL.md |

### 5. 模型与路由

| 能力 | 说明 |
|------|------|
| 多模型支持 | 7 个已配置模型：glm-5, glm-5.2, kimi-k2.5, kimi-k3, qwen3.6-35b-a3b, claude-sonnet-4-6, minimax-m2.5, gemini-3-pro-image |
| Per-Agent 模型选择 | 每个 Agent 可独立配置默认模型 |
| 模型路由 | 基于 bindings 配置的消息路由 |

### 6. 多 Agent 管理

| 能力 | 说明 |
|------|------|
| 并行运行 | 多 Agent 同时运行，各自独立 workspace + agentDir + sessions |
| 独立沙箱 | Per-agent sandbox 和 tool 限制 |
| 消息路由 | 支持 peer > parentPeer > guildId+roles > guildId > teamId > accountId > channel > default 优先级链 |
| Per-Agent 心跳 | 每个 Agent 独立心跳配置 |
| Per-Agent Skill 白名单 | 限制各 Agent 可用的 Skill 集合 |
| Agent 创建 | `openclaw agents add <id>` |

### 7. 通道与集成

| 能力 | 说明 |
|------|------|
| 多通道绑定 | bindings 配置 channel + accountId + peer 匹配 |
| 凭据管理 | credentials/ 目录存储渠道凭据 |
| Browser 自动化 | 支持 Chromium 浏览器控制，含 tab/frames/refs 管理 |
| Node 配对 | Android/iOS/macOS 节点配对与远程控制 |
| Notion 集成 | Notion CLI/API 操作（页面、内容、数据源等） |
| OpenClaw Farm | farm-runtime-observer 插件，跨设备运行时观测 |

### 8. 钩子（Hooks）系统

| 能力 | 说明 |
|------|------|
| Internal Hooks | Gateway 内部事件触发自动化 |
| 事件类型 | command:new, command:reset, command:stop, session:compact:before/after, agent:bootstrap, gateway:startup/shutdown, message:received/sent 等 |
| 执行方式 | HOOK.md + handler.ts 定义 |
| BOOT.md 触发 | gateway:startup 事件自动执行 workspace 启动检查 |

### 9. 工具能力

| 能力 | 说明 |
|------|------|
| 文件操作 | read / write / edit / apply_patch |
| Shell 执行 | exec + process（后台、PTY、输入控制） |
| Web 访问 | web_search / web_fetch |
| 浏览器控制 | browser 工具，含 snapshot/screenshot/act/evaluate 等 |
| 终端调试 | node-inspect-debugger / python-debugpy |
| 多媒体 | gemini_image / meme-maker / diagram-maker / sag (TTS) |
| 系统健康 | healthcheck |
| 技能管理 | clawhub / skill-creator |
| 任务编排 | taskflow / taskflow-inbox-triage |

### 10. 人格与工作区文件

| 文件 | 作用 |
|------|------|
| AGENTS.md | 行为规则、工作流程、工具使用规范，每 session 自动注入 |
| SOUL.md | 人格、语气、边界，每 session 自动注入 |
| USER.md | 用户信息，每 session 自动注入 |
| IDENTITY.md | Agent 名字/vibe/emoji，bootstrap 时创建/更新 |
| TOOLS.md | 本地工具约定笔记 |
| HEARTBEAT.md | 心跳检查清单（可选），支持 tasks: 块 |
| BOOT.md | 启动检查清单（可选），gateway:startup 触发 |
| BOOTSTRAP.md | 一次性首次运行仪式，完成后删除 |
| DREAMS.md | 梦境日记（可选），dreaming 系统写入 |
| canvas/ | Canvas UI 文件 |

### 11. 配置与安全

| 能力 | 说明 |
|------|------|
| 模式配置 | local / lan 绑定，端口 18789 |
| humanDelay | 可关闭，控制模型响应延迟 |
| thinkingDefault | 可配置思考级别（如 medium） |
| 认证管理 | agents/<agentId>/agent/auth-profiles.json |
| Canvas 控制 | canvasHost 可启用/禁用 |

---

## B. 三层架构分类

基于能力性质，将所有 Runtime 能力分为三层：

### 第一层：内核层（Kernel Layer）—— 直接可用，无需配置

这些是 OpenClaw Runtime 内核自带的核心机制，启动即生效。

| 能力 | 说明 |
|------|------|
| 多 Session 管理 | 内核直接管理，自动持久化到 SQLite |
| Session 压缩与 Memory Flush | 自动触发，无需用户干预 |
| 文件 I/O 工具 | read/write/edit/apply_patch 直接可用 |
| Shell 执行 | exec/process 工具直接可用 |
| Web 访问 | web_search/web_fetch 直接可用 |
| Memory 语义搜索 | memory_search/memory_get 工具直接可用 |
| 消息路由 | bindings 路由逻辑由内核实现 |
| 工作区文件注入 | AGENTS.md/SOUL.md/USER.md 等自动加载 |
| 定时器基础 | 心跳定时器内核直接支持 |

### 第二层：配置层（Configuration Layer）—— 需 YAML/JSON 配置，启用即生效

这些能力需要用户通过配置声明，但一旦配置好即可开箱即用，无需额外开发。

| 能力 | 说明 |
|------|------|
| Cron 调度 | 在 openclaw.json 声明调度规则即可 |
| 心跳 tasks | 在 HEARTBEAT.md 声明 tasks 块即可 |
| Per-Agent 模型选择 | 在 Agent 配置中声明模型 |
| Per-Agent 沙箱/Tool 限制 | 在 Agent 配置中声明 allowlist/denylist |
| Per-Agent 心跳 | 在 Agent 配置中声明 interval/activeHours |
| Per-Agent Skill 白名单 | 在 Agent 配置中声明 |
| 通道绑定 | 在 bindings 中声明 channel/accountId 路由 |
| 多模型池 | 在 openclaw.json 的 models 中声明 |
| activeHours | 在 heartbeat 配置中声明活跃时段 |
| isolatedSession / lightContext | 在心跳/ cron 配置中声明 |
| Command Payload | 在 cron 声明中指定 command 而非 model |
| delivery 模式 | 在 cron 声明中指定 announce/webhook/none |
| Thinking 级别 | 配置 thinkingDefault |
| humanDelay | 配置 humanDelay: off |

### 第三层：扩展层（Extension Layer）—— 需开发/安装，按需启用

这些能力需要额外安装 Skill、编写 Hook handler 或开发自定义扩展。

| 能力 | 说明 |
|------|------|
| Skill 安装（managed） | 通过 clawhub 安装第三方 Skill |
| Skill Workshop 流程 | 提案、审查、审批、应用 Skill 变更 |
| Hook Handlers | 编写 HOOK.md + handler.ts 实现事件响应 |
| BOOT.md 启动流程 | 编写 workspace 根目录的 BOOT.md |
| Dreaming 后台整合 | 启用 dreaming 配置 + 后台进程 |
| Browser 自动化 | 需配置 browser 插件 + 可用浏览器实例 |
| Node 配对与控制 | 需配对 Android/iOS/macOS 设备 |
| Memory Wiki 插件 | 安装并配置 memory-wiki |
| 多后端记忆 | 配置 QMD/Honcho/LanceDB 等后端 |
| Workspace Skills | 在 workspace/skills/ 目录下自建 Skill |
| Farm Runtime Observer | 安装 farm-runtime-observer 插件 |

---

## C. 自动配置可行性目标分析

以下按**无需人工干预、完全可通过 Gateway 启动时自动配置完成**的标准，评估各目标的可行性。

### C1. ✅ 完全自动可实现（零人工配置）

| 目标 | 实现方式 | 说明 |
|------|----------|------|
| 每日记忆日志初始化 | 内核自动创建 `memory/YYYY-MM-DD.md` | 每次 session 自动注入当天+昨日文件 |
| Session 压缩与 Flush | 内核自动触发 | 无需任何用户配置 |
| 心跳定时器启动 | 内核默认 30 分钟间隔 | 默认即生效 |
| 工作区文件注入 | 内核自动加载 AGENTS.md/SOUL.md/USER.md 等 | 无需配置 |
| 记忆语义索引 | memory_search 默认使用 builtin SQLite | 开箱即用 |
| 多 Session 持久化 | 内核自动写入 SQLite | 零配置 |
| 消息路由默认链 | peer → default 链默认启用 | 无需额外声明 |
| 基础 Shell 执行 | exec 工具默认可用 | 零配置 |
| Web 搜索与抓取 | web_search/web_fetch 默认可用 | 零配置 |
| 文件操作 | read/write/edit/apply_patch 默认可用 | 零配置 |

**结论：** 所有内核层能力均为零配置即用，自动配置覆盖率 100%。

### C2. ⚠️ 半自动可实现（需最低限度声明性配置）

| 目标 | 所需配置 | 自动化程度 |
|------|----------|------------|
| 自定义心跳 tasks | HEARTBEAT.md 中声明 tasks: 块 | 可预置模板，运行时自动加载 |
| Cron 调度任务 | openclaw.json 中声明 cron 规则 | 可预置常用调度规则模板 |
| Per-Agent 模型选择 | Agent 配置中指定 model | 可默认继承全局默认模型 |
| activeHours 限制 | heartbeat 配置中声明 | 可预置默认活跃时段 |
| isolatedSession 模式 | 心跳/cron 配置中声明 | 推荐开启，可设为默认 |
| lightContext 模式 | 心跳配置中声明 | 推荐开启，可设为默认 |
| Command Payload | cron 声明中指定 command | 可预置常用脚本模板 |
| delivery 模式 | cron 声明中指定 | 可默认 announce |
| Thinking 级别 | thinkingDefault 配置 | 默认 medium 已配置 |
| humanDelay | humanDelay 配置 | 默认 off 已配置 |
| Per-Agent Skill 白名单 | Agent 配置中声明 allowlist | 可默认全开放，按需收紧 |

**结论：** 上述能力可通过预置配置模板实现"准自动"——用户在首次使用时只需确认模板，无需从零编写。

### C3. ❌ 需人工干预（无法完全自动）

| 目标 | 原因 |
|------|------|
| 安装第三方 Skill | 需 clawhub 搜索和确认，涉及安全审查 |
| 编写 Hook Handlers | 需理解事件语义，编写 handler.ts 代码 |
| 配置外部凭据 | credentials/ 中的凭据需用户提供 |
| Node 配对 | 需物理设备参与扫码/认证 |
| Browser 实例配置 | 需本地 Chromium 浏览器运行 |
| 多后端记忆切换 | 需部署额外存储（QMD/Honcho/LanceDB） |
| 自定义 Workspace Skills | 需理解 Skill 规范并编写 SKILL.md |
| Farm 跨设备配置 | 需多台设备在线并相互发现 |
| Memory Wiki 结构化知识库 | 需定义知识结构和分类 |
| BOOT.md 启动流程 | 需根据用户需求定制启动检查 |
| Dreaming 后台进程 | 需启用 dreaming 配置 + 额外计算资源 |
| Skill Workshop 提案审批 | 需人工审查提案内容 |

**结论：** 这些能力均涉及外部依赖、安全敏感操作或个性化定制，必须由人工介入。

---

## D. 能力矩阵总览

| 维度 | 内核层 | 配置层 | 扩展层 |
|------|--------|--------|--------|
| **自动配置可行性** | ✅ 100% | ⚠️ ~70%（模板化） | ❌ <20% |
| **是否需要配置** | 否 | 是（YAML/JSON/MD） | 是（代码/安装） |
| **开发工作量** | 零 | 低（声明式） | 高（编码/集成） |
| **典型能力数** | ~10 | ~12 | ~13 |
| **示例** | 文件 I/O、消息路由、Session 管理 | Cron、心跳 tasks、Per-Agent 配置 | Hook Handler、第三方 Skill、Node 配对 |

---

## E. 当前实例能力快照

基于实际运行时状态的快照。

| 类别 | 状态 | 详情 |
|------|------|------|
| 运行模式 | local | LAN 绑定，端口 18789 |
| 默认模型 | phanrouter-o/glm-5.2 | — |
| 可用模型（共 8 个） | ✅ | glm-5, glm-5.2, kimi-k2.5, kimi-k3, qwen3.6-35b-a3b, claude-sonnet-4-6, minimax-m2.5, gemini-3-pro-image |
| 已启用插件 | 3 个 | browser, device-pair, farm-runtime-observer |
| Bundled Skills | 52 个 | 涵盖开发、媒体、任务管理、硬件控制等 |
| Managed Skills | 4 个 | baidu-search, gemini_image, huashu-nuwa, ocf_update |
| Workspace Skills | 0 个 | 尚未自建 |
| Canvas | 禁用 | canvasHost: disabled |
| humanDelay | 关闭 | off |
| Thinking | medium | thinkingDefault: medium |
| 记忆后端 | builtin (SQLite) | — |
| Heartbeat 间隔 | 30 分钟（默认） | — |
| 多 Agent | 支持 | 已安装，具体实例数待查 |

---

## F. 架构优势与限制

### 优势

1. **分层清晰**：内核/配置/扩展三层分离，关注点明确
2. **记忆系统完善**：三层记忆 + 自动 flush + dreaming，形成完整记忆生命周期
3. **调度灵活**：心跳 + Cron 双重机制，覆盖实时与周期性需求
4. **多 Agent 原生支持**：非插件附加，是内核级别的能力
5. **Skill 优先级体系**：6 层加载顺序，workspace 优先确保自定义覆盖
6. **钩子系统**：内部事件驱动自动化，减少轮询开销
7. **持久化完备**：SQLite 存储会话、Cron、状态，重启无损
8. **模型可互换**：8 个可用模型覆盖不同场景，Per-Agent 独立选择
9. **安全边界清晰**：AGENTS.md 明确 red lines，多 Agent 独立沙箱
10. **扩展生态**：clawhub + Skill Workshop 形成技能市场与审核流程

### 限制

1. **扩展层门槛高**：Hook Handler 和 Workspace Skills 需编程能力
2. **Bundled Skill 数量虽多但覆盖面有限**：52 个但未覆盖所有场景
3. **Browser 自动化依赖外部 Chromium**：需本地浏览器实例运行
4. **Node 配对需物理设备**：无法纯软件模拟
5. **多后端记忆需额外部署**：QMD/Honcho/LanceDB 非开箱即用
6. **Canvas 默认禁用**：需显式启用
7. **Heartbeat 间隔最小约 30 分钟**：高频监控场景可能不够
8. **Command Payload 仅限 cron**：心跳任务不支持无模型执行

---

## G. 最终结论

### 总体评价

OpenClaw Runtime 是一个**架构成熟、能力覆盖全面**的 Agent 运行平台。其三层能力分层设计使得不同技术水平的用户都能找到适合自己的使用深度：

- **新手用户**：依赖内核层能力 + 预置配置模板，即可获得 70%+ 的核心功能
- **进阶用户**：通过配置层声明式配置，可定制多 Agent、心跳任务、Cron 调度
- **高级用户**：通过扩展层编写 Hook、自建 Skill、接入外部系统，可实现深度定制

### 自动配置覆盖率

| 层级 | 自动配置覆盖率 | 关键前提 |
|------|----------------|----------|
| 内核层 | **100%** | 无需任何配置 |
| 配置层 | **~70%** | 需预置配置模板 |
| 扩展层 | **<20%** | 大部分需人工介入 |
| **整体** | **~55%** | 内核 + 半自动配置 |

### 关键发现

1. **内核层是绝对主力**：文件操作、Shell 执行、Web 访问、消息路由、Session 管理、记忆搜索——这些零配置能力已构成完整的 Agent 基础操作集。

2. **配置层是最大的可优化空间**：通过预置 HEARTBEAT.md 模板、Cron 规则模板、Agent 配置模板，可将配置层自动覆盖率从 ~70% 提升至 ~90%。

3. **扩展层是差异化的来源**：Hook Handler、自定义 Skill、外部系统集成——这些正是 OpenClaw 区别于固定流程 Agent 框架的核心竞争力。

4. **记忆系统是亮点**：三层结构 + 自动 flush + dreaming 构成了完整的记忆生命周期管理，这是许多同类平台所不具备的。

5. **多 Agent 是重量级能力**：内核级别的多 Agent 支持（独立 workspace、沙箱、模型、心跳、Skill 白名单）使其天然适合复杂场景。

### 建议

- **短期**：预置 HEARTBEAT.md 和 Cron 规则模板，提升配置层自动化水平
- **中期**：完善 ClawHub 技能生态，降低扩展层使用门槛
- **长期**：探索 Dreaming 后台整合的默认启用，让记忆系统更智能地自主管理

---

*文档结束*
