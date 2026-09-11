# 代码审查复核报告 — Shard C（M-19 ~ M-31）

复核日期：2026-09-10
复核依据：磁盘当前真实源码，逐行比对。

---

## M-19 AgentTaskPanel SSE 事件竞态，旧任务事件污染新任务状态

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`apps/desktop/src/features/tasks/AgentTaskPanel.tsx:100-116` → 实际 `104-116`（setTask 调用本体），偏差在 ±2 行内，视为准确。
- 证据：
```tsx
104:              if (event.data.status || event.data.progress !== undefined) {
105:                setTask((current) =>
106:                  current
107:                    ? {
108:                        ...current,
109:                        ...(event.data.status ? { status: event.data.status } : {}),
110:                        ...(event.data.progress !== undefined
111:                          ? { progress: event.data.progress }
112:                          : {}),
113:                      }
114:                    : current,
115:                );
116:              }
```
- 说明：`setTask` 的函数式更新只做了 `current ? {...} : current`，**未检查 `current.id === activeTaskId`**。虽然 effect 依赖 `[activeTaskId, client]` 并在 cleanup 中 `controller.abort()`，但在旧 effect cleanup 执行与新 effect 启动之间的窗口内，已在飞行的 SSE 回调仍可能用旧任务事件覆写 `task` 状态。报告主张成立。

---

## M-20 SettingsPanel retentionDays NaN 校验缺失

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`apps/desktop/src/features/settings/SettingsPanel.tsx:136,138` → 实际 `136`、`138`，完全一致。
- 证据：
```tsx
136:        <label>天数<input type="number" min="7" max="3650" value={retentionDays} onChange={(event) => setRetentionDays(Number(event.target.value))} /></label>
137:        <div className="settings-actions">
138:          <button type="button" onClick={saveDataPolicy} disabled={busy || retentionDays < 7 || retentionDays > 3650}>保存策略</button>
```
- 说明：`Number(event.target.value)` 在输入异常时可产生 `NaN`（例如浏览器允许的中间态 `"-"`、`"e"` 等）。JS 中 `NaN < 7` 和 `NaN > 3650` **均为 false**，因此 disabled 守卫对 NaN 完全失效，按钮可被点击并把 NaN 发给后端。报告主张成立。

---

## M-21 空通道导致 log_analysis 启动即 IndexError

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`application/services/log_analysis.py:151` → 实际 `151`，完全一致。
- 证据：
```python
146:        steps = len(channels) + 1
147:        self._repository.update(
148:            analysis_id,
149:            status="running",
150:            progress=0,
151:            current_step=f"{query_spec.name}:{channels[0]}",
152:        )
```
- `start()` 方法（66-102 行）签名接收 `channels: tuple[LogChannel, ...]`，**全程无 `if not channels:` 校验**，直接透传给 `_run`。当 `channels=()` 时，151 行 `channels[0]` 抛 `IndexError`。
- 偏差说明：IndexError 发生在 `_run`（async task）而非 `start()` 同步调用栈内；`_run_guarded`（345 行 `except Exception`）会捕获并把记录标记为 failed，不会未处理崩溃。但报告主张的"不校验非空 + channels[0] 抛 IndexError"在代码层面属实。

---

## M-22 application 层直接 new 具体 OpenAICompatibleProvider

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`application/services/provider_settings.py:10,81-94` → 实际 `10`、`81-94`，完全一致。
- 证据：
```python
10: from sysmind.agent.providers import OpenAICompatibleConfig, OpenAICompatibleProvider
...
81:    def configured_provider(self) -> OpenAICompatibleProvider | None:
82:        settings = self._repository.get()
83:        if settings is None or settings.provider != "openai_compatible":
84:            return None
85:        api_key = (
86:            self._secrets.get(settings.secret_reference) if settings.secret_reference else None
87:        )
88:        if not api_key:
89:            return None
90:        return OpenAICompatibleProvider(
91:            OpenAICompatibleConfig(
92:                settings.endpoint, settings.model, SecretStr(api_key), timeout_seconds=5.0
93:            )
94:        )
```
- 说明：application 层服务直接 import 并 `new` 了 infrastructure 层的具体类 `OpenAICompatibleProvider`，未通过 port/接口抽象或工厂注入，违反 `application -> domain` 方向上对 infrastructure 实现细节的解耦。报告主张成立。

---

## M-23 brain._execute_tool 无 try/finally，取消路径留下未关闭 tool_call 审计行

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`agent/brain.py:257-289` → 实际 `257-289`，完全一致。
- 证据：
```python
257:        self._repository.create_tool_call(
258:            call_id=call_id,
259:            task_id=task.id,
260:            provider_call_id=tool_call.id,
261:            tool_name=tool_call.name,
262:            tool_version=tool_call.version,
263:            arguments=_audit_arguments(tool_call.arguments, registered=definition is not None),
264:            arguments_hash=digest,
265:            risk_level=risk_level,
266:            started_at=started_at,
267:        )
268:        self._event(
269:            task.id,
270:            "tool.started",
271:            {"call_id": call_id, "tool": f"{tool_call.name}@{tool_call.version}"},
272:        )
273:        result = await self._executor.execute(
274:            name=tool_call.name,
275:            version=tool_call.version,
276:            arguments=tool_call.arguments,
277:            allowed_tools=task.allowed_tools,
278:            cancel_event=cancel_event,
279:        )
280:        self._repository.finish_tool_call(
281:            call_id,
282:            status=result.status,
...
289:        )
```
- 说明：`create_tool_call`（257）开启审计行后，直接 `await self._executor.execute(...)`（273），**无 try/finally 包裹**。若 `execute` 抛出异常（如 `ToolCancelledError`、`asyncio.CancelledError`），`finish_tool_call`（280）永不执行，留下一条只有 `started_at` 没有 `finished_at`/`status` 的悬空审计行。`run()` 中 `asyncio.gather` 也无外层补偿。报告主张成立。

---

## M-24 Settings 双构造路径可能产生不同的随机 session_token

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`core/config.py:67-69 + __main__.py:17-31` → 实际 `config.py:67-69`、`__main__.py:17-31`，完全一致。
- 证据：
```python
# config.py:31-34（session_token 默认工厂）
31:    session_token: SecretStr = Field(
32:        default_factory=lambda: SecretStr(secrets.token_urlsafe(32)),
33:        min_length=32,
34:    )
...
67: @lru_cache
68: def get_settings() -> Settings:
69:     return Settings()
```
```python
# __main__.py:17-31
17: def main() -> None:
18:     args = parse_args()
19:     if args.data_dir:
20:         settings = Settings(
21:             host=args.host,
22:             port=args.port,
23:             data_dir=args.data_dir,
24:         )
25:     else:
26:         settings = Settings(host=args.host, port=args.port)
27:     try:
28:         run_server(settings)
```
- 说明：`session_token` 使用 `default_factory`，**每次 `Settings()` 构造都会执行 `secrets.token_urlsafe(32)` 生成新随机值**。`__main__.py:main()` 直接 `Settings(...)` 构造并传给 `run_server`，而 `get_settings()`（lru_cache）是另一条独立构造路径。两条路径各自产生不同的随机 token，进程内可能存在两个不一致的 Settings 实例。报告主张成立。

---

## M-25 domain GpuInfo 把基础设施实现细节写进纯领域模型

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`domain/diagnostics.py:39-41` → 实际 `39-41`，完全一致。
- 证据：
```python
31: @dataclass(frozen=True, slots=True)
32: class GpuInfo:
33:     name: str
34:     memory_bytes: int | None
35:     driver_version: str | None
36:     telemetry_available: bool = False
37:     utilization_percent: float | None = None
38:     memory_used_bytes: int | None = None
39:     telemetry_limitation: str | None = (
40:         "Real-time GPU utilization is unavailable from the metadata-only Windows adapter."
41:     )
```
- 说明：纯领域模型 `GpuInfo` 的默认文案直接点名了 infrastructure 层的实现细节 "metadata-only Windows adapter"，使 domain 层知道了 Windows 适配器的存在，违反了 domain 不应依赖基础设施实现细节的边界。报告主张成立。

---

## M-26 GpuInfo 可出现 telemetry_available=True 与"不可用"文案自相矛盾

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`domain/diagnostics.py:36-41` → 实际 `36-41`，完全一致。
- 证据：
```python
36:     telemetry_available: bool = False
37:     utilization_percent: float | None = None
38:     memory_used_bytes: int | None = None
39:     telemetry_limitation: str | None = (
40:         "Real-time GPU utilization is unavailable from the metadata-only Windows adapter."
41:     )
```
- 说明：`telemetry_available`（默认 False）与 `telemetry_limitation`（默认值为"不可用"文案）是两个独立字段，**无任何 validator 约束二者一致**。调用方可以构造 `GpuInfo(name="X", ..., telemetry_available=True)` 而不显式覆盖 `telemetry_limitation`，结果得到 `telemetry_available=True` 同时文案为"unavailable"的自相矛盾对象。报告主张成立。

---

## M-27 frozen dataclass 持有可变 list/dict

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`domain/diagnostics.py:84-85`、`domain/event_logs.py:65-67` → 实际 `diagnostics.py:84-85`、`event_logs.py:65-67`，完全一致。
- 证据：
```python
# diagnostics.py:76-86
76: @dataclass(frozen=True, slots=True)
77: class ScanRecord:
...
84:     summary: dict[str, object] | None
85:     failures: list[dict[str, str]]
```
```python
# event_logs.py:57-68
57: @dataclass(frozen=True, slots=True)
58: class LogAnalysisRecord:
...
65:     query: dict[str, object]
66:     summary: dict[str, object] | None
67:     failures: list[dict[str, str]]
```
- 说明：`frozen=True` 仅阻止字段重新赋值（`instance.field = ...`），不阻止对内部 `dict`/`list` 对象的原地 mutation（`record.summary["key"] = ...`、`record.failures.append(...)`）。两个纯领域记录均持有可变容器，"不可变"保证不完整。报告主张成立。

---

## M-28 测试中 3 处硬编码计数/修订号

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`test_database.py:104`、`test_scans.py:149`、`test_event_logs.py:200` → 实际均完全一致。
- 证据：
```python
# test_database.py:104
104:     assert revision == "0010_phase32"
```
```python
# test_scans.py:149
149:     assert audit_count == 7
```
```python
# test_event_logs.py:200
200:     assert len(rows) == 3
```
- 说明：三处均为硬编码字面量——头部修订号字符串 `"0010_phase32"`、审计事件计数 `== 7`、步事件行数 `== 3`。一旦后续新增迁移或扫描步骤数变化，这些断言会脆弱地失败，需人工同步修改。报告主张成立。

---

## M-29 test_release_hardening.py 跨测试模块 import + 运行时替换私有属性

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`tests/test_release_hardening.py:19,84` → 实际 `19`、`84`，完全一致。
- 证据：
```python
19: from tests.test_phase5_actions import FakeStartupActions, coordinator
```
```python
83:     # Swap in an adapter that raises outside every mapped error family.
84:     service._adapter = ExplodingStartupActions()  # noqa: SLF001 - test seam
```
- 说明：19 行从另一个测试模块 `tests.test_phase5_actions` import 了 `FakeStartupActions` 和 `coordinator`，测试模块间产生耦合；84 行运行时直接替换私有属性 `service._adapter`（虽有 `# noqa: SLF001` 注释声明为 test seam）。两处均属实。（另：46 行 `service._repository` 也是同类私有属性访问，但报告未标注。）报告主张成立。

---

## M-30 审计 request_hash 在测试侧重算序列化参数

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`tests/test_phase4_diagnosis.py:518-526,556-564` → 实际 `518-526`、`556-564`，完全一致。
- 证据：
```python
# 518-526
518:     expected_hash = hashlib.sha256(
519:         json.dumps(
520:             asdict(provider.requests[0]),
521:             ensure_ascii=False,
522:             sort_keys=True,
523:             separators=(",", ":"),
524:         ).encode()
525:     ).hexdigest()
526:     assert row.request_hash == expected_hash
```
```python
# 556-564
556:     expected_hash = hashlib.sha256(
557:         json.dumps(
558:             asdict(provider.requests[0]),
559:             ensure_ascii=False,
560:             sort_keys=True,
561:             separators=(",", ":"),
562:         ).encode()
563:     ).hexdigest()
564:     assert row.request_hash == expected_hash
```
- 说明：两处测试均在测试侧重新实现了与生产代码相同的 SHA-256 序列化配方（`ensure_ascii=False, sort_keys=True, separators=(",", ":")`），而非调用生产侧的哈希函数。这意味着测试与生产序列化逻辑形成隐式重复耦合——生产侧若修改序列化参数（如加 `default=str`），测试需同步复制修改，且测试本身并不能验证生产哈希函数的正确性。报告主张成立。

---

## M-31 env.py 未启用 render_as_batch，0009/0010 downgrade 的 drop_column 不可靠

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`alembic/env.py:37` + 0009/0010 downgrade → 实际 `env.py:37`；0009 downgrade `81-83`；0010 downgrade `86-89`。
- 证据：
```python
# env.py:37（online 模式 configure）
37:         context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
```
（无 `render_as_batch=True` 参数。offline 模式 19-25 行同样未设置。）

```python
# 0009_phase31_agent_planner.py downgrade:81-83
81:     op.drop_column("diagnoses", "clarification_question")
82:     op.drop_column("diagnoses", "planner_status")
83:     op.drop_column("diagnoses", "plan_confidence")
```
```python
# 0010_phase32_adaptive_agent.py downgrade:86-89
86:     op.drop_column("diagnoses", "stop_reason")
87:     op.drop_column("diagnoses", "max_tool_calls")
88:     op.drop_column("diagnoses", "max_agent_rounds")
89:     op.drop_column("diagnoses", "agent_round_count")
```
- 说明：SQLite 后端下，Alembic 对 `drop_column` 的推荐做法是启用 batch mode（`render_as_batch=True`），由 Alembic 自动重建表并拷贝数据。当前 env.py 两条 `context.configure` 调用均未设置该参数，0009/0010 downgrade 直接发出 `op.drop_column`，在 SQLite 上依赖原生 `ALTER TABLE DROP COLUMN`（SQLite 3.35+ 才支持，且对索引/约束有额外限制），跨版本不可靠。事实前提（未启用 render_as_batch + downgrade 调用 drop_column）均属实。报告主张成立。

---

## 汇总

| 编号 | 判定 | 行号偏差 |
|------|------|----------|
| M-19 | Confirmed | 实际 104-116 vs 报告 100-116，±2 内 |
| M-20 | Confirmed | 无偏差 |
| M-21 | Confirmed | 无偏差（IndexError 在 async task 内，被 _run_guarded 捕获） |
| M-22 | Confirmed | 无偏差 |
| M-23 | Confirmed | 无偏差 |
| M-24 | Confirmed | 无偏差 |
| M-25 | Confirmed | 无偏差 |
| M-26 | Confirmed | 无偏差 |
| M-27 | Confirmed | 无偏差 |
| M-28 | Confirmed | 无偏差 |
| M-29 | Confirmed | 无偏差 |
| M-30 | Confirmed | 无偏差 |
| M-31 | Confirmed | 无偏差（env.py:37；0009 downgrade 81-83；0010 downgrade 86-89） |

**13 条全部为 Confirmed，无 Partial，无 False Positive。**
