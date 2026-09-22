# SysMind AI 深度修复报告（依据两份审查报告）

> 修复日期：2026-09-11
> 依据：`CODE_REVIEW_REPORT.md`（141 条发现）+ `CODE_REVIEW_VERIFICATION.md`（复核结论）
> 范围：后端 Python、前端 TS/React、Rust Tauri、Alembic 迁移、测试

---

## 一、质量门禁（全部通过）

| 门禁 | 命令 | 结果 |
|---|---|---|
| 后端 lint | `ruff check .` | All checks passed |
| 后端类型 | `mypy src` | 123 个源文件无问题 |
| 后端测试 | `pytest` | **175 passed, 4 skipped**（基线 162，新增 13 条） |
| 前端 lint/typecheck/test | `pnpm lint && pnpm typecheck && pnpm test` | 36/36 全通过 |
| Rust 类型/格式 | `cargo check --tests` / `cargo fmt --check` | 通过 |

> `cargo test` 在本机**无法链接**：`link.exe` 解析到的不是 MSVC 链接器
> （`link: missing operand after '@...'`），属环境既有问题，与本次改动无关。
> 已改用 `cargo check --tests` 保证 Rust 代码类型正确。

---

## 二、P0 / P1 修复

| 编号 | 问题 | 修复 |
|---|---|---|
| **H-02** | sidecar 握手阻塞读 stdout 无超时，进程沉默时 UI 永久转圈 | stdout 读取改为 mpsc channel + `recv_timeout(20s)`；新增 `await_handshake()`，区分「超时」与「进程提前退出」两种错误文案；补 3 条 Rust 单测 |
| **M-09** | release 包仍可被 `SYSMIND_BACKEND_EXECUTABLE` 劫持执行任意二进制 | 用 `#[cfg(debug_assertions)]` 包住该 override，release 只允许 bundled 资源目录下的 `sysmind-backend.exe` |
| **M-01** | SQLite 无 `busy_timeout` + 每个协调器各建 engine 争抢 WAL 写锁 | 连接加 `PRAGMA busy_timeout=5000`；组合根创建**单一** sessionmaker 注入全部仓储，lifespan 结束时统一 `dispose()`（顺带修 L-15） |
| **M-07** | 日志 message / 异常堆栈未脱敏，绝对路径含用户名进 JSON 日志 | `JsonFormatter` 对 message、`formatException` 及所有字符串值统一调用 `redact_text` |
| **M-08** | `AgentRunError` 的 `str(error)` 原样落库并暴露给 UI | 落库前 `redact_text` + 截断至 280 字符；语义与相邻泛型分支一致 |
| **M-12** | Executor 超时不置位取消信号，后台线程继续跑 | 为**每次执行**创建 `_AnyCancelEvent(cancel_event, timed_out)`，超时只置位 `timed_out`（见第四节） |
| **M-24** | `Settings` 双构造路径产生不同随机 session_token | `core/config.py` 改为进程级单例 `configure_settings()` / `get_settings()`；`__main__` 启动时绑定 |
| **M-19** | SSE 事件把旧任务状态合并到新任务 | 回调捕获 `expectedTaskId`，`setTask`/`setEvents` 均校验归属 |
| **M-10** | 诊断协调器把**原始** arguments 落库 | 新增 `security.redaction.redact_arguments()`；两个仓储端口参数改名 `redacted_arguments` 固化契约 |
| **M-02** | `rsplit("@",1)` 无版本号时 ValueError 崩事务 | 改为安全拆分，缺版本号回退 `"1.0"` |
| **M-31** | 0009/0010 downgrade 的 `drop_column` 在旧 SQLite 不可靠 | `env.py` 两组 `context.configure` 均启用 `render_as_batch=True` |

---

## 三、Medium / Low 主要修复

**数据完整性**
- **M-06 + 新迁移 `0011_phase6_integrity`**：`diagnosis_steps.tool_call_id` 改 `ON DELETE SET NULL`（SQLite 表重建方式），避免删 diagnosis 时级联顺序触发外键错误；新增回归测试直接验证。
- **M-11**：`scan_step_events` 补 `arguments_hash`，与 event-log 审计口径一致。
- **M-05**：`baseline()` 的 except 补 `AttributeError`，并对非 dict/list 字段做类型守卫。
- **L-13**：诊断删除影响面统计补全 9 张子表（原仅 3 张）。
- **M-04 / L-08 / L-09**：动作 `tool_version` 改为调用方传入（新增 `domain.actions.ACTION_TOOL_VERSIONS`）；`close()` 不再 dispose 共享 engine；`create_restore` 校验原动作确为 startup 类。

**安全与脱敏**
- **L-30**：审计打码键名从只匹配 `command` 扩展到 `cmd/shell/script/executable/powershell` 等。
- **L-38 / L-42**：动作适配器异常、启动失败 stderr 均走脱敏。
- **M-15**：`X-Correlation-ID` 校验字符集 + 长度 ≤64，非法值回退 `uuid4`（防响应头注入）。
- **L-52 / L-53**：诊断 id 路径参数加安全字符集与长度约束（保留 `phase32-waiting` 这类可读 id）。
- **L-44 / L-48 / L-43 / L-60**：GPU 采集超时翻译、事件按解析时间排序、severity 未知值不 KeyError、`zip(strict=True)` 改显式 `strict=False`。
- **L-57 / L-56 / L-96**：阻塞凭据读取移出事件循环、动作错误码显式映射 HTTP 状态、导出脚本改为随机 token。

**架构与领域模型**
- **M-22**：新增 `application.ports.agent_providers.AgentProviderFactory`，`ProviderSettingsService` 不再直接 new 具体 Provider（实现放在 `agent/providers/factory.py`，由组合根注入）；顺带修 L-25（校验与落库使用同一归一化值）。
- **M-23 / L-29**：`brain._execute_tool` 取消路径补 `finish_tool_call(status="cancelled")`；`asyncio.gather` 加 `return_exceptions=True` 后重新抛出首个异常，避免兄弟任务成孤儿。
- **M-25 / M-26 / L-106 / L-108**：`GpuInfo` 移除 "metadata-only Windows adapter" 实现泄漏文案并加不变量校验；`EventLogQuery` 增加 1..168 / 1..200 边界（channel 白名单仍留给适配器，是有意的纵深防御）；`domain/__init__` 文档更新。
- **M-27 / L-14 / L-16 / L-104 / L-105**：frozen 记录的可变容器改 tuple 并做防御拷贝；两个仓储显式继承端口 Protocol；历史值对象迁到 `domain/history.py`；`ports/secrets.py` 补 `__future__`；`repositories/__init__` 整理导入顺序。
- **M-21**：log analysis 入口校验空 channels，避免后台任务里抛含糊 IndexError。
- **M-17 / M-18**：SSE 生成器捕获 DB 异常并下发 `event: error`；终态后再查一次事件，避免漏发 `task.completed`。

**前端（L-64 ~ L-72）**
SSE 收尾 flush 残留 buffer、CRLF 全 buffer 归一化、204/空 body 不再误报 network_error、`download` 错误带 correlationId 且返回同 realm 的 Blob、轮询 wait 支持 abort signal、导出从 service 层移回表现层并延迟 `revokeObjectURL`、限制列表 key 去重。

**测试质量（M-28 / M-29 / M-30 / L-84 / L-89 / L-90 / L-94 / L-95）**
- head 修订号改为 `ScriptDirectory` 动态获取；审计计数改为按规格推导/按工具名断言。
- 新建 `tests/fakes/actions.py`，消除跨测试模块 import；爆炸适配器改为**构造时注入**，不再替换私有属性。
- 新增 `provider_request_hash()` 公共 helper，测试不再重复实现哈希配方。
- `auth_headers` 由 `settings` fixture 派生；health 断言改为校验 UUID 格式；`test_observability` 恢复 logger 现场。
- 打包脚本去掉硬编码 head 与 `-O` 下失效的 `assert`。

---

## 四、经核实为「建议有害」而未采纳/已回退的三条

1. **H-01 / L-02 / N-03（动作外键加 CASCADE）** —— 复核报告第九节已判定为刻意审计留存设计，加级联会销毁审计链。未改。
2. **L-07 / L-11（`mark_interrupted` 纳入 `waiting_user_input`）** —— 试改后
   `test_waiting_state_survives_restart_and_can_resume` 失败：该状态被刻意保留以便重启后继续，
   置为 interrupted 会让用户补充信息丢失。已回退并加注释说明。
3. **M-12 的字面建议（超时直接 `cancel_event.set()`）** —— 该事件是**任务级共享**的，
   照做会让单个工具超时取消整个诊断，把有价值的 partial 结果变成 cancelled
   （`test_phase4_windows_tools` 稳定失败；实测该用例从 26.8s 变失败）。
   最终改为每次执行独立的 `_AnyCancelEvent(cancel_event, timed_out)`：超时只置位 `timed_out`，
   既让 handler 的取消检查点生效，又不影响兄弟工具。修复后该用例 12.6s 通过。

---

## 五、过程中修复的环境事故

- **Git 仓库损坏**：一次被中断的 `git stash` 导致 `.git/refs` 与 objects pack 丢失，git 报
  "not a git repository"。已依据 `.git/logs` 的 reflog 重建 6 个分支引用，再 `git fetch origin`
  取回全部对象（954 个），孤立 `.idx` 重命名为 `.idx.orphan`。仓库已恢复，`git status` 正常。
- **pytest 后台运行假失败**：`run_in_background` 跑全量后端测试会大量报 `SystemExit: 1`
  （94 个 ERROR），而前台运行完全正常。推断与沙箱后台任务的文件访问有关。
  **结论：后端测试须前台运行并重定向到文件**（`pytest > file 2>&1`）。

---

## 六、遗留未改（Low，需人工决策）

| 编号 | 说明 |
|---|---|
| L-12 | `cleanup()` 不回收 agent_tasks —— 与「审计留存」设计取向冲突，自动清理会销毁审计，需产品决策 |
| L-41 | 日志只走 StreamHandler，本就没有文件增长问题，加轮转无实际收益 |
| L-54 | `start_diagnosis` 未接收 correlation_id（需改协调器 `_schedule` 签名链，收益低） |
| L-58 / L-61 / L-62 | DTO 暴露 `provider_call_id`、时间戳类型不统一、candidate 移除 pid —— 涉及前端契约，改动面大 |
| L-73 / L-74 / L-76 / L-79 / L-80 / L-82 / L-83 | Rust sidecar 自愈重启、updater 空 pubkey、restart 竞态等，属产品/发布决策 |
| L-92 / L-93 / L-99 / L-100 / L-102 / L-103 | 引用完整性补外键需存量数据校验；其余为类型收窄（裸 str → Literal），涉及 DTO 与前端 |

---

## 七、清单逐条对账（141 条）

`CODE_REVIEW_REPORT.md` 正文共 **141** 条编号：H-01~H-02（2）、M-01~M-31（31）、L-01~L-108（108）。

| 分类 | 条数 | 编号 |
|---|---|---|
| **已修复** | **104** | 第二节、第三节所列；另含未写入前文但已核实修好的 M-03、M-13、M-16、M-20 |
| 判定为有害建议，未采纳 | 4 | H-01、L-02（动作外键 CASCADE）、L-07 / L-11（`mark_interrupted`） |
| 需产品/发布决策，暂不改（第六节） | 19 | L-12、L-41、L-54、L-58、L-61、L-62、L-73、L-74、L-76、L-79、L-80、L-82、L-83、L-92、L-93、L-99、L-100、L-102、L-103 |
| 第二轮补齐（原「未处理」14 条） | 14 | L-28、L-33、L-34、L-45、L-46、L-47、L-49、L-50、L-81、L-85、L-86、L-87、L-91、L-107 —— 见第九节 |

---

## 八、事后发现的遗留缺陷（已修）

- **`PRAGMA busy_timeout` 被注释失效**：M-12 定位期间为做二分在
  `infrastructure/database/engine.py` 留下 `# TEMP disabled for bisect`，把
  `busy_timeout` 一行注释掉后未恢复，导致 M-01 的修复实际未生效
  （SQLite 并发写仍会立即抛 "database is locked"）。已恢复该 PRAGMA，
  并全树扫描确认无其他调试残留。恢复后重跑门禁：
  `ruff` / `mypy`(123 files) 通过，`pytest` **166 passed, 4 skipped**。

---

## 九、第二轮：补齐原未处理的 14 条

### 一致性收窄

| 编号 | 处理 |
|---|---|
| **L-28** | `agent/planning.py` 新增 `MAX_PLAN_STEPS` 与 `remaining_plan_budget()`，两个 planner 共用同一实现。此前 Fake 用 `max(0, 8-n)`、Provider 用 `8-n`，超预算时后者会得到负数，反而放开限制 |
| **L-33** | `openai_compatible._parse_action` 不再把非 JSON 内容静默包装成 `finalize`。提示词明确要求「只返回 JSON」，因此这是协议违规，与解析器其余分支（非 dict、非法 action、畸形 tool_call）统一抛 `ProviderProtocolError`。brain 路径此前会把模型噪声当作最终答案直接结束任务 |
| **L-34** | `agent/contracts.py` 新增 `ProviderName` Literal 与 `KNOWN_PROVIDER_NAMES`，`AgentProvider.name` 返回类型收窄，两个 provider 与测试替身统一引用。新增 provider 必须先登记，否则 mypy 直接拒绝 |
| **L-107** | `domain/platform_inspection.py` 给 `StartupAssessment` / `ServiceAssessment` 加 `__post_init__` 不变量：`item_count` / `service_count` 必须等于集合长度，子集计数必须落在 `[0, total]`。此前这些冗余计数字段可静默漂移 |

### Windows 适配器语义

| 编号 | 处理 |
|---|---|
| **L-45** | `request_close` 改为先投递全部窗口再判断：只有**一个都没投递成功**才抛错。此前第 N 个窗口失败就抛 `ToolUnavailableError`，而前 N-1 个已经收到关闭消息，对外却表现为「什么都没发生」 |
| **L-46** | `terminate` 超时路径改用 `ActionVerificationError` 而非 `ToolUnavailableError`。`TerminateProcess` 已被接受，进程仍在退出中属于「已接受、待验证」，不是「能力不可用」 |
| **L-47** | `restore` 对磁盘 metadata 里的 `name` 加白名单（长度 ≤255、禁路径/通配符字符、禁控制字符）。该值会被用作 Run 键值名与启动目录文件名 |
| **L-49** | `has_default_route` 在「路由表读不到」或「无活动网卡」时返回 `None`（未知）而非 `False`（确定没有）。此前会基于未测量的事实产出确定的 `no_default_route` 结论；同时「读不到」的失败原因不再因无活动网卡而被吞掉 |
| **L-50** | `_basename` 对未加引号命令按可执行文件后缀锚定，修复 `C:\Program Files\App\app.exe` 被截断成 `C:\Program`。`startup_actions.py` 里的重复实现改为复用同一份，避免再次漂移 |

### 测试脆弱性

| 编号 | 处理 |
|---|---|
| **L-85** | 异步边界测试不再断言 `elapsed < 0.1s`，改为在阻塞调用期间统计事件循环 tick 次数。同样能证明「阻塞调用跑在循环外」，但不依赖墙上时钟 |
| **L-86** | `test_runtime_process_snapshot_propagates_cancellation` 里的 `cancellation` 提前定义，消除前向引用闭包 |
| **L-87** | SSE 重连测试抽出 `ids()` 辅助函数，两次读取用同一套解析；不再把 `\n` 写进期望字符串，避免绑定单一行尾约定 |
| **L-91** | 去掉 `assert _CRED_PERSIST_LOCAL_MACHINE == 2` 这类自证常量断言，改为在结果里 pin Win32 字面值 `2`；并说明 `object.__new__` 绕过 `__init__` 的理由（避开 advapi32 绑定，让结构体编组逻辑跨平台可测） |

### L-81：记录为既定取舍，不改

CSP `connect-src` 对 `http://127.0.0.1:*` 放行是随机回环端口架构的必然结果 —— 静态 CSP
无法枚举运行时端口。收紧的可行路径是让前端改走 Tauri IPC（由 Rust 侧代理后端请求），
属架构变更，超出 Low 级修复范围。已把该取舍与迁移路径写入 `LIMITATIONS.md`「运行与数据限制」，
避免后来者在不了解背景的情况下「收紧」它而直接打断前后端通信。

### 第二轮门禁

| 门禁 | 结果 |
|---|---|
| 后端 `ruff check src tests` | All checks passed |
| 后端 `mypy src` | 123 个源文件无问题 |
| 后端 `pytest` | **175 passed, 4 skipped**（新增 9 条回归测试） |
| 前端 `pnpm lint` / `typecheck` / `test` | 通过（36/36） |
| Rust `cargo fmt --check` / `cargo check --tests` | 通过 |
