# SysMind AI 全量代码复审报告（第二轮）

- 审查日期：2026-09-02
- 审查基线：分支 `agent/release-materials-v0-1-0`，HEAD `986f824`（第一轮修复提交后的干净树）
- 审查方式：在第一轮（2026-08-30）逐行审查的基础上，对**全部文件、每一行代码**重新扫描，不因已审查过而跳过；对第一轮报告的 11 项修复逐行核对是否引入回归；对 29 个后端测试文件、11 个前端测试文件与 styles.css（2175 行）本轮完成全文逐行；对存疑点编写只读探针实测。
- 性质：只读审查，未修改任何代码。

---

## 1. 总体结论

**本轮全量扫描未发现任何结构性、逻辑性或功能性错误级（P1/P2）缺陷，未发现第一轮修复引入的回归。** 新发现 4 个 P4 级（外观/防御纵深/健壮性打磨）问题与若干沿袭的已知限制，均不影响正确性与安全边界。

质量门状态（本会话早前在与 `986f824` 完全一致的树上实测）：后端 ruff ✓、mypy strict ✓、pytest **160 通过**+4 设计性跳过、前端 eslint ✓、tsc ✓、vitest **36 通过**、Rust cargo test **5 通过**、OpenAPI 契约零差异。

---

## 2. 本轮覆盖清单

| 范围 | 数量 | 本轮方式 |
|---|---|---|
| 后端 `src/sysmind/**` | 120 文件 | 全部重读；11 个变更文件（第一轮修复）逐行精读并做导入/行为探针 |
| 后端 `tests/**` | 29 文件（4541 行） | **全文逐行**（第一轮为通读+重点核对） |
| 前端 `src/**` | 38 文件 | 全部重读；6 个变更文件逐行精读 |
| 前端测试 | 11 文件 | 全文逐行 |
| `styles.css` | 2175 行 | **全文逐行**（第一轮仅结构抽查），含括号平衡与自定义属性核对 |
| Tauri Rust（sidecar.rs/lib.rs/main.rs） | 3 文件 | 全部重读 |
| 配置/CI/脚本/契约 | pyproject、alembic.ini、tauri.conf、capabilities、vite/tsconfig/eslint、ci.yml、release.yml、package.ps1、check.ps1、run-phase5a/6.ps1、export-openapi.py、test_packaged_backend/desktop.py、PyInstaller spec、handshake schema、OpenAPI | 全部重读 |
| 文档 | README、INSTALL、USER_GUIDE、LIMITATIONS、PRODUCT、DESIGN、privacy、security、SECURITY、release-checklist、releases/cases/progress、第一轮报告 | 一致性与交叉引用核对（全部引用文件存在） |

---

## 3. 第一轮修复的回归核对（全部通过）

对 `c36b0a8` 的 11 项修复逐行核对结论：

| 修复 | 核对结果 |
|---|---|
| P2-1 ToolDescriptor 下沉 `tools/contracts.py` | ✓ 无循环；6 个关键模块独立导入探针全部 OK |
| P2-2 `ActionVerificationError(recovery_id=...)` | ✓ except 链次序正确（268 行先于 293 行 ToolUnavailableError）；restore 失败时不消费原始 recovery（可重试）；`create_restore`/DTO/前端按钮三处状态集一致 |
| P2-3 `VITE_SYSMIND_UPDATER_AVAILABLE` 门控 | ✓ `package.ps1` finally 还原环境变量；vitest 模式默认可用使既有测试不受影响 |
| P3 进度/取消摘要/空假设清理/spec 名称查找/React key/format 遮蔽/SSE 退避/argv 令牌移除 | ✓ 逐一核对；`export_format` 的 `Query(alias="format")` 保持 OpenAPI 零差异（实测） |
| 9 个新回归测试 | ✓ 断言正确且与实现互洽；其中 `test_event_logs` 既有超时测试被强化为故意交换 spec 顺序，覆盖名称查找修复 |

特别核对过的边界：`_finish_cancelled` 三个调用点均传入 `max_events` 并按统一排序截断，与正常路径口径一致；`replace_hypotheses` 的 DELETE 借助 autoflush 先落新行、`not_in(active_keys)` 不会误删本轮数据；`resume_with_input` 的 UPDATE…RETURNING 原子认领 + 同事务身份映射同步正确（有测试固化）。

---

## 4. 本轮新发现（全部为 P4 打磨级）

### P4-1 styles.css 使用了从未定义的 CSS 自定义属性（9 处无回退）

- 位置：`styles.css:44, 1538, 1565, 1598, 1623, 1736, 1778, 1900, 1940, 2104`
- 现象（grep 实证）：`--text-strong`、`--text-body`、`--text-muted`、`--panel`、`--muted`、`--danger` 六个变量在样式表与 `index.html` 中**均无定义**。带回退的用法（如 `var(--border, #d8dde5)`）正常解析；无回退的 9 处（`color: var(--text-strong)` 等）按 CSS 规则成为"计算值时无效"声明，回落到**继承色**。
- 影响：由于 body 基色 `#1a241f` 与设计意图的深色文本几乎相同，视觉上无可辨破损——属于死变量/设计令牌残留，不是可见 bug。
- 建议：在 `:root` 补齐这 6 个定义，或统一改为带回退的字面量。

### P4-2 `ConsentService.verify` 对"HMAC 合法但载荷为非 JSON 对象"的票据会抛出契约外异常

- 位置：`security/consent.py`（`verify` 内 `payload.get(...)` 前未校验 `isinstance(payload, dict)`）
- 现象（探针实证）：构造合法 HMAC 签名但载荷为 `["x"]` 的票据 → `verify` 抛 `AttributeError`，逃出 `ConsentError` 契约；`ActionCoordinator.execute` 的票据验证段只捕获 `ConsentError`（`actions/coordinator.py:216`），该异常会继续冒泡成 HTTP 500。
- 可达性：**外部不可达**——签名校验先于 JSON 解析，只有本服务 `issue()` 能产出合法签名，而 `issue()` 恒生成 JSON 对象。属纯防御纵深问题。
- 建议：解析后加一行 `if not isinstance(payload, dict): raise ConsentError("Consent ticket is invalid.")`。

### P4-3 `ProviderSettingsService.test_connection` 只捕获 `ProviderError`

- 位置：`application/services/provider_settings.py:110`、`api/routes/settings.py`（`test_provider` 仅映射 ValueError→409）
- 现象：provider 实现若抛出 `ProviderError` 之外的异常（未来适配器 bug），`/api/v1/providers/test` 会以 500 冒泡（FastAPI 默认 500 不泄漏细节，correlation id 仍在）；且该次测试不会写入 `provider_connection_tests` 审计行。
- 建议：捕获 `Exception` 记为 `failed`/`internal_error` 审计后返回，与"provider 失败降级"的产品口径一致。

### P4-4 Rust 侧握手不校验 `backend_version`

- 位置：`sidecar.rs` `EndpointHandshake { host, port, api_version }` vs `contracts/schemas/sidecar-handshake.schema.json`（`backend_version` 为 required）
- 现象：JSON schema 把 `backend_version` 列为握手契约必填，Python 侧也确实发送；但 Rust 反序列化结构没有该字段，等于只按 `api_version` 门控协议偏斜，不感知后端二进制版本。
- 影响：前后端同包分发、版本恒一致，实际风险极低；属契约完备性观察。

### 沿袭的已知限制（第一轮已判定可接受，本轮复核维持原判）

1. `wait_for + to_thread` 超时后工作线程不可中断，靠 probe 内部 deadline 与全局 30s 预算兜底。
2. `agent/brain._call_provider` 用 25ms 轮询检测取消（功能正确，轻微低效）。
3. `startup_actions.restore` 中元数据 `KeyError` 会被映射为 `ToolPermissionError`（语义略偏，但恢复材料保留、可重试）。
4. 前端 `SettingsPanel`/`HistoryPanel` 测试仍偏薄（1 个/文件）——本轮未再扩大测试面。

---

## 5. 重查确认无缺陷的关键点（本轮再次验证）

1. **并发与异步边界**：所有 `asyncio.create_task` 调用点均在事件循环上（async 路由或已运行的协程内）；阻塞存储/凭据调用走 `run_in_threadpool` 或 `to_thread`；`ActionCoordinator.execute` 持锁 + 票据 CAS 消费，无双执行路径；SSE 轮询用 `to_thread` 且以 `Last-Event-ID` 单调推进。
2. **资金/审计型状态机**：动作状态机（proposed→confirmed→executing→verifying→succeeded/…）所有异常分支都落到终态；`mark_interrupted` 覆盖全部中间态；重启后无任何自动重放。
3. **证据闭环**：`_validate_report_evidence` + `EvidenceComposer` fail-closed；受限 JSONPath 正则白名单（`$.__class__.__mro__`、`$[lambda:1]` 注入用例有测试）。
4. **脱敏链**：日志 formatter、事件摘要、报告导出、provider 请求四层脱敏互为冗余；正则对时间戳（`12:34:56`）与 UNC 路径的边界行为有专项测试。
5. **迁移与模型**：0001–0010 与 ORM 列级一致；升级/回滚 round-trip 测试存在；诊断删除级联有回归测试固化（本轮修复新增）。
6. **前端状态机**：各面板轮询/SSE 均随终态停止并清理定时器；反馈防重、SSE 事件去重、指数退避上限、abort 传播均正确。
7. **文档与代码同步**：README 所有引用文件存在；`--session-token` 在全部代码/文档中已无残留（除历史审查记录）；安全文档描述与实现逐条对得上。

---

## 6. 结论

第二轮全量逐行扫描的答案：**没有发现新的结构、逻辑或功能错误与 BUG**。第一轮的全部修复被证实未引入回归；遗留问题仅为 4 个 P4 打磨项（CSS 死变量、consent 防御纵深、provider 测试异常映射、握手版本字段）与若干第一轮已判定可接受的已知限制。项目在当前基线上可继续推进发布流程；P4 项可作为低优先级随手清理，不构成发布阻碍。

---

## 7. P4 修复验证记录（2026-09-02 追记）

§4 的 4 个 P4 项已全部修复并测试固化：

| 项 | 修复方式 | 配套测试 |
|---|---|---|
| P4-1 CSS 死令牌 | 在 `:root` 依据 `.impeccable/design.json` 补齐 7 个设计令牌（`--text-strong: #1a241f`、`--text-body: #526159`（Strong Ink 色阶第 4 档，对比度约 6.2:1）、`--text-muted: #667085`、`--panel: #fff`、`--border: #d8dde5`、`--muted: #5e6b62`、`--danger: #b42318`），并将全部 8 处带回退用法统一为裸 `var(--token)`（0 处残留回退）；`:root` 文本色同步引用令牌 | 前端 production build 编译通过；vitest 36 通过 |
| P4-2 consent 载荷类型 | `verify` 在 JSON 解析后增加 `isinstance(payload, dict)` 防御，非对象载荷归入 `ConsentError` 契约 | `test_consent_verify_rejects_signed_non_object_payloads`（自签非对象票据，断言 ConsentError） |
| P4-3 provider 测试异常映射 | `test_connection` 增加 `except Exception` 兜底：记 `internal_error` 失败审计（`log_event` 仅含 error_type），返回 `succeeded=False`；`CancelledError` 不受影响（BaseException） | `test_provider_test_connection_maps_unexpected_errors_to_failed_audit`（注入抛错 provider，断言返回值与 `provider_connection_tests` 审计行） |
| P4-4 握手版本字段 | `EndpointHandshake` 增加 `backend_version`（`Option<String>`）；四处契约检查抽取为 `handshake_contract_error`，缺失/空白 `backend_version` 给出精确失败消息；不比较跨版本相等（保留 `SYSMIND_BACKEND_EXECUTABLE` 混合版本开发缝，`api_version` 仍是协议门控） | Rust 新增 2 个契约测试（缺字段/空白字段/非 loopback/协议不匹配四情形），既有 2 个握手测试更新为 schema 完整形态 |

### 修复后全量质量门（实测）

| 质量门 | 结果 |
|---|---|
| 后端 `ruff check` | 通过 |
| 后端 `mypy --strict`（120 文件） | 通过 |
| 后端 `pytest` | **162 通过**（+2），4 跳过（破坏性 Sandbox 测试，符合设计） |
| 前端 `eslint` / `tsc` / `vitest` | 通过 / 通过 / **36 通过** |
| 前端 production build | 通过 |
| `cargo fmt --check` / `cargo test --lib` | 通过 / **7 通过**（+2） |
| OpenAPI 契约再生成对比 | 零差异（设置服务行为变化不影响 API 形状） |

§6 结论维持成立：P4 项已清零，无阻断发布问题。
