# 复核结果 Shard B（M-09 ~ M-18）

复核基准：以磁盘当前真实源码为唯一依据，行号偏差 ±2 内视为准确。

---

## M-09 release 包中 SYSMIND_BACKEND_EXECUTABLE env 覆盖仍然生效

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`src-tauri/src/sidecar.rs:436-441` → `src-tauri/src/sidecar.rs:436-441`（完全一致）
- 证据：
  ```rust
  435	    fn resolve(app: &AppHandle) -> Result<Self, String> {
  436	        if let Some(program) = std::env::var_os("SYSMIND_BACKEND_EXECUTABLE") {
  437	            return Ok(Self {
  438	                program: PathBuf::from(program),
  439	                prefix_args: Vec::new(),
  440	            });
  441	        }
  ...
  453	        if !cfg!(debug_assertions) {
  454	            return Err(
  455	                "The packaged SysMind backend is missing. Reinstall the application from a trusted installer."
  456	                    .to_string(),
  457	            );
  458	        }
  ```
- 说明：env override 分支（436-441）在 bundled 路径回退（443-451）与 `!cfg!(debug_assertions)` 发布守卫（453）**之前**，且命中即 `return`。因此 NSIS 正式包（release）只要设置了 `SYSMIND_BACKEND_EXECUTABLE`，就会直接改用该外部可执行文件，根本走不到 453 的守卫。主张属实。

---

## M-10 create_tool_call 把未脱敏原始参数交给仓储

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`application/ports/diagnoses.py:86-96` → `application/ports/diagnoses.py:86-96`（完全一致）
- 证据：
  ```python
  86	    def create_tool_call(
  87	        self,
  88	        *,
  89	        call_id: str,
  90	        diagnosis_id: str,
  91	        tool_name: str,
  92	        tool_version: str,
  93	        arguments: dict[str, object],
  94	        arguments_hash: str,
  95	        started_at: str,
  96	    ) -> None: ...
  ```
  domain 实体 `DiagnosisToolCall`（`domain/diagnosis.py:116-126`）字段为：
  ```python
  116 class DiagnosisToolCall:
  117     id: str
  118     diagnosis_id: str
  119     tool_name: str
  120     tool_version: str
  121     status: str
  122     result: object | None
  123     summary: dict[str, object] | None
  124     error_code: str | None
  125     started_at: str | None = None
  126     finished_at: str | None = None
  ```
- 说明：端口同时接收原始 `arguments` dict（93 行）与 `arguments_hash`（94 行），而 domain 的 `DiagnosisToolCall` 不含 `arguments` 字段——原始参数被直接交给仓储层落库，domain 仅保留哈希。主张属实。

---

## M-11 扫描步骤事件缺 arguments_hash

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`application/ports/scans.py:23-36` vs `log_analyses.py:36` → 完全一致
- 证据：
  ```python
  # application/ports/scans.py:23-36
  23	    def add_step_event(
  24	        self,
  25	        *,
  26	        scan_id: str,
  27	        tool_name: str,
  28	        tool_version: str,
  29	        status: StepStatus,
  30	        started_at: str,
  31	        finished_at: str,
  32	        duration_ms: int,
  33	        result_summary: dict[str, object] | None = None,
  34	        error_code: str | None = None,
  35	        error_message: str | None = None,
  36	    ) -> None: ...
  ```
  ```python
  # application/ports/log_analyses.py:26-40
  26	    def add_step_event(
  27	        self,
  28	        *,
  29	        analysis_id: str,
  30	        tool_name: str,
  31	        tool_version: str,
  32	        status: StepStatus,
  33	        started_at: str,
  34	        finished_at: str,
  35	        duration_ms: int,
  36	        arguments_hash: str,
  37	        result_summary: dict[str, object] | None = None,
  38	        error_code: str | None = None,
  39	        error_message: str | None = None,
  40	    ) -> None: ...
  ```
- 说明：`LogAnalysisRepository.add_step_event` 在 36 行强制要求 `arguments_hash: str`；`ScanRepository.add_step_event` 全段无该字段。调用侧 `quick_scan.py:_record_event`（302-313）也确实未传 `arguments_hash`。主张属实。

---

## M-12 Executor 超时不置位 cancel_event

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`tools/executor.py:76-79` → `tools/executor.py:76-79`（wait_for 块一致；超时分支在 90-91）
- 证据：
  ```python
  74	        try:
  75	            async with self._global_semaphore, key_semaphore:
  76	                raw = await asyncio.wait_for(
  77	                    asyncio.to_thread(definition.handler, validated, cancel_event),
  78	                    timeout=definition.timeout_seconds,
  79	                )
  ...
  90	        except TimeoutError:
  91	            return self._error("timeout", "Tool execution timed out.", digest, started)
  ```
- 说明：`asyncio.wait_for` 超时仅取消其包裹的 awaitable；`except TimeoutError` 分支（90-91）直接返回错误结果，全程没有任何 `cancel_event.set()` 调用。`cancel_event` 仅作为参数透传给 handler，超时本身不置位。主张属实。

---

## M-13 log.crash.analyze 超时在两处声明不一致（3.0s vs 12.0s）

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`tools/log/toolset.py:12` vs `tools/runtime_tools.py:298` → 完全一致
- 证据：
  ```python
  # tools/log/toolset.py:10-13
  10 LOG_TOOL_SPECS = (
  11	    ToolSpec("log.windows_event.query", "1.0", 12.0),
  12	    ToolSpec("log.crash.analyze", "1.0", 3.0),
  13	)
  ```
  ```python
  # tools/runtime_tools.py:289-303
  289	        ToolDefinition(
  290	            "log.crash.analyze",
  291	            "1.0",
  292	            "Aggregate bounded Application Error and WER summaries; never reads crash dumps.",
  ...
  298	            12.0,
  299	            "event_log",
  300	            "none",
  301	            crash_analysis,
  302	            _list_summary,
  303	        ),
  ```
- 说明：同一工具 `log.crash.analyze` 在 `LOG_TOOL_SPECS` 声明为 3.0s，而注册进 ToolRegistry 的 `ToolDefinition` 用 12.0s。调用方 `log_analysis.py:274` 用 `spec.timeout_seconds`（来自 LOG_TOOL_SPECS=3.0），Registry 内的 12.0s 是另一条并行路径。主张属实。

---

## M-14 子目录 toolset 提供绕过 Registry/Executor 的执行路径

- **判定：Partial**
- 报告文件:行号 → 实际文件:行号：
  - `tools/system/toolset.py:27-34` → `tools/system/toolset.py:27-34`（准确）
  - `tools/process/toolset.py:19-23` → `tools/process/toolset.py:19-23`（准确）
  - `tools/log/toolset.py:69-82` → `tools/log/toolset.py:69-82`（行号准确，但形态不符）
- 证据：
  ```python
  # tools/system/toolset.py:27-34
  27	    def handlers(self) -> dict[str, Callable[[], object]]:
  28	        return {
  29	            "system.os": self._probe.operating_system,
  30	            "system.cpu": self._probe.cpu,
  31	            "system.gpu": self._probe.gpus,
  32	            "system.memory": self._probe.memory,
  33	            "system.disks": self._probe.disks,
  34	        }
  ```
  ```python
  # tools/process/toolset.py:19-23
  19	    def handlers(self, cancel_event: Event) -> dict[str, Callable[[], object]]:
  20	        return {
  21	            "process.snapshot": lambda: self._probe.snapshot(cancel_event=cancel_event),
  22	            "process.high_usage": lambda: self._probe.high_usage(cancel_event),
  23	        }
  ```
  ```python
  # tools/log/toolset.py:69-82（注意：无 handlers() 字典，是实例方法）
  69 class LogTools:
  70	    def __init__(self, probe: EventLogProbe) -> None:
  71	        self._probe = probe
  73	    def query(self, query: EventLogQuery, cancel_event: Event) -> Sequence[WindowsEvent]:
  74	        return self._probe.query(query, cancel_event)
  76	    @staticmethod
  77	    def analyze(events: Sequence[WindowsEvent]) -> tuple[CrashGroup, ...]:
  78	        return analyze_crashes(events)
  80	    @staticmethod
  81	    def aggregate(events: Sequence[WindowsEvent]) -> tuple[EventGroup, ...]:
  82	        return aggregate_events(events)
  ```
  仍被引用并在执行路径上：
  ```python
  # application/services/quick_scan.py:109-112, 158-160
  109	        handlers = {
  110	            **self._system_tools.handlers(),
  111	            **self._process_tools.handlers(cancellation),
  112	        }
  158	                value = await asyncio.wait_for(
  159	                    asyncio.to_thread(handlers[name]), timeout=spec.timeout_seconds
  160	                )
  # application/services/log_analysis.py:272-275
  272	            value = await asyncio.wait_for(
  273	                asyncio.to_thread(self._tools.query, query, cancellation),
  274	                timeout=spec.timeout_seconds,
  275	            )
  ```
- 偏差说明：
  - **属实部分**：三个类均仍被 `bootstrap.py` 装配、被 `quick_scan.py` / `log_analysis.py` 直接驱动，确实**绕过了 `ToolRegistry.authorize` 与 `ToolExecutor`**（未走 policy 授权、input_model 校验、全局/键信号量），自行用 `asyncio.wait_for(to_thread(...))` 调用探针。
  - **不属实部分**：(1) 仅 `SystemTools`、`ProcessTools` 以 `{name: callable}` 字典暴露；`LogTools` 并无 `handlers()` 字典，而是 `query/analyze/aggregate` 三个具名方法被直接调用。(2) 报告称"并行执行路径"，但 `quick_scan.py:140` 是 `for name in ordered_names` 串行循环、`log_analysis.py:163` 也是逐通道串行，均为串行而非并行。核心安全主张（绕过 Registry/Executor）成立，但表述细节有误。

---

## M-15 客户端 Correlation-ID 未经验证即反射到响应头

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`api/middleware.py:26,48` → `api/middleware.py:26,48`（完全一致）
- 证据：
  ```python
  26	        correlation_id = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
  ...
  47	        response = await call_next(request)
  48	        response.headers[CORRELATION_HEADER] = correlation_id
  49	        return response
  ```
- 说明：客户端传入的 `CORRELATION_HEADER` 取值后未做任何长度、字符集或格式校验/截断，直接赋给 `response.headers[CORRELATION_HEADER]` 原样反射（错误分支 `_error` 的 63 行同样反射）。主张属实。

---

## M-16 Health 端点硬编码 ready=True

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`api/routes/health.py:11-16` → `api/routes/health.py:11-16`（完全一致）
- 证据：
  ```python
  10 @router.get("/health", response_model=HealthResponse)
  11 def health() -> HealthResponse:
  12     return HealthResponse(
  13	        backend_version=BACKEND_VERSION,
  14	        api_version=API_VERSION,
  15	        ready=True,
  16	    )
  ```
  lifespan 确实维护了状态（`api/app.py:96,98`）：
  ```python
   96         app.state.ready = True
   98         app.state.ready = False
  ```
- 说明：`health()` 不接收 `Request`，完全不读 `app.state.ready`，硬编码 `ready=True`，与 lifespan 维护的真实就绪状态脱钩。主张属实。

---

## M-17 SSE 事件流未捕获底层 DB 异常

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`api/routes/agent_tasks.py:116-135` → `api/routes/agent_tasks.py:116-135`（完全一致）
- 证据：
  ```python
  116	    async def event_stream() -> AsyncIterator[str]:
  117	        nonlocal cursor
  118	        heartbeat_at = time.monotonic()
  119	        while True:
  120	            if await request.is_disconnected():
  121	                return
  122	            events = await asyncio.to_thread(manager.events_after, task_id, cursor)
  ...
  129	            current = await asyncio.to_thread(manager.get, task_id)
  130	            if current is None or (current.status in _TERMINAL and not events):
  131	                return
  132	            if time.monotonic() - heartbeat_at >= 10:
  133	                heartbeat_at = time.monotonic()
  134	                yield ": keep-alive\n\n"
  135	            await asyncio.sleep(0.2)
  ```
- 说明：整个事件生成循环（119-135）无任何 try/except。`manager.events_after`（122）与 `manager.get`（129）经 `asyncio.to_thread` 调用仓储/DB，一旦抛 DB 异常会直接向上冒泡到 StreamingResponse，未被捕获转换为 SSE 错误事件。（107-114 的 try/except 仅用于 cursor 解析，与本主张无关。）主张属实。

---

## M-18 SSE 终态终止条件存在竞态窗口

- **判定：Confirmed**
- 报告文件:行号 → 实际文件:行号：`api/routes/agent_tasks.py:129-131` → `api/routes/agent_tasks.py:129-131`（完全一致）
- 证据：
  ```python
  122	            events = await asyncio.to_thread(manager.events_after, task_id, cursor)
  123	            for event in events:
  124	                cursor = event.id
  ...
  129	            current = await asyncio.to_thread(manager.get, task_id)
  130	            if current is None or (current.status in _TERMINAL and not events):
  131	                return
  ```
- 说明：终止条件 `current.status in _TERMINAL and not events` 中，`events` 在 122 行先取，`current` 在 129 行后取。若管理器在这两行之间**先追加终态事件、再把状态置为 terminal**（或二者非原子），则本轮 `events` 为空（事件尚未写入即已查询），而 `current.status` 已是 terminal → 命中 `not events` 直接 return，刚追加的终态事件永远不会被 yield。存在真实竞态窗口。主张属实。

---

## 汇总

| 编号 | 判定 |
|------|------|
| M-09 | Confirmed |
| M-10 | Confirmed |
| M-11 | Confirmed |
| M-12 | Confirmed |
| M-13 | Confirmed |
| M-14 | Partial |
| M-15 | Confirmed |
| M-16 | Confirmed |
| M-17 | Confirmed |
| M-18 | Confirmed |
