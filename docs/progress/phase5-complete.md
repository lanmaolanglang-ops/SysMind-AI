# Phase 5 完成检查点

记录日期：2026-08-20

## 已完成范围

- Action Plan、风险状态、确认/拒绝审计、短期参数绑定单次票据、执行前重验、执行后验证、
  重启中断与失败状态。
- 当前用户 Run 与 Startup 文件夹单项禁用/恢复；恢复是新的计划和新的确认。
- 有高占用进程 finding 直接证据的当前用户 GUI 应用，可逐项请求优雅关闭；仅发送固定
  `WM_CLOSE`，等待最多 8 秒，绝不自动升级。
- 只有优雅关闭返回 `close_pending` 后，才能生成固定目标的强制终止计划；30 秒内完成两次
  明确确认，执行前再次核验 PID 创建时间、SID、Session、映像和窗口身份，执行后验证目标
  身份消失。
- 系统关键、安全、Shell、跨用户/Session、较高权限、无可见窗口、SysMind 自身及身份读取
  失败的进程均 fail closed。
- 桌面 UI 明确展示影响、不可恢复限制、保存提示、逐次确认、第二次终止确认和验证结果。
- 状态变更路径不进入模型 Tool Registry，不接受任意 PID、句柄、路径、命令、消息或退出码。
- `0006_phase5a` 迁移承载动作计划、确认、事件、恢复记录；REST/OpenAPI 契约已覆盖完整 Phase 5。

## 有意拒绝的范围

- `service.change_state` 白名单为空。现有只读服务证据不足以证明任何具体服务可安全启停，
  因此不创建 privileged helper、UAC 或服务动作占位模块。
- 不提供批量动作、长期授权、后台自动修复、进程树终止、任意命令执行、网络/代理修改、
  文件删除或注册表通用写入。

这些不是功能缺口，而是 ADR-011 和 PRD“可选 privileged helper / 只实现明确白名单动作”的
安全结论。未来若增加服务控制，必须先提交具体非空白名单和新的安全评审。

## 验证状态

- 默认单元/契约测试覆盖确认拒绝、篡改、重放、过期、目标变化、执行中断、恢复冲突、优雅
  关闭 pending、禁止自动升级、强制终止前置条件和双重确认。
- 真实状态变更测试有双重安全门，只能在 Windows Sandbox 或带 marker 的一次性 VM 中运行；
  覆盖 HKCU Run、Startup 文件、真实 GUI `WM_CLOSE` 和拒绝关闭后的真实强制终止。
- 当前开发机不满足隔离环境门，真实状态变更测试按设计跳过；不得为了得到绿色结果绕过门。

当前 Windows 工作区最终结果：Ruff 通过；mypy 105 个源文件通过；pytest 87 项通过、4 项
隔离测试跳过；前端 ESLint/TypeScript/22 项 Vitest/生产构建通过；Tauri `cargo fmt --check`
与 3 项 Rust 测试通过；Alembic `0005_phase4 -> 0006_phase5a -> 0005_phase4 ->
0006_phase5a` 往返通过；OpenAPI 的 5 个 Phase 5 关键路径已验证；`git diff --check` 无空白错误。
唯一普通警告来自 Starlette TestClient/httpx 的上游弃用提示，Rust 链接器另输出非失败信息。
