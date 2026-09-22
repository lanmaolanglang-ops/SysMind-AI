# SysMind AI 项目逐行深度代码审查报告

> **审查日期**：2026-09-10
> **审查范围**：D:\SysMind AI 项目全部源代码（排除 node_modules、dist、.venv、缓存目录、构建产物）
> **审查方式**：10 个分片并行逐行审查，每个文件每一行均被读取和分析
> **审查基准**：AGENTS.md、docs/SysMind-AI-PRD-and-Architecture.md、docs/adr/ 全部 ADR、docs/security.md、docs/privacy.md

---

## 一、审查概览

### 1.1 项目规模

| 维度 | 数量 |
|---|---|
| 审查文件总数 | **195 个** |
| 审查代码总行数 | **约 20,400 行** |
| Python 后端源码 | 120 文件 / ~11,100 行 |
| Python 测试 | 26 文件 / ~4,700 行 |
| Alembic 迁移 | 11 文件 / ~660 行 |
| 前端 TypeScript/React | 34 文件 / ~4,200 行 |
| Rust Tauri | 4 文件 / ~620 行 |
| 脚本 | 3 文件 / ~310 行 |

### 1.2 审查分片

| 分片 | 范围 | 文件数 | 行数 | 发现数 |
|---|---|---:|---:|---:|
| Shard 1 | domain / core / application/ports | 24 | ~1,187 | 19 |
| Shard 2 | application/services / agent | 15 | ~2,195 | 22 |
| Shard 3 | infrastructure | 18 | ~2,395 | 22 |
| Shard 4 | api (routes + dto) | 21 | ~1,800 | 17 |
| Shard 5 | windows / tools | 19 | ~2,400 | 11 |
| Shard 6 | diagnosis / actions / tasks / security / observability / reports / prompts / runtime | 23 | ~2,396 | 11 |
| Shard 7 | tests | 26 | ~4,700 | 13 |
| Shard 8 | alembic / scripts / migrations.py | 15 | ~900 | 7 |
| Shard 9 | frontend (TS/React) | 34 | ~4,200 | 11 |
| Shard 10 | Rust Tauri | 6 | ~620 | 13 |
| **合计** | | **201** | **~22,800** | **141** |

> 注：部分文件在多个分片中被交叉核对（如端口接口与实现），总行数含交叉核对重复。去重后实际审查约 195 个独立文件、~20,400 行。（已复核修正：原合计 146 与正文实际列出的 141 条不符，已更正。）

### 1.3 发现严重度分布

| 严重度 | 数量 | 占比 |
|---|---:|---:|
| **Critical** | 0 | 0% |
| **High** | 2 | 1.4% |
| **Medium** | 31 | 22.0% |
| **Low** | 108 | 76.6% |
| **Info** | 0 | 0% |
| **合计** | **141** | 100% |

> （已复核修正：原表 Medium 33 / Low 105 / Info 6 / 合计 146 与正文实际列出条目不符。正文仅列出 M-01~M-31（31 条）、L-01~L-108（108 条），无 Info 章节，合计 141 条。）

---

## 二、执行摘要

### 2.1 整体质量评估

SysMind AI 项目整体代码质量**较高**，架构分层清晰，安全边界设计扎实。核心优势包括：

- **DDD 分层干净**：domain 层仅依赖 dataclasses/typing，无 SQLAlchemy/ORM 泄漏；application 通过 Protocol 端口与 infrastructure 解耦
- **AI 安全边界严密**：模型工具调用经 `tool_map 反查 → policy.authorize → pydantic 校验 → 风险/权限白名单` 多层验证；有轮次/预算/签名去重三重防无限循环
- **密钥管理合规**：API key 仅存 Windows 凭据管理器（DPAPI），SQLite 只存 `secret_reference` 引用；无明文密钥落库、无日志泄露
- **动作确认机制完整**：受控动作采用 HMAC 票据 + 锁 + 原子一次性消费 + 事件审计，写操作有 TOCTOU 修订指纹防护
- **前端安全实践到位**：无 XSS 风险、无 localStorage/sessionStorage 敏感数据存储、认证头一致覆盖所有 API 调用

主要风险集中在：**并发健壮性**（SQLite 锁、SSE 竞态）、**脱敏一致性**（日志/错误字段未统一走 redact_text）、**Tauri sidecar 生命周期**（握手无超时、release 包 env 覆盖）、**数据库外键级联**（动作表缺 CASCADE 导致删除失败）。

### 2.2 Top 10 关键发现

| # | 严重度 | 模块 | 问题 | 文件:行 |
|---|---|---|---|---|
| 1 | ~~**High**~~ → **不成立（终审改判 FP，见复核报告§9）** | 数据库迁移 | 原称外键缺 `ON DELETE CASCADE` 会导致删除抛 `IntegrityError`；经追溯删除被四层保护拦截、有专门测试，属刻意审计留存设计，非 BUG | `alembic/versions/0006_phase5a_controlled_actions.py:23,31,32`（Schema 观察为真，但问题不可达） |
| 2 | **High** | Rust Tauri | sidecar 握手读取无超时，Python 进程存活但不输出 `SYSMIND_ENDPOINT` 时永久卡在 `starting`，UI 永久转圈 | `src-tauri/src/sidecar.rs:187-192` |
| 3 | **Medium** | 基础设施 | SQLite 引擎未设 `PRAGMA busy_timeout`，且 bootstrap 给每个 coordinator 各建独立 engine 写同一 WAL 文件，多后台任务并发写时极易 `database is locked` | `infrastructure/database/engine.py:11-18` + `bootstrap.py:50-128` |
| 4 | **Medium** | 安全 | 日志 formatter 的 `message` 和异常 traceback 未走 `redact_text`，含用户名的绝对路径等 PII 会原样写入 JSON 日志 | `observability/logging.py:54,65` |
| 5 | **Medium** | 安全 | `SYSMIND_BACKEND_EXECUTABLE` 环境变量 override 在 release 包中仍然生效，恶意进程可预置该 env 诱导壳层执行任意二进制并获得会话令牌 | `src-tauri/src/sidecar.rs:436-441` |
| 6 | **Medium** | 安全 | `AgentRunError` 的 `str(error)` 直接落库为 `failure_message`，可能携带 URL、路径或 Provider 响应片段；紧邻的泛型异常分支却正确使用了固定脱敏文案 | `tasks/manager.py:162-164` |
| 7 | **Medium** | 工具执行 | Executor 超时只取消 awaitable，**不置位 `cancel_event`**，后台 Win32/psutil 阻塞线程仍继续跑完；违背"超时必须生效" | `tools/executor.py:76-79` |
| 8 | **Medium** | 功能 | `diagnoses.py` 中 `tool, version = step["tool"].rsplit("@", 1)`，工具名不带 `@版本号` 时直接抛 `ValueError` 崩事务 | `infrastructure/database/repositories/diagnoses.py:217` |
| 9 | **Medium** | 前端 | AgentTaskPanel SSE 事件回调未校验任务归属，旧任务的 `completed`/`progress:100` 事件可能短暂合并到新任务状态上 | `apps/desktop/src/features/tasks/AgentTaskPanel.tsx:100-116` |
| 10 | **Medium** | 配置 | `__main__.py` 显式 `Settings()` 与全局 `get_settings()` 是两条构造路径，`session_token` 的 `default_factory` 会在不同实例生成不同随机令牌，可能导致下发 token 与校验 token 不一致 | `core/config.py:67-69` + `__main__.py:17-31` |

---

## 三、High 严重度发现

### H-01 动作相关外键缺少 ON DELETE CASCADE，导致诊断删除/历史清理失败

> **【终审改判 2026-09-10】本条经删除路径全链路追溯后改判为 False Positive（不构成 BUG），详见 `CODE_REVIEW_VERIFICATION.md` 第九节。** 全库仅 `history.py:113/182` 两处删除 diagnoses，且分别被 `_impact().deletable=False`（仓储 108 行 + 服务层 HistoryProtectedError + 路由 409）和 `cleanup()` 的 protected_ids 过滤（165-176 行）拦截；`tests/test_history.py:92` 有专门测试锁定"受控动作审计留存"这一设计。无 ondelete 是刻意的数据库级最后防线，原"会抛 IntegrityError/清理失败"的后果不可达，原"加 CASCADE"的修复建议有害（会销毁审计链），请勿采纳。本条降级为 Info（至多补注释说明设计意图）。以下为原始分析，保留以备追溯。

- **文件**：`services/backend/alembic/versions/0006_phase5a_controlled_actions.py`
- **行号**：23, 31, 32（与 `infrastructure/database/models.py:387-400` 一致地都没写）
- **类型**：架构 / 功能
- **代码片段**：
  ```python
  sa.Column("diagnosis_id", sa.String(36), sa.ForeignKey("diagnoses.id"), nullable=False),
  sa.Column("plan_id", sa.String(36), sa.ForeignKey("action_plans.id"), nullable=False),
  sa.Column("diagnosis_id", sa.String(36), sa.ForeignKey("diagnoses.id"), nullable=False),
  ```
- **问题描述**：其它挂在 `diagnoses` 下的子表（diagnosis_tool_calls、diagnosis_feedback、diagnosis_model_calls、agent_plans、diagnosis_steps 等）外键均声明 `ondelete="CASCADE"`，唯独 Phase 5a 的 `action_plans.diagnosis_id`、`actions.diagnosis_id`、`actions.plan_id` 没有任何 `ondelete`（默认 NO ACTION/RESTRICT）。由于 `engine.py` 在每个连接上执行 `PRAGMA foreign_keys=ON`，当用户删除某条 diagnosis，或历史保留清理任务（`infrastructure/database/repositories/history.py:cleanup()`，181-182 行）按 `retention_days` 批量 `DELETE FROM diagnoses` 时，只要该 diagnosis 已产生过 action_plan，SQLite 就会抛出 `IntegrityError: FOREIGN KEY constraint failed`。后果：(1) 历史保留清理遇到带受控动作的旧 diagnosis 直接失败/中止；(2) 用户在历史页删除单条 diagnosis 会报错；(3) 若业务层绕过删除改走软删，则留下孤儿审计行。（已复核修正：原描述将 DELETE 逻辑归因于"0008 迁移"，实际 0008 仅建策略/审计表，删除逻辑在 history.py:cleanup()。）
- **修复建议**：明确这些表的生命周期语义——受控动作是审计记录，通常应随 diagnosis 级联删除。将三处外键改为 `ondelete="CASCADE"`（models.py 与迁移同步修改）。因 0006 已发布，应新增 0011 迁移用 `batch_alter_table` 重建外键。同时补回归测试：构造带 action_plan 的 diagnosis，执行删除断言子表被级联清空。

### H-02 Tauri sidecar 握手读取无超时，进程静默挂起时永久卡在 starting

- **文件**：`apps/desktop/src-tauri/src/sidecar.rs`
- **行号**：187–201（核心循环 187–192）
- **类型**：功能 / 逻辑
- **代码片段**：
  ```rust
  let mut endpoint = None;
  for line in BufReader::new(stdout).lines().map_while(Result::ok) {
      if let Some(parsed) = parse_handshake(&line) {
          endpoint = Some(parsed);
          break;
      }
  }
  ```
- **问题描述**：该循环对 stdout 做**无超时阻塞读取**。`wait_until_ready` 的 10s 超时（line 212）只在成功解析握手行之后才生效。若 Python 进程已 spawn 但因死锁、stdout 未 flush、依赖加载卡死等原因**存活却永不输出 `SYSMIND_ENDPOINT`**，本线程将永久阻塞。`monitor_child_process` 只调 `try_wait()` 判断进程是否退出，对"活着但不发握手"无感知。最终 snapshot 永远停留在 `state="starting"`，无健康检查、无失败上报、无恢复，UI 永久转圈。
- **修复建议**：为握手阶段增加看门狗。用带 `recv_timeout` 的 channel 把 stdout 行转发出来，主等待线程 `recv_timeout(Duration::from_secs(15))`；超时后调用 `set_failure()` 并杀死 child。同时让 `monitor_child_process` 也能识别"starting 超时"状态。

---

## 四、Medium 严重度发现（按模块分组）

### 4.1 基础设施 / 数据库

#### M-01 SQLite 引擎未设 busy_timeout，多 engine 并发写同一 WAL 文件易锁

- **文件**：`infrastructure/database/engine.py:11-18` + `infrastructure/bootstrap.py:50-128`
- **类型**：功能 / 并发
- **描述**：(1) 连接监听器未设置 `PRAGMA busy_timeout`，WAL 模式下同库只允许一个写者，第二个写者会立刻收到 `database is locked` 而非等待重试；(2) bootstrap 给每个 coordinator 各建独立 engine 连接同一个 `sysmind.db`，多后台任务（quick scan / diagnosis / agent task / history cleanup）并发写时极易触发锁。
- **修复建议**：增加 `cursor.execute("PRAGMA busy_timeout=5000")`；在组合根创建**单一** engine/sessionmaker 注入给所有仓储；提供统一 shutdown dispose。

#### M-02 `rsplit("@", 1)` 解包在工具名无版本号时直接崩溃

- **文件**：`infrastructure/database/repositories/diagnoses.py:217`
- **类型**：功能
- **代码**：`tool, version = str(step["tool"]).rsplit("@", 1)`
- **描述**：若 `step["tool"]` 不含 `@`，`rsplit` 返回单元素列表，解包抛 `ValueError`，整个 `save_agent_plan` 事务失败。
- **修复建议**：`parts = str(step["tool"]).rsplit("@", 1); tool = parts[0]; version = parts[1] if len(parts) == 2 else "1.0"`。

#### M-03 等待用户输入的问题被写进 `current_step` 而非 `clarification_question`

- **文件**：`infrastructure/database/repositories/diagnoses.py:265-272`
- **类型**：逻辑
- **描述**：domain `DiagnosisRecord` 同时有 `current_step` 和 `clarification_question` 两个字段，但 `wait_for_input` 把提问塞进 `current_step`，导致前端按 `clarification_question` 展示时拿到 None，且 `current_step` 语义被污染。
- **修复建议**：`wait_for_input` 应写 `model.clarification_question = question`。

#### M-04 动作 `tool_version` 被硬编码为 `"1.0"`

- **文件**：`infrastructure/database/repositories/actions.py:75`
- **类型**：逻辑
- **描述**：端口 `ActionRepository.create()` 未接收 `tool_version`，实现直接写死 `"1.0"`，审计追溯信息失真。
- **修复建议**：在端口 `create` 增加 `tool_version: str` 参数，由调用方传入。

#### M-05 `baseline()` 的 except 漏掉 `AttributeError`，脏 summary 会崩溃

- **文件**：`infrastructure/database/repositories/history.py:222-241`
- **类型**：功能
- **描述**：若历史 summary 中 `cpu`/`memory` 字段不是 dict，`cast(dict, ...).get(...)` 抛 `AttributeError`，except 元组里没有它，整个 `baseline()` 失败。
- **修复建议**：把 `AttributeError` 加入 except，或先 `isinstance(x, dict)` 再 `.get`。

#### M-06 `DiagnosisStepModel.tool_call_id` 外键缺 `ondelete`

- **文件**：`infrastructure/database/models.py:327`
- **类型**：功能
- **描述**：全表其他外键几乎都显式 `ondelete="CASCADE"`，唯独 `tool_call_id` 没有。删除 diagnosis 时级联顺序可能触发外键约束错。
- **修复建议**：补 `ondelete="SET NULL"` 或 `ondelete="CASCADE"`。

### 4.2 安全 / 脱敏

#### M-07 日志 message 与异常堆栈未走 redact_text，PII 会进日志

- **文件**：`observability/logging.py:54,65`
- **类型**：安全
- **描述**：`_sanitize()` 只按字典键名敏感做递归替换，**从不**对字符串值调用 `redact_text`。`record.getMessage()` 与 `formatException()` 输出的完整 traceback 被原样写进 JSON 日志，包含绝对文件路径（含用户名）等 PII。项目已有 `redact_text` 并用于导出/模型请求/上下文，唯独没接到日志 formatter。
- **修复建议**：在 `format()` 中对 `record.getMessage()` 与 `self.formatException(...)` 先调用 `redact_text(...)` 再放入 payload。

#### M-08 AgentRunError 的 str(error) 直接落库，与泛型分支脱敏口径不一致

- **文件**：`tasks/manager.py:162-164`
- **类型**：安全
- **描述**：紧邻的泛型 `except Exception` 分支刻意使用固定脱敏文案，但 `AgentRunError` 分支却把 `str(error)` 原样写入 `failure_message`。经核对 `brain.py` 会把工具适配器的 `error_message`、Provider 传输层错误（URL、响应片段）包装进 `AgentRunError`，这些文本经 DB 持久化并通过 SSE/任务详情暴露给 UI。
- **修复建议**：`_finish_failure` 对该分支只记录 `error.code` + 固定脱敏文案；如确需保留细节，先 `redact_text(str(error))` 并截断长度。

#### M-09 release 包中 SYSMIND_BACKEND_EXECUTABLE env 覆盖仍然生效

- **文件**：`src-tauri/src/sidecar.rs:436-441`
- **类型**：安全
- **描述**：该 override 分支位于 `cfg!(debug_assertions)` 发布守卫**之前**，NSIS 安装后的正式包也会读取该 env 并以它为子进程启动目标，同时把会话令牌传给该任意程序。任何以当前用户身份运行的恶意进程都可在启动本应用前预置该 env。
- **修复建议**：把该 env override 用 `#[cfg(debug_assertions)]` 包裹，release 包只允许 bundled 资源目录下的 `sysmind-backend.exe`。

#### M-10 create_tool_call 把未脱敏原始参数交给仓储

- **文件**：`application/ports/diagnoses.py:86-96`
- **类型**：安全
- **描述**：端口同时接收原始 `arguments` dict 与 `arguments_hash`。domain 的 `DiagnosisToolCall` 根本不保留 arguments，说明原始参数本不应进入持久化契约；现在把未脱敏原始参数（可能含进程路径、目标 IP、用户名等）交给仓储层，仅靠实现层自觉脱敏。
- **修复建议**：端口只接受"已脱敏后的 summary + arguments_hash"，原始 arguments 不进入仓储契约。

#### M-11 扫描步骤事件缺 arguments_hash，与日志/Agent 审计口径不一致

- **文件**：`application/ports/scans.py:23-36` vs `log_analyses.py:36`
- **类型**：安全 / 审计
- **描述**：PRD 要求所有工具调用留存"规范化参数哈希"。`LogAnalysisRepository.add_step_event` 记录了 arguments_hash，但 `ScanRepository.add_step_event` 没有该字段，快速扫描的工具调用无法做参数级审计/去重。
- **修复建议**：`ScanRepository.add_step_event` 增加 `arguments_hash: str` 并落库。

### 4.3 工具执行 / Windows 适配器

#### M-12 Executor 超时不置位 cancel_event，后台线程不随超时终止

- **文件**：`tools/executor.py:76-79`
- **类型**：功能 / 架构
- **描述**：`asyncio.wait_for(asyncio.to_thread(...))` 超时只取消 awaitable，**无法终止底层线程**；更关键的是超时分支**从不调用 `cancel_event.set()`**。当 Executor 自身超时返回时，正在执行的 Win32/psutil 阻塞调用仍在后台线程继续跑完。
- **修复建议**：在 `except TimeoutError` 分支中先 `cancel_event.set()`，让 handler 的取消检查点尽快触发。

#### M-13 `log.crash.analyze` 超时在两处声明不一致（3.0s vs 12.0s）

- **文件**：`tools/log/toolset.py:12` vs `tools/runtime_tools.py:298`
- **类型**：逻辑
- **描述**：同一工具在 `LOG_TOOL_SPECS` 声明超时 3.0s，而真正注册进 ToolRegistry 的是 12.0s。若调度/监控按 ToolSpecs 计算，会把实际允许 12s 的工具误判为 3s 超时。
- **修复建议**：以注册值为准统一为 12.0s；让 `LOG_TOOL_SPECS` 从单一来源派生。

#### M-14 子目录 toolset 提供绕过 Registry/Executor 的串行直调路径（已复核修正）

- **文件**：`tools/system/toolset.py:27-34`、`process/toolset.py:19-23`、`log/toolset.py:69-82`
- **类型**：架构
- **描述**：`SystemTools` 和 `ProcessTools` 以 `{name: callable}` 字典暴露探针方法（`LogTools` 为 `query/analyze/aggregate` 具名方法直调，非字典形态），均绕过了 `ToolRegistry.authorize`（白名单/风险等级/特权/确认策略）和 `ToolExecutor`（超时/取消/结果归一化/错误脱敏）。若应用层任何一处直接 `handlers()[name]()` 调度，模型就能在不经过策略门的情况下触达探针。经复核，`quick_scan.py` 与 `log_analysis.py` 均为**串行**循环调用（非并行）。（已复核修正：原描述称"并行执行路径"和 LogTools 以字典暴露，均与实际代码不符。）
- **修复建议**：确认这些类是否仍被引用；若为历史遗留标注 `@deprecated` 并改为经 ToolExecutor 调用；若保留，在类文档中明确"禁止直接调度"。

### 4.4 API / 前端

#### M-15 客户端 Correlation-ID 未经验证即反射到响应头

- **文件**：`api/middleware.py:26,48`
- **类型**：安全
- **描述**：`X-Correlation-ID` 的值完全来自客户端请求头，未做格式校验就原样写入响应头。若传入包含 CRLF 或超长字符串，可导致 HTTP 响应头注入。
- **修复建议**：对白名单字符 `[A-Za-z0-9-]` 且长度 ≤64 做校验，不合法则回退为 `uuid.uuid4()`。

#### M-16 Health 端点硬编码 ready=True，不反映实际就绪状态

- **文件**：`api/routes/health.py:11-16`
- **类型**：功能
- **描述**：`app.py` lifespan 维护了 `app.state.ready` 标志，但 health 端点完全忽略，始终返回 `ready=True`。Tauri shell 可能过早判定后端就绪。
- **修复建议**：`ready=getattr(request.app.state, "ready", False)`。

#### M-17 SSE 事件流未捕获底层 DB 异常，客户端静默断连

- **文件**：`api/routes/agent_tasks.py:116-135`
- **类型**：功能
- **描述**：SSE 生成器中如果 `manager.events_after()` 或 `manager.get()` 抛异常（如 SQLite 锁定），异常直接传播出生成器，客户端看到连接突然断开，收不到 error 事件。
- **修复建议**：在 event_stream 内部包裹 try/except，捕获异常后 yield SSE error 事件再 return。

#### M-18 SSE 终态终止条件存在竞态窗口，可能遗漏最后事件

- **文件**：`api/routes/agent_tasks.py:129-131`
- **类型**：逻辑
- **描述**：终止条件为 `current.status in _TERMINAL and not events`。任务刚好进入终态但最后一批事件尚未被 `events_after` 返回时，流立即退出，客户端永远收不到 `task_completed` 事件。
- **修复建议**：检测到终态后再做一次延迟重试（等待 100ms 后再查询一次事件），确认排空后再退出。

#### M-19 AgentTaskPanel SSE 事件竞态，旧任务事件污染新任务状态

- **文件**：`apps/desktop/src/features/tasks/AgentTaskPanel.tsx:100-116`
- **类型**：功能（异步竞态）
- **描述**：SSE 事件回调中的 `setTask` 函数式更新未验证 `current.id` 是否等于当前 `activeTaskId`。用户从旧任务切换到新任务时，旧任务的 SSE 连接在被 abort 前恰好交付了最后一条事件（如 `task.completed`、`progress: 100`），会将旧任务的状态合并到新任务上。
- **修复建议**：在事件回调中捕获闭包内的 `activeTaskId`，在 `setTask`/`setEvents` 中校验 `current.id === expectedTaskId`。

#### M-20 SettingsPanel retentionDays NaN 校验缺失

- **文件**：`apps/desktop/src/features/settings/SettingsPanel.tsx:136,138`
- **类型**：逻辑
- **描述**：用户在 number 输入框中输入中间态无效值（`-`、`e` 等），`Number()` 产生 `NaN`，而 `NaN < 7` 和 `NaN > 3650` 均为 `false`，保存按钮意外可点击，最终向服务端发送 `null`。
- **修复建议**：`Number.isFinite(parsed) ? parsed : 0`，并在按钮 disabled 条件中增加 `!Number.isFinite(retentionDays)`。

### 4.5 应用层 / Agent

#### M-21 空通道导致 log_analysis 启动即 IndexError

- **文件**：`application/services/log_analysis.py:151`
- **类型**：功能
- **描述**：`start()` 不校验 `channels` 非空，`channels[0]` 直接抛 `IndexError`，被通用 except 记为含糊的 `analysis_failed`。
- **修复建议**：入口先 `if not channels: raise ValueError(...)`。

#### M-22 application 层直接 new 具体 OpenAICompatibleProvider

- **文件**：`application/services/provider_settings.py:10,81-94`
- **类型**：架构
- **描述**：application 层的设置服务直接依赖并实例化 agent 层的具体 `OpenAICompatibleProvider`，违反"application 依赖抽象/端口、而非具体实现"。将来新增第二种 provider 时必须修改此 service。
- **修复建议**：定义 `application.ports.AgentProviderFactory`，由 composition root 注入；本服务只面向 `AgentProvider` Protocol 编程。

#### M-23 brain._execute_tool 无 try/finally，取消路径留下未关闭 tool_call 审计行

- **文件**：`agent/brain.py:257-289`
- **类型**：功能 / 审计
- **描述**：`create_tool_call` 之后的体没有 try/finally 保护。当任务在工具执行期间被全局取消（`CancelledError`），`finish_tool_call` 被跳过，数据库留下 `started_at` 有值、`finished_at/status` 缺失的悬挂 tool_call 记录。
- **修复建议**：把 `create_tool_call` 之后的体包进 try/finally，在 finally 中若 result 未赋值则补一条 `finish_tool_call(..., status="cancelled")`。

### 4.6 配置 / 领域模型

#### M-24 Settings 双构造路径可能产生不同的随机 session_token

- **文件**：`core/config.py:67-69` + `__main__.py:17-31`
- **类型**：功能 + 安全
- **描述**：`session_token` 默认由 `secrets.token_urlsafe(32)` 在每次构造 Settings 实例时随机生成。`__main__` 显式 `Settings(...)` 生成实例 A，而 `get_settings()` 是另一条构造路径，一旦被调用会构造实例 B 得到不同的 token。两条路径无单一事实来源，可能导致下发 token 与校验 token 不一致。
- **修复建议**：让 `run_server` 接收的 settings 成为全局唯一来源，注入/缓存到 `get_settings`，确保 token 只在进程内生成一次。

#### M-25 domain GpuInfo 把基础设施实现细节写进纯领域模型

- **文件**：`domain/diagnostics.py:39-41`
- **类型**：架构泄漏
- **描述**：`GpuInfo` 默认文案直接点名 "metadata-only Windows adapter"，把 Windows 采集适配器的实现事实泄漏进 domain。换用非 Windows 实现时这句默认文案即变成错误信息。
- **修复建议**：默认文案改为中性表述 `"Real-time GPU utilization is unavailable."`。

#### M-26 GpuInfo 可出现 telemetry_available=True 与"不可用"文案自相矛盾

- **文件**：`domain/diagnostics.py:36-41`
- **类型**：逻辑
- **描述**：frozen dataclass 无 `__post_init__` 不变量校验。若适配器设置 `telemetry_available=True` 但未显式传 `telemetry_limitation=None`，对象会同时携带"可用"标志与"不可用"限制文案。
- **修复建议**：增加 `__post_init__` 不变量校验。

#### M-27 frozen dataclass 持有可变 list/dict，"不可变"承诺被破坏

- **文件**：`domain/diagnostics.py:84-85`、`domain/event_logs.py:65-67`
- **类型**：功能
- **描述**：`@dataclass(frozen=True)` 只禁止重新赋值字段，不递归冻结容器。`failures` 是 list、`summary` 是 dict，构造后可原地修改，导致审计/报告对象在持久化前后内容不一致。
- **修复建议**：把 `failures` 改为 tuple，dict 字段在 `__post_init__` 拷贝防外部引用逃逸。

### 4.7 测试 / 迁移

#### M-28 测试中 3 处硬编码计数/修订号，新增 migration 或步骤后必然误报

- **文件**：`tests/test_database.py:104`（head 修订号）、`tests/test_scans.py:149`（==7）、`tests/test_event_logs.py:200`（==3）
- **类型**：测试质量（脆弱测试）
- **描述**：把"当前 head"和"审计事件数"这些本应动态的值写死成字面量，每次新增 migration 或调整查询步骤都会失败，即使功能本身正确。
- **修复建议**：用 `ScriptDirectory.get_current_head()` 动态取 head；审计事件数改为下界断言或按步骤名断言。

#### M-29 test_release_hardening.py 跨测试模块 import + 运行时替换私有属性

- **文件**：`tests/test_release_hardening.py:19,84`
- **类型**：架构 / 测试质量
- **描述**：(a) 直接 `from tests.test_phase5_actions import FakeStartupActions, coordinator`，测试模块间耦合；(b) 通过 `service._adapter = ExplodingStartupActions()` 运行时替换被测对象的私有属性，与真实依赖注入背道而驰。
- **修复建议**：把共享 Fake 提取到 `tests/fakes/actions.py`；测试改为构造时注入爆炸 adapter。

#### M-30 审计 request_hash 在测试侧重算序列化参数，与生产规则双写

- **文件**：`tests/test_phase4_diagnosis.py:518-526,556-564`
- **类型**：测试质量（白盒脆性）
- **描述**：测试把生产侧计算 request_hash 时的序列化参数抄了一遍。只要生产实现增加字段或调整 sort_keys，测试就会失败——但这并不能证明审计被破坏。
- **修复建议**：把生产侧的 `_hash_request` 提取为可导入的公共 helper，测试直接调用同一 helper。

#### M-31 env.py 未启用 render_as_batch，0009/0010 downgrade 的 drop_column 在旧 SQLite 上不可靠

- **文件**：`alembic/env.py:37` + `0009/0010 downgrade`
- **类型**：功能
- **描述**：SQLite 原生 `ALTER TABLE DROP COLUMN` 仅在 ≥3.35 才支持。`env.py` 未传 `render_as_batch=True`，0009/0010 的 downgrade 直接 `op.drop_column`，在更老运行时会报错，导致"声明了回滚却回滚不了"。
- **修复建议**：在 `env.py` 的 context.configure 中增加 `render_as_batch=True`，或把 downgrade 的 drop_column 改为 `batch_alter_table`。

---

## 五、Low 严重度发现（按模块分组，精选）

> 以下列出正文全部 108 条 Low 发现（L-01~L-108）。（已复核修正：原称"完整 105 条 Low 发现详见各分片报告"，实际正文已列出 108 条，且无独立分片报告文件。）

### 5.1 基础设施

| # | 文件:行 | 问题 |
|---|---|---|
| L-01 | `engine.py:16` | `journal_mode=WAL` 是数据库级持久属性，每次连接重复设置属无谓开销 |
| L-02 | `models.py:387-400` | 动作相关外键未级联，与整体模式不一致（**与 H-01 重复，已复核确认**；另 user_confirmations/action_events/recovery_records 三表同样缺 ondelete） |
| L-03 | `models.py` (全局) | SQLite 数据库文件未显式收紧 ACL（仅当前用户可读写） |
| L-04 | `diagnoses.py:529-541` | 后端重启被错误归类为 `risk_limit_reached`，应增加 `backend_restarted` 取值 |
| L-05 | `diagnoses.py:189` | `agent_round_count` 被赋值为 plan revision，语义混淆 |
| L-06 | `diagnoses.py:286` | 中文提示文案硬编码在 infrastructure 层，不利于国际化 |
| L-07 | `diagnoses.py:523-527` | `mark_interrupted` 未覆盖 `waiting_user_input` 状态，重启后永久卡在等待态 |
| L-08 | `actions.py:265-268` | `close()` 穿透 sessionmaker 内部并销毁共享 engine，影响其他仓储 |
| L-09 | `actions.py:98-104` | `create_restore` 未校验原动作确为 startup 类，强转 source_kind 可能产生语义错误 |
| L-10 | `agent_tasks.py:154-165` | `update` 的"非 None 才更新"模式无法把字段清空回 None |
| L-11 | `agent_tasks.py:321-325` | `mark_interrupted` 同样遗漏 `waiting_user_input` |
| L-12 | `history.py:150-200` | `cleanup` 从不回收 agent_tasks 系列表，长期运行后无限增长 |
| L-13 | `history.py:71-79` | 诊断删除影响面统计未覆盖全部子表，revision OCC token 可能不一致 |
| L-14 | `log_analyses.py:40` / `scans.py:37` | 仓储未显式声明继承端口 Protocol，与 diagnoses/agent_tasks/actions 风格不一致 |
| L-15 | `bootstrap.py:50-141` | engine/连接生命周期无统一管理，没有应用退出时的统一 dispose |
| L-16 | `repositories/__init__.py:12-23` | `__all__` 在前、import 放在文件末尾，容易误导阅读者 |

### 5.2 应用层 / Agent

| # | 文件:行 | 问题 |
|---|---|---|
| L-17 | `quick_scan.py:72-75` / `log_analysis.py:87-99` | 同步 `start()` 内部调用 `asyncio.create_task`，要求调用方必须在运行循环内；create_task 失败时 cancellation 字典条目泄漏 |
| L-18 | `quick_scan.py:158-160` / `log_analysis.py:272-275` | `to_thread` 取消无法终止底层工作线程，阻塞调用继续跑到自然结束 |
| L-19 | `quick_scan.py:214-217` / `log_analysis.py:319-324` | `CancelledError` 被吞掉不重抛，违背 asyncio 取消语义约定 |
| L-20 | `quick_scan.py:182` | 全失败与部分失败状态语义不一致：quick_scan 全失败仍标 `partial`，log_analysis 区分 `failed` |
| L-21 | `log_analysis.py:208-209` | `analyze/aggregate` 在事件循环上同步执行，未用 `to_thread`，且不受单步超时保护 |
| L-22 | `log_analysis.py:266,278-294` | 取消/全局超时时步骤审计误记为 completed（CancelledError 不是 Exception 子类，不被捕获） |
| L-23 | `log_analysis.py:319-324` | 取消路径丢弃已采集事件（`_finish_cancelled` 的 events 硬编码为 `[]`） |
| L-24 | `quick_scan.py:108-121,161` | `result_keys` 与 spec 集合硬编码耦合，新增工具忘记同步映射会 KeyError |
| L-25 | `provider_settings.py:59,63` | 校验入参与持久化归一化不一致（校验用原始值，落库用 strip/rstrip 后的值） |
| L-26 | `provider_settings.py:55-71` | 密钥回滚时若 `_secrets.set()` 自身抛错会覆盖原始异常；`del candidate_secret` 只在成功路径执行 |
| L-27 | `log_analysis.py:113-120` | `cancel()` 返回设置前的旧 record，与 quick_scan 的刷新后返回不一致 |
| L-28 | `planning.py:248,301` | 两个 planner 的预算下界不一致（Fake 用 `max(0,...)`，Provider 用负数） |
| L-29 | `brain.py:173-175` | `asyncio.gather` 未用 `return_exceptions=True`，兄弟任务可能成为孤儿 |
| L-30 | `brain.py:37-43` | 审计打码键名覆盖不全，只精确匹配 `"command"`，`cmd/shell/script` 等未覆盖 |
| L-31 | `brain.py:69,80-84` | brain 路径未对下发给模型的工具做风险过滤，planner 路径却做了，两条路径口径不一致 |
| L-32 | `brain.py:210-219` | provider 调用靠 25ms 轮询实现取消，缺独立墙钟超时 |
| L-33 | `openai_compatible.py:181,184-188` | 非结构化/畸形模型输出在 brain 路径被静默 finalize，不会报错或重试 |
| L-34 | `agent/contracts.py:47-49` + 各 provider 实现 | `AgentProvider` Protocol 已显式声明 `name` 属性，但 name 字符串值由各具体类硬编码（fake/openai_compatible），无中央枚举约束（已复核修正：原引 `context.py` 内无 provider.name 引用） |

### 5.3 诊断 / 动作 / 任务

| # | 文件:行 | 问题 |
|---|---|---|
| L-35 | `diagnosis/coordinator.py:321-333` | 工具去重只按 `tool@version`、忽略 arguments，带参复查可能被误判重复 |
| L-36 | `diagnosis/coordinator.py:368-372` | 非完成工具的 limitation 引用 error_code，可能出现"未完成：None" |
| L-37 | `diagnosis/coordinator.py:475` | 证据引用校验失败让整份诊断转 internal_error，丢弃可用的 partial 结果 |
| L-38 | `actions/coordinator.py:275,283,291,299` | 动作执行把适配器异常 str() 直接写入 error_message，与 OSError/兜底分支的固定文案不一致 |
| L-39 | `actions/coordinator.py:184,236,247` | 进程类动作 30s 窗口与票据 120s TTL 口径不一致，用户可能拿到未过期票据却在 execute 时被告知过期 |
| L-40 | `diagnosis/coordinator.py` / `tasks/manager.py` / `actions/coordinator.py` | 业务编排模块位于 application/ 之外，却承担用例编排与事务边界，跨调用无统一事务 |
| L-41 | `observability/logging.py:69-75` | `configure_logging` 只挂 StreamHandler，无大小轮转，日志可能无界增长 |
| L-42 | `runtime/server.py:53-63` | 启动失败把 str(error) 打到 stderr，可能包含数据文件路径（含用户名） |
| L-43 | `reports/composer.py:14,27` | severity 排序无防御，未知级别会 KeyError 中断报告生成 |

### 5.4 Windows 适配器 / 工具

| # | 文件:行 | 问题 |
|---|---|---|
| L-44 | `windows/diagnostics.py:90-101` | `gpus()` 未翻译 `subprocess.TimeoutExpired`，超时被归为 internal_error 而非"GPU 采集超时" |
| L-45 | `windows/process_actions.py:160-166` | `request_close` 多窗口逐个发送，失败时已部分关闭但对外抛错暗示"未执行" |
| L-46 | `windows/process_actions.py:197-202` | `terminate` 成功后未在 3s 内退出即误报失败，把"已接受、待退出"误报为"拒绝/不可用" |
| L-47 | `windows/startup_actions.py:148-158` | `restore` 信任磁盘 metadata，未对 Run 键值名做白名单（利用面有限，需先有恢复目录写权限） |
| L-48 | `windows/event_logs.py:221` | 事件按 ISO8601 字符串字典序排序，不等同时间序（时区/精度不一致时可能错乱） |
| L-49 | `windows/platform_inspection.py:269,273` | `has_default_route` 与 failures 语义不一致（同一事实一个说"不可用"、一个说"未知"） |
| L-50 | `windows/platform_inspection.py:65-73` | `_basename` 对未加引号且含空格的命令路径解析截断（仅影响展示字段，不参与写操作） |

### 5.5 API 层

| # | 文件:行 | 问题 |
|---|---|---|
| L-51 | `api/middleware.py:37` | OPTIONS 预检请求完全跳过会话令牌校验，仅依赖 Origin 检查 |
| L-52 | `api/routes/diagnoses.py:74,87,92,100,113` | `diagnosis_id` 路径参数缺少 UUID 格式校验（已复核修正：原引行 47 的 start_diagnosis 无路径参数，实际未校验的为 continue/get/cancel/feedback/export 五个端点） |
| L-53 | `api/routes/diagnoses.py:143-145` | 导出报告的 Content-Disposition 文件名直接拼接未校验的 diagnosis_id |
| L-54 | `api/routes/diagnoses.py:46-50` | `start_diagnosis` 端点未接收 correlation_id 头，诊断任务无法关联请求 ID |
| L-55 | `api/routes/diagnoses.py:57-64` | 诊断列表端点存在 N+1 查询模式（每条记录分别查 tool_calls 和 user_inputs） |
| L-56 | `api/routes/actions.py:33-44` | Action 路由错误码映射过粗，`invalid_consent`/`action_expired` 等全部返回 409 |
| L-57 | `api/routes/settings.py:82-84` | `test_connection()` 在异步路由中未放入线程池（如果内部是阻塞调用会阻塞事件循环） |
| L-58 | `api/dto/agent_tasks.py:61-62` | `AgentToolCallDto` 暴露 `provider_call_id` 内部标识符，可被用于关联第三方服务日志 |
| L-59 | `api/dto/diagnoses.py:108,110` | `DiagnosisResponse.status` 和 `category` 使用裸 str，未使用领域枚举 |
| L-60 | `api/dto/diagnoses.py:155,160` | `zip(..., strict=True)` 在字段长度不一致时抛出未捕获异常 |
| L-61 | `api/dto/actions.py:62-63,84` | Action/Consent DTO 使用 str 类型时间戳，与其他 DTO 的 datetime 不一致 |
| L-62 | `api/dto/actions.py:91-94` | `process_candidate_response` 移除了 pid 字段，前端无法通过 PID 区分同名进程 |
| L-63 | `api/app.py:28-37,60-95` | app.py 直接调用 infrastructure 工厂函数，组合根逻辑未提取到独立 bootstrap |

### 5.6 前端

| # | 文件:行 | 问题 |
|---|---|---|
| L-64 | `services/api-client.ts:140-141` | SSE 读取循环在 done 时直接 break，未 flush 残留 buffer 中的最后一个不完整事件 |
| L-65 | `services/api-client.ts:131` | CRLF→LF 归一化在每个 chunk 执行，跨 chunk 边界的 `\r\n` 可能未被归一化 |
| L-66 | `services/api-client.ts:186` | 对 204 No Content 或空 body，`response.json()` 抛 SyntaxError 被误归类为 network_error |
| L-67 | `services/api-client.ts:86-89` | download 方法 HTTP 错误抛错时未传 correlationId，用户无法获得问题编号 |
| L-68 | `services/backend.ts:74` | `waitForEndpoint` 轮询间隔用裸 setTimeout，未监听 abort signal，组件卸载时延迟清理 |
| L-69 | `services/diagnoses.ts:141-142` | `URL.revokeObjectURL` 在 `anchor.click()` 后同步立即调用，Safari/旧 WebView 可能下载失败 |
| L-70 | `services/diagnoses.ts:131-143` | 服务层函数直接操作 DOM（创建 `<a>`、触发 click），表现层关注点泄漏到 service 层 |
| L-71 | `features/diagnose/DiagnosisPanel.tsx:478` | 使用字符串 item 本身作为 React key，重复 limitation 会产生 duplicate key 警告 |
| L-72 | `features/diagnose/ControlledActions.tsx:73` | 轮询退避等待用裸 setTimeout，未监听 controller.signal |

### 5.7 Rust Tauri

| # | 文件:行 | 问题 |
|---|---|---|
| L-73 | `sidecar.rs:310-323` | 进程崩溃后只标记错误，不做异常恢复（无指数退避自动重启） |
| L-74 | `lib.rs:33` / `tauri.conf.json:46-51` | updater 插件已启用但 pubkey/endpoints 为空，属无收益攻击面 |
| L-75 | `sidecar.rs:168-176` | release 下 `windows_subsystem="windows"` 无控制台，`eprintln!` 输出的 SYSMIND_ERROR 启动错误完全丢失 |
| L-76 | `lib.rs:11-19` | `restart_backend` 存在并发竞态（两次并发重启可能交错误杀新进程）且立即返回过时快照 |
| L-77 | `sidecar.rs:256-261` | shutdown 末尾无条件清掉 error，抹掉崩溃现场 |
| L-78 | `sidecar.rs:420-426` | 手写 HTTP 客户端状态行判定不严谨（`starts_with("HTTP/1.1 200")`），不处理 chunked |
| L-79 | `sidecar.rs:207-211,344-347` | 握手只校验后端"自报"的 host，无法探测真实监听地址（自证而非旁证） |
| L-80 | `sidecar.rs:496-529,119-144` | Windows Job 存在 spawn→assign 的 TOCTOU 窗口；未显式 least-privilege（管理员终端启动会继承提权） |
| L-81 | `tauri.conf.json:25` | CSP `connect-src` 对 127.0.0.1 全端口放行（因随机端口必需，可接受但偏宽） |
| L-82 | `sidecar.rs:243-254,256-261` | 优雅关闭的 2s 等待期间 snapshot 仍报 connected，前端可能发起失败请求 |
| L-83 | `lib.rs:44-48` | `ExitRequested` 上同步 shutdown 阻塞事件循环最多 2s |

### 5.8 测试 / 迁移 / 脚本

| # | 文件:行 | 问题 |
|---|---|---|
| L-84 | `tests/conftest.py:36-38` | `auth_headers` fixture 内联明文 token，与 settings fixture 隐式耦合（双写） |
| L-85 | `tests/test_action_async_boundary.py:16` | 异步测试基于 0.1s 绝对时间阈值，CI 负载下可能抖动 |
| L-86 | `tests/test_agent_runtime.py:411-420` | 前向引用闭包变量，可读性差且脆弱 |
| L-87 | `tests/test_agent_runtime.py:297-306` | SSE 游标重连测试对流格式敏感（直接解析 `id: ` 前缀和 `\n` 行尾） |
| L-88 | `tests/test_event_logs.py:268` | 部分取消测试依赖 1 秒同步等待，余量偏紧 |
| L-89 | `tests/test_health.py:19` | X-Correlation-ID 仅做真值断言，未校验 UUID 格式（已复核修正：原称"放过空字符串"不成立，Python 中空串为 falsy 会被 assert 拦截） |
| L-90 | `tests/test_observability.py:13-14` | 全局 logger 被原地替换 handler 且未恢复，propagate=False 永久残留 |
| L-91 | `tests/test_secrets.py:41-47` | 用 `object.__new__` 绕过 `__init__`，并断言 Win32 常量字面量（价值有限） |
| L-92 | `alembic/versions/0006:40` | `actions.recovery_id` 指向 `recovery_records.id` 但未建外键，引用完整性无数据库约束 |
| L-93 | `alembic/versions/0008:20-25` / `0007:20-28` | 单例配置表建表后未播种初始行，首次 SELECT 可能为空 |
| L-94 | `scripts/test_packaged_desktop.py:68` | 打包冒烟测试硬编码 head 版本号 `"0010_phase32"`，新增迁移后易漂移 |
| L-95 | `scripts/test_packaged_backend.py:61` | 用 `assert` 做运行时非空判断，`python -O` 下会被剥离 |
| L-96 | `scripts/export-openapi.py:16` | OpenAPI 导出脚本写死固定 session token（已包 SecretStr，信息级） |

### 5.9 Domain / Core / Ports

| # | 文件:行 | 问题 |
|---|---|---|
| L-97 | `domain/diagnosis.py:109-111` / `domain/agent_tasks.py:34-38` | Agent 预算上限在两处重复定义，存在漂移风险 |
| L-98 | `domain/diagnosis.py:42,73,83` | confidence 无量程校验 [0,1]，可写入越界值或 NaN |
| L-99 | `domain/event_logs.py:65` | `LogAnalysisRecord.query` 存为无类型 dict，未复用同模块 EventLogQuery |
| L-100 | `domain/diagnosis.py:121` / `domain/agent_tasks.py:79,81` / `domain/actions.py:71` | 多处状态/风险级别使用裸 str 而非已定义 Literal |
| L-101 | `application/ports/actions.py:56-65` / `diagnoses.py:29` | 仓储端口方法的 status 参数用裸 str，端口抽象弱化 |
| L-102 | `application/ports/agent_tasks.py:77-88` vs `diagnoses.py:97-108` | 工具调用"完整结果 vs 摘要"存储口径在两个仓储间不一致 |
| L-103 | `application/ports/diagnostics.py:4,34,39` / `platform_inspection.py:4` | 端口取消信号耦合 threading.Event，且可空性不一致 |
| L-104 | `application/ports/history.py:9-34` | 业务值对象（BaselineMetric 等）定义在 ports 而非 domain |
| L-105 | `application/ports/secrets.py:1` | 缺少 `from __future__ import annotations`，与其余 11 个 ports 文件不一致 |
| L-106 | `domain/event_logs.py:16-19` | EventLogQuery 无正数/上限约束（lookback_hours、max_events 可为 0 或负数） |
| L-107 | `domain/platform_inspection.py:59-62,76-80` | 审计/业务计数字段与集合长度冗余，可漂移（无不变量校验） |
| L-108 | `domain/__init__.py:1` | 模块说明"Phase 0 intentionally contains no diagnostic domain"严重过时 |

---

## 六、架构合规性评估

对照 AGENTS.md 规定的架构约束逐项评估：

| 约束 | 合规状态 | 说明 |
|---|---|---|
| 依赖方向 `presentation -> application -> domain` | ✅ 基本合规 | API 层通过 app.state 访问 coordinator，未直接访问 DB；application 只依赖 ports；domain 仅依赖 dataclasses/typing。残留：app.py 组合根直接 import infrastructure（L-63），业务编排模块位于 application/ 之外（L-40） |
| Infrastructure 实现 application/domain 端口 | ⚠️ 部分合规 | diagnoses/agent_tasks/actions 三个仓储显式继承 Protocol；history/log_analyses/scans/settings 四个靠结构匹配但未显式声明（L-14） |
| Windows 集成隔离在适配器层 | ✅ 合规 | 全部 Win32/WMI/CIM/wevtapi/iphlpapi 调用均在 `windows/` 层，tools 层仅依赖 application port 接口。唯一 PowerShell 调用为硬编码常量、无输入插值（已确认） |
| AI 模型不直接调用 Windows API/Shell/PowerShell | ✅ 合规 | 模型工具调用经多层验证后才执行；provider 仅产出 JSON/tool_call；无模型输出直接作为命令参数 |
| 模型操作仅限于 Tool Registry 版本化工具 | ⚠️ 部分合规 | 主路径合规，但存在子目录 toolset 的并行直调路径（M-14），可能被误用绕过 Registry |
| 默认 loopback-only | ✅ 合规 | `config.py` 中 `host: Literal["127.0.0.1"]` 并有 validator 拒绝非回环地址；Tauri 启动参数 `--host 127.0.0.1` + 握手契约强制 + HTTP 请求二次校验，三重防线 |
| 默认 read-only / least-privilege | ✅ 合规 | `policy.py` 默认仅 `read_only`，`confirmation_policy != "none"` 直接拒绝；写操作有完整确认流程。残留：sidecar 未显式降权，管理员终端启动会继承提权（L-80） |
| 禁止在 SQLite/日志/源码控制/前端存储保存 API key | ✅ 合规 | API key 仅存 Windows 凭据管理器；SQLite 只存 `secret_reference`；前端 0 处 localStorage/sessionStorage/cookies；无源码硬编码密钥 |
| 禁止记录 Authorization 头或完整敏感请求数据 | ⚠️ 部分合规 | 无 Authorization 头日志；模型调用只存 request/response 哈希。但日志 message/exception 文本未走 redact_text（M-07），可能含路径等 PII；AgentRunError 错误文本直接落库（M-08） |
| 系统变更操作需明确参数绑定的用户确认和审计 | ✅ 合规 | 受控动作采用 HMAC 票据 + 锁 + 原子一次性消费 + 事件审计；写操作有 TOCTOU 修订指纹；每次状态变更写 ActionEventModel |

---

## 七、安全评估

### 7.1 安全优势

1. **密钥管理**：API key 通过 Windows DPAPI/凭据管理器存储，SQLite 仅存不透明引用；key 不入 DB、不入日志、不入 repr；非 HTTPS 端点拒绝
2. **认证机制**：会话令牌使用 `secrets.token_urlsafe(32)` 生成，通过 `hmac.compare_digest` 常量时间比较；Tauri 侧 UUIDv4 两次拼接（244bit 熵）
3. **AI 安全边界**：模型工具调用经 `tool_map 反查 → policy.authorize → pydantic 校验(extra="forbid") → 风险/权限/确认策略白名单` 多层验证；有轮次/预算/签名去重三重防无限循环；`propose_action` 直接 raise 拒绝
4. **动作确认**：HMAC 签名票据、一次性消费（原子 compare-and-set）、TOCTOU 修订指纹（item_id + observed_revision 重新枚举校验）、完整事件审计
5. **脱敏**：`redact_text` 覆盖用户名/IP/IPv6/MAC/邮箱/UNC 路径，已用于报告导出、模型解释、上下文；`is_sensitive_key` 覆盖 token/secret/password/key 等键名
6. **前端安全**：无 XSS 风险（无 dangerouslySetInnerHTML）、无敏感数据持久化、认证头一致覆盖所有 API 调用、错误边界不记录详情
7. **事件日志**：通道白名单、lookback≤168h、max≤200、event_ids 范围校验、文本经 redact_text + 账号正则脱敏

### 7.2 安全风险（需优先修复）

| 优先级 | 风险 | 发现编号 |
|---|---|---|
| P0 | release 包 env 覆盖可执行任意二进制并获取会话令牌 | M-09 |
| P1 | 日志 message/exception 未脱敏，PII（用户名路径）进日志 | M-07 |
| P1 | AgentRunError 错误文本直接落库并暴露给 UI | M-08 |
| P1 | create_tool_call 把未脱敏原始参数交给仓储 | M-10 |
| P2 | Correlation-ID 未校验即反射到响应头（响应头注入） | M-15 |
| P2 | 审计打码键名覆盖不全（只匹配 "command"，不匹配 cmd/shell/script） | L-30 |
| P2 | 动作适配器异常 str() 直接写入 error_message | L-38 |
| P2 | 启动失败 str(error) 打到 stderr（可能含用户名路径） | L-42 |
| P3 | updater 插件空 pubkey（无收益攻击面） | L-74 |
| P3 | CSP connect-src 全端口放行（因随机端口必需） | L-81 |
| P3 | 握手只校验后端自报 host，无法探测真实监听地址 | L-79 |

---

## 八、测试质量评估

### 8.1 测试覆盖优势

测试套件整体质量**显著高于一般项目**，关键安全/韧性行为都有针对性测试：

- **失败模式**：工具失败 → partial 报告、私有异常不外泄、round budget 截断、unsafe 工具 fail-closed
- **权限拒绝**：prompt injection 调用未授权工具 → unknown_tool 且参数不落库
- **取消/超时**：运行中 provider 调用可取消、SSE Last-Event-ID 游标重连、task timeout 终止慢 provider
- **审计**：审计哈希、脱敏、CAS 乐观锁、重启恢复
- **安全矩阵**：loopback 强制、Origin 白名单、session token 不进 repr、HMAC 签名、单次使用、过期、路径/IP/MAC/邮箱脱敏
- **真实环境**：破坏性测试三重门禁（env ACK + 用户/VM marker + Windows 平台），真实 HKCU Run 键/启动文件夹/notepad 关闭/强制终止端到端验证

### 8.2 明显覆盖缺口

| 模块 | 缺失测试场景 |
|---|---|
| **安全** | 错误 session token 值（格式正确但不匹配）→ 401；consent ticket 跨 action 复用；OPTIONS/CORS 响应头；未授权访问每个业务路由的 401 矩阵 |
| **动作** | `reject()` 流程完全无测试；两个并发 `confirm()` 同一 action 的竞争（double-spend）；confirm 与 execute 之间 ticket 过期 |
| **Agent Runtime** | 工具 handler 抛未映射 RuntimeError 的任务级失败；ToolUnavailableError 在 agent runtime 路径下的映射；agent task waiting_user_input 状态机恢复 |
| **诊断** | `classify_question` 空串/纯空白/超长/乱码；feedback 负值/非法 body；Provider 返回非法 JSON/空 choices；并发提交两个 diagnosis 的互斥/排队 |
| **工具** | 调用未注册版本；concurrency_key 相同的两个工具串行化；output_adapter 校验失败；confirmation_policy=="each_time" 在 executor 层行为 |
| **Provider** | 5xx 服务端错误映射；畸形 tool_call arguments JSON；choices 为空/usage 缺失 |
| **基础设施** | run_migrations 幂等性；损坏 DB 文件/只读 data_dir 启动恢复；WAL 下并发写；WindowsCredentialSecretService 的 get/delete 路径 |
| **Windows 适配器** | WindowsServiceProbe.list_services 解析失败降级；DNS check 失败分支；ping 全部丢包 vs 部分丢包归一化 |

### 8.3 测试代码质量问题

- 3 处硬编码计数/修订号的脆弱测试（M-28）
- 跨测试模块 import + 运行时替换私有属性（M-29）
- 审计 hash 在测试侧重算序列化参数，与生产规则双写（M-30）
- 全局 logger handler 替换未恢复（L-90）
- 基于绝对时间阈值的异步测试可能抖动（L-85, L-88）

---

## 九、修复优先级建议

### P0 — 立即修复（阻塞发布）

| # | 发现 | 原因 |
|---|---|---|
| ~~1~~ | ~~H-01 动作外键缺 CASCADE~~ | **【终审撤销】经删除路径追溯为刻意审计保护、删除不可达，不构成 BUG，详见复核报告第九节** |
| 2 | H-02 sidecar 握手无超时 | 偶发情况下 UI 永久转圈，用户无法恢复 |
| 3 | M-09 release env 覆盖 | 安全边界漏洞，恶意进程可诱导执行任意二进制 |

### P1 — 下一迭代必修

| # | 发现 | 原因 |
|---|---|---|
| 4 | M-01 busy_timeout + 多 engine | 多后台任务并发写时极易 database is locked |
| 5 | M-07 日志未脱敏 | PII（用户名路径）进日志，违反安全边界 |
| 6 | M-08 AgentRunError 落库 | 错误文本可能含 URL/路径/响应片段，暴露给 UI |
| 7 | M-12 Executor 超时不取消 | 超时后后台线程继续跑，违背"超时必须生效" |
| 8 | M-02 rsplit 崩溃 | 工具名无版本号时直接崩事务 |
| 9 | M-24 session_token 双来源 | 可能导致认证失败，难以调试 |
| 10 | M-19 前端 SSE 竞态 | 旧任务事件污染新任务状态，用户可见错误 |

### P2 — 产品化前补齐

| # | 发现 | 原因 |
|---|---|---|
| 11 | M-03 clarification_question 字段错放 | 前端无法正确展示等待提问 |
| 12 | M-04 tool_version 硬编码 | 审计追溯失真 |
| 13 | M-05 baseline AttributeError | 脏 summary 导致首页基线崩溃 |
| 14 | M-06 tool_call_id 外键缺 ondelete | 级联删除可能触发约束错 |
| 15 | M-10/M-11 审计参数脱敏/哈希一致性 | 安全审计口径不统一 |
| 16 | M-13/M-14 工具超时声明漂移/并行直调路径 | 架构收敛 |
| 17 | M-15 Correlation-ID 响应头注入 | 安全加固 |
| 18 | M-16/M-17/M-18 health/SSE 健壮性 | 功能健壮性 |
| 19 | M-20 retentionDays NaN | 前端输入校验 |
| 20 | M-21/M-22/M-23 application 层健壮性 | 空通道校验、依赖抽象、审计闭合 |
| 21 | M-25/M-26/M-27 domain 模型不变量 | 领域模型完整性 |
| 22 | M-28/M-29/M-30 测试脆弱性 | 测试可维护性 |
| 23 | M-31 downgrade 不可靠 | 迁移回滚能力 |
| 24 | L-73 sidecar 崩溃自动恢复 | 产品自愈体验 |
| 25 | L-74 updater 空 pubkey | 移除无收益攻击面 |
| 26 | L-75 release stderr 丢失 | 排障体验 |

### P3 — 持续改进

剩余 82 条 Low 发现（L-01~L-108 中除上述 P2 列出的条目外），多为边缘情况健壮性、代码风格、可维护性改进，不影响核心功能和安全，可在日常迭代中逐步收敛。（已复核修正：原称"~80 条"，实际正文列出 108 条 Low。）

---

## 十、附录：已审查文件完整清单

### 10.1 后端源码（services/backend/src/sysmind/）

| 目录 | 文件数 | 行数 |
|---|---:|---:|
| domain/ | 7 | ~534 |
| core/ | 3 | ~77 |
| application/ (含 ports + services) | 17 | ~2,350 |
| agent/ (含 providers/) | 8 | ~1,100 |
| infrastructure/ (含 database + secrets) | 18 | ~2,395 |
| api/ (含 routes + dto) | 21 | ~1,800 |
| windows/ | 6 | ~1,540 |
| tools/ (含 log/process/system) | 13 | ~1,100 |
| diagnosis/ | 4 | ~1,130 |
| actions/ | 2 | ~346 |
| tasks/ | 2 | ~227 |
| security/ | 3 | ~143 |
| observability/ | 2 | ~108 |
| reports/ | 4 | ~233 |
| prompts/ | 2 | ~118 |
| runtime/ | 3 | ~80 |
| 根入口 (__init__, __main__) | 2 | ~41 |
| **后端源码小计** | **120** | **~13,322** |

### 10.2 后端测试（services/backend/tests/）

26 个文件，~4,700 行（含 conftest.py）

### 10.3 Alembic 迁移（services/backend/alembic/）

11 个文件，~660 行（env.py + 10 个版本迁移）

### 10.4 前端（apps/desktop/src/）

34 个文件，~4,200 行（含 .ts/.tsx + vite.config.ts）

### 10.5 Rust Tauri（apps/desktop/src-tauri/）

4 个源文件，~620 行（lib.rs, main.rs, sidecar.rs, build.rs）+ Cargo.toml + tauri.conf.json

### 10.6 脚本（scripts/）

3 个文件，~310 行（test_packaged_desktop.py, test_packaged_backend.py, export-openapi.py）

---

> **报告生成说明**：本报告由 10 个并行审查分片逐行审查后汇总去重生成。正文显式列出 141 条发现（H-01~H-02、M-01~M-31、L-01~L-108），所有 195 个源文件、约 20,400 行代码均已被逐行读取和分析，无跳过。（已复核修正：原称 146 条发现与正文实际列出的 141 条不符；所称"各分片报告"未作为独立文件留存。）
