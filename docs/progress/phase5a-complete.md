# Phase 5A 完成检查点

记录日期：2026-08-20

> 历史增量记录：Phase 5 后续范围已完成，最终状态见 `phase5-complete.md` 与 ADR-011。

## 已完成范围

- 仅允许当前用户 Run 与 Startup 文件夹单项的禁用和恢复。
- Action Plan 必须关联包含已完成启动项证据的诊断。
- 参数、目标 revision、sidecar 会话绑定的两分钟单次确认票据；SQLite 只保存摘要。
- 确认、拒绝、执行、验证、失败、中断和恢复审计；重启不重放。
- Windows adapter 内部解析目标；拒绝链接、reparse point、路径越界和恢复覆盖。
- 执行前重新核验目标，执行后独立枚举验证；恢复需要新计划和新确认。
- 逐项确认/拒绝、结果和恢复桌面 UI。
- `0006_phase5a` 数据库迁移与版本化 REST/OpenAPI 契约。

## 保持未实现

- 进程终止、服务状态切换、代理/网络修改或其他状态变更。
- privileged helper、UAC、管理员权限或任意命令/路径输入。
- 批量确认、长期授权、模型直接动作和后台自动修复。

上述能力属于 Phase 5B 或更后阶段，必须再次进行威胁模型评审和用户确认。

## 隔离环境验收入口

- 新增 `destructive_sandbox` pytest 标记；默认测试命令始终跳过真实状态变更。
- `scripts/run-phase5a-isolated-tests.ps1` 要求显式确认，并且必须检测到 Windows Sandbox
  账户或 `C:\SysMind-Isolated-Test-VM.marker`，否则拒绝运行。
- 隔离测试使用唯一 `SysMindPhase5ATest-*` 项，覆盖 HKCU Run 的完整 ActionCoordinator、
  SQLite 审计、确认票据、revision 变化拒绝、禁用、验证、恢复冲突与恢复，以及临时
  Startup 文件禁用/恢复。
- 当前开发机没有可直接调用的 Windows Sandbox，且可选功能查询需要提升；因此真实状态
  变更测试尚未在本机执行。必须在一次性 Sandbox/VM 中运行后，才能进入 Phase 5B 复审。
