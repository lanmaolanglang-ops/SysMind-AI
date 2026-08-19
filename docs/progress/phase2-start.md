# Phase 2 启动检查点

记录日期：2026-08-19

## 当前 Commit

- Commit：`c036e4fb0d049285d9b4e1bab9ad88e930d0ee86`
- 摘要：`feat: add Phase 1 read-only system scans`
- 分支：`main`
- 创建本文档前工作区状态：干净

## 已完成模块

### Phase 0：工程基础

- Tauri 2 + React + TypeScript strict + Vite 桌面端工程。
- FastAPI application factory、Pydantic Settings 和结构化日志。
- Tauri 管理 Python sidecar 的开发态生命周期，包括 loopback 随机端口、临时 session token、readiness、协议版本校验和优雅关闭。
- 统一前端 API Client，包括超时、错误归一化和 correlation ID。
- SQLite、SQLAlchemy 2、Alembic、WAL 和外键约束。
- SecretService 抽象及测试用 FakeSecretService；密钥不进入 SQLite 或日志。
- GitHub Actions 基础 CI 和 Windows smoke test。

### Phase 1：只读系统信息采集

- Windows Adapter：操作系统、CPU、GPU、内存、磁盘和进程快照。
- 短窗口高 CPU/内存占用进程识别；不提供进程终止能力。
- `system` 和 `process` 版本化只读工具封装。
- 工具能力探测、超时、取消、错误映射和部分失败处理。
- 快速扫描应用服务，包括后台执行、进度、取消、启动恢复和优雅关闭。
- 快速扫描 API：创建、查询、列表和取消。
- 扫描记录、步骤事件与安全结果摘要的 SQLite 持久化和审计。
- 前端设备概览、快速扫描、进度、取消、错误和证据展示。
- OpenAPI 契约、Phase 1 数据库迁移、ADR-006 和相关开发文档。
- 真实 Windows/Tauri 冒烟验证；退出应用后未留下 sidecar 子进程。

当前仍未实现 AI Agent、模型调用、Windows 事件日志读取、任意命令执行或系统修改能力。

## 当前测试状态

最近一次完整执行 `scripts/check.ps1` 的结果：

- Backend Ruff：通过。
- Backend mypy：通过，47 个源文件无类型错误。
- Backend pytest：24/24 通过。
- Frontend ESLint：通过。
- TypeScript strict typecheck：通过。
- Frontend Vitest：9/9 通过。
- Vite production build：通过。
- Rust/Tauri tests：3/3 通过。
- Rust formatting check：通过。
- `git diff --check`：通过，仅存在 Windows 行尾转换提示。
- 设计契约 JSON：解析通过。
- 最终前端可访问性审查：通过。

非阻塞警告：Starlette TestClient 对当前 `httpx` 集成产生一条弃用警告，后续依赖升级时处理。

## 下一步任务

执行架构基线中的 Phase 2：Windows 日志分析。

1. 阅读 PRD、现有 ADR、Phase 1 工具契约和审计实现，冻结 Phase 2 范围。
2. 定义事件日志领域模型、应用端口、版本化输入/输出 Schema 和错误分类。
3. 设计严格白名单查询参数：日志通道、时间窗口、事件级别、事件 ID 和最大返回数量。
4. 实现 Windows Event Log 只读 Adapter，并支持超时、取消、权限不足和能力不可用。
5. 实现 Application、System、Application Error 和 Windows Error Reporting 的限定范围读取。
6. 增加崩溃事件归一化、聚合与规则化摘要，不把原始完整日志默认发送到模型。
7. 接入现有任务、审计和持久化边界，保证单项失败不会阻断整体分析。
8. 增加日志分析 API 和基础前端展示，包括筛选、进度、错误与脱敏证据。
9. 使用脱敏 fixture 覆盖不同 Windows 语言、损坏事件、大结果集、超时和权限不足。
10. 在 Windows 10/11 环境执行只读冒烟测试，确认无系统修改和无限范围日志读取。

Phase 2 继续遵守：模型不得直接调用 Windows API、Shell 或 PowerShell；所有平台交互必须经过结构化 Tool 和 Windows Adapter；默认只读、最小范围、可取消、可审计。
