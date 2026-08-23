# Phase 3.1 Agent Planner + Tool Selection 完成检查点

记录日期：2026-08-23

## 完成范围

- 在现有自然语言诊断协调器前增加结构化 `DiagnosisPlanner`，保留原有 Tool Executor、
  Windows Adapter、规则 findings、报告、历史和受控操作链路。
- 离线 `FakeDiagnosisPlanner` 和严格 JSON 的 Provider Planner；Provider 只能返回计划，不能
  直接执行工具。
- 性能、开机慢、游戏掉帧、网络和崩溃问题的可解释工具选择；每一步包含工具、参数和原因。
- Registry 精确名称、输入 Schema、普通用户权限、确认策略、风险范围、重复调用和最多 8 次
  工具预算的执行前校验。
- 首轮工具摘要完成后允许一次有界重规划；必要信息不足时进入
  `waiting_user_input` 并给出具体追问。
- Context Builder 只包含脱敏问题、粗粒度设备摘要、受限工具目录和必要的有界观察；历史默认
  不进入模型上下文。
- Evidence Composer 将 finding 关联到 `tool_call_id`、工具名/版本、关键字段和原始结果摘要，
  并拒绝不存在或失败的证据引用。
- 新增 `agent_plans`、`diagnosis_steps`、`agent_decisions` 审计表和 Alembic 迁移
  `0009_phase31`；原有数据和表保持兼容。
- 桌面诊断页支持展示 Planner 的补充信息请求，避免对该终态持续轮询。

## 安全边界

- 未增加 Shell、PowerShell、CMD、任意命令、文件删除、注册表修改或系统自动修改入口。
- 状态变更/需确认/管理员工具不会出现在 Planner 上下文，校验层再次 fail closed。
- 网络工具只允许用于网络类别，并继续受原有固定目标和超时限制。
- 完整工具结果不发送给 Provider；历史摘要默认关闭。
- 模型文字仍不是事实来源；报告 finding 必须通过本地证据组合器。

## 验证结果

- Backend Ruff：通过。
- Backend mypy strict：119 个源文件通过。
- Backend pytest：122 passed，4 个仅 Sandbox/VM 可运行的状态变更测试跳过。
- Phase 3.1 专项：14 项通过，覆盖正常规划、选择理由、未知工具、非法参数、越权、网络
  范围、预算、主动询问、动态重规划、Provider Schema、上下文最小化、证据拒绝与审计落库。
- Frontend ESLint、TypeScript strict、Vitest 30 项和 Vite production build：通过。
- Alembic 单一 Head：`0009_phase31`；旧版本往返迁移测试通过。

## 当前限制

- 每次诊断最多进行一次结果驱动的计划修订，尚未实现多轮假设树或用户补充后的原任务恢复。
- Fake Planner 使用确定性关键词和安全规则，语义覆盖不等同于真实模型。
- 历史诊断默认不进入 Planner 上下文，设备摘要目前保持粗粒度。
- 规则引擎只为已有工具/字段生成结论；新增 Tool 仍需同步规则和证据测试。

## Phase 3.2 建议

- 增加可恢复的 `waiting_user_input -> planning` 输入续接协议。
- 引入显式假设、支持/反证和停止原因，允许在预算内多轮调整，但保持重复调用熔断。
- 建立脱敏 golden question 数据集与计划质量指标，比较 Fake 与真实 Provider 的选择准确率。
- 在用户明确允许时加入最多三条结构化历史摘要和设备基线差异，不发送完整历史。
