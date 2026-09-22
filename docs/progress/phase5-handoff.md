# SysMind AI Phase 5 交接说明

更新时间：2026-08-20
工作区：仓库根目录

Phase 2 至 Phase 5 位于同一批未提交工作中。不得重置、清理或覆盖这些文件；开始后续工作前
阅读 `AGENTS.md`、PRD、ADR-007 至 ADR-011，以及 `docs/progress/phase5-complete.md`。

Phase 5 已完成受控启动项禁用/恢复、GUI 优雅关闭及在 pending 后双重确认的单进程强制终止。
动作由应用层从诊断证据生成，模型 Tool Registry 保持只读。当前迁移唯一 head 为
`0006_phase5a`；尽管版本名保留首个增量名称，该 schema 已承载全部 Phase 5 动作审计。

服务控制有意不实现：具体服务安全白名单为空，因此没有 helper、UAC、服务变更模块或未来
占位。不要把黑名单当安全边界，也不要让 UI、模型或 API 传入任意服务名/命令。

默认质量门不会改变开发机状态。真实 Phase 5 Windows 测试必须在一次性 Sandbox/VM 中运行：

```powershell
.\scripts\run-phase5a-isolated-tests.ps1 -ConfirmIsolatedEnvironment
```

脚本名为兼容早期 Phase 5A 保留，当前会运行启动项与进程动作的全部隔离测试。当前开发机不
具备隔离 marker，因此这些测试应跳过而不是绕过。Phase 6 开始前仍应在干净 Windows 10/11
VM 中保存一次通过结果。

最终默认门禁：后端 Ruff/mypy 通过，pytest 87 passed/4 isolated skipped；前端 22 tests、
lint/typecheck/build 通过；Rust 3 tests 与 fmt 通过；迁移升级/回滚/再升级及 OpenAPI 检查通过。
