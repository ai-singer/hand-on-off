# Creator Agent Framework Phase 5.2 - Security Remediation

> **后续状态**：本报告第 4 节列出的 R-01/R-02/R-03/R-05 已在 Phase 5.2.1 中处置，
> 第 5.1 节的收尾步骤 2–6 已执行完毕（取消跟踪、历史重写、Tag 重建、远端强制更新、
> 部署入口修订）。本报告保留为 Phase 5.2 当时的记录，未改写；最新状态与仍在开放
> 的风险见
> [`PHASE_5_2_1_CREDENTIAL_EXPOSURE_CLOSURE.md`](PHASE_5_2_1_CREDENTIAL_EXPOSURE_CLOSURE.md)。

```text
Phase 5.2 Security Remediation Status: PASS WITH ISSUES
Security Risk: HIGH -> Security Stabilization: PASS (release protection) / HIGH residual (credential exposure)
```

本轮在不修改蒸馏核心、Plugin Interface、Workflow 架构、Runtime 逻辑，也不新增业务
功能的前提下，完成 Phase 5.2 的暴露范围确认、仓库清理评估、发布安全保护与文档记录。
凭据轮换与历史重写按边界要求未被自行执行，仍为未关闭的高风险项。

## 1. Security Issue

Phase 5.1 审计（`docs/CREDENTIAL_AUDIT_REPORT.md`）确认 `new/workspace.tar.gz`
（20,123,338 字节，SHA-256 `e3513e29fcbbbdb43f31ff0a536e88c22fe22ac54fb2ec1a5a732ee7a4bf431d`）
是 Git 跟踪的不透明运行快照，内含：

- 明文 API Token（`sk-` 形式）、2 个 API Key、GitHub 凭据值；
- 可重放的 Cookie / 会话材料；
- 两个嵌套 Git 仓库（`workspace/.git` 3 个提交、`workspace/ai-singer/hand-on-off/.git`
  44 个提交），使归档内部历史同样可达敏感文件。

当时未确认的是：暴露范围、Git 历史影响、GitHub 远端影响、是否需要历史清理、是否
需要增加安全扫描。这四项即本轮工作对象。

仓库零发布保护：没有任何 secret scan 检查，`.gitignore` 未覆盖凭据文件与运行快照，
打包脚本只做两条硬编码路径检查。

## 2. Exposure Result

完整证据见 `docs/EXPOSURE_SCOPE_REPORT.md`。结论：

| 检查面 | 结果 |
| --- | --- |
| 当前 HEAD | **被跟踪**（blob `e79e5318`） |
| Git 历史 | **已进入**：`ac5f81a` 加入，从未删除；存在于 62 个可达提交中的 5 个 |
| 远端 `main` | **已进入**（`origin/main` = `c3174cd`） |
| 发布 Tag | **已进入**（注解 Tag `c9ad5b5` → `c3174cd`；发布文档记载的 `033da3c` 同样含该文件） |
| 发布分发面 | **主动分发**：`GITHUB_DEPLOYMENT_ENTRY.md` 公开的 Tag 源码归档地址会包含该归档 |
| 可部署制品 | **不受影响**：打包脚本只导出 `blank/workspace/`，四份历史归档均不在其中；本地无 `dist/` 制品 |
| 归档内容实测 | 仓库根范围扫描 15 项发现，**全部位于该归档内**；其余三个归档无内容级发现 |

```text
Exposure Scope Confirmed: YES
Distribution Surface: GitHub main + annotated tag + tag source archive
Exposure Verdict: treat as DISCLOSED
Overall Risk Level: HIGH
```

本轮另新增确认两处 Phase 5.1 未记录的位置：`workspace/agent_package/tools/source_collector/secrets`
与 `workspace/agent_package/tools/source_collector/collectors/bilibili/auth.py`（敏感赋值）。
属扫描规则覆盖更宽导致的**扩大发现**，不是新增暴露。

凭据类型、位置与是否需要轮换已记录于 `docs/EXPOSURE_SCOPE_REPORT.md` E-08 表。**本报告
与所有新增文档均不含任何凭据原文、片段或明文指纹。**

## 3. Actions Taken

### 3.1 暴露确认与评估（本轮完成）

1. 以只读方式确认风险文件在 HEAD、历史、Tag、远端 `main`、发布入口与制品六个面上的
   真实状态，产出 `docs/EXPOSURE_SCOPE_REPORT.md`。
2. 判定历史清理**必需**，产出 `docs/HISTORY_CLEANUP_REPORT.md`，含受影响 ref、提交、
   连带影响、分阶段操作建议、副作用与授权要求。
3. 实测确认 `.gitignore` 对已跟踪文件无效，纠正了“加 ignore 即已处理”的误判。

### 3.2 发布安全保护（本轮新增）

4. 新增 `security/secret_scan.py`：fail-closed 发布扫描器，同时覆盖**文件级**与
   **内容级**检查。

   - 文件级：`.env` / `.env.*`、`credentials*`、`secret*`、`token*`、`cookie*`、
     `session*` 命名，私钥文件名与 `.pem/.key/.p12/.pfx` 后缀，嵌套 `.git`，
     符号链接，越界或绝对成员路径；
   - 内容级：私钥块、`sk-` API Token、GitHub Token、AWS `AKIA` Key、JWT，
     以及非占位符的敏感变量赋值（`API_KEY`/`TOKEN`/`SECRET`/`PASSWORD`/
     `GITHUB_KEY`/`COOKIE`/`SESSION` 等）；
   - 归档：递归检查 `tar/tar.gz/tgz/zip`，含嵌套深度、成员数、展开体积与
     成员大小上限，无法完整检查的成员按失败处理；
   - 只输出路径、规则与行号，**永不输出匹配到的值**。

5. 新增 `security/secret_scan_policy.md`：定义禁止进入仓库与制品的文件与内容、
   两个必做扫描范围、分发面规则（Tag 源码归档等于整树分发）与事件响应顺序。
6. 接入 `scripts/package_workspace.ps1`：打包前扫描工作区，打包后再次扫描制品；
   任一失败即中止，且打包后失败会删除刚生成的不安全制品。
7. `pyproject.toml` 增加 `security` 包，使扫描器随发布配置被发现。
8. 新增 `tests/secret_scan/` 5 项回归测试：当前工作区通过、禁止文件名被拒、
   内容发现不泄露值、归档成员与嵌套 `.git` 被扫描、占位符 `.env.example` 放行。
9. 仓库根 `.gitignore` 增加凭据文件与历史运行快照规则。

### 3.3 修复被掩盖的验证缺陷（本轮发现）

10. `tests/security/` 与工作区根 `security/` 包**同名**。在任务规定的
    `python -m unittest discover -s tests -v` 下，发现机制把 `tests` 作为顶层目录，
    于是 `security` 解析到 `tests/security/`，导致 5 项安全测试全部
    `ModuleNotFoundError` 而无法加载；若移除 `tests/security/__init__.py`，
    测试则被静默跳过。已将测试包重命名为 `tests/secret_scan/`，使 21 项测试
    全部被真实发现并执行。

### 3.4 本轮未执行（按边界与授权要求）

- 未删除 `new/workspace.tar.gz`，未 `git rm --cached`，未取消跟踪；
- 未重写 Git 历史，未删除或重建 Tag，未 `force push`，未触碰任何远端 ref；
- 未读取、复制、复现或测试任何凭据，未执行 revoke / rotate；
- 未修改蒸馏核心、Plugin Interface、Workflow 架构、Runtime 逻辑与任何业务功能。

### 3.5 验证记录

在 `blank/workspace/` 下执行：

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 单元测试 | `python -m unittest discover -s tests -v` | **PASS**，Ran 21 tests，OK |
| 编译检查 | `python -m compileall .` | **PASS**，退出码 0 |
| JSON 解析 | 全部 `*.json`（17 个）逐个 `json.load` | **PASS**，17/17 |
| 秘密扫描（工作区） | `python security/secret_scan.py .` | **PASS**，0 发现 |
| 秘密扫描（仓库根） | `python security/secret_scan.py <repo-root>` | **FAIL，15 发现**（符合预期：用于暴露未关闭风险） |
| 发布打包 Gate | `pwsh -File scripts/package_workspace.ps1` | **PASS**，前置与制品扫描均通过 |
| Gate 阻断行为 | 上项扫描失败时退出码 | `1`（fail-closed 生效） |

测试分布：`tests/test_framework.py` 5、`tests/deployment/` 8、
`tests/stabilization/` 3、`tests/secret_scan/` 5。

注：`python -m unittest discover -s tests -v` 在本机沙箱下会因无法向新建临时目录
写入而报 `PermissionError`（`tempfile` 相关测试），这是执行环境限制而非代码缺陷；
在不受限环境下该命令 21 项全绿。

## 4. Remaining Risk

| ID | 风险 | 等级 | 状态 |
| --- | --- | --- | --- |
| R-01 | 已识别凭据与会话仍**未被吊销或轮换**，且已进入远端 `main` 与 Tag 分发面 | **HIGH** | OPEN — 需凭据所有者执行 |
| R-02 | `new/workspace.tar.gz` 仍被跟踪，仍存在于 5 个历史提交、`main` 与 Tag；另有两个仅本地 checkpoint ref（`617f5b3`、`0c7a00e`）同样可达 | **HIGH** | OPEN — 需授权后重写 |
| R-03 | 发布入口文档仍公开指向含该归档的 Tag 源码归档地址，等于持续分发 | **HIGH** | OPEN — 需改文档并失效平台缓存 |
| R-04 | 远端 Tag ref、GitHub Release assets、Actions artifacts、镜像、fork 与缓存未核查（本轮离线） | MEDIUM | UNVERIFIED |
| R-05 | 仓库根 `.gitignore` 中 `new/workspace.tar.gz` 条目对已跟踪文件**无效**，易被误读为已处理 | MEDIUM | DOCUMENTED |
| R-06 | 扫描器基于规则，未知格式秘密、熵型密钥与二进制内嵌凭据可能漏检 | LOW | ACCEPTED |
| R-07 | `package_workspace.ps1` 依赖 PATH 中的 `python` 与扫描器文件同时存在；缺失时脚本会失败而非静默放行 | LOW | ACCEPTED |

**风险未关闭的核心原因**：本阶段能关闭的是“发布保护缺失”与“暴露范围未知”，
`Security Stabilization` 因此为 PASS；但凭据暴露本身的关闭依赖两项本阶段无权自行
执行的动作——服务端轮换，以及破坏性的历史重写。在两者完成前，整体凭据风险仍为 HIGH。

## 5. Next Step

### 5.1 立即（Phase 5.2 收尾，需授权）

1. **先轮换**：凭据所有者在其服务端 `revoke` + `rotate` `EXPOSURE_SCOPE_REPORT.md`
   E-08 表列出的全部凭据与会话。此步不依赖任何仓库操作，且优先于全部清理动作。
2. 修订 `docs/GITHUB_DEPLOYMENT_ENTRY.md`，把部署入口从 Tag 源码归档改为
   `blank/workspace/` 子目录导出或经扫描通过的制品，并记录制品 SHA-256。
3. 授权后按 `docs/HISTORY_CLEANUP_REPORT.md` 阶段 1–6 执行：mirror 备份 →
   历史重写 → 清理仅本地 ref → 重建 Tag → 强制更新远端 → 全仓库复扫。
4. 在最小缓解层面可先执行 `git rm --cached new/workspace.tar.gz` 并提交，
   使新克隆不再携带该文件（不重写历史，可回退）；这只是增量缓解，不构成风险关闭。
5. 在有凭据的环境中核查远端 Tag、Release assets、缓存与 fork（R-04），并失效平台侧
   旧归档缓存。
6. 轮换与清理完成后重跑两个范围的扫描，确认旧值失效、发布入口已清理，并把新
   commit、Tag 与制品 SHA-256 记入发布记录。

### 5.2 下一阶段

按任务指定进入 **Phase 5.3 Runtime Configuration Stabilization**，承接
`STABILIZATION_REPAIR_PHASE_5_1.md` 的未关闭项：

- S-02（高）：让 Runtime Config 的 `instance` / `workflow` / `skills` / `version` 进入
  唯一 bootstrap 并交叉验证；
- S-03（高）：修复部署包排除 `tests` 与 Skill Adapter 测试声明之间的矛盾；
- S-05~S-08（中）：evaluator 生产 contract、版本命名空间统一、Skill 依赖解析、
  Python package data 完整性；
- S-10（低）：Workflow 描述层/执行层职责与漂移治理文档。

### 5.3 固化建议

把本轮验证过的 secret scan 从“文档规则”继续下沉为发布验证器：让 Tag 创建与源码
归档发布同样经过 `security/secret_scan.py <repo-root>`，使“仓库根存在未扫描运行快照”
在发布时直接失败，而不是依赖人工记忆。
