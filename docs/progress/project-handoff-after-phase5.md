# SysMind AI 新对话完整交接文档（Phase 5 完成后）

更新时间：2026-08-20
工作区：仓库根目录
当前阶段：**Phase 5 实现完成；下一开发阶段为 Phase 6 打包发布**

## 1. 新对话必须先知道的事情

当前工作区包含从 Phase 2 到 Phase 5 连续完成的一整批**未提交修改**。大量文件显示为 modified
或 untracked 是正常现状，不代表它们可以删除。不要执行 `git reset --hard`、`git checkout --`、
`git restore`、`git clean` 或任何会丢失现有工作的命令，也不要在未经用户要求时提交或推送。

接手后首先阅读：

1. `AGENTS.md`
2. `docs/SysMind-AI-PRD-and-Architecture.md`
3. `docs/adr/ADR-007-bounded-windows-event-log-analysis.md`
4. `docs/adr/ADR-008-bounded-agent-runtime.md`
5. `docs/adr/ADR-009-evidence-bound-diagnosis-reports.md`
6. `docs/adr/ADR-010-parameter-bound-current-user-startup-actions.md`
7. `docs/adr/ADR-011-evidence-bound-current-user-process-actions.md`
8. `docs/progress/phase5-complete.md`

随后运行 `git status --short`，把所有现有改动视为用户已有成果并原样保护。

## 2. 总体架构和不可突破的边界

- 桌面端：Tauri 2 + React + TypeScript + Vite。
- 本地后端：FastAPI + Pydantic + SQLAlchemy 2 + SQLite + Alembic。
- 支持目标：Windows 10/11 x64。
- 依赖方向必须保持 `presentation -> application -> domain`，Windows/数据库/Provider 是实现
  内层 port 的基础设施 adapter。
- FastAPI 仅监听 loopback 随机端口，并校验启动期会话令牌与 Origin。
- AI 模型不能直接调用 Windows API、Shell、PowerShell、CMD 或任意命令。
- 模型只能使用 Tool Registry 中版本化、结构化、默认只读的工具。
- API key、会话 token、确认票据原文、Authorization header 和完整敏感请求不得进入 SQLite、
  日志、源码、Git 或浏览器存储。
- 所有状态变更都必须由应用从真实诊断证据生成计划，逐项确认、参数绑定、审计、执行后验证；
  重启后不自动重放。

## 3. 已完成的阶段

### Phase 0–1：桌面骨架与系统采集

- Tauri 管理本地 Python sidecar，随机 loopback 端口和内存中的短期会话令牌。
- 健康检查、生命周期、SQLite/Alembic、结构化日志和基础 secret port。
- OS、CPU、GPU、内存、磁盘、进程快照和短窗口高占用采集。
- 快速扫描持久化、进度、取消、部分失败、API 和桌面 UI。
- Windows read-only 冒烟与 fixture 测试已存在。

### Phase 2：Windows 事件日志分析

- 仅允许 `Application`、`System` 白名单通道。
- 限制时间窗、级别、事件 ID 和最大记录数；不接受任意 XPath/通道输入。
- 本地规范化、脱敏、聚合常见错误、Application Error 和 WER 崩溃。
- 单通道失败时保留另一通道证据。
- 分析任务、持久化、API、桌面 UI 和 fixture 回归测试完成。

主要入口：

- `services/backend/src/sysmind/windows/event_logs.py`
- `services/backend/src/sysmind/tools/log/`
- `services/backend/src/sysmind/application/services/log_analysis.py`
- `apps/desktop/src/features/logs/`

### Phase 3：受限 AI Agent 框架

- Tool Registry、Policy、Executor 和版本化 Schema。
- Fake Provider 默认离线；OpenAI-compatible adapter 有契约测试，但没有使用真实用户密钥。
- 有限轮次、总时间、工具次数、重复调用、并发、超时和取消预算。
- 任务、事件、工具调用与模型审计持久化；SSE 可重连。
- 未知工具、非法参数、越权、重复或超预算调用 fail closed。
- 后端重启把执行中任务标为 interrupted，不重放模型或工具调用。

主要入口：

- `services/backend/src/sysmind/agent/`
- `services/backend/src/sysmind/tools/registry.py`
- `services/backend/src/sysmind/tools/policy.py`
- `services/backend/src/sysmind/tools/executor.py`
- `services/backend/src/sysmind/tasks/`
- `apps/desktop/src/features/tasks/`

### Phase 4：自然语言诊断与证据报告

- 性能、网络、应用崩溃三类问题的确定性分类和固定工具计划。
- proxy、固定目标 DNS/Ping、分层网络诊断、启动项和服务只读分析。
- 每个 finding 必须引用真实 `tool_call_id + field_path`；引用不完整不能保存报告。
- Provider 只接收受限 findings 投影，不接收原始完整工具结果；失败或超时回退本地解释。
- 支持 partial 报告、限制说明、诊断历史、取消、反馈，以及脱敏 JSON/Markdown 导出。
- 自然语言诊断与报告桌面 UI 已完成。

主要入口：

- `services/backend/src/sysmind/diagnosis/`
- `services/backend/src/sysmind/prompts/`
- `services/backend/src/sysmind/reports/`
- `services/backend/src/sysmind/windows/platform_inspection.py`
- `apps/desktop/src/features/diagnose/`

### Phase 5：受控修复

Phase 5 已实现并完成默认质量门禁，具体白名单如下。

#### 当前用户启动项

- `startup.disable_current_user@1.0`
- `startup.restore_current_user@1.0`
- 仅允许当前用户 Run value 或当前用户 Startup 文件夹中的普通单文件。
- 拒绝机器级项目、链接、reparse point、UNC/device path、目录、任意注册表/文件操作。
- 禁用前保存恢复材料；恢复是新计划、新确认，并拒绝覆盖后来变化或被占用的位置。

#### 当前用户 GUI 进程优雅关闭

- `process.request_close_current_user@1.0`
- 必须来自已完成/partial 性能诊断中被 finding 直接引用的高占用进程证据。
- 仅允许当前用户、当前 Session、非提权、带可见顶层窗口的单个 GUI 进程。
- opaque ID/revision 绑定 PID、创建时间、SID、Session、映像身份与窗口集合。
- 计划最长 30 秒；执行时重新核验；只发送固定 `WM_CLOSE`，最多等待 8 秒。
- 返回 `closed` 或 `close_pending`，绝不自动升级为强制终止。

#### 强制终止

- `process.terminate_current_user@1.0`
- 只能从刚刚返回 `close_pending` 的优雅关闭动作创建，不能直接从诊断创建。
- 新计划最长 30 秒，必须完成两个明确分离的确认步骤。
- UI 明示未保存数据可能丢失、没有恢复能力。
- 执行前再次核验完整进程身份；只调用固定 `TerminateProcess`，退出码不由 UI/模型输入。
- 执行后只有确认绑定进程身份消失/PID 已复用才成功；`AccessDenied` 等无法验证情况按失败处理。
- 第一次确认后若后端重启，动作标记 interrupted，不能继续使用旧确认阶段。

#### 永久保护边界

- 系统关键、安全软件、Shell、跨用户、跨 Session、较高权限、无窗口、身份读取失败以及
  SysMind 自身进程树不进入候选。
- UI/API 不接收任意 PID、窗口句柄、路径、命令、消息 ID 或退出码。
- 状态变更动作不注册到模型 Tool Registry；模型不能执行或生成确认票据。

#### 服务控制结论

Phase 5 的 `service.change_state` 白名单**有意保持为空**。当前只读证据不足以证明任何具体
Windows 服务可以安全启停，因此没有创建 privileged helper、UAC、服务变更模块或未来占位。
这不是遗漏，而是 ADR-011 的安全决定。未来若要实现，必须先提供：

- 具体、版本化、非空的内置服务白名单；
- 每项允许方向、依赖、恢复和验证规则；
- 独立签名最小权限 helper 的固定 IPC 协议与 UAC 行为；
- 新 ADR、安全复审以及 Sandbox/VM 验收。

主要入口：

- `services/backend/src/sysmind/actions/coordinator.py`
- `services/backend/src/sysmind/security/consent.py`
- `services/backend/src/sysmind/windows/startup_actions.py`
- `services/backend/src/sysmind/windows/process_actions.py`
- `services/backend/src/sysmind/api/routes/actions.py`
- `services/backend/src/sysmind/infrastructure/database/repositories/actions.py`
- `apps/desktop/src/features/diagnose/ControlledActions.tsx`
- `apps/desktop/src/services/actions.ts`

## 4. 数据库和 API 当前状态

- 当前 Alembic 唯一 head：`0006_phase5a`。
- 名称保留首个 Phase 5 增量，但该 schema 已承载整个 Phase 5 的 Action Plan、动作、事件、确认、
  短期 ticket digest、恢复记录和审计。
- 已验证 `0005_phase4 -> 0006_phase5a -> 0005_phase4 -> 0006_phase5a` 往返。
- OpenAPI 已导出到 `contracts/openapi/sysmind-local-api.json`。
- 已验证 Phase 5 的候选、创建关闭、创建终止、确认和执行关键路径存在。

## 5. 最近一次完整验证结果

记录于 2026-08-20：

- 后端 Ruff：通过。
- 后端 mypy：105 个源文件通过。
- 后端 pytest：`87 passed, 4 skipped, 1 warning`。
- 前端 ESLint：通过。
- 前端 TypeScript：通过。
- 前端 Vitest：`22 passed`。
- Vite production build：通过。
- `cargo fmt --check`：通过。
- Rust tests：`3 passed`。
- Alembic 升级、回滚、再升级：通过。
- OpenAPI Phase 5 关键路径：通过。
- `git diff --check`：无空白错误；仅有 Windows LF/CRLF 提示。

唯一普通 Python 警告来自 Starlette TestClient/httpx 的上游弃用提示。Rust 链接器也输出过一条
非失败提示；两者均未导致门禁失败。

复验命令：

```powershell
Set-Location '<repository-root>\services\backend'
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic heads

Set-Location '<repository-root>'
pnpm lint
pnpm typecheck
pnpm test -- --run
pnpm build

Set-Location '<repository-root>\apps\desktop\src-tauri'
cargo fmt --check
cargo test
```

## 6. 尚未完成或尚未验证的事项

### Phase 5 外部隔离验收

默认 pytest 中跳过的 4 项是真实 Windows 状态变更测试，不允许在普通开发机执行。它们覆盖：

1. 真实 HKCU Run 禁用、revision 冲突和恢复；
2. 临时当前用户 Startup 文件禁用与恢复；
3. 真实 GUI 程序的有界 `WM_CLOSE`；
4. 拒绝关闭后，经过完整前置流程的真实强制终止。

当前机器不满足 Sandbox/VM 双重安全门，所以这 4 项尚未实际执行。进入正式发布前，应在一次性
Windows Sandbox 或带快照的 VM 中运行并保存输出：

```powershell
Set-Location '<repository-root>'
.\scripts\run-phase5a-isolated-tests.ps1 -ConfirmIsolatedEnvironment
```

脚本名为兼容早期 Phase 5A 保留，目前会运行完整 Phase 5 启动项和进程隔离测试。不得伪造
`C:\SysMind-Isolated-Test-VM.marker` 在真实开发机绕过限制。

### 未做的产品/发布工作

- 尚未创建 Git commit，也没有 push 或 PR。
- 没有真实云 Provider 凭据，未发起真实云模型调用；成功、失败、超时和数据边界由 Fake/
  contract tests 覆盖。
- 尚未完成 Tauri/WebView 截图式人工视觉 QA。
- Phase 6 尚未开始：Python sidecar 冻结、安装包、代码签名、升级/卸载、发布 CI、隐私与许可
  文档、干净 Windows 10/11 VM 安装验证都未完成。
- 没有证书或签名密钥；以后也不得写入仓库。
- 服务状态修改、网络/代理修改、删除文件、驱动安装、批量动作、后台自动修复和任意命令执行
  均未实现，并且不能在没有新安全决策时顺手加入。

## 7. 新对话建议的接手顺序

1. 阅读本文件、AGENTS、PRD、ADR-007 至 ADR-011。
2. 在仓库根目录运行 `git status --short`，确认现有未提交成果仍完整。
3. 若目标是进入 Phase 6，严格按 PRD 的 Phase 6 范围先检查现有 Tauri/sidecar/CI 配置。
4. 不要重新实现 Phase 2–5，也不要用“清理工作区”删除 untracked 文件。
5. 开始 Phase 6 前，优先安排一次性 Windows VM 的 Phase 5 隔离测试并保存结果。
6. Phase 6 任何签名、发布、上传或外部凭据操作都必须先确认授权；不得把 secret 写入仓库。
7. 每次修改后继续运行后端、前端、Tauri、迁移和 OpenAPI 全部门禁。

## 8. 可直接复制到新对话的开场提示

```text
请先阅读 AGENTS.md、docs/SysMind-AI-PRD-and-Architecture.md 和
docs/progress/project-handoff-after-phase5.md。当前仓库工作区包含 Phase 2–5 的
大量未提交成果，必须全部保留，禁止 reset/restore/clean。Phase 5 实现已经完成，默认质量门
为后端 87 passed、前端 22 passed、Rust 3 passed；4 项真实状态变更测试只能在 Sandbox/VM
运行，目前尚未完成外部隔离验收。请根据交接文档确认状态后，再继续 PRD 的 Phase 6，不要
重新实现已完成阶段，也不要擅自提交、推送或加入服务控制/helper。
```
