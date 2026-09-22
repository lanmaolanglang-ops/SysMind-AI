# Release Candidate 1：Product Validation & Polish 完成检查点

记录日期：2026-08-23

## 完成范围

- 沿用 Phase 3.1–3.3 的 Planner、Coordinator、Evidence Composer、Hypothesis 和多轮恢复，未增加 Windows 工具、Agent 层、页面、数据库表或系统修改能力。
- 将普通用户主入口文案收敛为“我的电脑有什么问题？”，保留常见问题示例、只读边界、网络固定目标说明、有限进度和取消入口。
- 报告中的每个 finding 在普通视图直接展示中文工具来源、检查时间和关键指标；Tool 名、版本、调用 ID 与字段路径只在技术引用中展示。
- Hypothesis 的支持证据和反证不再首先暴露内部 Tool/JSONPath，而先展示本机证据数量及友好证据摘要。
- Markdown 与 JSON 导出包含工具来源、检查时间、关键指标，并继续执行脱敏。
- 信息不足仍统一输出“当前证据不足，无法确定原因。”，综合置信度为 0，停止原因为 `insufficient_information`。

## 简化内容

- 删除不参与运行时、仅被测试使用的旧 `DiagnosticStep` / `plan_for()` 固定计划模板。测试 Registry 改用显式夹具工具清单，避免与 Phase 3.1 Planner 形成两套计划真相。
- 复用 `diagnosis_tool_calls` 已有的 `started_at` / `finished_at` 字段，没有新增追踪系统或数据库字段。
- 保持现有报告类型和单页工作流，没有增加聊天页面、评估平台或复杂展示。

## 最小场景验证

- `docs/cases/performance/`：电脑最近很卡。
- `docs/cases/network/`：无法联网。
- `docs/cases/crash/`：软件一直闪退。
- `docs/cases/startup/`：电脑开机很慢。
- 案例明确区分受控证据夹具与真实 Windows 适配器冒烟，不将夹具结果冒充真实用户设备故障。

## 稳定性与测试

- 工具失败保留成功证据并生成降权的 partial 报告。
- 数据不足不猜测；用户取消、等待输入跨重启恢复、运行中任务重启中断、超时、预算和重复调用均有既有回归测试。
- Backend Ruff 与 mypy：通过。
- Backend pytest：140 passed；4 个仅 Windows Sandbox/一次性 VM 可运行的状态变更测试按安全门跳过。
- Frontend TypeScript、ESLint、Vitest 33 项、production build：通过。
- Impeccable detector：无发现。
- Rust fmt 与 5 项单元测试：通过。
- 真实 Windows 只读冒烟：6 passed。
- Alembic：仍为 `0010_phase32` 单一 head；RC1 无数据库迁移。

## 发布判断与剩余工作

当前实现已经符合“普通用户描述问题，系统基于本机证据给出可信诊断与安全建议”的产品主线；安全边界、证据约束和不确定性表达均可验证。它仍是 Release Candidate，而不是可宣称广泛适配的正式版本：缺少多设备真实用户试用、阈值样本校准、Windows 10/11 干净机安装/升级/卸载验证，以及正式代码签名和更新签名凭据。
