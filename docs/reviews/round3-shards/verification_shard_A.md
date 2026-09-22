# 代码审查复核结果 — Shard A

复核时间：2026-09-10
复核方式：逐条 Read 磁盘真实源码，以当前代码为唯一依据比对行号与片段。
基准根：
- 后端：`D:\SysMind AI\services\backend\src\sysmind\`
- 迁移：`D:\SysMind AI\services\backend\alembic\`
- Rust：`D:\SysMind AI\apps\desktop\src-tauri\src\`

---

## H-01 动作相关外键缺少 ON DELETE CASCADE

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号
  - 0006:23,31,32 → `alembic/versions/0006_phase5a_controlled_actions.py:23,31,32`（逐字一致，无偏差）

**证据：**

(a) 0006 迁移三行（与报告片段逐字一致）：
```python
23:        sa.Column("diagnosis_id", sa.String(36), sa.ForeignKey("diagnoses.id"), nullable=False),   # action_plans.diagnosis_id
31:        sa.Column("plan_id", sa.String(36), sa.ForeignKey("action_plans.id"), nullable=False),     # actions.plan_id
32:        sa.Column("diagnosis_id", sa.String(36), sa.ForeignKey("diagnoses.id"), nullable=False),   # actions.diagnosis_id
```
三处 `sa.ForeignKey(...)` 均**无** `ondelete=`。

(b) models.py 对应模型同样未写 ondelete：
```python
387:    diagnosis_id: Mapped[str] = mapped_column(
388:        ForeignKey("diagnoses.id"), nullable=False, index=True      # ActionPlanModel，无 ondelete
389:    )
397:    plan_id: Mapped[str] = mapped_column(ForeignKey("action_plans.id"), nullable=False, index=True)   # ActionModel，无 ondelete
398:    diagnosis_id: Mapped[str] = mapped_column(
399:        ForeignKey("diagnoses.id"), nullable=False, index=True       # ActionModel，无 ondelete
400:    )
```

(c) 其他 diagnosis 子表外键确实均带 `ondelete="CASCADE"`：
```python
252:    diagnosis_id ... ForeignKey("diagnoses.id", ondelete="CASCADE")   # DiagnosisToolCallModel
273:    diagnosis_id ... ForeignKey("diagnoses.id", ondelete="CASCADE")   # DiagnosisFeedback
285:    diagnosis_id ... ForeignKey("diagnoses.id", ondelete="CASCADE")   # DiagnosisModelCall
300:    diagnosis_id ... ForeignKey("diagnoses.id", ondelete="CASCADE")   # AgentPlanModel
318:    diagnosis_id ... ForeignKey("diagnoses.id", ondelete="CASCADE")   # DiagnosisStepModel
```

(d) engine.py 每连接确实开启外键约束：
```python
11:    @event.listens_for(engine, "connect")
12:    def configure_sqlite(dbapi_connection, _connection_record):
15:        cursor.execute("PRAGMA foreign_keys=ON")
16:        cursor.execute("PRAGMA journal_mode=WAL")
```

(e) retention 清理确实会按 retention_days DELETE diagnoses——但**该逻辑不在 0008 迁移文件本身**，而在 `repositories/history.py`：
```python
150:    def cleanup(self, *, trigger: str) -> CleanupResult:
152:        cutoff = now - timedelta(days=self.retention_days())
162:        old_diagnoses = list(
163:            session.scalars(select(Diagnosis.id).where(Diagnosis.completed_at < cutoff))
...
181:        if deletable_diagnoses:
182:            session.execute(delete(Diagnosis).where(Diagnosis.id.in_(deletable_diagnoses)))
```
`0008_history_retention.py` 迁移本体仅 `create_table(data_retention_policy / data_cleanup_runs)`，无任何 DELETE 语句。

**偏差说明：** 核心缺陷（三处外键缺 ondelete + 模型层同样缺失 + 其余子表均 CASCADE + 每连接 foreign_keys=ON）全部属实。唯一措辞偏差：报告把"按 retention_days DELETE FROM diagnoses"归因于"0008 迁移"，实际删除逻辑在 `history.py:cleanup()`（0008 仅建策略/审计表）。功能实质成立，不影响缺陷定性。

---

## H-02 Tauri sidecar 握手读取无超时

- **判定：Confirmed**
- 报告文件:行号 → 实际 `apps/desktop/src-tauri/src/sidecar.rs:187-201`（核心循环 187-192，无偏差）

**证据：**
```rust
186:            let mut endpoint = None;
187:            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
188:                if let Some(parsed) = parse_handshake(&line) {
189:                    endpoint = Some(parsed);
190:                    break;
191:                }
192:            }
```
该循环对 stdout 做**阻塞式逐行读取**，循环体内无 `Instant/deadline/timeout`，若后端永不输出 `SYSMIND_ENDPOINT ` 行，线程将一直阻塞。

10s 超时只在握手解析成功之后才启动：
```rust
212:            match wait_until_ready(&backend_endpoint, Duration::from_secs(10)) {
```
而 `wait_until_ready` 的 deadline 在函数内（361-362 行）才建立，其循环只打 `/health`，与上面的 stdout 读取无关。

`monitor_child_process` 确实只调 `try_wait()`，不等待 stdout：
```rust
310:        match child.try_wait() {
```

---

## M-01 SQLite 引擎未设 busy_timeout，多 engine 并发写

- **判定：Confirmed**
- 报告文件:行号 → 实际 `infrastructure/database/engine.py:11-18` + `infrastructure/bootstrap.py:50-128`

**证据：**
```python
11:    @event.listens_for(engine, "connect")
12:    def configure_sqlite(dbapi_connection, _connection_record):
15:        cursor.execute("PRAGMA foreign_keys=ON")
16:        cursor.execute("PRAGMA journal_mode=WAL")
```
监听器只设 `foreign_keys=ON` 与 `journal_mode=WAL`，**没有** `PRAGMA busy_timeout`。

bootstrap 中每个协调器都各自调用 `create_session_factory` → `create_database_engine`（engine.py:23-25），即各自新建独立 engine：
```python
51:    repository = SqlAlchemyScanRepository(create_session_factory(database_url))
60:    repository = SqlAlchemyLogAnalysisRepository(create_session_factory(database_url))
75:    return HistoryService(SqlAlchemyHistoryRepository(create_session_factory(database_url)))
81:    repository = SqlAlchemyAgentTaskRepository(create_session_factory(database_url))
104:    repository = SqlAlchemyDiagnosisRepository(create_session_factory(database_url))
134:    sessions = create_session_factory(database_url)   # ActionCoordinator
```
同一 database_url（同一 WAL 文件）被多 engine 写，且无 busy_timeout，写并发时会直接 `database is locked`。

---

## M-02 rsplit("@", 1) 解包崩溃

- **判定：Confirmed**
- 报告文件:行号 → `infrastructure/database/repositories/diagnoses.py:217`

**证据：**
```python
217:                tool, version = str(step["tool"]).rsplit("@", 1)
```
若 `step["tool"]` 不含 `@`，`rsplit("@",1)` 返回单元素列表 `["name"]`，解包两个变量直接抛 `ValueError: not enough values to unpack`。行号精确。

---

## M-03 wait_for_input 把提问写进 current_step 而非 clarification_question

- **判定：Confirmed**
- 报告文件:行号 → `infrastructure/database/repositories/diagnoses.py:265-272`

**证据：**
```python
265:    def wait_for_input(self, diagnosis_id: str, *, question: str) -> DiagnosisRecord:
266:        with self._sessions.begin() as session:
267:            model = session.get(Diagnosis, diagnosis_id)
270:            model.status = "waiting_user_input"
271:            model.current_step = question
272:        return _record(model)
```
`question` 被写入 `current_step`，全程未触碰 `clarification_question`（该字段在 save_agent_plan:188 才赋值、resume_with_input:287 才清空）。行号精确。

---

## M-04 动作 tool_version 硬编码 "1.0"

- **判定：Confirmed**
- 报告文件:行号 → `infrastructure/database/repositories/actions.py:75`

**证据：**
```python
70:            model = ActionModel(
71:                id=action_id,
72:                plan_id=plan_id,
73:                diagnosis_id=diagnosis_id,
74:                tool_name=tool_name,
75:                tool_version="1.0",
```
硬编码字符串字面量，未从 `target` 或注册表取真实版本。行号精确。

---

## M-05 baseline() except 漏掉 AttributeError

- **判定：Confirmed**
- 报告文件:行号 → `infrastructure/database/repositories/history.py:222-241`

**证据：**
```python
222:            try:
223:                data = cast(dict[str, object], json.loads(raw))
224:                cpu = cast(dict[str, object], data.get("cpu", {})).get("utilization_percent")
225:                memory = cast(dict[str, object], data.get("memory", {})).get("utilization_percent")
226:                disks = cast(list[dict[str, object]], data.get("disks", []))
...
240:            except (TypeError, ValueError, json.JSONDecodeError, KeyError):
241:                continue
```
`cast` 不做运行时校验：若 `json.loads(raw)` 返回 list（`raw="[...]"`），`data.get`（223 起）或内层非 dict 值上的 `.get(...)`（224/225）、`item.get(...)`（230）会抛 **AttributeError**，不在 except 元组内，将中断整个 baseline()。行号精确。

---

## M-06 DiagnosisStepModel.tool_call_id 外键缺 ondelete

- **判定：Confirmed**
- 报告文件:行号 → `infrastructure/database/models.py:327`

**证据：**
```python
327:    tool_call_id: Mapped[str | None] = mapped_column(ForeignKey("diagnosis_tool_calls.id"))
```
对比同模型其它外键（316、319 行均带 `ondelete="CASCADE"`），此 FK 无 `ondelete`。行号精确。

---

## M-07 日志 message 与异常堆栈未走 redact_text

- **判定：Confirmed**
- 报告文件:行号 → `observability/logging.py:54,65`

**证据：**
```python
54:            "message": record.getMessage(),
...
64:        if record.exc_info:
65:            payload["exception"] = self.formatException(record.exc_info)
...
66:        return json.dumps(_sanitize(payload), ensure_ascii=False, default=str)
```
`_sanitize`（35-43 行）只对 dict **键名**做敏感词脱敏，对字符串值原样返回（43 行 `return value`）。故 `record.getMessage()`（54）与 `formatException` 堆栈（65）均原样进日志。仓库中确存在文本级脱敏函数 `security/redaction.py:57 def redact_text(value: str)`（已被 agent/context.py、reports、event_logs.py 等使用），但本文件仅 `import is_sensitive_key`（第 8 行），未导入也未调用 `redact_text`。行号精确。

---

## M-08 AgentRunError 的 str(error) 直接落库

- **判定：Confirmed**
- 报告文件:行号 → `tasks/manager.py:162-164`

**证据：**
```python
162:        except AgentRunError as error:
163:            status = "cancelled" if error.code == "cancelled" else "failed"
164:            self._finish_failure(record, status, error.code, str(error))
...
167:        except Exception as error:
168:            self._finish_failure(
169:                record,
170:                "failed",
171:                "internal_error",
172:                "Agent task failed without exposing sensitive details.",
173:            )
```
紧邻的泛型 `except Exception` 分支用固定脱敏文案（172 行），而 `AgentRunError` 分支把 `str(error)`（164 行）原样作为 failure_message 落库，两处处理策略不一致。行号精确。

---

## 汇总

| 编号 | 判定 | 行号偏差 |
|------|------|----------|
| H-01 | Confirmed | 无（仅"删除逻辑位置"措辞偏差：在 history.py 而非 0008 迁移本体） |
| H-02 | Confirmed | 无 |
| M-01 | Confirmed | 无 |
| M-02 | Confirmed | 无 |
| M-03 | Confirmed | 无 |
| M-04 | Confirmed | 无 |
| M-05 | Confirmed | 无 |
| M-06 | Confirmed | 无 |
| M-07 | Confirmed | 无 |
| M-08 | Confirmed | 无 |

本 shard 无 False Positive，无 Partial（H-01 仅一处归属措辞偏差，不影响缺陷成立）。
