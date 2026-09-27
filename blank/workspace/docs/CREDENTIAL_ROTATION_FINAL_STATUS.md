# Credential Rotation Final Status

```text
Rotation Executed By This Task: NONE
Reason: rotation requires authenticated action on each third-party service.
        DSH has no access to those services and must not fabricate completion.
```

本文件记录 Phase 5.2.2 时点的凭据轮换事实状态。**本轮没有执行任何轮换，也没有验证
任何凭据仍然有效**（不调用外部服务测试凭据）。所有条目均为 `PENDING`。

按任务约束，本文件不记录任何 secret 值、token 值、token 片段或 hash。

## 1. Status Summary

| 类型 | 状态 | 说明 |
| --- | --- | --- |
| API Key | **PENDING** | 3 项（1 个 `sk-` 形式 API Token、2 个 API Key）尚未在签发方撤销或轮换。 |
| GitHub Token | **PENDING** | 1 项 GitHub 凭据尚未撤销；该凭据可能同时是本机 `git` 推送所用凭据，轮换前需先确认可重新认证。 |
| Cookie/Session | **PENDING** | 1 项业务账号 Cookie/会话材料尚未失效；需账号侧退出全部会话或改密。 |
| 其他 Credential | **PENDING** | 2 处未分类敏感赋值 + 1 个凭据文件名尚未完成服务归属确认，因此也尚未轮换。 |

```text
Rotated: 0 / 7 locations (6 credential classes)
Pending: 7 / 7 locations
```

## 2. Rotation Plan（所有者执行）

定位列指向隔离副本中的相对路径，仅用于确认"哪一条凭据需要轮换"；本文件不含任何
凭据内容。隔离副本位置见 `BACKUP_DISPOSAL_STATUS.md`。

| ID | 类型 | 定位（隔离副本内） | 需要执行的动作 | 完成判据 |
| --- | --- | --- | --- | --- |
| R1 | `sk-` 形式 API Token | `workspace/phanthy_poller.py`；`workspace/memory/2026-09-22-phanthy-publish-debug.md` | 在签发方撤销并重新签发 | 旧值调用返回 401/403 |
| R2 | API Key A | `workspace/credentials.json` → `agents[0].api_key` | 在对应服务轮换密钥 | 旧值鉴权失败 |
| R3 | API Key B | `workspace/credentials.json` → `agents[1].api_key` | 在对应服务轮换密钥 | 旧值鉴权失败 |
| R4 | GitHub Token | `workspace/.env` → `GITHUB_KEY` | 在 GitHub Settings 撤销该 token 并重新签发 | 旧 token 调用 API 返回 401 |
| R5 | Cookie / Session | `workspace/xiaohongshu_cookies.txt` | 目标账号退出全部会话，或改密后重新登录 | 旧 Cookie 请求被拒绝或跳转登录 |
| R6 | 未分类敏感赋值 | `agent_package/tools/source_collector/collectors/bilibili/auth.py`（2 处） | 先确认服务归属，再按所属服务轮换 | 按具体服务确认旧值失效 |
| R7 | 凭据文件 | `agent_package/tools/source_collector/secrets` | 确认其归属服务并轮换其中全部凭据 | 按具体服务确认旧值失效 |

### 执行注意

1. **R4 有副作用**：若该 GitHub 凭据同时用于本机 `git push`，撤销后必须重新认证才能
   继续推送。请先确认已掌握重新签发途径。
2. **顺序**：R4 可最后做；R1–R3、R5–R7 相互独立，可并行。
3. **每条凭据的完成判据是"旧值失效"，不是"文件已删除"。** 删除文件不构成轮换。
4. 全部完成后，销毁 `BACKUP_DISPOSAL_STATUS.md` 中列出的隔离副本与镜像。
5. 收尾复核：`python security/secret_scan.py <repository-root>` 必须 PASS。

## 3. Verification Method（由所有者执行）

DSH 不接触凭据，因此**验证必须由所有者在其服务端或受控环境中完成**。建议的最小
验证集合：

| 验证项 | 方法 | 期望 |
| --- | --- | --- |
| 旧 API Token / Key 失效 | 用旧值向对应服务发起一次鉴权请求 | 401/403，或明确的"凭据已撤销"响应 |
| 旧 GitHub Token 失效 | 用旧 token 调用 GitHub API 读取当前用户 | 401 |
| 旧 Cookie 失效 | 携带旧 Cookie 请求目标站点受限页面 | 跳转登录或 401 |
| 新凭据可用 | 用新值完成一次正常业务调用 | 成功 |
| 无残留引用 | 在业务代码与配置中确认不再引用旧值 | 0 命中 |

## 4. Why This Cannot Be Marked DONE Here

任务已明确：DSH 不能替用户执行外部平台凭据操作。因此本文件的可信度取决于**如实
记录 PENDING**，而不是给出一个未经执行的 `DONE`。

```text
Credential Validity Closure: NOT ACHIEVED (owner-blocked)
```

在完成第 2 节之前，"已泄露的秘密不会继续有效"这一目标**尚未成立**。仓库侧清理与
发布链加固（见 `PHASE_5_2_2_FINAL_CREDENTIAL_CLOSURE.md`）也不能替代轮换。
