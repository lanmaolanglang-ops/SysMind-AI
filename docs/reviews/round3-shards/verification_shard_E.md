# 复核报告 Shard E（L-37 ~ L-72）

复核基准：以磁盘当前真实源码为唯一依据。行号偏差 ±2 行内视为准确。

---

### 5.3 诊断 / 动作 / 任务

#### L-37 | Confirmed | 报告行 475 → 实际行 475（调用点），ValueError 抛出点 543

**证据：**
```python
# diagnosis/coordinator.py:475
self._validate_report_evidence(report, calls)
```
```python
# diagnosis/coordinator.py:538-543
if any(
    ref.tool_call_id not in valid_calls
    or not evidence_path_exists(valid_calls[ref.tool_call_id], ref.field_path)
    for ref in references
):
    raise ValueError("Report contains an invalid evidence reference.")
```
该 `ValueError` 沿 `_finalize` → `_run_bounded` → `_run` 传播，被 `_run` 的 `except Exception`（第188行）捕获，调用 `_stop_and_fail(code="internal_error", message="诊断失败，未暴露敏感错误细节。")`。证据校验失败确实导致整份诊断（含已完成 findings）转为 internal_error。

**偏差说明：** 行号准确。

---

#### L-38 | Confirmed | 报告行 275,283,291,299 → 实际行 275,283,291,299

**证据：**
```python
# actions/coordinator.py:268-299
except ActionVerificationError as error:
    ...
    error_message=str(error),          # line 275
except TargetChangedError as error:
    ...
    error_message=str(error),          # line 283
except ToolPermissionError as error:
    ...
    error_message=str(error),          # line 291
except ToolUnavailableError as error:
    ...
    error_message=str(error),          # line 299
```
四个适配器异常处理器均将 `str(error)` 直接写入 `error_message`，未做脱敏或泛化。

**偏差说明：** 行号完全准确。

---

#### L-39 | Confirmed | 报告行 184,236,247 → 实际行 184,236,247

**证据：**
```python
# actions/coordinator.py:184
and self._age_seconds(action) > 30
```
```python
# actions/coordinator.py:236
if (datetime.now(UTC) - created_at).total_seconds() > 30:
    raise TargetChangedError("Process action plan expired; refresh the target.")
```
```python
# actions/coordinator.py:247
if (datetime.now(UTC) - created_at).total_seconds() > 30:
    raise TargetChangedError("Termination plan expired; refresh the target.")
```
票据 TTL 确认为 120 秒（`security/consent.py:24` `ttl_seconds: int = 120`）。进程类动作创建后 30 秒即过期，但同意票据有效期为 120 秒——用户在 30~120 秒区间内执行时票据仍有效却被动作窗口拒绝，口径不一致。

**偏差说明：** 行号准确。

---

#### L-40 | Confirmed | 报告模块路径 → 实际：sysmind/diagnosis/、sysmind/tasks/、sysmind/actions/

**证据：**
- `sysmind/diagnosis/coordinator.py` — `DiagnosisCoordinator` 类（业务编排）
- `sysmind/tasks/manager.py` — `AgentTaskManager` 类（业务编排）
- `sysmind/actions/coordinator.py` — `ActionCoordinator` 类（业务编排）

项目中存在 `sysmind/application/` 包（含 `ports/` 子包，如 `from sysmind.application.ports.diagnoses import DiagnosisRepository`），但三个编排模块均位于 `application/` 之外的顶层包。

**偏差说明：** 结构性观察，行号不适用。

---

#### L-41 | Confirmed | 报告行 69-75 → 实际行 69-75

**证据：**
```python
# observability/logging.py:69-75
def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
```
仅挂载 `StreamHandler`，无 `RotatingFileHandler` 或任何大小轮转策略。

**偏差说明：** 行号完全准确。

---

#### L-42 | Confirmed | 报告行 53-63 → 实际行 53-63

**证据：**
```python
# runtime/server.py:53-63
def report_startup_failure(error: BaseException) -> None:
    payload = {
        "event": "sysmind_startup_error",
        "code": type(error).__name__,
        "message": str(error),
    }
    print(
        f"SYSMIND_ERROR {json.dumps(payload, separators=(',', ':'))}",
        file=sys.stderr,
        flush=True,
    )
```
启动失败将 `str(error)` 原样序列化到 stderr 输出，未经过滤或脱敏。

**偏差说明：** 行号完全准确。

---

#### L-43 | Confirmed | 报告行 14,27 → 实际行 14,27

**证据：**
```python
# reports/composer.py:14
_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3}
```
```python
# reports/composer.py:27
ordered = tuple(sorted(findings, key=lambda item: _SEVERITY_RANK[item.severity], reverse=True))
```
使用 `_SEVERITY_RANK[item.severity]` 直接字典取值，若 `item.severity` 不在已知四键中将抛 `KeyError`，无 `.get()` 防御。

**偏差说明：** 行号完全准确。

---

### 5.4 Windows 适配器 / 工具

#### L-44 | Confirmed | 报告行 90-101 → 实际行 90-101（subprocess.run 调用块）

**证据：**
```python
# windows/diagnostics.py:90-99
completed = subprocess.run(
    [self._powershell_path, "-NoProfile", "-NonInteractive", "-Command", _GPU_COMMAND],
    check=False, capture_output=True, text=True,
    encoding="utf-8", errors="replace",
    timeout=6,
    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
)
if completed.returncode != 0:   # line 100-101
    raise ToolUnavailableError("Windows did not return GPU information.")
```
`timeout=6` 触发时 `subprocess.TimeoutExpired` 异常未被捕获（函数中无 `except subprocess.TimeoutExpired`），将直接向上传播而非翻译为 `ToolUnavailableError`。

**偏差说明：** 行号准确。

---

#### L-45 | Confirmed | 报告行 160-166 → 实际行 160-166

**证据：**
```python
# windows/process_actions.py:160-166
for handle in handles:
    owner = wintypes.DWORD()
    user32.GetWindowThreadProcessId(wintypes.HWND(handle), ctypes.byref(owner))
    if owner.value != candidate.pid:
        raise TargetChangedError("Window ownership changed after confirmation.")
    if not user32.PostMessageW(wintypes.HWND(handle), _WM_CLOSE, 0, 0):
        raise ToolUnavailableError("Windows rejected the bounded close request.")
```
循环逐句柄发送 `WM_CLOSE`；若第 N 个句柄发送失败抛异常，前 N-1 个句柄已收到关闭消息（进程已部分响应关闭），状态不一致。

**偏差说明：** 行号完全准确。

---

#### L-46 | Confirmed | 报告行 197-202 → 实际行 197-202

**证据：**
```python
# windows/process_actions.py:197-202
deadline = time.monotonic() + 3.0
while time.monotonic() < deadline:
    if not self._same_process(candidate):
        return MutationResult(None, None, "terminated")
    time.sleep(0.05)
raise ToolUnavailableError("Process termination could not be verified.")
```
`TerminateProcess` 已在第 193 行成功调用，但若进程在 3 秒内未完全退出（内核清理延迟、句柄释放等），第 202 行仍抛误报失败。

**偏差说明：** 行号完全准确。

---

#### L-47 | Confirmed | 报告行 148-158 → 实际行 148-158

**证据：**
```python
# windows/startup_actions.py:138-139
metadata = self._read_metadata(directory)
kind, name = metadata.get("kind"), metadata.get("name")
```
```python
# windows/startup_actions.py:148-158
try:
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(
            key,
            name,    # ← 直接使用磁盘 metadata 中的 name
            0,
            int(cast(Any, metadata["value_type"])),
            cast(Any, metadata["value"]),
        )
```
`name` 直接取自磁盘 `metadata.json`，仅在第 140 行做了 `isinstance(name, str)` 类型检查，未对 Run 键值名做白名单或字符校验。若 recovery 目录被篡改，可恢复任意 Run 值名。

**偏差说明：** 行号准确。

---

#### L-48 | Confirmed | 报告行 221 → 实际行 221

**证据：**
```python
# windows/event_logs.py:221
events.sort(key=lambda item: item.timestamp, reverse=True)
```
`item.timestamp` 为 ISO8601 字符串（来源于 `TimeCreated[@SystemTime]`，第 80 行），排序按字典序进行。虽然 Windows 事件时间戳格式统一为 UTC 固定精度时字典序恰好等价于时间序，但代码依赖字符串比较而非 `datetime` 解析，缺乏防御性。

**偏差说明：** 行号准确。

---

#### L-49 | Confirmed | 报告行 269,273 → 实际行 269,273

**证据：**
```python
# windows/platform_inspection.py:269
elif active_adapters and gateways is None:
    failures.append("default_route_unavailable")
```
```python
# windows/platform_inspection.py:273
(None if gateways is None else bool(gateway)) if active_adapters else False,
```
语义不一致：无活动适配器时 `has_default_route=False` 但不记录任何 failure；有活动适配器但无网关时 `has_default_route=None`（未知）却记录 `default_route_unavailable`。两个字段的真值语义与 failures 列表不对应。

**偏差说明：** 行号完全准确。

---

#### L-50 | Confirmed | 报告行 65-73 → 实际行 65-73

**证据：**
```python
# windows/platform_inspection.py:65-73
def _basename(command: str) -> str | None:
    text = command.strip()
    if not text:
        return None
    if text.startswith('"') and '"' in text[1:]:
        executable = text.split('"', 2)[1]
    else:
        executable = text.split()[0]       # ← 未加引号含空格时截断
    return Path(executable).name or None
```
未加引号且路径含空格的命令（如 `C:\Program Files\App\app.exe`）走 `text.split()[0]`，得到 `C:\Program`，`Path("C:\\Program").name` 为 `Program`，路径被错误截断。

**偏差说明：** 行号完全准确。

---

### 5.5 API 层

#### L-51 | Confirmed | 报告行 37 → 实际行 37

**证据：**
```python
# api/middleware.py:37-45
if request.method != "OPTIONS":
    provided = request.headers.get(SESSION_HEADER, "")
    if not provided or not hmac.compare_digest(provided, self._expected_token):
        return self._error(...)
```
OPTIONS 预检请求完全跳过会话令牌校验（仅 CORS origin 检查在第 29 行执行）。这是标准浏览器 CORS 预检行为，但报告作为安全观察项列出。

**偏差说明：** 行号准确。

---

#### L-52 | Partial | 报告行 47,74 → 实际行 74（continue_diagnosis），其余路径参数在 87/92/100/113

**证据：**
```python
# api/routes/diagnoses.py:47  ← 此行无 diagnosis_id 路径参数
async def start_diagnosis(payload: StartDiagnosisRequest, request: Request) -> DiagnosisResponse:
```
```python
# api/routes/diagnoses.py:74  ← 此行有 diagnosis_id: str 但无 UUID 校验
async def continue_diagnosis(
    diagnosis_id: str, payload: ContinueDiagnosisRequest, request: Request
) -> DiagnosisResponse:
```
其他未校验的路径参数：`get_diagnosis`（行87）、`cancel_diagnosis`（行92）、`submit_feedback`（行100）、`export_diagnosis`（行113）均为裸 `str`。对比 `actions.py:53,61` 使用了 `Query(min_length=36, max_length=36)`。

**偏差说明：** 行 47 指向的 `start_diagnosis` 端点无 `diagnosis_id` 路径参数，行号引用错误。核心发现（路径参数缺少 UUID 格式校验）属实，但实际涉及行号为 74、87、92、100、113。

---

#### L-53 | Confirmed | 报告行 143-145 → 实际行 143-145

**证据：**
```python
# api/routes/diagnoses.py:143-145
headers={
    "Content-Disposition": f'attachment; filename="sysmind-report-{diagnosis_id}.{suffix}"'
},
```
`diagnosis_id` 路径参数直接拼入 `Content-Disposition` 响应头，未做 CRLF 或引号字符过滤。虽然实际仅当记录存在时才构建此头（查找失败走 404），但代码本身未对输入做头注入防御。

**偏差说明：** 行号准确。

---

#### L-54 | Confirmed | 报告行 46-50 → 实际行 46-50

**证据：**
```python
# api/routes/diagnoses.py:46-50
@router.post("", response_model=DiagnosisResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_diagnosis(payload: StartDiagnosisRequest, request: Request) -> DiagnosisResponse:
    # Coordinator.start schedules asyncio tasks and must run on the event loop.
    record = _coordinator(request).start(payload.question)
    return DiagnosisResponse.from_record(record)
```
未从 `request.headers` 提取 `X-Correlation-ID` 头，也未将其传递给 `coordinator.start()`。中间件虽生成 correlation_id 并放入响应头（`middleware.py:48`），但路由处理函数无法访问它。

**偏差说明：** 行号准确。

---

#### L-55 | Confirmed | 报告行 57-64 → 实际行 57-64

**证据：**
```python
# api/routes/diagnoses.py:57-64
def _build() -> DiagnosisListResponse:
    items = [
        DiagnosisResponse.from_record(
            item, coordinator.tool_calls(item.id), coordinator.user_inputs(item.id)
        )
        for item in coordinator.recent()
    ]
    return DiagnosisListResponse(items=items)
```
对列表中每条诊断记录分别调用 `coordinator.tool_calls(item.id)` 和 `coordinator.user_inputs(item.id)`，每条产生 2 次额外 DB 查询，构成 N+1 模式。

**偏差说明：** 行号准确。

---

#### L-56 | Confirmed | 报告行 33-44 → 实际行 33-44

**证据：**
```python
# api/routes/actions.py:33-44
def _run(call: Callable[[], T]) -> T:
    try:
        return call()
    except ActionError as error:
        code = (
            status.HTTP_404_NOT_FOUND
            if error.code == "action_not_found"
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(
            status_code=code, detail={"code": error.code, "message": str(error)}
        ) from error
```
除 `action_not_found` → 404 外，所有其他 `ActionError` 子类码（`target_changed`、`invalid_action_state`、`consent_replayed_or_expired`、`action_expired`、`termination_not_allowed`、`recovery_unavailable`、`diagnosis_not_ready` 等）统一映射为 409，错误码粒度过粗。

**偏差说明：** 行号准确。

---

#### L-57 | Confirmed | 报告行 82-84 → 实际行 82-84

**证据：**
```python
# api/routes/settings.py:82-84
async def test_provider(request: Request) -> ProviderTestResponse:
    try:
        succeeded, error_code, duration_ms = await _service(request).test_connection()
```
`test_connection()` 直接在 async 路由中调用，未包裹 `run_in_threadpool`。同文件其他路由（`get_settings` 行43、`update_settings` 行52、`clear_credential` 行72）均使用了 `run_in_threadpool`。`test_connection` 涉及网络请求，会阻塞事件循环。

**偏差说明：** 行号准确。

---

#### L-58 | Confirmed | 报告行 61-62 → 实际行 61-62

**证据：**
```python
# api/dto/agent_tasks.py:60-62
class AgentToolCallDto(BaseModel):
    id: str
    provider_call_id: str
```
```python
# api/dto/agent_tasks.py:106
"provider_call_id": call.provider_call_id,
```
`provider_call_id` 作为公开 API 字段暴露，此为内部 provider 调用标识符。

**偏差说明：** 行号准确。

---

#### L-59 | Confirmed | 报告行 108,110 → 实际行 108,110

**证据：**
```python
# api/dto/diagnoses.py:108
    status: str
# api/dto/diagnoses.py:110
    category: str
```
`status` 和 `category` 使用裸 `str` 类型，未使用 `Literal` 枚举或 `Enum` 约束。对比 `api/dto/agent_tasks.py:78` 中 `status: AgentTaskStatus` 使用了类型别名。

**偏差说明：** 行号完全准确。

---

#### L-60 | Confirmed | 报告行 155,160 → 实际行 155,160

**证据：**
```python
# api/dto/diagnoses.py:155
for item, finding in zip(finding_data, record.report.findings, strict=True):
```
```python
# api/dto/diagnoses.py:160
for item, hypothesis in zip(hypothesis_data, record.report.hypotheses, strict=True):
```
`zip(..., strict=True)` 在两个可迭代对象长度不一致时抛 `ValueError`，此异常未被捕获，将作为未处理 500 错误返回。`finding_data` 来自 `asdict(record)["report"]["findings"]`，理论上应与 `record.report.findings` 等长，但无防御。

**偏差说明：** 行号完全准确。

---

#### L-61 | Confirmed | 报告行 62-63,84 → 实际行 62-63,84

**证据：**
```python
# api/dto/actions.py:62-63
    created_at: str
    updated_at: str
```
```python
# api/dto/actions.py:84
    expires_at: str | None
```
时间戳字段使用裸 `str` 类型。对比 `api/dto/diagnoses.py:124` 中 `created_at: datetime` 使用了 `datetime` 类型。

**偏差说明：** 行号完全准确。

---

#### L-62 | Confirmed | 报告行 91-94 → 实际行 91-94

**证据：**
```python
# api/dto/actions.py:91-94
def process_candidate_response(item: ProcessActionCandidate) -> ProcessCandidateResponse:
    data = asdict(item)
    data.pop("pid")
    return ProcessCandidateResponse.model_validate(data)
```
`pid` 字段被主动从响应 DTO 中移除。`ProcessCandidateResponse`（行22-29）不含 `pid` 字段。

**偏差说明：** 行号完全准确。

---

#### L-63 | Confirmed | 报告行 28-37,60-95 → 实际行 28-37（imports），60-95（lifespan 调用）

**证据：**
```python
# api/app.py:28-37
from sysmind.infrastructure.bootstrap import (
    create_action_coordinator, create_agent_task_manager,
    create_diagnosis_coordinator, create_history_service,
    create_log_analysis_coordinator, create_provider_settings_service,
    create_quick_scan_coordinator,
)
```
```python
# api/app.py:62-94（lifespan 内）
history = history_service or create_history_service(resolved_settings.database_url)
coordinator = quick_scan_coordinator or create_quick_scan_coordinator(...)
log_coordinator = log_analysis_coordinator or create_log_analysis_coordinator(...)
provider_settings = provider_settings_service or create_provider_settings_service(...)
task_manager = agent_task_manager or create_agent_task_manager(...)
diagnoses = diagnosis_coordinator or create_diagnosis_coordinator(...)
actions = action_coordinator or create_action_coordinator(...)
```
`app.py` 直接 import 并调用 `infrastructure.bootstrap` 工厂函数，未经过 application 层组合根。

**偏差说明：** 行号准确。

---

### 5.6 前端

#### L-64 | Confirmed | 报告行 140-141 → 实际行 140

**证据：**
```typescript
// services/api-client.ts:129-141
while (true) {
  const { done, value } = await reader.read();
  buffer += decoder.decode(value, { stream: !done }).replaceAll("\r\n", "\n");
  let boundary = buffer.indexOf("\n\n");
  while (boundary >= 0) {
    ...
  }
  if (done) break;    // ← line 140
}
```
当 `done=true` 时，内层 while 循环处理完所有完整 `\n\n` 分隔块后，若 `buffer` 中仍残留不完整 SSE 块（无 `\n\n` 终止符），直接 break 丢弃，未 flush 或解析残留内容。

**偏差说明：** 报告标注 140-141，实际 break 语句在行 140，偏差 ±1 行内。

---

#### L-65 | Confirmed | 报告行 131 → 实际行 131

**证据：**
```typescript
// services/api-client.ts:131
buffer += decoder.decode(value, { stream: !done }).replaceAll("\r\n", "\n");
```
`.replaceAll("\r\n", "\n")` 在每个 chunk 读取后执行，对整个解码文本做正则替换。可在流入口统一处理而非逐 chunk 重复。

**偏差说明：** 行号准确。

---

#### L-66 | Confirmed | 报告行 186 → 实际行 186

**证据：**
```typescript
// services/api-client.ts:186
return (await response.json()) as T;
```
当响应为 204 No Content 或空 body 时，`response.json()` 抛 `SyntaxError`。该异常被外层 catch（行187）捕获后归入 `"network_error"`，错误分类不准确。

**偏差说明：** 行号准确。

---

#### L-67 | Confirmed | 报告行 86-89 → 实际行 86-89

**证据：**
```typescript
// services/api-client.ts:86-89
if (!response.ok) {
  throw new ApiClientError("download_error", "Report export was unavailable.", {
    status: response.status,
  });
}
```
对比 `#request` 方法（行181）在错误时传递了 `correlationId`，此处 `download` 方法抛错时未传 `correlationId`。请求中的 `X-Correlation-ID`（行81）是内联 `crypto.randomUUID()`，未存入变量也未从响应头读取。

**偏差说明：** 行号完全准确。

---

#### L-68 | Confirmed | 报告行 74 → 实际行 74

**证据：**
```typescript
// services/backend.ts:74
await new Promise<void>((resolve) => window.setTimeout(resolve, 150));
```
轮询退避使用裸 `window.setTimeout` 包裹 Promise，未集成 `AbortSignal`（第52行虽有 `signal?.aborted` 检查，但在等待 150ms 期间若 signal 被 abort，不会立即响应）。

**偏差说明：** 行号准确。

---

#### L-69 | Confirmed | 报告行 141-142 → 实际行 141-142

**证据：**
```typescript
// services/diagnoses.ts:141-142
anchor.click();
URL.revokeObjectURL(url);
```
`anchor.click()` 后同步立即调用 `URL.revokeObjectURL(url)`。在部分浏览器中，下载尚未开始即 revoke URL 会导致下载失败或空文件。推荐使用 `setTimeout` 延迟 revoke。

**偏差说明：** 行号完全准确。

---

#### L-70 | Confirmed | 报告行 131-143 → 实际行 131-143

**证据：**
```typescript
// services/diagnoses.ts:131-143
export async function downloadDiagnosis(
  client: ApiClient, id: string, format: "json" | "markdown",
) {
  const blob = await client.download(`/api/v1/diagnoses/${id}/export?format=${format}`);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `sysmind-report-${id}.${format === "markdown" ? "md" : "json"}`;
  anchor.click();
  URL.revokeObjectURL(url);
}
```
服务层函数直接操作 DOM（`document.createElement`、`anchor.click()`、`URL.createObjectURL`），违反服务层/视图层分离。

**偏差说明：** 行号完全准确。

---

#### L-71 | Confirmed | 报告行 478 → 实际行 478

**证据：**
```tsx
// features/diagnose/DiagnosisPanel.tsx:478
<ul>{diagnosis.report.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
```
React `key` 直接使用 limitation 字符串内容 `item`。若存在两条完全相同的 limitation 文本，将产生重复 key 警告。

**偏差说明：** 行号准确。

---

#### L-72 | Confirmed | 报告行 73 → 实际行 73

**证据：**
```tsx
// features/diagnose/ControlledActions.tsx:73
await new Promise((resolve) => window.setTimeout(resolve, 1_000));
```
轮询退避等待使用裸 `window.setTimeout`，未集成 `controller.signal`（第59行循环条件检查 abort，但在 1000ms 等待期间 abort 不会立即中断等待）。

**偏差说明：** 行号准确。

---

## 汇总

| 判定 | 数量 | 编号 |
|------|------|------|
| Confirmed | 35 | L-37, L-38, L-39, L-40, L-41, L-42, L-43, L-44, L-45, L-46, L-47, L-48, L-49, L-50, L-51, L-53, L-54, L-55, L-56, L-57, L-58, L-59, L-60, L-61, L-62, L-63, L-64, L-65, L-66, L-67, L-68, L-69, L-70, L-71, L-72 |
| Partial | 1 | L-52 |
| False Positive | 0 | — |

- L-52 部分属实：核心发现（diagnosis_id 路径参数缺少 UUID 格式校验）成立，但报告引用的行 47 指向的 `start_diagnosis` 端点并无 `diagnosis_id` 路径参数；实际未校验的路径参数位于行 74（continue_diagnosis）、87（get_diagnosis）、92（cancel_diagnosis）、100（submit_feedback）、113（export_diagnosis）。
