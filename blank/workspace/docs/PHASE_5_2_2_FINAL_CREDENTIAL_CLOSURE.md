# Creator Agent Framework Phase 5.2.2 - Final Credential Closure

```text
Phase 5.2.2 Final Credential Closure Status: PASS WITH ISSUES

Repository State:      CLEAN
Release Chain:         HARDENED
Credential Validity:   NOT CLOSED (owner-blocked)
Distribution State:    NOT CLEAN (GitHub cache views)
```

本轮在不修改 Creator Agent 架构、蒸馏流程、Plugin Interface、Workflow、Skill 与
Creator Plugin 的前提下，完成凭据生命周期记录、暴露面复核、隔离副本盘点、Release
Gate 增强与全量验证。**没有伪造任何"已轮换"状态。**

## 1. Incident Summary

`new/workspace.tar.gz` 是一份被 Git 跟踪的不透明运行快照，内含明文 API Token、
2 个 API Key、GitHub 凭据、业务账号 Cookie/会话材料，以及两个嵌套 Git 仓库。该文件
曾存在于公开仓库 `ai-singer/hand-on-off` 的 `main` 与发布 Tag
`creator-agent-template-v0.1.0` 中，并被部署入口文档推荐的 GitHub 整树源码归档
持续分发。

| 阶段 | 处置 |
| --- | --- |
| Phase 5.1 | 确认归档敏感性，风险等级 HIGH |
| Phase 5.2 | 确认暴露范围（历史 / 远端 / Tag / 分发面），建立 secret scan |
| Phase 5.2.1 | 取消跟踪、历史重写、Tag 重建、远端强制更新、部署入口修订 |
| Phase 5.2.2（本轮） | 凭据生命周期记录、缓存暴露复核、备份盘点、Release Gate 增强、复验 |

## 2. Repository Cleanup

| 检查项 | 结果 |
| --- | --- |
| 风险文件在当前工作树 | **不存在** |
| 风险文件在 Git 历史（全部 ref） | **不可达** |
| 风险文件在远端 `main` / Tag | **不存在** |
| 本地对象库可否取回该 blob | **否**（`git cat-file` 报对象不存在） |
| 仓库根 secret scan | **PASS**，0 发现 |
| 工作区 secret scan | **PASS**，0 发现 |
| 被跟踪的归档 | 仅剩 3 个已扫描干净的归档（`new/skills.tar.gz`、`old/skills_backup_*.tar.gz`、`blank/openclaw-backup-*.tar.gz`） |

```text
Repository State: CLEAN
```

提交映射与重建后的 Tag 见 `PHASE_5_2_1_CREDENTIAL_EXPOSURE_CLOSURE.md`。

## 3. Credential Rotation

```text
Rotated: 0 / 7 locations (6 credential classes)
Status:  ALL PENDING
```

| 类型 | 状态 |
| --- | --- |
| API Key | PENDING |
| GitHub Token | PENDING |
| Cookie/Session | PENDING |
| 其他 Credential | PENDING |

DSH 不能替用户执行外部平台凭据操作。本轮**没有执行轮换，也没有验证任何凭据是否
仍然有效**（未调用外部服务测试凭据）。完整清单、执行顺序、副作用提示与逐条完成
判据见 `CREDENTIAL_ROTATION_FINAL_STATUS.md`。

```text
Credential Validity Closure: NOT ACHIEVED (owner-blocked)
```

这是本轮唯一**无法由本任务关闭**的风险类别。

## 4. Cache Exposure

强制推送使旧提交从分支与 Tag 视图消失，但**平台侧缓存视图仍然有效**。本轮重新
执行了全部三类探测，结果与 Phase 5.2.1 一致——说明**时间流逝不会自动解决该问题**。

| 探测 | 结果 |
| --- | --- |
| `github.com/.../raw/<旧commit>/...` | `200`，`Content-Length: 20123338` → **可下载** |
| `raw.githubusercontent.com/<owner>/<repo>/<旧commit>/...` | `200`，`Content-Length: 20123338` → **可下载** |
| GitHub blob API | `200`，`size: 20123338` → **内容可取得** |
| `git fetch origin <旧commit>` | 退出码 0，且 blob 可实体化 → **可按 SHA 取回** |

```text
Old SHA accessible: YES
Distribution State: NOT CLEAN
```

这是 GitHub 的既定行为，不是操作失误：官方文档说明重写历史只能让提交"从分支与 Tag
不可达"，这些提交"可能仍可通过 SHA-1 在缓存视图中访问"，只有 GitHub Support 能永久
移除缓存视图。同一文档的关键政策是：**Support 仅在判定风险无法通过轮换凭据缓解时
才协助移除敏感数据**——因此轮换是官方预期的首要缓解手段。

建议顺序与可行性评估（含"删除并重建"路径：当前仓库 `forks=0 / PR=0 / issues=0 /
stars=0`，代价极低）见 `CACHE_EXPOSURE_STATUS.md`。**本任务不自行执行删除仓库。**

## 5. Release Security Improvements

新增 `security/release_security_gate.md`，把本次事故的两条教训固化为可执行 Gate：

| Gate | 内容 | 本次事故对应教训 |
| --- | --- | --- |
| 1. Current Tree Scan | 工作区 + **仓库根** + 单元测试 + 编译 + 被跟踪归档清单 | 只扫描工作区无法发现仓库根的历史快照 |
| 2. Artifact Scan | 打包前扫描 + 制品扫描 + 记录 SHA-256 | 源码干净不等于制品干净 |
| 3. Historical Exposure Probe | 对已被清除的对象做 raw URL / blob API / fetch-by-SHA 三类探测 | **"重写历史"不等于"数据已消失"** |
| 4. Deployment Source Validation | 禁止直接部署仓库整树源码归档；只能使用已验证制品或可部署子树导出 | 部署入口曾公开分发含凭据的整树归档 |

配套改动：

- 修复 `security/secret_scan.py` 的一个真实缺陷：归档扫描会把**目录名**当作凭据
  文件名判定，导致合法路径 `tests/secret_scan` 在归档中被误报为 `forbidden-filename`，
  进而使 Release Gate 3/1 对 `git archive` 产物误失败。修复后仅对文件条目应用文件名
  规则，目录内的成员仍逐个扫描。
- 新增对应回归测试：归档中的目录名不触发文件名规则，而同一归档中的真实凭据文件
  `credentials.json` 仍被拦截。

```text
Release Chain: HARDENED
```

## 6. Final Risk Assessment

### 6.1 Verification Evidence

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 单元测试 | `python -m unittest discover -s tests -v` | **PASS**，Ran 22 tests, OK |
| 编译检查 | `python -m compileall .` | **PASS**，exit 0 |
| JSON 解析 | 全部 `*.json`（17 个） | **PASS**，17/17 |
| Secret scan — 工作区 | `python security/secret_scan.py .` | **PASS**，0 发现 |
| Secret scan — 发布目录 | `python security/secret_scan.py blank/dist` | **PASS**，0 发现 |
| Secret scan — 被跟踪文件 | `git archive HEAD` → 扫描该归档 | **PASS**，0 发现 |
| Secret scan — 仓库根 | `python security/secret_scan.py <repo-root>` | **PASS**，0 发现 |
| 发布打包 Gate | `pwsh -File scripts/package_workspace.ps1` | **PASS**，前置与制品扫描均通过 |
| 制品（本轮 Gate 2 验证产物） | `creator-agent-workspace-20260927-132212.tar.gz` | 90,783 B，SHA-256 `18515DCDA8A0CD446E0394EF13E54CF5DBF2BF5EA037DE6F56E5E349E7FFC4D8` |
| 隔离副本盘点 | 见 `BACKUP_DISPOSAL_STATUS.md` | 2 处，均未销毁（刻意保留） |

> 关于制品 SHA-256：制品由打包时点的树内容决定，因此**不能**把"包含本行的制品"的
> 哈希写进本行（会形成自指）。上表记录的是本轮 Gate 2 验证运行实际产出的制品，用以
> 证明该 Gate 可执行且可复现；正式发布时应在打包时点重新记录，见
> `security/release_security_gate.md` 第 2 节。发布制品 SHA-256 的**记录机制**已就位，
> 具体数值由每次发布产生。

### 6.2 Risk Table

| ID | 风险 | 等级 | 状态 |
| --- | --- | --- | --- |
| R-01 | 已泄露凭据**尚未轮换**，仍可能有效 | **HIGH** | **OPEN** — 所有者执行 |
| R-02 | 已清除归档仍可从 GitHub 按旧 SHA 完整下载 | **HIGH** | **OPEN** — 平台侧 |
| R-03 | 本机隔离副本与重写前镜像仍持有同一份材料 | MEDIUM | **OPEN** — 轮换后销毁 |
| R-04 | 扫描器基于规则，未知格式秘密与二进制内嵌凭据可能漏检 | LOW | ACCEPTED |
| R-05 | 仓库根其余 3 个历史快照归档扫描干净，但长期跟踪策略未决 | LOW | DOCUMENTED |

已关闭：风险文件被跟踪 / 存在于历史 / 存在于远端 Tag / 由发布入口持续分发 /
仅本地 checkpoint ref 保留该 blob / 远端 Tag 状态未验证 / 归档目录名误报导致 Gate 失效。

### 6.3 Success Criteria

| 成功标准 | 状态 |
| --- | --- |
| 当前仓库无风险文件 | **满足** |
| 部署入口安全 | **满足** |
| Release Gate 增强 | **满足** |
| Exposure Audit 重新确认 | **满足** |
| 所有凭据已失效 | **未满足**（所有者阻塞） |
| 明确轮换计划完成 | **满足** — 逐条清单含定位、动作与完成判据 |

### 6.4 Verdict

```text
Security Status: PASS WITH ISSUES
```

**仓库侧与发布链侧可以判定为 PASS**：当前树干净、历史与远端已清理、部署入口不再
分发整树归档、Release Gate 已增强并全部实测通过、暴露面已重新确认。

**凭据有效性侧不能判定为 PASS**：已泄露凭据未被轮换，且旧归档仍可按 SHA 从 GitHub
下载。R-01 与 R-02 都是本任务无权执行的动作（外部平台操作与破坏性仓库操作），因此
不予伪造关闭。

按本任务的核心原则自检：

> 不要证明"当前没有秘密"。要证明"已经泄露的秘密不会继续有效，并且发布链不会再次传播。"

- **"发布链不会再次传播" —— 已成立。** Gate 1–4 全部就位并实测通过；部署入口改为
  已验证制品或可部署子树导出；整树源码归档被明确禁止默认可部署。
- **"已经泄露的秘密不会继续有效" —— 尚未成立。** 在完成 `CREDENTIAL_ROTATION_FINAL_STATUS.md`
  的 7 项之前，该命题为假。这是本阶段唯一未达成的目标。

## 7. Next Step

1. **（凭据所有者，最高优先）** 执行 `CREDENTIAL_ROTATION_FINAL_STATUS.md` 第 2 节的
   7 项轮换，并按第 3 节逐条验证旧值失效。
2. 轮换完成后销毁 `BACKUP_DISPOSAL_STATUS.md` 第 2 节列出的隔离副本与镜像。
3. 按 `CACHE_EXPOSURE_STATUS.md` 第 4 节决定：联系 GitHub Support 清除缓存视图，
   或删除并重建仓库。
4. 通知所有协作方**重新克隆**（历史已重写，旧克隆 `pull` 会回混旧历史）。
5. 回到 **Phase 5.3 Runtime Configuration Stabilization**：S-02（Runtime Config
   instance/workflow/skills/version 进入唯一 bootstrap 并交叉验证）、S-03（部署包排除
   `tests` 与 Skill Adapter 测试声明之间的矛盾），以及 S-05~S-08、S-10。

## 8. Harness / Rule Distillation Review

```text
PROMOTE_TO_VERIFIER
```

本次事故沉淀出两条应当作为发布验证器（而非文字规则）执行的检查，已写入
`security/release_security_gate.md`：

1. **发布后旧 SHA 可达性探测**：重写历史后必须实测 raw URL / blob API / fetch-by-SHA，
   确认对象确实不可取得。只做重写就宣布"数据已删除"是本事故中最危险的一步推理。
2. **仓库根范围扫描**：只扫描可部署工作区会漏掉仓库根的不透明快照，而部署文档推荐的
   整树源码归档会把这些快照一并分发出去。

另附一条工具质量教训：安全 Gate 自身的**误报**会直接摧毁 Gate 的可信度——本次
`tests/secret_scan` 目录名误报若不修复，会导致每次 `git archive` 产物扫描失败，从而
训练出"忽略该 Gate"的行为。Gate 的假阳性与假阴性同等重要。
