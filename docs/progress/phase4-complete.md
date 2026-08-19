# Phase 4 完成检查点

记录日期：2026-08-19

## 起点判断

Phase 3 已提供 Provider、受限 Agent、Tool Registry/Policy/Executor、任务持久化和 SSE。
进入本阶段时尚无自然语言问题分类、专项诊断计划、网络/启动项/服务工具、规则 findings、
证据约束报告、导出或反馈功能。

## 已完成范围

- 性能、网络和应用崩溃三类本地分类与固定计划模板；模糊问题明确标注限制。
- current-user/WinHTTP 代理、白名单 DNS/ICMP、分层 network diagnose 只读/受限网络工具。
- Run 注册表、Startup 文件夹、可访问计划任务名称和 Windows 服务元数据只读工具。
- 本地规则 findings、严重程度、建议、置信度和 `tool_call_id + field_path` 证据引用。
- 报告保存前证据完整性校验；失败工具保留成功证据并生成 partial 报告。
- Provider 只接收 finding 投影；超时/失败回退本地解释，调用使用哈希审计。
- 诊断历史、取消、崩溃恢复、JSON/Markdown 脱敏导出和有用性反馈。
- `/api/v1/diagnoses` 创建、列表、详情、取消、导出和反馈 API。
- 桌面端问题输入、网络范围说明、计划进度、证据报告、限制、历史、导出和反馈 UI。
- `0005_phase4` 数据库迁移、ADR-009、README、PRODUCT、DESIGN 和 OpenAPI 更新。

## 保持未实现

- 终止进程、修改代理、禁用启动项、启动/停止服务或任何其他系统状态变更。
- 管理员 helper、UAC、确认票据、执行后验证和恢复；这些属于 Phase 5。
- 任意目标 DNS/Ping、任意网络请求、任意事件通道或 Shell/PowerShell 命令。

## 验证结果

- 后端：Ruff 通过；mypy 检查 94 个源文件无问题；pytest 75 项通过。
- 前端：ESLint、TypeScript 和生产构建通过；Vitest 20 项通过。
- Tauri：`cargo fmt --check` 通过；Rust 3 项测试通过。
- 数据库：Alembic 仅有 `0005_phase4 (head)` 一个迁移头。
- API 契约：重新导出 OpenAPI，并验证 5 个 Phase 4 路径存在。
- Windows 实机：6 项只读冒烟通过，其中包含固定目标 DNS/ICMP、启动项/服务/代理和完整性能诊断。

当前环境未配置真实云 Provider 凭据，因此 Provider 的成功、超时和失败回退由契约测试覆盖，
没有发起真实模型调用。桌面端需要 Tauri bridge，未在普通浏览器中进行截图式视觉验证；代码级
响应式、焦点、长证据换行和交互状态均已完成评审与自动化验证。
