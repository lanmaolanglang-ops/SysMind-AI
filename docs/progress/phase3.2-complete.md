# Phase 3.2 Adaptive Diagnosis Agent 完成检查点

记录日期：2026-08-23

## 完成范围

- `waiting_user_input -> running` 原任务续接：保留 diagnosis/task ID、已有计划、工具调用、
  证据与假设，并持久化用户补充信息。
- 每次续接重新规划；Provider 上下文只包含脱敏原问题和最多四条、每条最多 500 字的必要补充。
- 已成功完成的同版本工具在后续计划中标为 `skipped_duplicate` 并关联原
  `tool_call_id`，不会再次执行。
- 最多 4 个持久化规划轮次、8 次工具调用、45 秒活动超时，以及无新工具熔断。
- 显式停止原因：`evidence_sufficient`、`user_cancelled`、
  `insufficient_information`、`budget_exceeded`、`risk_limit_reached`。
- 诊断假设包含理由、支持证据、反证、置信度和
  `active/confirmed/rejected/insufficient` 状态，并写入报告、JSON/Markdown 导出与桌面 UI。
- findings 与 hypotheses 的每条证据均校验成功工具调用和实际字段路径；API 同时投影工具名、
  版本、关键字段和有界原始结果摘要。
- Fake Planner 保持离线可测；原 Planner、Tool Executor、Windows Adapter、规则 findings、
  报告历史和受控操作没有被重写。

## 架构变化

```text
Frontend
  -> Diagnosis API / Application Service
    -> Adaptive Diagnosis Coordinator
      -> Diagnosis Planner
      -> Hypothesis Engine / Evidence Composer
      -> Tool Registry -> Tool Executor -> Windows Adapter
```

- Coordinator 只请求版本化 Registry Tool；每轮计划在应用层再次 fail closed 校验。
- Repository 提供原子输入续接、假设 upsert 和停止原因追加审计。
- 等待用户输入的任务在重启恢复检查中保持等待；运行中任务仍标为 interrupted，禁止自动重放。

## 数据库变化

- Alembic：`0009_phase31 -> 0010_phase32`，单一 head。
- `diagnoses` 新增轮次、轮次预算、工具预算和最新停止原因字段。
- 新增 `task_user_inputs`、`diagnosis_hypotheses`、`agent_stop_reasons`。
- 迁移支持从 Phase 5/Phase 3.1 升级、降级后再升级；旧报告缺少 hypotheses 时按空列表读取。

## 主要文件变化

- `services/backend/src/sysmind/diagnosis/coordinator.py`
- `services/backend/src/sysmind/diagnosis/hypotheses.py`
- `services/backend/src/sysmind/domain/diagnosis.py`
- `services/backend/src/sysmind/application/ports/diagnoses.py`
- `services/backend/src/sysmind/infrastructure/database/models.py`
- `services/backend/src/sysmind/infrastructure/database/repositories/diagnoses.py`
- `services/backend/src/sysmind/api/dto/diagnoses.py`
- `services/backend/src/sysmind/api/routes/diagnoses.py`
- `services/backend/src/sysmind/reports/composer.py`
- `services/backend/src/sysmind/reports/evidence.py`
- `services/backend/alembic/versions/0010_phase32_adaptive_agent.py`
- `services/backend/tests/test_phase32_adaptive_agent.py`
- `apps/desktop/src/services/diagnoses.ts`
- `apps/desktop/src/features/diagnose/DiagnosisPanel.tsx`
- `apps/desktop/src/features/diagnose/DiagnosisPanel.test.tsx`

## 验证结果

- Backend Ruff、mypy：通过；完整 pytest：129 passed，4 个仅隔离 Sandbox/VM 可运行的
  状态变更测试按安全门跳过。
- Phase 3.1/3.2、既有诊断和迁移定向回归：41 passed；最终续接路径复核 24 passed。
- Frontend ESLint、TypeScript、Vitest 32 项、production build：通过。
- Rust fmt 与 5 项单元测试通过；真实 Windows 只读冒烟 3 passed。
- OpenAPI 已重新导出；开发数据库和 Alembic 单一 head 均为 `0010_phase32`。

## 当前限制

- Fake Planner 仍是确定性关键词实现；它用于离线回归，不代表真实 Provider 的语义覆盖。
- 用户补充只进入当前任务，不自动检索完整历史；历史仍默认不发送给模型。
- 被后端重启打断的运行中工具不会自动恢复，需用户重新发起诊断。
- `rejected` 假设只在存在明确、字段级反证时成立；证据不足不会伪装成反证。

## 下一阶段建议

- Phase 3.3 建立脱敏 golden-question / observation 数据集与 Planner 质量评估，度量分类、工具
  精确率、追问质量、无效轮次和停止原因准确率。
- 在明确授权策略下研究最多三条结构化历史基线摘要；继续禁止发送完整历史和完整工具结果。
- 增加 Provider 级假设更新协议，但仍由本地 Evidence Composer 决定证据是否合法。
