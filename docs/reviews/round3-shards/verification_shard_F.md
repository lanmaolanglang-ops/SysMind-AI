# 复核结果 Shard F（L-73 ~ L-108，Low 严重度）

复核方法：逐条用 Read 打开磁盘真实源码定位标注行号，以当前代码为唯一依据。
判定口径：Confirmed（属实）/ Partial（部分属实）/ False Positive（误报）。行号偏差 ±2 行内视为准确。

---

## 5.7 Rust Tauri

| 编号 | 判定 | 报告行号→实际行号 | 证据（真实代码行） | 偏差说明 |
|---|---|---|---|---|
| L-73 | Confirmed | sidecar.rs:310-323 → 310-323 | `match child.try_wait() { Ok(Some(status)) => { managed.child = None; … managed.snapshot = BackendSnapshot { state: "disconnected", endpoint: None, error: Some(format!("Backend process exited unexpectedly ({status}).")) }; return; }` | 行号完全准确。进程异常退出后仅置 error 并 return，无任何自动重启/恢复逻辑。 |
| L-74 | Confirmed | lib.rs:33 / tauri.conf.json:46-51 → 33 / 46-51 | lib.rs:33 `.plugin(tauri_plugin_updater::Builder::new().build())`；tauri.conf.json:48 `"pubkey": "",` 49 `"endpoints": []` | 行号准确。updater 插件已启用，但配置中 pubkey 与 endpoints 均为空。另注 bundle.createUpdaterArtifacts=false（34 行），与启用插件自相矛盾。 |
| L-75 | Confirmed | sidecar.rs:168-176 → 168-176 | sidecar.rs:172 `eprintln!("SysMind backend startup error: {line}");`；main.rs:1 `#![cfg_attr(all(windows, not(debug_assertions)), windows_subsystem = "windows")]` | 行号准确。release（not debug_assertions）下 windows_subsystem="windows" 无控制台，eprintln! 写入不存在的 stderr，输出丢失。 |
| L-76 | Confirmed | lib.rs:11-19 → 11-19 | `manager.shutdown(); manager.start(&app); manager.snapshot()`（16-18） | 行号准确。start() 仅起后台线程即返回，紧接着 snapshot() 必然返回 "starting" 瞬时快照而非 connected；shutdown→start 之间存在 generation/child 交错窗口。 |
| L-77 | Confirmed | sidecar.rs:256-261 → 256-261 | `runtime.snapshot = BackendSnapshot { state: "disconnected", endpoint: None, error: None };` | 行号准确。shutdown 末尾无条件把 error 清为 None，之前记录的后端崩溃错误信息被抹掉。 |
| L-78 | Confirmed | sidecar.rs:420-426 → 420-426 | `if !headers.starts_with("HTTP/1.1 200") { return Err("Backend returned a non-success response.") }` | 行号准确。用前缀匹配判定状态行：未对 "200" 做空格边界校验，且硬要求 HTTP/1.1，不解析 reason phrase，判定方式不严谨。 |
| L-79 | Confirmed | sidecar.rs:207-211,344-347 → 207-211,344-347 | 208 `base_url: format!("http://127.0.0.1:{}", handshake.port)`；345 `if handshake.host != "127.0.0.1"` | 行号准确。握手只比对后端"自报"的 host 字符串是否等于 127.0.0.1，未独立验证。补充：实际连接在 208 行已硬编码 127.0.0.1、send_http_request(398) 再校验一次，故安全影响有限。 |
| L-80 | Confirmed | sidecar.rs:496-529,119-144 → 496-529,119-144 | 119 `command.spawn()` → 134 `WindowsJob::assign(&child)` → 522 `AssignProcessToJobObject(job, child.as_raw_handle()…)` | 行号准确。spawn(119) 与 AssignProcessToJobObject(522) 之间存在时间窗：子进程可能在被纳入 Job 前已运行/逃逸，典型 spawn→assign TOCTOU。 |
| L-81 | Confirmed | tauri.conf.json:25 → 25 | `"csp": "default-src 'self'; connect-src 'self' http://127.0.0.1:*; …"` | 行号准确。connect-src 对 127.0.0.1 全端口（*）放行，任意本机监听端口均可被前端连接。 |
| L-82 | Confirmed | sidecar.rs:243-254,256-261 → 243-254,256-261 | 243-250 `while Instant::now() < deadline { try_wait… }`；256-261 才把 snapshot 置 disconnected | 行号准确。2s 优雅等待窗口（243-250）期间 snapshot 仍保留旧的 "connected" 状态，直到等待结束才更新。 |
| L-83 | Confirmed | lib.rs:44-48 → 44-48 | 45 `if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {` 46 `app_handle.state::<BackendManager>().shutdown();` | 行号准确。在 run 回调中同步调用 shutdown()，后者含 2s 等待循环（sidecar.rs:243），阻塞事件循环最多约 2s。 |

## 5.8 测试 / 迁移 / 脚本

| 编号 | 判定 | 报告行号→实际行号 | 证据（真实代码行） | 偏差说明 |
|---|---|---|---|---|
| L-84 | Confirmed | conftest.py:36-38 → 36-38 | 37 `def auth_headers() -> dict[str, str]:` 38 `return {"X-SysMind-Session": TEST_TOKEN, "Origin": "tauri://localhost"}`；12 `TEST_TOKEN = "test-session-token-that-is-long-enough"` | 行号准确。fixture 直接返回明文 token（常量为内联字符串）。 |
| L-85 | Confirmed | test_action_async_boundary.py:16 → 16 | `assert asyncio.run(scenario()) < 0.1` | 行号准确。异步边界测试基于 0.1s 绝对墙钟阈值，受 CI 负载抖动影响。 |
| L-86 | Confirmed | test_agent_runtime.py:411-420 → 411-420 | 414 `assert cancel_event is cancellation`（在类方法内引用）；420 `cancellation = Event()`（之后才定义） | 行号准确。方法体内前向引用闭包变量 cancellation，依赖 Python 晚绑定在调用时才解析，属代码异味。 |
| L-87 | Confirmed | test_agent_runtime.py:297-306 → 297-306 | 299 `event_ids = [int(line.removeprefix("id: ")) for line in lines if line.startswith("id: ")]`；305-306 `assert f"id: {event_ids[0]}\n" not in reconnect.text` | 行号准确。SSE 游标重连断言依赖 "id: " 前缀与 "\n" 行尾的确切流格式。 |
| L-88 | Confirmed | test_event_logs.py:268 → 268 | `assert probe.system_started.wait(1)` | 行号准确。部分取消测试依赖 1 秒同步等待（Event.wait(1)）。 |
| L-89 | Partial | test_health.py:19 → 19 | `assert response.headers["X-Correlation-ID"]` | 行号准确，确为真值断言（未校验 UUID 格式）。但"放过空字符串"的具体说法不成立：Python 中空串为 falsy，`assert ""` 会抛 AssertionError，空串实际会被拦下。故仅"弱断言"部分属实。 |
| L-90 | Confirmed | test_observability.py:13-14 → 13-14 | 13 `logger.handlers = [handler]`；14 `logger.propagate = False` | 行号准确。对 logger 原地替换 handlers 并改 propagate，测试结束无 fixture 恢复。补充：该 logger 为专用命名 "sysmind.test.redaction"，非 root logger，污染面有限。 |
| L-91 | Confirmed | test_secrets.py:41-47 → 41-45 | 41 `service = object.__new__(WindowsCredentialSecretService)`；42-43 手工塞 `_namespace`/`_advapi32` | 行号准确。用 object.__new__ 绕过 __init__，再手工注入私有属性。 |
| L-92 | Confirmed | alembic/0006:40 → 40 | 40 `sa.Column("recovery_id", sa.String(36)),`（无 ForeignKey）；70-71 recovery_records 主键 id | 行号准确。actions.recovery_id 语义指向 recovery_records.id，但仅为普通列，未建外键（反向 recovery_records.action_id 才有 FK）。 |
| L-93 | Confirmed | alembic/0008:20-25 / 0007:20-28 → 20-25 / 20-28 | 0008:20-25 `op.create_table("data_retention_policy", …)`；0007:20-28 `op.create_table("provider_settings", …)`，两者 upgrade() 均无 op.execute(INSERT…) | 行号准确。两表建表后均未播种初始行。补充：data_retention_policy 确为单例策略表；provider_settings 含非唯一 provider 列、未必是单例，"单例"定性对其偏弱。 |
| L-94 | Confirmed | test_packaged_desktop.py:68 → 68 | `if revision == ("0010_phase32",):` | 行号准确。冒烟测试硬编码 head 版本号 "0010_phase32"，新增迁移后会失配。 |
| L-95 | Confirmed | test_packaged_backend.py:61 → 61 | `assert process.stdout is not None` | 行号准确。用 assert 做运行时非空判断；python -O 下 assert 被剥离后该保护消失。 |
| L-96 | Confirmed | export-openapi.py:16 → 16 | `session_token=SecretStr("contract-generation-session-token"),` | 行号准确。OpenAPI 导出脚本写死固定 session token 字面量。 |

## 5.9 Domain / Core / Ports

| 编号 | 判定 | 报告行号→实际行号 | 证据（真实代码行） | 偏差说明 |
|---|---|---|---|---|
| L-97 | Confirmed | diagnosis.py:109-111 / agent_tasks.py:34-38 → 109-111 / 34-38 | diagnosis.py:110-111 `max_agent_rounds: int = 4` / `max_tool_calls: int = 8`；agent_tasks.py:35-36 `max_rounds: int = 4` / `max_tool_calls: int = 8` | 行号准确。预算上限 4 轮 / 8 次工具调用在 DiagnosisRecord 与 AgentBudget 两处重复定义。 |
| L-98 | Confirmed | diagnosis.py:42,73,83 → 42,73,83 | 42 `confidence: float`（Finding）；73 `confidence: float`（DiagnosisHypothesis）；83 `confidence: float`（DiagnosisReport） | 行号准确。三处 confidence 均为裸 float，无 [0,1] 量程校验（dataclass 无 validator）。 |
| L-99 | Confirmed | event_logs.py:65 → 65 | `query: dict[str, object]` | 行号准确。LogAnalysisRecord.query 存为无类型 dict，未用 EventLogQuery 值对象。 |
| L-100 | Confirmed | diagnosis.py:121 / agent_tasks.py:79,81 / actions.py:71 → 121 / 79,81 / 71 | diagnosis.py:121 `status: str`；agent_tasks.py:79 `status: str`、81 `risk_level: str`；actions.py:71 `outcome: str = "succeeded"` | 行号准确（actions.py:71 为 MutationResult.outcome，属状态类裸 str）。四处状态/风险级别均用裸 str 而非 Literal 别名。 |
| L-101 | Confirmed | ports/actions.py:56-65 / diagnoses.py:29 → 56-65 / 29 | actions.py:60 `status: str,`（set_status）；diagnoses.py:29 `status: str,`（update_progress） | 行号准确。仓储端口方法的 status 形参用裸 str，未复用 ActionStatus/DiagnosisStatus 类型别名。 |
| L-102 | Confirmed | ports/agent_tasks.py:77-88 vs diagnoses.py:97-108 → 77-88 vs 97-108 | agent_tasks.py:84 `full_result: object | None` / 85 `result_summary: dict…`；diagnoses.py:102 `result: object | None` / 103 `summary: dict…` | 行号准确。两套 finish_tool_call 都存 result+summary，但参数命名（full_result/result_summary vs result/summary）与参数顺序不一致，口径不统一。 |
| L-103 | Confirmed | ports/diagnostics.py:4,34,39 / platform_inspection.py:4 → 4,34,39 / 4 | diagnostics.py:4 `from threading import Event`；34 `cancel_event: Event \| None = None`；39 `cancel_event: Event,`；platform_inspection.py:4 `from threading import Event` | 行号准确。端口抽象直接耦合具体的 threading.Event，而非自定义取消抽象。 |
| L-104 | Confirmed | ports/history.py:9-34 → 9-34 | 9-16 `@dataclass(frozen=True) class DeletionImpact`；19-25 `class CleanupResult`；28-34 `class BaselineMetric` | 行号准确。DeletionImpact/CleanupResult/BaselineMetric 等业务值对象定义在 application/ports 层，而非 domain 层。 |
| L-105 | Confirmed | ports/secrets.py:1 → 1 | 1 `from typing import Protocol`（无 `from __future__ import annotations`）；9 `def get(self, key: str) -> str \| None` | 行号准确。其余 ports 文件第 1 行均有 future import，仅此文件缺失；返回注解用了 PEP 604 语法。 |
| L-106 | Confirmed | event_logs.py:16-19 → 16-19 | 16 `lookback_hours: int`；19 `max_events: int`（17-18 为 levels/event_ids） | 行号准确。EventLogQuery 的 lookback_hours、max_events 为裸 int，无正数/上限约束。 |
| L-107 | Confirmed | platform_inspection.py:59-62,76-80 → 59-62,76-80 | 59 `item_count: int`、60 `high_impact_count: int`、62 `unknown_signature_count: int`（与 58 `items` 同列）；78 `service_count: int`、79 `stopped_automatic_count: int`（与 77 `services` 同列） | 行号准确。item_count/service_count 与 len(items)/len(services) 冗余，另有可从集合派生的计数字段。 |
| L-108 | Confirmed | domain/__init__.py:1 → 1 | 1 `"""Pure domain definitions. Phase 0 intentionally contains no diagnostic domain."""` | 行号准确。包内已含 diagnosis/agent_tasks/actions/event_logs 等诊断域，docstring 仍称"Phase 0 无诊断域"，严重过时。 |

---

## 汇总

- 总数：36 条（L-73 ~ L-108）
- **Confirmed：35 条**（L-73~L-88、L-90~L-108）
- **Partial：1 条**（L-89）
- **False Positive：0 条**

唯一 Partial 说明：L-89（test_health.py:19）行号准确、确为弱真值断言，但"放过空字符串"这一具体后果不成立——Python 中 `assert ""` 会失败，空串实际会被拦截；仅"未校验 UUID 格式"这一弱化断言的观察成立。
