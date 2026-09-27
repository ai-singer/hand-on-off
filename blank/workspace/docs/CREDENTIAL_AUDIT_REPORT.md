# Creator Agent Framework Credential Audit Report

## Audit Scope

本次审计仅覆盖仓库中 Git 跟踪的四个历史归档，不修改归档、Git 历史、发布内容或任何凭据：

| 归档 | SHA-256 | 常规文件数 | 审计结果 |
| --- | --- | ---: | --- |
| `old/skills_backup_20260922_072844.tar.gz` | `42b60ade16bda4e5fa56d747e1ac5ea73570286937611717e5b2ad7c8a87064b` | 35 | 未发现敏感值 |
| `new/workspace.tar.gz` | `e3513e29fcbbbdb43f31ff0a536e88c22fe22ac54fb2ec1a5a732ee7a4bf431d` | 1126 | 发现敏感值与嵌套 Git 历史 |
| `new/skills.tar.gz` | `065f0c954fbb124dfb8794cdfd677e65e6722f7d95fa497fae6c672b756e48b6` | 10 | 未发现敏感值 |
| `blank/openclaw-backup-20260922.tar.gz` | `18b29109693a0b24bfb10fcc3c8f06f9fe8fea1375aef5bcf0de0d94d065b7a0` | 11 | 未发现敏感值 |

审计方法包括归档成员清单检查、文本内容规则扫描、结构化 JSON/ENV 检查、嵌套 ZIP 递归检查，以及对归档内两个 Git 仓库的只读可达历史搜索。为避免再次泄露，本报告不包含任何凭据原文；脱敏指纹是值的 SHA-256 前 12 位，仅用于确认重复项。

## Findings

### F-01：`new/workspace.tar.gz` 包含明文凭据和会话材料

| 归档内位置 | 类型 | 脱敏证据 | 是否敏感 |
| --- | --- | --- | --- |
| `workspace/memory/2026-09-22-phanthy-publish-debug.md` | `sk-` 形式 API Token | 长度 51；指纹 `af321885956b` | 是 |
| `workspace/phanthy_poller.py` | 与上一项相同的 API Token | 长度 51；指纹 `af321885956b` | 是 |
| `workspace/credentials.json` 的 `$.agents[0].api_key` | API Key | 长度 40；指纹 `b1eb23b77283` | 是 |
| `workspace/credentials.json` 的 `$.agents[1].api_key` | API Key | 长度 40；指纹 `211b1f6b4932` | 是 |
| `workspace/xiaohongshu_cookies.txt` | Cookie / 会话材料 | 长度 1589；指纹 `8ecc39d622ce` | 是 |
| `workspace/.env` 的 `GITHUB_KEY` | GitHub 凭据值 | 长度 93；指纹 `2d2e6ba8efaa` | 是 |
| `workspace/environment_resources/.env` 的 `API_KEY` | 空值声明 | 长度 0 | 否 |

所有敏感项均为非空、非明显占位符值。规则扫描未发现 PEM 私钥、JWT、AWS `AKIA` Key、Google AI Key、标准 `gh*` Token 或 URL 内嵌凭据；这不构成对未知格式秘密的绝对排除。

### F-02：同一归档包含嵌套 Git 仓库

- `workspace/.git` 含 3 个可达提交。API Token 所在的 Markdown 和 Python 文件在三个提交中均可达，因此只删除当前快照文件不能消除历史暴露。
- `workspace/ai-singer/hand-on-off/.git` 含 44 个可达提交。本次规则搜索未在该嵌套仓库的可达历史中发现同类敏感路径或高置信凭据。
- `.env`、`credentials.json` 和 Cookie 文件未出现在归档内根 Git 仓库的 HEAD 树中，但它们仍直接存在于已跟踪的 tar 快照中。

### F-03：其余三个归档未发现敏感值

`old/skills_backup_20260922_072844.tar.gz`、`new/skills.tar.gz` 和 `blank/openclaw-backup-20260922.tar.gz` 的全部常规文件均已扫描，未发现 API Key、Token、Secret、密码、私钥、Cookie/会话值或环境变量实际值。

## Risk Level

```text
Overall Risk Level: HIGH
```

原因：`new/workspace.tar.gz` 是 Git 跟踪的不透明归档，其中包含多个明文凭据、可重放的会话材料和带敏感文件历史的嵌套 Git 仓库。若仓库或 release 曾向第三方开放，应按“凭据已经泄露”处理。其余三个归档在本次范围内的风险等级为 `NONE`。

本轮只关闭了“敏感性是否存在”的审计不确定性，没有关闭凭据暴露本身。受任务限制，本轮未验证这些凭据是否仍有效，也未执行轮换、删除、历史改写或发布制品清理。

## Recommendation

1. 立即在对应服务端撤销并轮换所有已识别凭据和会话，轮换顺序优先于仓库清理。
2. 核查 GitHub 仓库、tag、release asset、镜像、缓存和所有克隆副本是否分发过 `new/workspace.tar.gz`；必要时按安全事件流程处理。
3. 在单独授权的修复阶段移除或替换该归档。若需重写 Git 历史，必须先评估协作影响并获得明确批准；本轮不得执行。
4. 将归档内容清单和 secret scan 固化为发布 Gate，禁止提交包含 `.env`、凭据文件、Cookie、嵌套 `.git` 或不透明运行快照的制品。
5. 轮换完成后重新执行同范围扫描，并单独验证旧值已失效、发布入口已清理。

## Audit Limitations

- 本审计基于静态内容和规则识别，不调用任何外部服务测试凭据有效性。
- 独立并行复核因执行账户用量限制未能完成；主审计已逐成员覆盖四个归档，并对关键发现进行了结构化复核。
- 未扫描本任务明确范围之外的仓库文件、远端平台、CI Secret、容器、主机环境或生产实例。
