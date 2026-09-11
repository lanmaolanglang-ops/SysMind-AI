# 代码审查复核记录 — Shard D（L-01 ~ L-36）

复核基准：`D:\SysMind AI\services\backend\src\sysmind\`
复核方式：逐条用 Read 打开磁盘真实源码定位证据；行号偏差 ±2 行内视为准确。
判定统计：Confirmed 35 / Partial 1 / False Positive 0。

---

## 5.1 基础设施

### L-01 | Confirmed | engine.py:16 → engine.py:16
- 证据（`infrastructure/database/engine.py:11-18`）：
  ```python
  @event.listens_for(engine, "connect")
  def configure_sqlite(dbapi_connection: object, _connection_record: object) -> None:
      cursor = dbapi_connection.cursor()
      try:
          cursor.execute("PRAGMA foreign_keys=ON")
          cursor.execute("PRAGMA journal_mode=WAL")   # ← 第 16 行
  ```
- 偏差说明：行号完全一致。`journal_mode=WAL` 是数据库文件级持久属性，一旦写入即持久化，挂在每次新连接触发的 `connect` 监听器上重复设置确属冗余；且 engine 使用 `NullPool`（第 9 行），每条会话都新建连接，重复设置每次连接都发生。属实。

### L-02 | Confirmed | models.py:387-400 → models.py:387-400
- 证据（`infrastructure/database/models.py`）：
  ```python
  # 387-389  ActionPlanModel.diagnosis_id —— 无 ondelete
  diagnosis_id: Mapped[str] = mapped_column(
      ForeignKey("diagnoses.id"), nullable=False, index=True)
  # 397      ActionModel.plan_id —— 无 ondelete
  plan_id: Mapped[str] = mapped_column(ForeignKey("action_plans.id"), nullable=False, index=True)
  # 398-400  ActionModel.diagnosis_id —— 无 ondelete
  diagnosis_id: Mapped[str] = mapped_column(
      ForeignKey("diagnoses.id"), nullable=False, index=True)
  ```
  对比同文件其他外键均带 `ondelete="CASCADE"`（如 90、125、170、182、205、253、274、286、301、316、319、335、348、359、376 行）。
- 偏差说明：行号完全一致。动作系列外键（action_plans/action_plans→actions/actions→diagnoses）确实全部缺级联；418/429/438 行的 user_confirmations/action_events/recovery_records→actions 同样无 ondelete，问题属实。报告自注"与 H-01 重叠"不影响本条事实判定。

### L-03 | Confirmed | models.py（全局）→ 全库无对应代码
- 证据：对整个 `services/backend/src` 全量 grep `chmod|icacls|stat.S_|FILE_ATTRIBUTE|SetNamedSecurityInfo|acl`，除 `dataclass` 误命中与两处 Windows 文件属性读取（`windows/startup_actions.py:202`、`windows/platform_inspection.py:322`，均为读用途）外，**没有任何一处对 SQLite 数据库文件设置 ACL/权限位**。`engine.py` 仅 `create_engine`，`bootstrap.py` 无文件权限处理。
- 偏差说明：本条为"缺阴性"类发现，以全库搜索结论佐证。SQLite 文件默认继承用户目录权限，确未显式收紧。属实。

### L-04 | Confirmed | diagnoses.py:529-541 → diagnoses.py:529-541
- 证据（`infrastructure/database/repositories/diagnoses.py:521-542`）：
  ```python
  model.status, model.failure_code = "interrupted", "backend_restarted"   # 529
  model.failure_message = "本地服务重启，诊断未自动重放。"                # 530
  ...
  model.stop_reason = "risk_limit_reached"                                # 532
  session.add(AgentStopReasonModel(
      diagnosis_id=model.id,
      reason="risk_limit_reached",                                        # 536
  ```
- 偏差说明：行号完全一致。failure_code 正确标记 `backend_restarted`，但 stop_reason 与停止原因审计却写为 `risk_limit_reached`，语义错配属实。

### L-05 | Confirmed | diagnoses.py:189 → diagnoses.py:189
- 证据（`repositories/diagnoses.py:189`）：
  ```python
  diagnosis.agent_round_count = max(diagnosis.agent_round_count, revision)
  ```
- 偏差说明：行号完全一致。`agent_round_count`（语义=Agent 实际执行轮数）被直接赋成 plan revision 序号（该参数来自 `save_agent_plan(..., revision: int)`），二者语义不同，属实。

### L-06 | Confirmed | diagnoses.py:286 → diagnoses.py:286
- 证据（`repositories/diagnoses.py:284-290`）：
  ```python
  .values(
      status="running",
      current_step="正在根据补充信息调整检查项目",   # 286 行硬编码中文
  ```
  另见同文件 530、537 行中文文案（"本地服务重启，诊断未自动重放。"）。
- 偏差说明：行号完全一致。UI 提示文案硬编码在 infrastructure 仓储层，属实。

### L-07 | Confirmed | diagnoses.py:523-527 → diagnoses.py:523-527
- 证据（`repositories/diagnoses.py:523-527`）：
  ```python
  models = list(
      session.scalars(
          select(Diagnosis).where(Diagnosis.status.in_(("queued", "running")))
      )
  )
  ```
  而 `waiting_user_input` 状态确实存在（同文件 270 行 `model.status = "waiting_user_input"`）。
- 偏差说明：行号完全一致。mark_interrupted 只捞 queued/running，等待用户输入的诊断重启后不会被标记 interrupted，属实。

### L-08 | Confirmed | actions.py:265-268 → actions.py:265-268
- 证据（`repositories/actions.py:265-268`）：
  ```python
  def close(self) -> None:
      bind = self._sessions.kw.get("bind")   # 穿透 sessionmaker 私有属性
      if bind is not None:
          bind.dispose()                     # 销毁共享 engine
  ```
- 偏差说明：行号完全一致。直接读 `sessionmaker.kw` 内部字典拿 bind 并 dispose engine，而该 session_factory 在 bootstrap.py:134 被 ActionRepository 与 DiagnosisRepository 共享，dispose 会波及另一仓储，属实。

### L-09 | Confirmed | actions.py:98-104 → actions.py:96-112（判定核心在 96-97）
- 证据（`repositories/actions.py:93-112`）：
  ```python
  def create_restore(self, *, plan_id, action_id, original: ActionRecord, created_at):
      if not original.recovery_id:
          raise ValueError("Action has no recovery record.")   # 仅校验 recovery_id
      target = StartupActionCandidate(...)                     # 98-104 直接构造
      return self.create(tool_name="startup.restore_current_user", ...)
  ```
- 偏差说明：报告区间 98-104 实际为 StartupActionCandidate 构造段；真正缺失的校验（未检查 `original.tool_name` 是否 startup 类）位于 96-97 唯一守卫处，偏差 ≤2 行。只看 recovery_id 存在就生成恢复动作，属实。

### L-10 | Confirmed | agent_tasks.py:154-165 → agent_tasks.py:154-165
- 证据（`repositories/agent_tasks.py:154-165`）：
  ```python
  if started_at is not None:    model.started_at = ...
  if finished_at is not None:   model.finished_at = ...
  if final_output is not None:  model.final_output = final_output
  if failure_code is not None:  model.failure_code = failure_code
  if failure_message is not None: model.failure_message = failure_message
  if cancel_requested is not None: model.cancel_requested = cancel_requested
  ```
- 偏差说明：行号完全一致。所有可空字段均"非 None 才更新"，调用方无法把 failure_code/failure_message/finished_at 等清空回 None，属实。

### L-11 | Confirmed | agent_tasks.py:321-325 → agent_tasks.py:321-325
- 证据（`repositories/agent_tasks.py:321-325`）：
  ```python
  statement = select(AgentTask).where(
      AgentTask.status.in_(
          ("created", "planning", "running_tools", "analyzing", "cancelling")
      )
  )
  ```
  佐证 `waiting_user_input` 确为 AgentTask 合法状态（`agent/brain.py:123` `status="waiting_user_input"`；`tasks/manager.py:201` 终态豁免集合中也含 "waiting_user_input"）。
- 偏差说明：行号完全一致。与 L-07 同型遗漏，AgentTask 等待用户输入期间重启不会被 mark_interrupted 覆盖，属实。

### L-12 | Confirmed | history.py:150-200 → history.py:150-200
- 证据（`repositories/history.py:150-200` cleanup 方法）：仅 `delete(SystemScan)`（178）、`delete(EventLogAnalysis)`（180）、`delete(Diagnosis)`（182）；import 清单（18-30 行）与方法体内均无 `AgentTask / AgentTaskEventModel / AgentToolCall / AgentModelCall` 任何引用。
- 偏差说明：行号完全一致。留存清理从不回收 agent_tasks 系列四表，重启残留的 AgentTask 数据将无限堆积，属实。

### L-13 | Confirmed | history.py:71-79 → history.py:71-79
- 证据（`repositories/history.py:71-79`）：
  ```python
  dependent = sum(
      ... for table, column in (
          (DiagnosisToolCallModel, ...),
          (DiagnosisFeedback, ...),
          (DiagnosisModelCall, ...),
      )
  )
  ```
  models.py 中归属 diagnosis 的子表实际还有 AgentPlanModel(297)、DiagnosisStepModel(312)、AgentDecisionModel(331)、TaskUserInputModel(344)、DiagnosisHypothesisModel(355)、AgentStopReasonModel(372)，impact 统计均未计入。
- 偏差说明：行号完全一致。删除影响面子表覆盖不全，属实。

### L-14 | Confirmed | log_analyses.py:40 / scans.py:37 → 同
- 证据：
  - `repositories/log_analyses.py:40`：`class SqlAlchemyLogAnalysisRepository:`（无任何基类）
  - `repositories/scans.py:37`：`class SqlAlchemyScanRepository:`（无任何基类）
  - 对比端口确为 Protocol：`application/ports/log_analyses.py:9 class LogAnalysisRepository(Protocol):`、`application/ports/scans.py:8 class ScanRepository(Protocol):`；其余仓储均显式继承（diagnoses.py:121 `(DiagnosisRepository)`、actions.py:48、agent_tasks.py:94）。
- 偏差说明：行号完全一致。两个仓储未显式声明端口 Protocol 继承，属实（结构化子类型未在类名上体现）。

### L-15 | Confirmed | bootstrap.py:50-141 → bootstrap.py:50-141
- 证据：每个 create_* 工厂各自调用 `create_session_factory(database_url)` 并创建独立 engine（51、60、70、75、81、104、134 行）；全文件无共享 engine、无 `dispose/close/shutdown engine` 生命周期管理代码。
- 偏差说明：行号区间一致。engine/连接生命周期分散、无统一管理，属实。

### L-16 | Confirmed | repositories/__init__.py:12-23 → 同
- 证据：
  ```python
  __all__ = [                      # 12-20 行：先声明导出清单
      "SqlAlchemyAgentTaskRepository", ...
  ]
  from sysmind.infrastructure.database.repositories.agent_tasks import (   # 21-23：import 放在末尾
      SqlAlchemyAgentTaskRepository,
  )
  ```
- 偏差说明：行号完全一致。`__all__` 在前、被其导出的 agent_tasks import 在文件末尾，属实。

---

## 5.2 应用层 / Agent

### L-17 | Confirmed | quick_scan.py:72-75 / log_analysis.py:87-99 → 同
- 证据：
  - `application/services/quick_scan.py:67 def start(...)`（同步方法）内 72-75 行：`task = asyncio.create_task(self._run_guarded(...), name=...)`。
  - `application/services/log_analysis.py:66 def start(...)`（同步方法）内 87-99 行：`task = asyncio.create_task(self._run_guarded(...))`。
- 偏差说明：行号完全一致。同步入口方法内部直接 `asyncio.create_task`，依赖调用方必在运行中的事件循环里，属实。

### L-18 | Confirmed | quick_scan.py:158-160 / log_analysis.py:272-275 → 同
- 证据：
  - quick_scan.py:158-160：`await asyncio.wait_for(asyncio.to_thread(handlers[name]), timeout=spec.timeout_seconds)`
  - log_analysis.py:272-275：`await asyncio.wait_for(asyncio.to_thread(self._tools.query, query, cancellation), timeout=spec.timeout_seconds)`
- 偏差说明：行号完全一致。`asyncio.to_thread` 的工作线程无法被取消，wait_for 超时/取消只能让协程返回，底层线程继续运行，属实。

### L-19 | Confirmed | quick_scan.py:214-217 / log_analysis.py:319-324 → 同
- 证据：
  - quick_scan.py:214-217：
    ```python
    except asyncio.CancelledError:
        record = self._repository.get(scan_id)
        if record and record.status in {"queued", "running"}:
            self._finish_cancelled(scan_id, record.summary or {}, record.failures)
    ```
    （无 re-raise）
  - log_analysis.py:319-324：同构，`except asyncio.CancelledError:` 后直接 `self._finish_cancelled(analysis_id, [], ...)`，无重抛。
- 偏差说明：行号完全一致。CancelledError 被吞掉不重抛，任务无法正确传播取消状态，属实。

### L-20 | Confirmed | quick_scan.py:182 → 同
- 证据：
  ```python
  # quick_scan.py:182
  final_status: Literal["partial", "completed"] = "partial" if failures else "completed"
  ```
  对照 log_analysis.py:232-234：
  ```python
  final_status: AnalysisStatus = "partial" if failures else "completed"
  if failures and not typed_events:
      final_status = "failed"
  ```
- 偏差说明：行号完全一致。quick_scan 全部步骤失败时终态仍是 "partial"（无 failed），与 log_analysis 的"全失败→failed"语义不一致，属实。

### L-21 | Confirmed | log_analysis.py:208-209 → 同
- 证据（`application/services/log_analysis.py:206-209`）：
  ```python
  started_at = _now()
  started = time.monotonic()
  crash_groups = self._tools.analyze(typed_events)   # 208：同步阻塞调用
  event_groups = self._tools.aggregate(typed_events) # 209：同步阻塞调用
  ```
- 偏差说明：行号完全一致。两个 CPU 密集聚合直接在事件循环协程内同步执行，未 to_thread，属实。

### L-22 | Confirmed | log_analysis.py:266,278-294 → 同
- 证据（`application/services/log_analysis.py`）：
  ```python
  266:  status: StepStatus = "completed"          # 默认 completed
  278:  except Exception as error:                # 278-280：只捕 Exception
  279:      error_code, error_message, status = _failure(error)
  280:      raise
  281:  finally:
  282:      self._repository.add_step_event(... status=status ...)   # 282-294
  ```
- 偏差说明：行号完全一致。`asyncio.CancelledError`（3.8+ 为 BaseException）与外层 `asyncio.timeout(30)` 经取消链路注入的 CancelledError 都不会被 `except Exception` 捕获，status 保持默认 "completed"，finally 把被取消/超时的步骤误记为 completed，属实。

### L-23 | Confirmed | log_analysis.py:319-324 → 同
- 证据：
  ```python
  except asyncio.CancelledError:
      record = self._repository.get(analysis_id)
      if record and record.status in {"queued", "running"}:
          self._finish_cancelled(analysis_id, [], record.failures, max_events=max_events)
          #                                ↑ 已采集 events 被替换成空列表
  ```
  而 `_finish_cancelled(events, ...)`（377-403）本身会保留传入 events，此处传入 `[]`，取消路径丢弃了 _run 内存中已收集的全部事件。
- 偏差说明：行号完全一致。属实。

### L-24 | Confirmed | quick_scan.py:108-121,161 → 108/113-121/161
- 证据：
  ```python
  108:  specs = {spec.name: spec for spec in (*SYSTEM_TOOL_SPECS, *PROCESS_TOOL_SPECS)}
  113-121: result_keys = {"system.os": "operating_system", ...,
                          "process.high_usage": "high_usage_processes"}   # 硬编码 7 项
  161:  summary[result_keys[name]] = _serialize(value)
  ```
- 偏差说明：报告 108-121 实际覆盖 108（specs 集合）+113-121（result_keys），161 使用点一致。新增 spec 但未同步 result_keys 会 KeyError，硬编码耦合属实。

### L-25 | Confirmed | provider_settings.py:59,63 → 同
- 证据：
  ```python
  59:  OpenAICompatibleConfig(endpoint, model, SecretStr(candidate_secret), 5.0)  # 用原始值校验
  63:  self._repository.save(provider, model.strip(), endpoint.rstrip("/"), ...) # 持久化归一化
  ```
- 偏差说明：行号完全一致。校验用未 strip/rstrip 的原始 endpoint/model，入库用归一化值；校验通过的内容与最终落库内容可能不一致（如尾斜杠），属实。

### L-26 | Confirmed | provider_settings.py:55-71 → 62-70
- 证据：
  ```python
  62:  try:
  63:      self._repository.save(...)
  64:  except Exception:
  65:      if api_key:
  66:          if previous_secret is None:
  67:              self._secrets.delete(_SECRET_REFERENCE)
  68:          else:
  69:              self._secrets.set(_SECRET_REFERENCE, previous_secret)  # 回滚可能再抛
  70:      raise
  ```
- 偏差说明：报告区间 55-71 覆盖整个 save 的密钥处理段，实际回滚代码 64-70。若 69 行 `_secrets.set()` 自身抛错，该新异常会覆盖 63 行原始 repository.save 异常，`raise` 永不执行，属实。

### L-27 | Confirmed | log_analysis.py:113-120 → 同
- 证据：
  ```python
  def cancel(self, analysis_id):
      record = self._repository.get(analysis_id)   # 114：先取 record
      if record is None: return None
      cancellation = self._cancellations.get(analysis_id)
      if cancellation and record.status in {"queued", "running"}:
          cancellation.set()                       # 119：之后才置取消
      return record                                # 120：返回设置前的旧 record
  ```
- 偏差说明：行号完全一致。返回的是 cancellation.set() 之前读到的快照，状态仍为 queued/running，属实。

### L-28 | Confirmed | planning.py:248,301 → agent/planning.py:248,301
- 证据（注意：真实文件是 `agent/planning.py`，`diagnosis/planning.py` 仅 15 行分类函数）：
  ```python
  # agent/planning.py:248  FakeDiagnosisPlanner.revise_plan
  max_steps=max(0, 8 - len(calls)),          # 有下界钳制 0
  # agent/planning.py:301  ProviderDiagnosisPlanner.revise_plan
  return self._parse(..., already_called=called, max_steps=8 - len(calls))  # 无钳制，可为负
  ```
- 偏差说明：报告所指 planning.py 实际位于 agent/ 包；行号 248、301 完全一致。两个 planner 的 revision 预算下界一个 `max(0,...)` 一个不钳制，不一致属实。

### L-29 | Confirmed | brain.py:173-175 → 同
- 证据（`agent/brain.py:173-175`）：
  ```python
  indexed_results = await asyncio.gather(
      *(execute_one(index) for index in range(len(action.tool_calls)))
  )   # 无 return_exceptions=True
  ```
- 偏差说明：行号完全一致。任一 execute_one 抛错会令 gather 整体抛出、其余协程成孤儿，属实。

### L-30 | Confirmed | brain.py:37-43 → 同
- 证据（`agent/brain.py:40-42` + `security/redaction.py:5-54`）：
  ```python
  return {
      key: "[REDACTED]" if is_sensitive_key(key) or key.casefold() == "command" else value
      for key, value in arguments.items()
  }
  ```
  `SENSITIVE_KEYS` 为固定集合（access_token/api_key/password/secret/token 等，redaction.py:5-29），键名额外打码仅精确匹配 `"command"`；`cmd/cmdline/script/shell/executable/path` 等变体均不命中。
- 偏差说明：行号完全一致。审计打码键名覆盖不全、只精确匹配 command，属实。

### L-31 | Confirmed | brain.py:69,80-84 → 同
- 证据：
  ```python
  # brain.py:69
  descriptors = self._registry.descriptors(task.allowed_tools)
  # brain.py:80-84
  request = build_provider_request(user_goal=task.user_goal, tools=descriptors, memory=memory)
  ```
  `registry.descriptors`（tools/registry.py:91-92）仅 `self.require(name).descriptor()`，**无任何 risk_level 过滤**。
- 偏差说明：行号完全一致。brain 把 allowed_tools 的描述符原样下发给模型，未在本层做风险过滤（仅上游 tasks/manager.py:60-63 在建任务时强制 read_only，属另一层防御），属实。

### L-32 | Confirmed | brain.py:210-219 → 同
- 证据（`agent/brain.py:210-218`）：
  ```python
  provider_task = asyncio.create_task(self._provider.complete(request))
  try:
      while not provider_task.done():
          if cancel_event.is_set():
              provider_task.cancel(); ...
          await asyncio.sleep(0.025)      # 217：25ms 轮询
  ```
- 偏差说明：行号完全一致。取消不是事件驱动，而是 25ms 忙轮询 cancel_event，属实。

### L-33 | Confirmed | openai_compatible.py:181,184-188 → 同
- 证据：
  ```python
  180-181: except json.JSONDecodeError:
               return ProviderAction("finalize", content=content[:4000])   # 非 JSON 静默 finalize
  184:     if {"problem_category","confidence","status","steps"} <= parsed.keys():
  185-188:     return ProviderAction("finalize", content=json.dumps(parsed,...))  # 只看键存在，不看 status 值
  ```
- 偏差说明：行号完全一致。非结构化文本与畸形 plan（键齐全但 status 非法）都被静默 finalize，未抛协议错误，属实。

### L-34 | Partial | context.py（全局）→ 实际证据在 contracts.py:47-49 / fake.py:30-32 / openai_compatible.py:73-75
- 证据：
  - `agent/contracts.py:47-49`：`class AgentProvider(Protocol): @property def name(self) -> str: ...` —— name 是 Protocol 显式声明的属性，并非完全隐式。
  - 具体取值硬编码在各实现类：`providers/fake.py:31-32 return "fake"`、`providers/openai_compatible.py:73-75 return "openai_compatible"`，无中央枚举/注册表。
  - 但 `agent/context.py` 全文 122 行内**没有任何 provider.name 引用**（context 只组装 request）。
- 偏差说明：所引文件 context.py 中不存在该代码；且 Protocol 已显式声明 name 属性，"隐式依赖"说法偏重。事实内核（name 字符串值由各具体类硬编码、无集中约束）成立，故判 Partial。

### L-35 | Confirmed | diagnosis/coordinator.py:321-333 → 321-329
- 证据：
  ```python
  completed = {
      f"{call.tool_name}@{call.tool_version}": call.id   # 321-325：键只含 tool@version
      for call in calls if call.status == "completed"
  }
  ...
  existing_call_id = completed.get(step.tool)             # 329：按 tool@version 判重
  ```
  模型中本有 `arguments_hash` 字段（models.py:258）却未参与去重键。
- 偏差说明：报告 321-333 覆盖整个过滤方法，核心去重逻辑 321-329，区间吻合。同工具不同参数会被误判为重复跳过，属实。

### L-36 | Confirmed | diagnosis/coordinator.py:368-372 → 同
- 证据：
  ```python
  limitations = [
      f"工具 {call.tool_name}@{call.tool_version} 未完成：{call.error_code}"
      for call in calls
      if call.status != "completed"
  ]
  ```
  非完成（如 cancelled/timed_out/interrupted）的工具调用 `error_code` 可能为 None， limitation 文本会输出 "…未完成：None"。
- 偏差说明：行号完全一致。属实。

---

## 汇总

| 判定 | 数量 | 编号 |
|---|---|---|
| Confirmed | 35 | L-01 ~ L-33、L-35、L-36（L-09 行号偏差 ≤2 行，按规则视为准确） |
| Partial | 1 | L-34（所引文件 context.py 内无 provider.name 代码；且 Protocol 已显式声明 name 属性，仅"name 值由具体类硬编码、无中央约束"的事实内核成立） |
| False Positive | 0 | — |
