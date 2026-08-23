# Phase 3.3 Agent Stabilization & Product Readiness 完成检查点

记录日期：2026-08-23

## 完成范围

- 稳定现有“问题分类 → Diagnosis Plan → Tool 执行 → Evidence → Hypothesis → Report”链路，
  未增加 Windows 工具、Agent 层、页面、数据库表或自动修复能力。
- 区分诊断结论与能力/背景观察。GPU 实时指标不可用、代理已启用、探针能力受限等事实仍
  可见，但不再单独产生高置信度原因结论或 `evidence_sufficient`。
- 无确定性结论时统一输出“当前证据不足，无法确定原因。”，报告置信度为 0，假设状态为
  `insufficient`，停止原因为 `insufficient_information`。
- 报告综合置信度使用首要诊断结论，并按成功工具覆盖率降权；问题分类不明确时上限为 65%。
- 工具失败继续保留其他成功证据和 partial 报告，不因单项失败终止整个诊断。
- 达到规划轮次或工具预算时保留已有证据生成 partial 报告并记录 `budget_exceeded`，不再
  抛弃报告进入无结果失败状态。
- 扩充模糊问题识别和追问文案，要求用户补充具体症状、发生场景和大致时间。
- 修复网络 optional 字段的证据路径选择，避免工具成功但报告因引用不存在字段而失败。
- 报告 UI 明确展示问题概述、发现的问题、证据来源、可能原因、下一步建议、停止状态和限制；
  假设状态改为中文，空 findings 有明确说明。

## 简化与维护性

- 使用领域层两个纯函数统一“Finding 是否构成诊断结论”的判断，规则、Hypothesis 和 Report
  不再各自维护一套语义。
- 未创建复杂 Trace 系统；继续复用 task、plan、tool call、evidence、agent decision 和 stop
  reason 审计记录，不保存隐藏思维过程。
- 假设展示从嵌套小卡片简化为现有报告中的平面分隔行。
- 未新增迁移；数据库仍为 `0010_phase32` 单一 head，OpenAPI 契约未变化。

## 稳定性验证

- 四条产品验收问题覆盖：“电脑最近很卡”“游戏突然掉帧”“软件一直闪退”“无法联网”。
- 覆盖正常证据链、模糊问题追问、Agent/Provider 异常、单工具失败、正常快照但信息不足、
  预算停止后保留报告、重复工具熔断、用户续接和 optional 网络证据字段。
- Backend Ruff、mypy：通过。
- Backend pytest：138 passed；4 个仅隔离 Sandbox/VM 可运行的状态变更测试按安全门跳过。
- Frontend TypeScript、ESLint、Vitest 33 项、production build：通过。
- Impeccable UI detector：无发现。
- Rust fmt 与 5 项单元测试：通过。
- 真实 Windows 只读冒烟：3 passed。

## 当前限制

- Fake Planner 使用确定性关键词，只保证离线与常见问题覆盖，不等同于真实模型语义能力。
- 当前诊断主要基于短时快照；间歇性卡顿、偶发掉帧和很久以前的闪退仍需要在复现时重跑。
- 本地规则阈值尚缺少大规模真实用户样本校准，当前置信度代表证据强度而非统计因果概率。
- 被服务重启中断的运行中工具仍不会自动重放；这是安全选择，用户需要重新发起诊断。
- 没有生产遥测或用户研究数据，无法声称已覆盖所有 Windows 硬件和企业策略环境。

## 下一阶段建议

- 进入小范围 Product Validation / Release Candidate 阶段，以真实 Windows 设备上的脱敏问题
  样本、完成率、信息不足率和错误报告为依据，只修复高频问题。
- 建立精简 golden corpus 校准分类、规则阈值、追问和 stop reason；暂不增加新工具或 Agent 层。
- 在不采集隐藏思维和完整敏感数据的前提下，整理可由用户主动导出的诊断审计包用于支持。
