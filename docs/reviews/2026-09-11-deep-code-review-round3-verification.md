# SysMind AI 代码审查报告 — 独立复核报告

> **复核日期**：2026-09-10
> **复核对象**：`D:\SysMind AI\CODE_REVIEW_REPORT.md`
> **复核方式**：6 个分片并行，每条发现均用 Read 工具打开磁盘真实源文件，定位到报告标注行号逐字比对
> **复核基准**：以当前磁盘源码为唯一依据，行号偏差 ±2 行内视为准确
> **复核覆盖**：报告正文显式列出的全部 141 条发现（H-01~H-02、M-01~M-31、L-01~L-108），逐条判定，无抽样、无跳过

---

## 一、复核总览

### 1.1 判定统计

| 判定 | 数量 | 占比 |
|---|---:|---:|
| **Confirmed（属实）** | **137** | 97.2% |
| **Partial（部分属实）** | **4** | 2.8% |
| **False Positive（误报）** | **0** | 0% |
| **合计** | **141** | 100% |

**准确率（Confirmed + Partial 中事实内核成立）：100%** — 无一条完全误报，4 条 Partial 的核心问题均真实存在，仅行号引用或描述细节有偏差。

### 1.2 原报告自身统计偏差

原报告概览声称 **146 个发现**（High 2 / Medium 33 / Low 105 / Info 6），但正文实际列出：

| 严重度 | 报告声称 | 正文实际列出 | 偏差 |
|---|---:|---:|---|
| High | 2 | H-01, H-02 = 2 | 一致 |
| Medium | 33 | M-01~M-31 = 31 | **少 2 条** |
| Low | 105 | L-01~L-108 = 108 | **多 3 条** |
| Info | 6 | **0 条**（正文无 Info 章节） | **缺 6 条** |
| 合计 | 146 | 141 | **差 5 条** |

> 报告称"完整 105 条 Low 发现详见各分片报告"，但项目中不存在分片详细报告文件；Info 6 条在正文中完全没有出现。本次复核覆盖正文全部 141 条显式发现。

### 1.3 严重度分布复核

| 严重度 | 复核数 | Confirmed | Partial | False Positive |
|---|---:|---:|---:|---:|
| High | 2 | 2 | 0 | 0 |
| Medium | 31 | 30 | 1 (M-14) | 0 |
| Low | 108 | 105 | 3 (L-34, L-52, L-89) | 0 |
| **合计** | **141** | **137** | **4** | **0** |

---

## 二、Partial 发现详细证据

### M-14 子目录 toolset 提供绕过 Registry/Executor 的执行路径 — Partial

- **报告文件**：`tools/system/toolset.py:27-34`、`process/toolset.py:19-23`、`log/toolset.py:69-82`
- **实际行号**：全部准确
- **属实部分**：三个类均仍被 `bootstrap.py` 装配、被 `quick_scan.py` / `log_analysis.py` 直接驱动，确实绕过了 `ToolRegistry.authorize` 与 `ToolExecutor`（未走 policy 授权、input_model 校验、全局/键信号量），自行用 `asyncio.wait_for(to_thread(...))` 调用探针。
- **不属实部分**：
  1. 仅 `SystemTools`、`ProcessTools` 以 `{name: callable}` 字典暴露；`LogTools` 并无 `handlers()` 字典，而是 `query/analyze/aggregate` 三个具名方法被直接调用。
  2. 报告称"并行执行路径"，但 `quick_scan.py:140` 是 `for name in ordered_names` 串行循环、`log_analysis.py:163` 也是逐通道串行，均为串行而非并行。
- **修正建议**：将描述改为"绕过 Registry/Executor 的串行直调路径"，并明确 LogTools 的形态为具名方法而非字典。

### L-34 context.py 中 provider.name 隐式依赖具体类 — Partial

- **报告文件**：`context.py`（全局）
- **实际证据位置**：`agent/contracts.py:47-49`、`providers/fake.py:31-32`、`providers/openai_compatible.py:73-75`
- **属实部分**：name 字符串值由各具体实现类硬编码（`"fake"`、`"openai_compatible"`），无中央枚举/注册表约束。
- **不属实部分**：
  1. `agent/context.py` 全文 122 行内**没有任何 provider.name 引用**（context 只组装 request），所引文件不存在该代码。
  2. `agent/contracts.py:47-49` 的 `AgentProvider` Protocol 已显式声明 `name` 属性，并非完全"隐式依赖"。
- **修正建议**：将引用文件改为 `agent/contracts.py` 与各 provider 实现，描述改为"name 字符串值由具体类硬编码、无集中约束"。

### L-52 diagnosis_id 路径参数缺少 UUID 格式校验 — Partial

- **报告文件**：`api/routes/diagnoses.py:47,74`
- **实际行号**：行 47 指向的 `start_diagnosis` 端点**无** `diagnosis_id` 路径参数；实际未校验的路径参数位于行 74（continue_diagnosis）、87（get_diagnosis）、92（cancel_diagnosis）、100（submit_feedback）、113（export_diagnosis）。
- **属实部分**：核心问题（路径参数缺少 UUID 格式校验）确实存在，上述 5 个端点均为裸 `str`，对比 `actions.py:53,61` 使用了 `Query(min_length=36, max_length=36)`。
- **不属实部分**：行号 47 引用错误——`start_diagnosis` 是 POST 根路径，无路径参数。
- **修正建议**：将行号改为 `74,87,92,100,113`。

### L-89 X-Correlation-ID 真值断言放过空字符串 — Partial

- **报告文件**：`tests/test_health.py:19`
- **实际行号**：19，准确
- **属实部分**：`assert response.headers["X-Correlation-ID"]` 确为弱真值断言，未校验 UUID 格式或非空约束。
- **不属实部分**：报告称"放过空字符串"不成立——Python 中空串是 falsy，`assert ""` 会抛 `AssertionError`，空串实际会被拦截。仅"未校验 UUID 格式"这一观察成立。
- **修正建议**：将后果描述改为"未校验 UUID 格式，仅做真值断言"。

---

## 三、High 发现复核明细

| 编号 | 报告文件:行号 | 实际文件:行号 | 判定 | 证据/偏差说明 |
|---|---|---|---|---|
| H-01 | 0006_phase5a_controlled_actions.py:23,31,32 | 同（精确） | Confirmed | 三处 FK 确无 ondelete；models.py:387-400 同样缺失；其余 5 个 diagnosis 子表均带 ondelete="CASCADE"；engine.py:15 每连接 PRAGMA foreign_keys=ON。**措辞偏差**：按 retention_days DELETE 的逻辑在 history.py:cleanup()（181-182），不在 0008 迁移本体（0008 仅建策略/审计表）。功能实质成立。 |
| H-02 | sidecar.rs:187-201 | 同（精确） | Confirmed | 187-192 阻塞读 stdout 无超时；10s wait_until_ready 在 212 行握手成功后才启动；monitor_child_process 用 try_wait()（310 行）。 |

---

## 四、Medium 发现复核明细（M-01 ~ M-31）

| 编号 | 报告文件:行号 | 实际文件:行号 | 判定 | 证据/偏差说明 |
|---|---|---|---|---|
| M-01 | engine.py:11-18 + bootstrap.py:50-128 | 同 | Confirmed | 监听器只设 foreign_keys/WAL，无 busy_timeout；bootstrap 每个协调器各建独立 engine 写同一 WAL。 |
| M-02 | diagnoses.py:217 | 同 | Confirmed | `tool, version = str(step["tool"]).rsplit("@", 1)` 无 @ 即 ValueError。 |
| M-03 | diagnoses.py:265-272 | 同 | Confirmed | wait_for_input:271 把 question 写入 current_step，未用 clarification_question。 |
| M-04 | actions.py:75 | 同 | Confirmed | `tool_version="1.0"` 硬编码。 |
| M-05 | history.py:222-241 | 同 | Confirmed | except 元组（240 行）缺 AttributeError；cast 后 .get 可触发。 |
| M-06 | models.py:327 | 同 | Confirmed | tool_call_id FK 无 ondelete，同模型其他外键均有。 |
| M-07 | logging.py:54,65 | 同 | Confirmed | message 与异常堆栈原样落日志；redact_text 存在但未被引入。 |
| M-08 | manager.py:162-164 | 同 | Confirmed | AgentRunError 分支 str(error) 落库（164），紧邻泛型分支用固定脱敏文案（172）。 |
| M-09 | sidecar.rs:436-441 | 同 | Confirmed | env override 命中即 return，位于 !cfg!(debug_assertions) 守卫（453）之前，release 包确可被 env 覆盖。 |
| M-10 | ports/diagnoses.py:86-96 | 同 | Confirmed | 端口同时收原始 arguments 与 arguments_hash；domain DiagnosisToolCall 无 arguments 字段。 |
| M-11 | ports/scans.py:23-36 vs log_analyses.py:36 | 同 | Confirmed | ScanRepository.add_step_event 无 arguments_hash；LogAnalysisRepository 强制要求。 |
| M-12 | executor.py:76-79 | 同（超时分支 90-91） | Confirmed | except TimeoutError 只 return，从不 cancel_event.set()。 |
| M-13 | log/toolset.py:12 vs runtime_tools.py:298 | 同 | Confirmed | LOG_TOOL_SPECS 为 3.0s，注册 ToolDefinition 为 12.0s。 |
| M-14 | system/toolset.py:27-34 等 | 同 | **Partial** | 绕过 Registry/Executor 且仍被引用属实；但 LogTools 无 {name:callable} 字典（具名方法直调），且两处均为串行循环而非"并行"。详见第二节。 |
| M-15 | middleware.py:26,48 | 同 | Confirmed | 取值未校验，原样反射回响应头。 |
| M-16 | health.py:11-16 | 同 | Confirmed | 硬编码 ready=True，无视 app.py:96/98 维护的 app.state.ready。 |
| M-17 | agent_tasks.py:116-135 | 同 | Confirmed | 事件循环无 try/except，DB 异常直接冒泡。 |
| M-18 | agent_tasks.py:129-131 | 同 | Confirmed | 先取 events（122）后取 status（129），存在终态事件被漏发竞态。 |
| M-19 | AgentTaskPanel.tsx:100-116 | 实际 104-116 | Confirmed | setTask 未校验 current.id === activeTaskId；行号偏差 ±2 内。 |
| M-20 | SettingsPanel.tsx:136,138 | 同 | Confirmed | NaN < 7 / NaN > 3650 均为 false，disabled 守卫失效。 |
| M-21 | log_analysis.py:151 | 同 | Confirmed | start() 不校验空 channels，channels[0] 抛 IndexError（在 async task 内被 _run_guarded 捕获）。 |
| M-22 | provider_settings.py:10,81-94 | 同 | Confirmed | application 层直接 new OpenAICompatibleProvider。 |
| M-23 | brain.py:257-289 | 同 | Confirmed | create_tool_call 后无 try/finally，取消时 finish_tool_call 被跳过。 |
| M-24 | config.py:67-69 + __main__.py:17-31 | 同 | Confirmed | session_token 用 default_factory 每次构造随机生成；__main__ 与 get_settings() 两条路径。 |
| M-25 | diagnostics.py:39-41 | 同 | Confirmed | 默认文案点名 "metadata-only Windows adapter"。 |
| M-26 | diagnostics.py:36-41 | 同 | Confirmed | telemetry_available 与 telemetry_limitation 无 validator 保证一致。 |
| M-27 | diagnostics.py:84-85, event_logs.py:65-67 | 同 | Confirmed | frozen dataclass 持有 dict/list 可变容器。 |
| M-28 | test_database.py:104, test_scans.py:149, test_event_logs.py:200 | 同 | Confirmed | 三处硬编码："0010_phase32"、==7、==3。 |
| M-29 | test_release_hardening.py:19,84 | 同 | Confirmed | 跨测试模块 import + 运行时替换 service._adapter。（补充：46 行 service._repository 同类问题未标注。） |
| M-30 | test_phase4_diagnosis.py:518-526,556-564 | 同 | Confirmed | 测试侧重算 SHA-256 序列化配方，与生产规则双写。 |
| M-31 | env.py:37 + 0009/0010 downgrade | env.py:37；0009 downgrade 81-83；0010 downgrade 86-89 | Confirmed | env.py 无 render_as_batch=True；downgrade 直接 drop_column。 |

---

## 五、Low 发现复核明细（L-01 ~ L-108）

### 5.1 基础设施（L-01 ~ L-16）

| 编号 | 报告行号 | 实际行号 | 判定 | 说明 |
|---|---|---|---|---|
| L-01 | engine.py:16 | 同 | Confirmed | journal_mode=WAL 每次连接重复设置；NullPool 使每条会话新建连接。 |
| L-02 | models.py:387-400 | 同 | Confirmed | 动作外键缺级联（与 H-01 重叠）；user_confirmations/action_events/recovery_records 同样无 ondelete。 |
| L-03 | models.py（全局） | 全库无对应代码 | Confirmed | 全库 grep 确认无任何 chmod/icacls/ACL 收紧代码。 |
| L-04 | diagnoses.py:529-541 | 同 | Confirmed | failure_code="backend_restarted" 但 stop_reason 写 "risk_limit_reached"。 |
| L-05 | diagnoses.py:189 | 同 | Confirmed | agent_round_count 被赋为 plan revision。 |
| L-06 | diagnoses.py:286 | 同 | Confirmed | 中文提示文案硬编码在 infrastructure 层。 |
| L-07 | diagnoses.py:523-527 | 同 | Confirmed | mark_interrupted 只捞 queued/running，遗漏 waiting_user_input。 |
| L-08 | actions.py:265-268 | 同 | Confirmed | close() 穿透 sessionmaker.kw 拿 bind 并 dispose 共享 engine。 |
| L-09 | actions.py:98-104 | 实际 96-112（核心 96-97） | Confirmed | create_restore 仅校验 recovery_id，未检查 tool_name 是否 startup 类；偏差 ≤2 行。 |
| L-10 | agent_tasks.py:154-165 | 同 | Confirmed | "非 None 才更新"模式无法清空字段。 |
| L-11 | agent_tasks.py:321-325 | 同 | Confirmed | mark_interrupted 遗漏 waiting_user_input（与 L-07 同型）。 |
| L-12 | history.py:150-200 | 同 | Confirmed | cleanup 仅删 SystemScan/EventLogAnalysis/Diagnosis，从不回收 agent_tasks 四表。 |
| L-13 | history.py:71-79 | 同 | Confirmed | 删除影响面统计仅覆盖 3 个子表，遗漏 AgentPlan/DiagnosisStep 等 6 表。 |
| L-14 | log_analyses.py:40 / scans.py:37 | 同 | Confirmed | 两个仓储未显式继承端口 Protocol。 |
| L-15 | bootstrap.py:50-141 | 同 | Confirmed | 每个工厂各自建 engine，无共享、无统一 dispose。 |
| L-16 | repositories/__init__.py:12-23 | 同 | Confirmed | __all__ 在前、import 在末尾。 |

### 5.2 应用层 / Agent（L-17 ~ L-36）

| 编号 | 报告行号 | 实际行号 | 判定 | 说明 |
|---|---|---|---|---|
| L-17 | quick_scan.py:72-75 / log_analysis.py:87-99 | 同 | Confirmed | 同步 start() 内调用 asyncio.create_task。 |
| L-18 | quick_scan.py:158-160 / log_analysis.py:272-275 | 同 | Confirmed | to_thread 取消无法终止底层工作线程。 |
| L-19 | quick_scan.py:214-217 / log_analysis.py:319-324 | 同 | Confirmed | CancelledError 被吞掉不重抛。 |
| L-20 | quick_scan.py:182 | 同 | Confirmed | 全失败仍标 partial，与 log_analysis 的 failed 语义不一致。 |
| L-21 | log_analysis.py:208-209 | 同 | Confirmed | analyze/aggregate 同步阻塞在事件循环上。 |
| L-22 | log_analysis.py:266,278-294 | 同 | Confirmed | except Exception 捕不到 CancelledError，步骤默认 completed 误记。 |
| L-23 | log_analysis.py:319-324 | 同 | Confirmed | 取消路径 _finish_cancelled 传入空列表，丢弃已采集事件。 |
| L-24 | quick_scan.py:108-121,161 | 108/113-121/161 | Confirmed | result_keys 硬编码 7 项，与 spec 集合耦合。 |
| L-25 | provider_settings.py:59,63 | 同 | Confirmed | 校验用原始值，落库用 strip/rstrip 后值。 |
| L-26 | provider_settings.py:55-71 | 实际 62-70 | Confirmed | 回滚时 _secrets.set() 再抛会覆盖原始异常。 |
| L-27 | log_analysis.py:113-120 | 同 | Confirmed | cancel() 返回设置前的旧 record。 |
| L-28 | planning.py:248,301 | agent/planning.py:248,301 | Confirmed | 文件实为 agent/planning.py；Fake 用 max(0,...)，Provider 不钳制。 |
| L-29 | brain.py:173-175 | 同 | Confirmed | asyncio.gather 无 return_exceptions=True。 |
| L-30 | brain.py:37-43 | 同 | Confirmed | 打码仅精确匹配 "command"，cmd/shell/script 等不命中。 |
| L-31 | brain.py:69,80-84 | 同 | Confirmed | brain 路径未做风险过滤，planner 路径做了。 |
| L-32 | brain.py:210-219 | 同 | Confirmed | 25ms 轮询实现取消，无事件驱动。 |
| L-33 | openai_compatible.py:181,184-188 | 同 | Confirmed | 畸形输出被静默 finalize。 |
| L-34 | context.py（全局） | contracts.py:47-49 / fake.py:31-32 / openai_compatible.py:73-75 | **Partial** | context.py 内无 provider.name 引用；Protocol 已显式声明 name；仅"name 值由具体类硬编码"成立。详见第二节。 |
| L-35 | diagnosis/coordinator.py:321-333 | 321-329 | Confirmed | 去重键只含 tool@version，忽略 arguments_hash。 |
| L-36 | diagnosis/coordinator.py:368-372 | 同 | Confirmed | 非完成工具的 error_code 可能为 None，输出"未完成：None"。 |

### 5.3 诊断 / 动作 / 任务（L-37 ~ L-43）

| 编号 | 报告行号 | 实际行号 | 判定 | 说明 |
|---|---|---|---|---|
| L-37 | coordinator.py:475 | 同（抛出点 543） | Confirmed | 证据校验失败抛 ValueError，被 _run 捕获转 internal_error。 |
| L-38 | actions/coordinator.py:275,283,291,299 | 同 | Confirmed | 四个适配器异常分支均 str(error) 直写 error_message。 |
| L-39 | actions/coordinator.py:184,236,247 | 同 | Confirmed | 动作 30s 窗口 vs 票据 120s TTL（consent.py:24），口径不一致。 |
| L-40 | diagnosis/ / tasks/ / actions/ | 同 | Confirmed | 三个编排模块位于 application/ 之外。 |
| L-41 | logging.py:69-75 | 同 | Confirmed | 仅 StreamHandler，无大小轮转。 |
| L-42 | server.py:53-63 | 同 | Confirmed | 启动失败 str(error) 打到 stderr。 |
| L-43 | composer.py:14,27 | 同 | Confirmed | _SEVERITY_RANK 直接字典取值，未知级别 KeyError。 |

### 5.4 Windows 适配器 / 工具（L-44 ~ L-50）

| 编号 | 报告行号 | 实际行号 | 判定 | 说明 |
|---|---|---|---|---|
| L-44 | diagnostics.py:90-101 | 同 | Confirmed | subprocess.TimeoutExpired 未被捕获翻译。 |
| L-45 | process_actions.py:160-166 | 同 | Confirmed | 多窗口逐个 PostMessage，失败时已部分关闭。 |
| L-46 | process_actions.py:197-202 | 同 | Confirmed | terminate 后 3s 未退出即误报失败。 |
| L-47 | startup_actions.py:148-158 | 同 | Confirmed | restore 信任磁盘 metadata，Run 键值名无白名单。 |
| L-48 | event_logs.py:221 | 同 | Confirmed | ISO8601 字符串字典序排序。 |
| L-49 | platform_inspection.py:269,273 | 同 | Confirmed | has_default_route 与 failures 语义不一致。 |
| L-50 | platform_inspection.py:65-73 | 同 | Confirmed | _basename 对未加引号含空格路径截断。 |

### 5.5 API 层（L-51 ~ L-63）

| 编号 | 报告行号 | 实际行号 | 判定 | 说明 |
|---|---|---|---|---|
| L-51 | middleware.py:37 | 同 | Confirmed | OPTIONS 跳过会话令牌校验（标准 CORS 行为，作为安全观察项）。 |
| L-52 | diagnoses.py:47,74 | 实际 74,87,92,100,113 | **Partial** | 行 47 的 start_diagnosis 无路径参数；核心问题属实，实际涉及 5 个端点。详见第二节。 |
| L-53 | diagnoses.py:143-145 | 同 | Confirmed | Content-Disposition 直接拼接 diagnosis_id。 |
| L-54 | diagnoses.py:46-50 | 同 | Confirmed | start_diagnosis 未接收 correlation_id 头。 |
| L-55 | diagnoses.py:57-64 | 同 | Confirmed | 列表端点 N+1 查询（每条 2 次额外查询）。 |
| L-56 | actions.py:33-44 | 同 | Confirmed | 除 action_not_found→404 外全部映射 409。 |
| L-57 | settings.py:82-84 | 同 | Confirmed | test_connection 未用 run_in_threadpool，同文件其他路由均用了。 |
| L-58 | agent_tasks.py:61-62 | 同 | Confirmed | AgentToolCallDto 暴露 provider_call_id。 |
| L-59 | diagnoses.py:108,110 | 同 | Confirmed | status/category 用裸 str。 |
| L-60 | diagnoses.py:155,160 | 同 | Confirmed | zip(strict=True) 长度不一致时未捕获。 |
| L-61 | actions.py:62-63,84 | 同 | Confirmed | 时间戳用裸 str，与其他 DTO 的 datetime 不一致。 |
| L-62 | actions.py:91-94 | 同 | Confirmed | process_candidate_response 移除 pid 字段。 |
| L-63 | app.py:28-37,60-95 | 同 | Confirmed | app.py 直接 import 并调用 infrastructure.bootstrap 工厂。 |

### 5.6 前端（L-64 ~ L-72）

| 编号 | 报告行号 | 实际行号 | 判定 | 说明 |
|---|---|---|---|---|
| L-64 | api-client.ts:140-141 | 实际 140 | Confirmed | done 时直接 break，残留 buffer 未 flush；偏差 ±1 行。 |
| L-65 | api-client.ts:131 | 同 | Confirmed | CRLF→LF 逐 chunk 归一化。 |
| L-66 | api-client.ts:186 | 同 | Confirmed | 204/空 body 时 response.json() 抛 SyntaxError 被误归 network_error。 |
| L-67 | api-client.ts:86-89 | 同 | Confirmed | download 错误未传 correlationId。 |
| L-68 | backend.ts:74 | 同 | Confirmed | 轮询用裸 setTimeout，未监听 abort signal。 |
| L-69 | diagnoses.ts:141-142 | 同 | Confirmed | revokeObjectURL 在 click() 后同步立即调用。 |
| L-70 | diagnoses.ts:131-143 | 同 | Confirmed | 服务层直接操作 DOM。 |
| L-71 | DiagnosisPanel.tsx:478 | 同 | Confirmed | 用字符串 item 作 React key，重复 limitation 产生 duplicate key。 |
| L-72 | ControlledActions.tsx:73 | 同 | Confirmed | 轮询退避用裸 setTimeout，未监听 controller.signal。 |

### 5.7 Rust Tauri（L-73 ~ L-83）

| 编号 | 报告行号 | 实际行号 | 判定 | 说明 |
|---|---|---|---|---|
| L-73 | sidecar.rs:310-323 | 同 | Confirmed | 进程崩溃后只标记 error，无自动恢复。 |
| L-74 | lib.rs:33 / tauri.conf.json:46-51 | 同 | Confirmed | updater 插件启用但 pubkey/endpoints 为空。**复核新发现**：bundle.createUpdaterArtifacts=false 与启用插件自相矛盾。 |
| L-75 | sidecar.rs:168-176 | 同 | Confirmed | main.rs:1 确有 windows_subsystem="windows" cfg_attr，release 下 eprintln! 丢失。 |
| L-76 | lib.rs:11-19 | 同 | Confirmed | restart_backend 立即返回 snapshot（必为 starting），存在并发竞态。 |
| L-77 | sidecar.rs:256-261 | 同 | Confirmed | shutdown 末尾无条件清 error=None。 |
| L-78 | sidecar.rs:420-426 | 同 | Confirmed | starts_with("HTTP/1.1 200") 前缀匹配，不严谨。 |
| L-79 | sidecar.rs:207-211,344-347 | 同 | Confirmed | 握手只校验自报 host；实际连接硬编码 127.0.0.1，安全影响有限。 |
| L-80 | sidecar.rs:496-529,119-144 | 同 | Confirmed | spawn(119)→AssignProcessToJobObject(522) 存在 TOCTOU 窗口。 |
| L-81 | tauri.conf.json:25 | 同 | Confirmed | connect-src 对 127.0.0.1 全端口放行。 |
| L-82 | sidecar.rs:243-254,256-261 | 同 | Confirmed | 2s 优雅关闭期间 snapshot 仍报 connected。 |
| L-83 | lib.rs:44-48 | 同 | Confirmed | ExitRequested 同步 shutdown 阻塞事件循环最多 2s。 |

### 5.8 测试 / 迁移 / 脚本（L-84 ~ L-96）

| 编号 | 报告行号 | 实际行号 | 判定 | 说明 |
|---|---|---|---|---|
| L-84 | conftest.py:36-38 | 同 | Confirmed | auth_headers fixture 内联明文 token。 |
| L-85 | test_action_async_boundary.py:16 | 同 | Confirmed | 基于 0.1s 绝对时间阈值。 |
| L-86 | test_agent_runtime.py:411-420 | 同 | Confirmed | 前向引用闭包变量 cancellation。 |
| L-87 | test_agent_runtime.py:297-306 | 同 | Confirmed | SSE 游标重连测试对流格式敏感。 |
| L-88 | test_event_logs.py:268 | 同 | Confirmed | 依赖 1 秒同步等待。 |
| L-89 | test_health.py:19 | 同 | **Partial** | 弱真值断言属实，但"放过空字符串"不成立（Python 空串 falsy）。详见第二节。 |
| L-90 | test_observability.py:13-14 | 同 | Confirmed | 全局 logger 原地替换 handlers 且未恢复；补充：该 logger 为专用命名 "sysmind.test.redaction"，非 root，污染面有限。 |
| L-91 | test_secrets.py:41-47 | 实际 41-45 | Confirmed | object.__new__ 绕过 __init__。 |
| L-92 | 0006:40 | 同 | Confirmed | actions.recovery_id 无 ForeignKey。 |
| L-93 | 0008:20-25 / 0007:20-28 | 同 | Confirmed | 建表后未播种初始行；补充：provider_settings 含非唯一 provider 列，"单例"定性偏弱。 |
| L-94 | test_packaged_desktop.py:68 | 同 | Confirmed | 硬编码 "0010_phase32"。 |
| L-95 | test_packaged_backend.py:61 | 同 | Confirmed | assert 做运行时非空判断，-O 下被剥离。 |
| L-96 | export-openapi.py:16 | 同 | Confirmed | 写死固定 session token。 |

### 5.9 Domain / Core / Ports（L-97 ~ L-108）

| 编号 | 报告行号 | 实际行号 | 判定 | 说明 |
|---|---|---|---|---|
| L-97 | diagnosis.py:109-111 / agent_tasks.py:34-38 | 同 | Confirmed | 预算上限 4 轮/8 次工具在两处重复定义。 |
| L-98 | diagnosis.py:42,73,83 | 同 | Confirmed | 三处 confidence 为裸 float，无 [0,1] 校验。 |
| L-99 | event_logs.py:65 | 同 | Confirmed | query 存为无类型 dict。 |
| L-100 | diagnosis.py:121 / agent_tasks.py:79,81 / actions.py:71 | 同 | Confirmed | 多处状态/风险级别用裸 str。 |
| L-101 | ports/actions.py:56-65 / diagnoses.py:29 | 同 | Confirmed | 端口 status 参数用裸 str。 |
| L-102 | ports/agent_tasks.py:77-88 vs diagnoses.py:97-108 | 同 | Confirmed | 两套 finish_tool_call 参数命名与顺序不一致。 |
| L-103 | ports/diagnostics.py:4,34,39 / platform_inspection.py:4 | 同 | Confirmed | 端口耦合 threading.Event。 |
| L-104 | ports/history.py:9-34 | 同 | Confirmed | 业务值对象定义在 ports 而非 domain。 |
| L-105 | ports/secrets.py:1 | 同 | Confirmed | 缺少 from __future__ import annotations，与其余 11 个 ports 不一致。 |
| L-106 | event_logs.py:16-19 | 同 | Confirmed | EventLogQuery 无正数/上限约束。 |
| L-107 | platform_inspection.py:59-62,76-80 | 同 | Confirmed | 计数字段与集合长度冗余。 |
| L-108 | domain/__init__.py:1 | 同 | Confirmed | docstring 仍称"Phase 0 无诊断域"，严重过时。 |

---

## 六、对原报告的修正建议清单

### 6.1 必须修正（行号/描述错误）

| 编号 | 修正类型 | 具体修正 |
|---|---|---|
| M-14 | 描述修正 | "并行执行路径"→"串行直调路径"；LogTools 形态从"{name: callable} 字典"改为"具名方法直调" |
| L-34 | 文件引用修正 | 引用文件从 `context.py` 改为 `agent/contracts.py:47-49` + 各 provider 实现；"隐式依赖"改为"name 值由具体类硬编码、无中央约束" |
| L-52 | 行号修正 | 行号从 `47,74` 改为 `74,87,92,100,113`（5 个实际有路径参数的端点） |
| L-89 | 描述修正 | "放过空字符串"→"未校验 UUID 格式，仅做真值断言"（空串在 Python 中为 falsy，会被 assert 拦截） |
| H-01 | 归属措辞修正 | "0008 历史清理按 retention_days DELETE FROM diagnoses"→"history.py:cleanup() 按 retention_days DELETE FROM diagnoses（0008 迁移仅建策略/审计表）" |

### 6.2 统计修正

- 概览中 Medium 数量从 33 改为 **31**（正文仅 M-01~M-31）
- Low 数量从 105 改为 **108**（正文 L-01~L-108）
- Info 数量从 6 改为 **0**（正文无 Info 章节），或补充缺失的 6 条 Info 发现
- 总数从 146 改为 **141**
- 各分片发现数合计（146）与正文实际列出数（141）不一致，需统一

### 6.3 重复发现标注

- **L-02 与 H-01 完全重复**：均指向动作外键缺 CASCADE。L-02 应标注"与 H-01 重复，合并"或降级为 Info。
- **L-07 与 L-11 同型**：均为 mark_interrupted 遗漏 waiting_user_input，分别在 diagnoses 和 agent_tasks 仓储。可合并为一条跨模块发现。

### 6.4 严重度评估

- 4 条 Partial 的核心问题均成立，严重度定级合理，无需调整。
- 无 False Positive，无需删除任何条目。

---

## 七、复核新发现

复核过程中在原报告之外发现的真实问题：

| # | 位置 | 问题 | 来源 |
|---|---|---|---|
| N-01 | `tauri.conf.json:34` | `bundle.createUpdaterArtifacts=false` 与已启用的 updater 插件（lib.rs:33）自相矛盾——启用了插件但不生成更新包，属无收益攻击面配置错误 | 复核 L-74 时发现 |
| N-02 | `tests/test_release_hardening.py:46` | `service._repository` 与报告标注的 84 行 `service._adapter` 同为运行时替换私有属性，原报告仅标注了后者 | 复核 M-29 时发现 |
| N-03 | `infrastructure/database/models.py:418,429,438` | user_confirmations、action_events、recovery_records 三个动作相关子表的外键同样无 ondelete，原报告 H-01/L-02 仅提及 action_plans 和 actions 两张表 | 复核 L-02 时发现 |

---

## 八、复核结论

1. **原报告整体准确性极高**：141 条显式发现中 137 条完全属实（97.2%），4 条部分属实（核心问题均成立，仅行号引用或描述细节有偏差），**零误报**。
2. **Top 问题因果链全部成立**：H-01（外键缺 CASCADE + foreign_keys=ON + 清理 DELETE）、H-02（握手无超时 + wait_until_ready 后置 + monitor 只 try_wait）、M-09（env override 在 release 守卫之前）经多文件交叉验证，因果链完整。
3. **原报告主要缺陷在自身统计**：声称 146 条但正文仅 141 条，Medium/Low/Info 计数均与正文不符，Info 6 条完全缺失。
4. **行号引用质量优秀**：除 L-52（行 47 引用错误）和 L-09/L-26（偏差 ≤2 行）外，其余全部精确命中。
5. **建议优先修正**：4 条 Partial 的描述/行号、统计数字、L-02 与 H-01 的重复标注。

---

## 九、终审修正：H-01 改判为 False Positive（二次独立可达性追溯）

> 本节由主代理在分片复核完成后，对唯一的 High 级争议项做删除路径全链路追溯后追加。分片 A 对 H-01 只验证了 Schema 层事实（FK 无 ondelete、其他子表有 CASCADE、foreign_keys=ON），**未验证"删除语句是否真的能到达该外键"**——而这才是它构不构成 BUG 的关键。追溯结论：**到达不了，H-01 不构成功能/架构 BUG，改判 False Positive（作为 BUG）/ 降级 Info（作为一致性备注）**。

### 9.1 全库删除点穷举

对后端源码全量 grep `delete(Diagnosis)` / `DELETE FROM diagnoses`，**仅有两处**会删除 diagnoses 行，且两处都有受控动作保护：

| 删除点 | 保护逻辑 | 结果 |
|---|---|---|
| `repositories/history.py:113`（单条手动删除） | 同事务 `_impact()` 后，line 108：`if impact is None or not impact.deletable or impact.revision != revision: return False`——SQL DELETE 不可达 | 受保护 |
| `repositories/history.py:182`（保留期清理） | line 165-176 先算 `protected_ids = 有 ActionPlan 的 diagnosis_id`，再 `deletable_diagnoses = [d for d in old if d not in protected_ids]`，line 182 只删可删集合 | 受保护 |

### 9.2 保护是四层显式设计，非巧合

1. **影响预览层** `repositories/history.py:80-99`：显式 `count(ActionPlanModel)`，有则 `protected="Diagnoses linked to controlled-action audit are retained."`，`DeletionImpact.deletable=False`。
2. **服务层** `application/services/history.py:31-32`：`if not impact.deletable: raise HistoryProtectedError(...)`，在调用仓储前拦截。
3. **仓储层** `repositories/history.py:108`：事务内二次校验 `not impact.deletable → return False`（TOCTOU 防护）。
4. **路由层** `api/routes/history.py:80-81`：`HistoryProtectedError → HTTP 409`（干净的业务拒绝，不是 500 IntegrityError 崩溃）。

### 9.3 有专门测试锁定该意图

`tests/test_history.py:92 test_action_linked_diagnosis_is_protected_from_delete_and_retention`：构造带 ActionPlan 的旧诊断，断言删除预览 `deletable is False`、`protected_reason` 含 "audit"、清理接口 `protected_records == 1`、清理后该诊断仍在。证明"不级联删除受控动作审计记录"是**刻意的审计留存设计**，无 ondelete 的外键是最后一道数据库级防线（defense-in-depth）。

### 9.4 对原报告三条具体后果的裁定

- 原称"历史保留清理遇到带受控动作的旧 diagnosis 直接失败/中止" → **不成立**：清理显式跳过并计入 protected_records，有测试。
- 原称"用户在历史页删除单条 diagnosis 会报错（IntegrityError）" → **不成立**：返回的是设计内的 409 + 明确文案，SQL 根本不执行，不会出现 IntegrityError。
- 原修复建议"三处外键改 ondelete=CASCADE 并新增迁移" → **有害，不应采纳**：级联删除会销毁受控动作审计/确认/事件链，直接违背审计留存设计。N-03 所列 user_confirmations/action_events/recovery_records 三表同理（它们指向 actions.id，actions 本身也不可删），同为刻意设计而非遗漏。

### 9.5 修正后的最终统计

| 判定 | 分片复核数 | 终审调整 | **最终数（141 条正文发现）** |
|---|---:|---|---:|
| Confirmed | 137 | H-01 移出 | **136** |
| Partial | 4 | — | **4** |
| False Positive | 0 | H-01 移入 | **1** |

- H-01 的 Schema 层观察（FK 未写 ondelete）本身**事实为真、行号精确**，但它不是 BUG：问题不可达、是刻意设计、有测试锁定。若希望代码自解释，可作为 **Info 级**建议（补注释说明"无 ondelete 是审计留存的最后防线"），而非 High/P0。
- 相应地，原报告"P0 阻塞发布第 1 项"撤销；真正的最高优先级为 **H-02（sidecar 握手无超时）** 与 **M-09（release env 覆盖，严重度 Low~Medium）**。
- L-02 与 H-01 同主题，一并按本结论处理（不构成 BUG）。
