# SysMind AI 新对话交接说明

更新时间：2026-08-19
工作区：`D:\SysMind AI`

## 给新对话的首要说明

当前工作区已在同一批未提交改动中连续完成 Phase 2、Phase 3 和 Phase 4。不要清理、重置、覆盖或只保留
Phase 4 文件；这些未提交内容共同构成当前可运行状态。开始任何新工作前，请先阅读：

1. `AGENTS.md`
2. `docs/SysMind-AI-PRD-and-Architecture.md`
3. `docs/adr/ADR-007-bounded-windows-event-log-analysis.md`
4. `docs/adr/ADR-008-bounded-agent-runtime.md`
5. `docs/adr/ADR-009-evidence-bound-diagnosis-reports.md`
6. `docs/progress/phase4-complete.md`

请先执行 `git status --short`，将现有修改视为用户已有工作。除非用户明确要求，不要使用
`git reset --hard`、`git checkout --`、`git restore` 或其他可能丢失改动的操作，也不要擅自提交或推送。

## 当前阶段状态

Phase 4 已按 PRD 完成，核心状态如下：

- Phase 2：Windows Event Log 只读分析、持久化、API 和桌面 UI 已存在。
- Phase 3：Provider 抽象、受限 Agent、Tool Registry/Policy/Executor、任务持久化、SSE 和桌面 UI 已存在。
- Phase 4：自然语言专项诊断、证据约束报告、导出、反馈、历史记录和桌面 UI 已完成。
- 数据库迁移链当前唯一 head 为 `0005_phase4`。
- OpenAPI 已重新导出至 `contracts/openapi/sysmind-local-api.json`。
- 尚未创建 Git commit。

## Phase 4 已完成内容

### 诊断领域与流程

- 支持性能、网络和应用崩溃三类问题的本地分类。
- 每类诊断使用固定、可审计的工具计划，不允许模型自行调用 Windows API、Shell 或任意命令。
- 诊断任务支持后台执行、持久化、进度查询、取消和进程重启后的 interrupted 恢复标记。
- 工具部分失败时保留成功证据并生成 partial 报告。
- 总诊断时间和 Provider 解释时间均有边界。

主要代码：

- `services/backend/src/sysmind/diagnosis/planning.py`
- `services/backend/src/sysmind/diagnosis/rules.py`
- `services/backend/src/sysmind/diagnosis/coordinator.py`
- `services/backend/src/sysmind/domain/diagnosis.py`
- `services/backend/src/sysmind/application/ports/diagnoses.py`

### Windows 只读工具

- 当前用户代理与 WinHTTP 默认代理读取。
- 固定白名单域名 DNS 查询。
- 固定白名单公共 IP 的有界 ICMP 测试。
- 分层网络诊断。
- Run 注册表、Startup 文件夹及可访问计划任务名称读取。
- Windows 服务元数据读取和本地规则分析。
- 不包含修改代理、禁用启动项、启停服务、终止进程或其他状态变更。

主要代码：

- `services/backend/src/sysmind/windows/platform_inspection.py`
- `services/backend/src/sysmind/tools/platform_tools.py`
- `services/backend/src/sysmind/tools/runtime_tools.py`
- `services/backend/src/sysmind/domain/platform_inspection.py`
- `services/backend/src/sysmind/application/ports/platform_inspection.py`

### 证据约束报告与模型边界

- 每个 finding 都必须引用真实的 `tool_call_id + field_path`。
- 报告保存前会验证引用完整性。
- Provider 仅接收 findings 投影，不接收原始用户问题和完整工具结果。
- Provider 超时或失败时回退到本地确定性解释。
- Provider 调用使用哈希审计，不保存敏感完整请求。
- JSON 和 Markdown 导出会再次脱敏路径、IP 和邮箱等内容。

主要代码：

- `services/backend/src/sysmind/prompts/report_explainer.py`
- `services/backend/src/sysmind/reports/composer.py`
- `services/backend/src/sysmind/reports/redaction.py`
- `docs/adr/ADR-009-evidence-bound-diagnosis-reports.md`

### 数据库与 API

- 新增 diagnoses、diagnosis tool calls、feedback 和 model-call audit 持久化。
- 新增创建、列表、详情、取消、反馈和报告导出 API。

主要代码：

- `services/backend/alembic/versions/0005_phase4_diagnoses.py`
- `services/backend/src/sysmind/infrastructure/database/models.py`
- `services/backend/src/sysmind/infrastructure/database/repositories/diagnoses.py`
- `services/backend/src/sysmind/api/dto/diagnoses.py`
- `services/backend/src/sysmind/api/routes/diagnoses.py`

### 桌面端

- 自然语言问题输入与只读边界说明。
- 网络诊断固定目标流量披露。
- 计划、进度、取消、证据 findings、置信度和限制展示。
- 历史报告选择、JSON/Markdown 导出及有用性反馈。
- 同一会话中新诊断与轮询结果会实时更新历史。
- 长 evidence reference 和移动端历史选择器已处理溢出。
- 反馈成功和 pending 状态均按 diagnosis ID 维护，防止同报告重复提交及跨历史切换竞态。
- UI 已完成 code-only 复审；当前环境未进行 Tauri/WebView 截图式视觉验证。

主要代码：

- `apps/desktop/src/features/diagnose/DiagnosisPanel.tsx`
- `apps/desktop/src/features/diagnose/DiagnosisPanel.test.tsx`
- `apps/desktop/src/services/diagnoses.ts`
- `apps/desktop/src/services/api-client.ts`
- `apps/desktop/src/styles.css`

## 最近一次完整验证结果

以下验证均于 2026-08-19 在当前 Windows 工作区通过：

### 后端

- Ruff：通过。
- mypy：94 个源文件无问题。
- pytest：75 项通过，1 个来自 Starlette TestClient/httpx 的依赖弃用警告。

命令：

```powershell
Set-Location 'D:\SysMind AI\services\backend'
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -q
```

### 前端

- ESLint：通过。
- TypeScript：通过。
- Vitest：20 项通过。
- Vite 生产构建：通过。

命令：

```powershell
Set-Location 'D:\SysMind AI'
pnpm lint
pnpm typecheck
pnpm test -- --run
pnpm build
```

### Tauri/Rust

- `cargo fmt --check`：通过。
- Rust：3 项测试通过。

命令：

```powershell
Set-Location 'D:\SysMind AI\apps\desktop\src-tauri'
cargo fmt --check
cargo test
```

### 迁移、契约和 Windows 实机

- `alembic heads` 输出：`0005_phase4 (head)`。
- OpenAPI 中 5 个 Phase 4 路径已验证存在。
- Windows `windows_smoke`：6 项通过、69 项未选择。
- 实机冒烟覆盖代理、启动项、服务、固定目标 DNS/ICMP 和完整性能诊断。

命令：

```powershell
Set-Location 'D:\SysMind AI\services\backend'
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m pytest -m windows_smoke -q

Set-Location 'D:\SysMind AI'
.\services\backend\.venv\Scripts\python.exe .\scripts\export-openapi.py
```

## 已知限制与注意事项

- 当前环境未配置真实云 Provider 凭据，没有发起真实云模型请求。Provider 成功、超时、失败回退和数据边界由契约测试覆盖。
- Phase 4 仍然严格只读。任何系统状态变更、管理员 helper、UAC、确认票据、执行后验证或恢复均属于 Phase 5，不能提前混入。
- DNS/Ping 只允许代码中定义的固定测试目标；不要开放任意网络目标。
- 不得将 API key、会话 token、Authorization header 或完整敏感请求写入 SQLite、日志、源码或浏览器存储。
- 当前 `git diff --check` 没有空白错误，但 Git 会在 Windows 上提示部分文件下次触碰时 LF 将转为 CRLF；这是换行提示，不是测试失败。
- 工作区包含 Phase 2、3、4 的大量 tracked/untracked 改动。不要根据文件是否 untracked 判断其是否可以删除。

## 新对话建议的接手顺序

1. 阅读本文件、PRD、AGENTS.md 和 ADR-007 至 ADR-009。
2. 执行 `git status --short`，确认未提交工作仍完整存在。
3. 若用户要求进入 Phase 5，先只分析 PRD 中 Phase 5 的明确范围和安全约束，再实施；不要创建未来阶段占位模块。
4. 修改后按 AGENTS.md 重新运行后端、前端和 Tauri 的全部质量门禁。
5. 若只需确认 Phase 4，不必重新实现；从 `docs/progress/phase4-complete.md` 和现有测试开始核验即可。
