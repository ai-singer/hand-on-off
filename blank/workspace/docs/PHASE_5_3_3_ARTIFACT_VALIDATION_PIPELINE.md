# Creator Agent Framework Phase 5.3.3 - Artifact Validation Pipeline

```text
Phase 5.3.3 Artifact Validation Pipeline Status: PASS

Build -> Artifact Manifest -> Artifact Validation -> Deploy    CLOSED
```

本轮在不修改 Distillation Engine、Runtime Bootstrap、Plugin Interface、Workflow Schema
与 Security Gate 逻辑的前提下，为部署制品建立可验证身份与部署前验证层。

## 1. Before

部署制品没有任何身份与验证：

```text
Package (tar)  ->  Secret scan  ->  Output artifact
                                        |
                                        v
                                     Deploy
```

- 制品没有文件清单：无法回答"这个包到底包含什么"；
- 制品没有哈希记录：无法判断解包后内容是否被改动；
- 制品没有声明它需要哪个 runtime 契约、启用哪些 plugin/skill；
- 打包成功即视为可部署，没有"制品是否与预期一致"的判定点。

## 2. After

```text
Package (tar)  ->  Secret scan
     |
     v
Generate Manifest  (artifact/manifest.py)
     |   artifact_id / version / created_at
     |   runtime_version / config_version
     |   enabled_plugins / enabled_skills
     |   files[] = {path, sha256, size}
     v
Validate Artifact  (artifact/validator.py)
     |   对**解包后的制品**逐文件比对清单
     v
Success  ->  Output artifact + <artifact>.manifest.json
Failure  ->  删除制品与清单，exit code != 0
```

新增 `artifact/` 层：

| 文件 | 职责 |
| --- | --- |
| `artifact/manifest.py` | 递归扫描、SHA-256、稳定排序、清单生成 |
| `artifact/validator.py` | 清单与制品的一致性验证，收集全部发现项 |
| `artifact/schema.json` | 清单结构 Schema（复用既有 `core.schema_validation`）|
| `artifact/__init__.py` | 惰性再导出（见第 5 节说明）|

### 关键设计决定：清单从何而来

清单**从源工作区生成**，随后对**解包后的制品**做验证。若改为"先解包、再据解包内容
生成清单、再验证同一份解包内容"，验证将变成自证（自己和自己比对），无法证明制品与
打包输入一致。当前做法使 Gate 具备真实判别力：归档在打包过程中丢失、改写或夹带文件
都会被发现。

清单以**旁挂文件**形式输出（`<artifact>.manifest.json`），不放进 tar 包内：放进包内
会使清单必须在打包后才生成，从而回到自证问题，并且会改变制品自身的哈希。

## 3. Manifest Schema

`artifact/schema.json`（使用 `core/schema_validation.py` 支持的子集：`type`、`enum`、
`required`、`properties`、`additionalProperties`、`items`、`minItems`）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `manifest_version` | string | 清单格式版本，当前 `1.0.0`（`enum` 限定）|
| `artifact_id` | string | 制品标识，默认取制品内 runtime config 的 `instance.name` |
| `version` | string | 制品版本，默认取 config 的 `version`（发布流程可覆盖）|
| `created_at` | string | UTC ISO-8601，形如 `2026-09-27T14:17:59Z` |
| `runtime_version` | string | 制品要求的 runtime 契约版本，默认 `runtime.SUPPORTED_CONFIG_VERSION` |
| `config_version` | string | 制品内 runtime config 声明的版本 |
| `enabled_plugins` | string[] | 来自制品内 config 的 `plugins.enabled` |
| `enabled_skills` | string[] | 来自制品内 config 的 `skills.enabled` |
| `files` | object[] | `{path, sha256, size}`，`path` 为相对 POSIX 路径 |

约定：

- `files` **按 path 升序稳定排序**，保证同一输入产生同序清单；
- 清单**不记录自身**，因此可安全地放在它所描述的目录内（含自定义路径）；
- 生成与验证双方共用同一套遍历规则，保证"清单里有什么"与"目录里有什么"判定一致；
- 忽略 `__pycache__`、`.pytest_cache`、`.mypy_cache`、`*.pyc`、`*.pyo`；
- 跳过符号链接（清单记录的是常规文件内容，软链目标在部署主机上未必存在）。

## 4. Validation Rules

`validate_artifact(artifact_dir, *, manifest_path=None, runtime_version=None)`

| # | 规则 | 触发条件 |
| --- | --- | --- |
| 0 | `artifact-missing` / `manifest-missing` | 制品目录或清单不存在 / 不可读 |
| 1 | `manifest-invalid` | 清单不满足 `artifact/schema.json`（缺字段、类型错、多余字段）|
| 2 | `runtime-incompatible` | 清单 `runtime_version` 主版本 ≠ 当前 runtime 实现的契约主版本 |
| 3 | `config-missing` | 制品内不含 `config/runtime/default.json`，或该配置无法通过 loader 校验 |
| 4 | `config-mismatch` | 清单的 `config_version` / `enabled_plugins` / `enabled_skills` 与制品内 config 不一致 |
| 5 | `plugin-missing` | 清单声明的 plugin 模块路径在制品内不存在（缺 `plugins/<pkg>/__init__.py`）|
| 6 | `skill-missing` | 清单声明的 skill 在制品内没有 `skills/openclaw/<name>/manifest.json` |
| 7 | `file-missing` | 清单声明的文件在制品内不存在 |
| 8 | `size-mismatch` | 文件实际大小 ≠ 清单声明大小 |
| 9 | `hash-mismatch` | 文件实际 SHA-256 ≠ 清单声明值 |
| 10 | `extra-file` | 制品含有清单未声明的文件 |

任务要求的 6 项检查（文件完整性、Hash、Runtime、Plugin、Skill、Config）分别对应
规则 7 / 8+9 / 2 / 5 / 6 / 3。规则 4 与规则 10 为本轮补充：前者校验清单的**语义声明**
与制品内配置一致，后者堵住"夹带未声明文件"这一清单机制的天然盲区。

验证**收集全部发现项**而非首个失败即返回，一次运行即可看到完整问题清单。

## 5. Deployment Gate

`scripts/package_workspace.ps1` 新流程：

```text
1. 打包前 secret scan（工作区）          [原有]
2. 拒绝 .env / .openclaw/openclaw.json   [原有]
3. tar 打包                              [原有]
4. 打包后 secret scan（制品）            [原有]
5. 生成 Artifact Manifest                [新增]
6. 解包制品 -> 按清单验证                [新增]
7. 成功：输出制品 + 旁挂 manifest
   失败：删除制品与 manifest，exit != 0  [新增]
```

- 第 5 步用 `--exclude tests` 让清单描述的文件集与 tar 的 `--exclude="workspace/tests"`
  一致；缓存目录由生成/验证双方共同忽略，因此即使归档里残留 `__pycache__` 也不会误判。
- 第 7 步的清理保证**失败时绝不留下可部署包**。

实测（成功路径）：

```text
Secret scan PASS: 1 target(s) inspected.       (打包前)
Secret scan PASS: 1 target(s) inspected.       (打包后)
Artifact manifest: ...creator-agent-workspace-20260927-141759.tar.gz.manifest.json
Files: 109
Artifact validation PASS: <temp>\workspace
Package:  ...creator-agent-workspace-20260927-141759.tar.gz
SHA256:   05E6D78833FDCAF24FD94F13B259375910AC838D77C495120A0DE781CD5DA84A
Manifest: ...creator-agent-workspace-20260927-141759.tar.gz.manifest.json
exit=0
```

实测（失败路径，故意破坏制品内 config 使清单生成失败）：

```text
Artifact manifest generation failed with exit code 1
gate exit=1
artifact left behind?          absent - OK
sidecar manifest left behind?  absent - OK
```

### 一处实现细节：惰性再导出

`artifact/__init__.py` 采用 PEP 562 惰性 `__getattr__`。若在包初始化时直接
`from .manifest import ...`，`python -m artifact.manifest` 会在 runpy 执行前就把该子模块
放进 `sys.modules`，导致子模块被**执行两次**并触发 runpy 警告。惰性导出同时保留了
`from artifact import generate_manifest` 的书写便利。

## 6. Test Evidence

新增 `tests/artifact_validation/test_artifact_validation.py`（16 项）：

| 任务要求 | 测试方法 | 结果 |
| --- | --- | --- |
| Test 1 Manifest 生成 | `test_manifest_records_identity_runtime_and_files` | 身份/版本/时间/runtime/config/plugin/skill 字段正确；`files` 稳定排序；清单不自列；声明哈希等于实际 `sha256_file` |
| Test 1（补）| `test_manifest_stored_inside_artifact_excludes_itself` | 自定义路径存于制品内时同样不自列，且验证通过 |
| Test 2 完整 Artifact | `test_complete_artifact_validates` | `ok` 为真，发现项为空 |
| Test 3 文件缺失 | `test_missing_declared_file_fails` | `file-missing` |
| Test 4 Hash 变化 | `test_changed_file_content_fails` | `hash-mismatch` + `size-mismatch` |
| Test 5 Plugin 缺失 | `test_missing_plugin_fails` | `plugin-missing` |
| Test 6 Skill 缺失 | `test_missing_skill_fails` | `skill-missing` |
| Test 7 Runtime 版本不兼容 | `test_incompatible_runtime_version_fails`、`test_runtime_version_mismatch_in_either_direction_fails` | `runtime-incompatible`（清单侧与运行时侧双向）|
| 补充 | `test_missing_manifest_fails` | 无清单时仅报 `manifest-missing` |
| 补充 | `test_structurally_invalid_manifest_fails` | 缺字段 + 多余字段 → `manifest-invalid` |
| 补充 | `test_undeclared_extra_file_fails` | `extra-file` |
| 补充 | `test_config_drift_fails` | `config-mismatch` |
| 补充 | `test_missing_runtime_config_fails` | `config-missing` |
| 集成 | `test_workspace_round_trip_validates` | 对**真实工作区**（123 文件）生成并验证清单 → PASS |
| 集成 | `test_packaging_excludes_are_excluded` | `--exclude tests` 生效，且 `artifact/` 自身被纳入清单 |

### 回归验证

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 单元测试 | `python -m unittest discover -s tests -v` | **PASS**，Ran **59** tests, OK（5.3.2 的 43 + 新 16） |
| 编译检查 | `python -m compileall .` | **PASS**，exit 0 |
| JSON 解析 | 全部 `*.json`（runtime config / skill manifest / schema / artifact manifest）| **PASS**，**21/21**（原 20 + 新 `artifact/schema.json`）|
| Secret scan — 工作区 | `python security/secret_scan.py .` | **PASS** |
| Secret scan — 仓库根 | `python security/secret_scan.py ..\..` | **PASS** |
| Deployment Gate — 成功路径 | `pwsh -File scripts/package_workspace.ps1` | **PASS**，制品 + manifest 输出，exit 0 |
| Deployment Gate — 失败路径 | 同上（故意破坏 config）| **FAIL 阻断**，exit 1，制品与 manifest 均已删除 |

新增 artifact 代码不含任何 secret（已由上述两个范围的 secret scan 覆盖）。

## 7. Remaining Issues

| ID | 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| R-01 | 打包排除项在两处声明：tar 的 `--exclude="workspace/tests"` 与脚本变量 `$artifactExcludes = @("tests")` | 两者若不一致，Gate 会把"清单声明但归档未含"报为 `file-missing`（fail-closed，不会漏放，但会误报） | 将排除项集中为单一来源（例如由 manifest 工具输出 tar 排除参数） |
| R-02 | 清单**未签名** | 清单与制品同时被替换时无法发现；只能防无意损坏，不能防主动篡改 | 后续可加签名/证明（cosign、GPG）；本轮未引入依赖 |
| R-03 | 清单为旁挂文件 | 消费方需另行获取清单才能自验；制品本身不自带身份 | 可考虑同时把清单放入制品并把"制品哈希"写入发布记录（需权衡 R-04）|
| R-04 | `created_at` 使清单逐次不同 | 同一源码两次打包的清单不可字节复现 | 发布流程可传入固定 `--created-at`；复现构建属独立议题 |
| R-05 | 验证器不检查 config 引用的 workflow 文件是否存在 | `workflow.default` 指向缺失文件时 Gate 仍通过（该问题由 `bootstrap()` 在运行时暴露）| 可在验证器中补 workflow 存在性检查 |
| R-06 | 符号链接被遍历跳过 | 制品若依赖软链，其目标不会被清单记录 | 属有意取舍，已在第 3 节记录；如需支持应先定义跨平台语义 |
| R-07 | 跨平台未验证 | 仅在 Windows + Python 3.13 上实测；路径已统一为 POSIX 相对路径，但 tar 排除语义、大小写敏感性未在 Linux 验证 | 在目标部署平台重跑 Gate |

### 成功标准核对

```text
Build               ->  PASS
Artifact Manifest   ->  PASS
Artifact Validation ->  PASS（10 条规则，16 项测试，含真实工作区往返）
Deploy              ->  PASS（Gate 成功/失败双向实测）
```

闭环成立，故判定 **PASS**。

## 8. Harness / Rule Distillation Review

```text
PROMOTE_TO_VERIFIER
```

1. **"生成清单"与"验证清单"若共用同一份产物，验证是自证**。本轮特意让清单源于打包输入、
   验证面向解包产物，Gate 才具备判别力。任何"校验和"机制都应自检这一点。
2. **清单必须排除自身**，否则形成自指（无法记录自己的哈希）。第 2 节与测试均已固化。
3. **失败路径需要与成功路径同等测试**。仅验证"Gate 通过"无法证明"失败时不留包"；
   本轮用一次受控破坏实测了清理逻辑，建议作为发布 Gate 的固定验收项。
