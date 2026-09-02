# SysMind AI v0.1.0 深度代码复核报告

- 审查日期：2026-08-30
- 审查基线：分支 `agent/release-materials-v0-1-0`，HEAD `4f26eda`（工作区干净）
- 审查方式：逐文件通读全部生产源码、测试、配置、脚本与 CI，结合 ADR/PRD 核对预期行为；对存疑点编写一次性探针脚本实测；全量运行质量门验证。
- 审查人：ZCode（自动化深度复核）

---

## 1. 审查范围

| 范围 | 文件数（约） | 方式 |
|---|---|---|
| 后端 Python（`services/backend/src/sysmind/**`，含 core/domain/application/infrastructure/api/tools/agent/tasks/diagnosis/actions/reports/prompts/security/observability/runtime/windows） | 120 源文件 + 29 测试文件 | 逐行通读 |
| Alembic 迁移（0001–0010 + env） | 12 | 逐行通读，并与 ORM 模型列级比对 |
| 前端 TS/TSX（`apps/desktop/src/**`） | 27 生产 + 11 测试 | 逐行通读（测试文件为通读+重点核对） |
| Tauri Rust（`sidecar.rs`、`lib.rs`、`main.rs`） | 3 | 逐行通读 |
| 配置与契约（tauri.conf.json、capabilities、vite/tsconfig/eslint、pyproject、alembic.ini、PyInstaller spec） | 12 | 逐行通读 |
| CI/发布（ci.yml、release.yml、package.ps1、check.ps1、run-phase5a/6-isolated-tests.ps1、export-openapi.py、test_packaged_backend/desktop.py） | 9 | 逐行通读 |
| 文档（PRD、ADR-001~015、README、release-checklist 等） | 关键部分 | 核对代码与文档一致性 |
| 未逐行审查 | `styles.css`（2175 行，纯样式，做结构与可访问性抽查）、第三方生成物（pnpm-lock、Cargo.lock、openapi JSON、packaging/build 下的 xref HTML） | 抽查 |

说明：仓库工作区中存在大量未被 git 跟踪的本地产物（`.pytest-tmp/`、`.sysmind-data/`、`.mypy_cache/`、`services/backend/sysmind.db`、`apps/desktop/dist/`、`node_modules/` 等），均已确认被 `.gitignore` 覆盖、不在版本库内（git 跟踪文件共 299 个，无一垃圾文件）。

---

## 2. 总体结论

**代码质量显著高于同规模项目的平均水平，本次复核未发现任何阻断发布（P1）级缺陷。** 安全边界（loopback、会话令牌、密钥存储、确认票据、审计）在代码层面完整落实且互相印证；架构分层（presentation → application → domain，基础设施实现端口）在全部已读代码中无一违反。

全部质量门实测通过：

| 质量门 | 结果 |
|---|---|
| 后端 `ruff check` | 全部通过 |
| 后端 `mypy --strict`（120 文件） | 无问题 |
| 后端 `pytest` | **154 通过，4 跳过**（跳过项为破坏性 Sandbox 测试，符合设计） |
| OpenAPI 契约再生成对比 | 与 `contracts/openapi/sysmind-local-api.json` 完全一致 |
| 前端 `eslint --max-warnings 0` | 通过 |
| 前端 `tsc -b`（strict + noUncheckedIndexedAccess + exactOptionalPropertyTypes） | 通过 |
| 前端 `vitest` | 34 通过 |
| Rust `cargo test` | 5 通过 |
| 疑点探针（级联删除、循环导入、import 顺序） | 1 项排除、1 项确认为低危问题（见 §4） |

---

## 3. 安全边界符合性核对（对照 AGENTS.md / ADR）

逐项核对全部通过：

1. **仅监听 loopback**：`core/config.py` 用 `Literal["127.0.0.1"]` + 校验器双重锁死；`runtime/server.py` 先绑定 socket 再交给 uvicorn；Rust 侧 `sidecar.rs:201` 还会对握手 `host` 做二次校验，非 127.0.0.1 直接判失败。
2. **令牌不经命令行传递**：Tauri 通过 `SYSMIND_SESSION_TOKEN` 环境变量注入（`sidecar.rs:111`），令牌为双 UUID（~244 bit 熵）；`scripts/test_packaged_desktop.py` 专门断言 `--session-token` 不出现在子进程命令行。`__main__.py` 的 `--session-token` 参数仅是开发便利（见 §4-14）。
3. **API 密钥不落 SQLite/日志**：`WindowsCredentialSecretService` 使用 Credential Manager（`CRED_PERSIST_LOCAL_MACHINE` 常量取值正确，`ERROR_NOT_FOUND(1168)` 正确映射为 `None`）；`provider_settings.py` 保存失败时有完整的密钥回滚逻辑；日志层 `JsonFormatter` + `is_sensitive_key` 双重脱敏。
4. **模型不能执行任意命令**：工具仅能来自 `ToolRegistry`（名称/版本正则、超时上限、schema 校验在注册期强制）；`ToolPolicy` 拒绝非 read-only、非 user 权限、需确认的工具；planner 层 `validate_plan` 再次独立校验（未知工具、越权、network 工具只允许 network 类问题、参数对 schema 验证、重复工具）；OpenAI 适配器对 tool name 做编码碰撞检测。PowerShell 仅在 `diagnostics.py` 中以**固定命令模板**调用（无任何用户输入拼接）。
5. **状态变更动作的完整闭环**（Phase 5a/5b）：证据绑定候选 → 参数绑定计划 → 确认（进程终止需二次确认，30 秒窗口）→ HMAC 票据（绑定 action/tool/target 哈希/revision/session/过期时间/nonce，密钥进程内存态、重启即失效）→ 数据库 CAS 消费（`consume_confirmation` 用 UPDATE…WHERE consumed_at IS NULL AND expires_at >= now 防重放）→ 执行期持锁 → 30 秒计划过期复查 → 执行后验证 → 恢复记录 → 全程审计事件。取消/过期/参数篡改/重启失效全部有测试覆盖。
6. **进程终止的防误伤链**（`process_actions.py`）：仅限同会话 + 同用户 SID + 非提权目标；保护名单（系统进程 + 关键 shell + 安全软件关键词）；`IsProcessCritical` 失败即视为关键进程（fail-closed）；目标身份 = SHA256(pid + 创建时间)，天然免疫 PID 复用；终止后 3 秒验证退出。
7. **证据闭环（fail-closed）**：报告生成后 `_validate_report_evidence` 逐一验证 evidence 引用的 tool_call 存在、已完成、且字段路径真实存在（自研受限 JSONPath 子集，正则白名单 + 逐段解析，无执行风险）；任何引用无效则整个诊断失败，绝不产出无证据报告。
8. **隐私**：事件日志只读白名单通道、XPath 全部数值化拼接、事件文本经账户名/路径/IP/MAC/邮箱脱敏后才入库；导出报告再过一次 `redact_text`；发给云模型的内容剥离原始问题并只用最小 findings 摘要（`report_explainer.py:93` 显式注释 `del question`）。
9. **日志管道无死锁**：Python logging 默认写 stderr；Rust 侧 stderr 有独立线程持续排空至 EOF，stdout 仅匹配 `SYSMIND_ENDPOINT ` 前缀，其余行忽略——握手通道与日志通道不会互相污染或阻塞。

---

## 4. 发现的问题

严重级别：P1 = 阻断发布；P2 = 应修复；P3 = 低危/打磨；P4 = 观察。

### P2-1 潜在循环导入：`sysmind.tools.executor` ↔ `sysmind.agent.brain`（导入顺序脆弱）

- 位置：`tools/registry.py:11`（`from sysmind.agent.contracts import ToolDescriptor`）、`tools/executor.py:17 → tools/policy.py:5 → tools/registry.py`、`agent/brain.py:24`、`agent/__init__.py:1`
- 现象（实测确认）：
  - `python -c "import sysmind.tools.executor"` → `ImportError: cannot import name 'ToolExecutionResult' from partially initialized module`（崩溃）。
  - 先导入 `sysmind.agent.brain` 再导入 `sysmind.tools.executor` → 正常。
- 影响：当前所有生产入口（`__main__` → api.app、bootstrap、alembic env、export-openapi）恰好都以"先 import agent 包"的顺序加载，所以**用户实际使用不受影响**（pytest 全绿也印证）。但任何新脚本、新入口、或某天有人把 `tools.registry` 的导入提前（例如某个 route 或第三方集成），就会当场崩溃。`api/routes/agent_tasks.py` 中 `sysmind.tasks`（触发 agent 导入）排在 `sysmind.tools.registry` 之前，正是靠 isort 字母序"侥幸"安全。
- 建议：解耦根因——`tools/registry.py` 不应反向依赖 `agent` 包。把 `ToolDescriptor` 下沉到 `tools/contracts.py` 或让 `registry.descriptor()` 返回本地结构，由 `agent` 层做映射。
- 附带说明：这条同时解释了为什么静态层面 mypy/ruff 都没报警——它只在特定运行时导入顺序下发生。

### P2-2 启动项停用"验证失败"路径会遗留孤儿恢复目录并丢失恢复链

- 位置：`windows/startup_actions.py:130-131`（执行后复核）+ `actions/coordinator.py:283-290`（`ToolUnavailableError` → `verification_failed`，且不回填 `recovery_id`）
- 场景：`disable()` 成功删除 Run 键值后，若在复核 `candidates()` 时该条目又被第三方进程立即重建，会抛 `ToolUnavailableError("Startup action could not be verified.")`。协调器把动作置为 `verification_failed`，但**不会**调用 `set_status(recovery_id=...)`，导致：恢复材料已写到磁盘（`action-recovery/<uuid>/`）且变更已实际生效，而数据库动作记录没有 `recovery_id` → 用户无法通过"恢复自动启动"找回，磁盘上留下孤儿目录。
- 概率评估：低（需要第三方在毫秒级窗口内重建同条目），且系统状态未损坏（条目=用户自己原来的值）。但这是审计/恢复链上的真实裂缝。
- 建议：`verification_failed` 分支若本地已知 recovery_id，应一并写入 `recovery_id`（数据库有 `RecoveryRecordModel` 支撑），或在此分支清理恢复目录。

### P2-3 普通生产构建（非 -Release 流程）下更新器 UI 会误导用户

- 位置：`features/updates/UpdatePanel.tsx:16`（`updaterAvailable = import.meta.env.PROD || MODE === "test"`）+ `tauri.conf.json` 的 `plugins.updater.pubkey/endpoints` 为空
- 现象：正式发布流程（`package.ps1 -Release`）会通过 overlay 注入 pubkey/endpoints，该路径没问题。但任何人直接 `pnpm tauri build` 得到的 PROD 构建 updater 未配置：按钮可点，点击后必然失败，用户看到"暂时无法连接安全更新服务"——把"未配置"误报成"网络问题"。
- 建议：`pubkey` 为空时也按"开发构建不提供更新"处理，或把 `latest.json` 检查 404 与配置缺失区分开。

### P3（低危 / 打磨项）

1. **等待用户输入时进度条回退到 5%**：`repositories/diagnoses.py:272` 的 `wait_for_input` 硬编码 `progress = 5`。若诊断已执行多轮工具（进度 40%+）后 Agent 决定 ask_user，UI 进度条会跳回 5%。
2. **日志分析取消时摘要自相矛盾**：`application/services/log_analysis.py:385-390`，`_finish_cancelled` 写入 `event_count: len(events)` 但 `events: []`——计数与内容不一致；且与 `quick_scan` 取消时保留已收集摘要的行为不对称。
3. **`replace_hypotheses` 空集不清理旧行**：`repositories/diagnoses.py:368-374`，仅当新假设集非空才删除失效键；若某轮生成零假设，历史假设会残留。当前 HypothesisEngine 恒返回 ≥1 条，未实际触发。
4. **`LOG_TOOL_SPECS[0]/[1]` 位置索引**：`log_analysis.py:143-144` 用下标取 spec，将来重排 `LOG_TOOL_SPECS` 元组顺序会静默错位（name 对、timeout 错）。建议改为按名称查找。
5. **超时后工作线程不可中断（已知限制）**：`ToolExecutor.execute`、quick_scan、log_analysis 的 `asyncio.wait_for(asyncio.to_thread(...), timeout)` 超时只是放弃等待，线程会继续运行到 handler 自然结束。有全局 30 秒预算、probe 内部 deadline（如事件日志 10 秒）和取消事件兜底，线程数量有界（每步一个），可接受；但值得作为已知行为记录。
6. **Provider 轮询等待**：`agent/brain.py:212-217` 用 25ms 轮询 `provider_task.done()` 而非纯 await（为了检查取消事件）。功能正确，轻微低效。
7. **前端 SSE 重连无退避上限**：`AgentTaskPanel.tsx:124-128`，任务活跃期间若后端持续不可用，每 350ms 无限重试（有错误提示，无指数退避）。
8. **计划列表 React key 依赖"计划不重复同一工具"**：`DiagnosisPanel.tsx:371` `key={step.tool}`。当前 `validate_plan` 的 already_called 机制保证不重复；若未来校验放宽会撞 key。
9. **`export_diagnosis(format=...)` 遮蔽内建 `format`**：`api/routes/diagnoses.py`。无运行时影响（ruff 未启用 flake8-builtins）。
10. **前端测试偏薄**：`HistoryPanel`、`SettingsPanel` 各仅 1 个测试；`ControlledActions` 的双确认流有 3 个测试覆盖但未覆盖 reconcile 全部分支。后端测试（154 个）覆盖失败路径很扎实，前端可对齐。
11. **`--session-token` argv 参数**：`__main__.py` 允许令牌走命令行（会进进程列表）。Tauri 正式路径与打包测试都不用它，且 release checklist 有对应检查项，属可控的开发便利。

### P4（正面确认，避免误判为问题）

- 各协调器 `_run` 捕获 `asyncio.CancelledError` 后不 re-raise：任务以"正常结束 + 状态落库"代替 cancelled 状态。这是全库一致的模式，shutdown/cancel 语义均正确，仅与"task.cancelled()"的教科书预期不同。
- `wait_until_ready`/`send_http_request`（Rust）是手写 HTTP/1.1——只打自家 loopback 后端、固定路径、800ms 超时，攻击面为零，属于合理取舍。

---

## 5. 实测排除的疑点（复核过程中怀疑过、已验证不是问题）

1. **诊断删除的外键级联**：`diagnosis_steps.tool_call_id` 外键（migration 0009）没有 ondelete 规则，理论上父表 `diagnosis_tool_calls` 先被级联删除时会触发 FK 约束失败。实测（对迁移到 head 的真实 schema 构造"已完成诊断 + 步骤链接 tool_call"场景）：删除成功，9 张子表全部清空、无残留。SQLite 的级联顺序在此 schema 下安全。建议将来补一个固化此行为的回归测试，防止模型/迁移改动悄悄破坏。
2. **`channels[0]` 越界**：`log_analysis.py:150` 取 `channels[0]`，看似可能在空列表时崩溃——DTO `min_length=1` 已在上游挡住。
3. **`asyncio.create_task` 在同步方法中调用**：四个协调器的 `start()` 都要求事件循环——所有调用点均为 async 路由，且路由内注释明确说明该约束。
4. **OpenAPI 契约漂移**：再生成后 `git diff` 零差异。
5. **stdout 握手污染**：见 §3-9，通道隔离正确。

---

## 6. 代码质量亮点（值得保持）

1. **`sidecar.rs` 的 generation 机制**：每次 start/shutdown 递增代数，所有异步线程（stdout 解析、健康探测、子进程监控）回写前先比对代数，陈旧线程的失败不会污染新会话——这是 sidecar 生命周期代码里最容易出错的地方，这里处理得干净，且有专门单测（`stale_generation_cannot_publish_failure`）。
2. **Windows Job Object（KILL_ON_JOB_CLOSE）**：保证 sidecar 及其全部后代随主进程消亡，符合 ADR-002。
3. **失败即失败的报告哲学**：`_validate_report_evidence`、`EvidenceComposer.compose_references`（引用缺失即抛错）、`diagnosis_tool_calls` 全量留本地而模型只见摘要——PRD 的"100% 结论带证据"不是口号，是 fail-closed 代码。
4. **DTO/输入校验完备**：所有请求模型 `extra="forbid"` 或强校验（长度、范围、白名单 Literal、去重）；工具注册期校验（名称正则、超时 0<t≤60、schema 非空、handler 可调用）。
5. **取消/超时/预算的真实测试**：154 个后端测试覆盖了取消竞态、超时映射、轮次/工具预算、重复调用熔断、prompt 注入越权、SSE 重连、重启中断恢复等失败路径——不是只测 happy path。
6. **迁移链完整可回滚**：0001–0010 与 ORM 模型逐列一致，downgrade 全部实现且顺序正确。
7. **可访问性**：面板错误边界、`aria-live` 状态播报、`focus-visible` 样式、确认卡片自动聚焦、`prefers-reduced-motion` 适配。

---

## 7. 建议的后续动作（按优先级）

1. 修复 P2-1 循环导入（约 30 分钟：移动 `ToolDescriptor` 到 `tools/contracts.py`，`agent/contracts.py` re-export 保持兼容）。
2. 修复 P2-2 的 recovery_id 丢失分支（`coordinator.py` 的 `ToolUnavailableError` 分支带上已知 recovery_id）。
3. 补两个回归测试：诊断删除级联（固化 §5-1 实测行为）、`import sysmind.tools.executor` 可独立导入（防止 P2-1 复发）。
4. P3 项可随手清理：`wait_for_input` 进度、取消摘要一致性、`LOG_TOOL_SPECS` 名称查找。
5. 发布前按 `docs/release-checklist.md` 完成：未勾选项（升级路径验证、签名物料、干净 VM 的 Phase 5/6 隔离测试）仍是发布前置条件，本报告不替代该清单。

---

## 8. 结论

对"每一行代码是否正确、功能是否有缺陷"的直接回答：**未发现会导致错误行为或功能失效的阻断级缺陷；发现 1 个依赖导入顺序的潜在崩溃点（P2-1）、1 个罕见但真实的恢复链裂缝（P2-2）、1 个构建路径下的 UI 误导（P2-3），以及 11 个低危打磨项。** 所有安全边界在代码层面成立并有测试背书；建议完成上述 1–3 项后即可继续推进 v0.1.0 发布流程。

---

## 9. 修复记录与复核验证（2026-08-30 追记）

报告发出后，修复已落在工作区（未提交）。逐项 diff 核对结论如下。

### 9.1 修复落实情况

| 报告条目 | 修复方式 | 配套测试 |
|---|---|---|
| P2-1 循环导入 | `ToolDescriptor` 下沉到 `tools/contracts.py`；`tools/registry.py` 改从 `tools.contracts` 导入；`agent/contracts.py` 以 `import ... as ToolDescriptor` 显式再导出保持兼容 | `test_executor_can_be_imported_without_agent_import_order_dependency`（子进程独立导入 `sysmind.tools.executor`） |
| P2-2 恢复链断裂 | 新增 `ActionVerificationError(recovery_id=...)`（ports/actions.py）；`startup_actions.disable` 验证失败时携带 recovery_id；协调器持久化 recovery_id；`create_restore` 与 DTO `recovery_available` 接受 `verification_failed`；前端恢复按钮按 `recovery_available` 显示 | `test_disable_verification_failure_keeps_recovery_chain`（端到端：验证失败 → recovery 落库 → 从失败动作创建恢复 → 执行成功 → 适配器状态还原）+ `ControlledActions` 前端测试 |
| P2-3 更新器 UI 误导 | 改为构建期环境变量门控 `VITE_SYSMIND_UPDATER_AVAILABLE`；`package.ps1` 仅在 `-Release` 时置 `true` 并在 finally 中还原环境 | 既有 `UpdatePanel` 测试不受影响（test 模式默认可用） |
| P3-1 进度回退 | `wait_for_input` 不再写 `progress=5`，保留当前进度 | `test_waiting_for_input_preserves_existing_progress`（55 保留） |
| P3-2 取消摘要矛盾 | `_finish_cancelled` 保留取消前已收集事件（排序截断至 max_events）并附加 notice | `test_cancelled_analysis_keeps_consistent_partial_event_summary` |
| P3-3 空假设不清理 | `replace_hypotheses` 空集时也删除全部旧行 | `test_replacing_hypotheses_with_empty_set_removes_stale_rows` |
| P3-4 位置索引 | `LOG_TOOL_SPECS` 改按名称查找 | 既有超时测试被强化为**故意交换 spec 顺序**以回归此修复 |
| P3-7 SSE 无退避 | `agentTaskReconnectDelay`：350ms 指数退避、5s 封顶 | `backs off repeated SSE reconnects with a bounded delay` |
| P3-8 React key | `key={\`${step.tool}-${index}\`}` | — |
| P3-9 内建遮蔽 | 参数改名 `export_format`，`Query(alias="format")` 保持线上契约不变（已实测 OpenAPI 零差异） | — |
| P3-11 argv 令牌 | 彻底移除 `--session-token` CLI 参数，README 改用环境变量并示范清理 | `test_packaged_desktop` 的 token-not-in-argv 断言仍有效 |
| §7-3 级联回归测试 | — | `test_diagnosis_delete_cascades_plan_step_and_linked_tool_call`（plan/step/tool_call 链接场景，经 API 删除后逐一断言 4 表清空） |

未修改项（报告原判为"已知限制/可接受"）：P3-5 `to_thread` 超时不可中断、P3-6 provider 轮询等待、P3-10 前端测试覆盖（已部分改善：+2 个测试）。

### 9.2 修复后全量质量门（实测）

| 质量门 | 结果 |
|---|---|
| 后端 `ruff check` | 通过 |
| 后端 `mypy --strict`（120 文件） | 通过 |
| 后端 `pytest` | **160 通过**（较复核时 +6），4 跳过（破坏性 Sandbox 测试，符合设计） |
| 前端 `eslint --max-warnings 0` | 通过 |
| 前端 `tsc -b` | 通过 |
| 前端 `vitest` | **36 通过**（+2） |
| Rust `cargo test --lib` | 5 通过 |
| OpenAPI 契约再生成对比 | 零差异 |
| `import sysmind.tools.executor` 独立导入 | 通过（原缺陷消除） |

### 9.3 追记结论

报告 §4 与 §7 所列问题已全部按建议方案修复或有意识的取舍关闭，新增 9 个回归测试固化修复行为，全部质量门实测通过。工作区改动待提交（当前分支 `agent/release-materials-v0-1-0`）。
