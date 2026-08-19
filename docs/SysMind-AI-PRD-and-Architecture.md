# SysMind AI 产品需求与系统架构设计

> 文档状态：架构设计稿 v0.1  
> 目标平台：Windows 10/11 x64  
> 技术基线：Tauri 2 + React + TypeScript + Vite / Python + FastAPI + SQLite  
> 产品原则：本地优先、只读优先、解释优先、用户授权、全程可追溯

## 0. 执行摘要

SysMind AI 是面向普通 Windows 用户的本地 AI 电脑诊断助手。它不是一个只提供通用回答的聊天窗口，而是一个在用户授权范围内采集系统状态、执行诊断工具、关联 Windows 日志并生成可解释结论的桌面 Agent。

首个可发布版本应聚焦“发现问题并解释问题”，而不是“自动修复一切”。MVP 默认仅执行只读工具；终止进程、修改代理、调整服务、删除文件等操作不进入 MVP 的自动执行范围。后续加入修复能力时，必须采用“生成计划 → 展示影响 → 用户明确确认 → 执行 → 验证 → 可恢复/回滚”的闭环。

推荐采用 Tauri 桌面壳管理 Python sidecar 的本地单机架构：前端负责交互和授权，FastAPI 负责业务编排，Agent 负责推理与工具选择，Windows Adapter 隔离平台细节，SQLite 保存配置、扫描、诊断、任务和审计记录。后端仅监听 `127.0.0.1`，每次启动使用随机端口和短期会话令牌。

---

## 第一部分：产品需求分析（PRD）

### 1. 项目目标

#### 1.1 用户目标

- 用自然语言描述“电脑很卡”“游戏掉帧”“无法上网”“软件总崩溃”等问题。
- 不需要理解任务管理器、事件查看器、服务管理器等专业工具。
- 一键完成受控的系统扫描，得到按严重程度排序的诊断结论。
- 看懂结论依据、风险、建议步骤，以及哪些操作需要管理员权限。
- 在任何会改变系统状态的操作前，看到明确影响并自主决定是否执行。

#### 1.2 产品目标

- 将分散的 Windows 状态、日志和网络检测统一到一个诊断工作流中。
- 通过工具调用让 AI 基于真实设备数据回答，减少纯语言模型猜测。
- 将每条结论关联到证据、工具结果和时间，形成可审计诊断报告。
- 支持多家 AI 提供商，同时为 Ollama 等本地模型预留统一适配层。
- 形成可扩展 Tool SDK，使新增诊断工具不需要修改 Agent 核心。

#### 1.3 非目标

- 不替代杀毒软件、EDR、驱动管理器或专业硬件维修工具。
- 不承诺自动修复所有蓝屏、硬件损坏或厂商驱动问题。
- 不绕过 Windows 权限、UAC、安全软件或组织策略。
- 不默认上传完整事件日志、文件内容、用户名、路径等敏感信息。
- 不让模型直接执行 PowerShell、CMD 或任意系统命令。

#### 1.4 成功指标

- 首次扫描完成率 ≥ 95%，取消操作后无残留后台任务。
- 常规快速扫描在主流设备上目标耗时 ≤ 30 秒。
- 所有诊断结论 100% 带有证据引用或明确标注“推测/信息不足”。
- 所有状态变更操作 100% 产生显式确认记录和审计日志。
- 崩溃后任务、工具调用和错误原因可追溯。
- 核心诊断工具在支持的 Windows 版本上测试通过率 ≥ 95%。

### 2. 用户使用场景

#### 场景 A：电脑变卡

用户输入“电脑最近开机后很卡”。SysMind AI 创建诊断任务，采集 CPU、内存、磁盘、启动项和高占用进程，必要时读取相关系统事件。最终给出“现象—证据—可能原因—建议”的报告，例如磁盘持续高负载、内存压力或启动项过多。

#### 场景 B：应用频繁崩溃

用户选择应用或描述应用名称。系统读取限定时间范围内的 Application Error、Windows Error Reporting 等相关事件，提取故障模块和异常码，合并应用版本与进程信息，给出排查顺序。

#### 场景 C：无法联网或访问缓慢

系统检查网络适配器、IP、DNS、系统代理，并按分层步骤执行本机协议栈、网关、DNS 解析和目标地址连通性测试，指出故障更可能位于本机配置、DNS、路由还是远端服务。

#### 场景 D：游戏掉帧或风扇噪声大

系统采集 CPU/GPU/内存状态和高占用进程，识别资源争用、后台进程或容量压力。温度和传感器数据仅在硬件/驱动接口确实可用时展示，不伪造不可得数据。

#### 场景 E：用户想优化开机速度

系统列出启动项来源、发布者、路径和风险提示，形成禁用建议。MVP 只提供解释和手动路径；后续版本才允许经确认执行禁用并提供恢复入口。

#### 场景 F：技术支持导出报告

用户可导出经过脱敏的诊断报告，主动选择是否包含设备名、用户名、IP、进程路径和原始日志。默认仅导出摘要与必要证据。

### 3. 核心功能列表

| 模块 | 核心能力 | 用户价值 | 默认风险等级 |
|---|---|---|---|
| 首页与设备概览 | 系统健康摘要、最近任务、风险提示 | 快速理解电脑当前状态 | 只读 |
| 快速扫描 | CPU、GPU、内存、磁盘、进程、网络基础检查 | 一次完成常见排查 | 只读 |
| 自然语言诊断 | 将用户问题转为诊断计划并调用工具 | 无需理解系统工具 | 只读为主 |
| Windows 日志分析 | 按来源、级别、事件 ID、时间过滤和聚合 | 定位崩溃与系统异常 | 只读、敏感 |
| 网络诊断 | 代理、DNS、Ping、网关和适配器检查 | 分层定位联网问题 | 只读、会访问网络 |
| 启动项与服务分析 | 识别异常、冗余或高影响项目 | 改善开机和后台负载 | 分析只读，修改危险 |
| 进程分析 | 查看进程、高占用检测、签名/路径信息 | 解释卡顿来源 | 查看只读，终止危险 |
| 诊断报告 | 结论、证据、置信度、建议和限制 | 结果可解释、可复查 | 只读 |
| 历史与审计 | 扫描、对话、工具调用、确认与错误历史 | 可追溯 | 含敏感数据 |
| 模型与隐私设置 | API、模型、超时、数据发送范围、脱敏 | 用户控制数据边界 | 配置变更 |

### 4. MVP 版本范围

#### 4.1 MVP 必须包含

- Windows 10/11 x64 单用户桌面应用。
- Tauri 启停并监控 FastAPI sidecar，异常时可恢复或给出明确错误。
- 首次启动引导：隐私说明、模型配置、连接测试。
- OpenAI Compatible Provider；DeepSeek 可通过兼容接口接入。Gemini 使用独立 Adapter 或其兼容端点，不把供应商差异泄漏到 Agent。
- 基础系统采集：操作系统、CPU、GPU、内存、磁盘。
- 进程查看和高 CPU/内存占用识别，仅分析不终止。
- 代理、DNS、Ping 基础诊断。
- Windows 事件日志限定范围读取与规则化摘要。
- 启动项与 Windows 服务只读分析。
- 基于白名单 Tool 的 Agent 诊断循环。
- 任务取消、超时、进度展示、错误展示。
- 诊断历史、工具审计、配置存储和基础脱敏。
- 诊断报告展示与 JSON/Markdown 脱敏导出。

#### 4.2 MVP 明确不包含

- 任意 Shell、PowerShell 或脚本生成后直接执行。
- 终止进程、修改注册表、启动/停止服务、修改网络配置。
- 自动清理磁盘、自动安装驱动或卸载软件。
- 常驻实时监控、云端账号同步、多设备管理。
- 自主无限循环 Agent、后台静默操作。
- 完整 Ollama 支持；MVP 仅完成接口抽象与能力探测预留。

#### 4.3 MVP 验收口径

用户能从一个自然语言问题发起任务，看到诊断计划和实时进度；系统只调用已注册的只读工具；失败工具不会阻断整份报告；报告能引用具体工具结果；关闭或取消任务不会留下孤儿进程；重启应用后可查看历史记录。

### 5. 后续版本规划

| 版本 | 主题 | 主要能力 |
|---|---|---|
| v0.1 MVP | 可解释诊断 | 只读采集、日志分析、Agent、报告、历史 |
| v0.2 | 诊断质量 | 规则引擎、基线对比、更多事件关联、反馈闭环 |
| v0.3 | 受控修复 | 低风险修复动作、逐项确认、执行后验证、恢复方案 |
| v0.4 | 本地 AI | Ollama、模型能力探测、无云模式、模型下载引导 |
| v0.5 | 深度 Windows 支持 | 蓝屏转储元数据、可靠性历史、驱动与更新状态分析 |
| v1.0 | 稳定发布 | 签名安装包、自动更新、兼容矩阵、遥测完全可选、恢复机制 |

---

## 第二部分：系统架构设计

### 6. 总体架构原则

- **边界清晰**：UI、业务用例、Agent、工具、Windows API、存储分别依赖抽象接口。
- **本地优先**：系统原始数据先在本地归一化、筛选和脱敏；只把完成当前推理所需的最小上下文发送给远端模型。
- **确定性优先**：数值计算、阈值判断、日志聚合交给本地规则；模型负责计划、解释和综合，不负责“猜数值”。
- **能力受限**：模型只能选择 Registry 中的结构化 Tool，不能传入任意命令。
- **权限分离**：主程序默认普通用户权限；未来需要提权时使用单独、短生命周期的 privileged helper，并逐次经 UAC/用户确认。
- **可观测**：每次任务、模型请求、工具调用、确认、错误和耗时都有结构化记录。

### 7. 文字版架构图

```text
┌──────────────────────────── Windows Desktop ────────────────────────────┐
│                                                                         │
│  ┌──────────────── Tauri 2 Shell ─────────────────┐                     │
│  │ Window / Tray / Lifecycle / Updater            │                     │
│  │ Python sidecar 启停、随机端口、会话令牌         │                     │
│  └──────────────────────┬─────────────────────────┘                     │
│                         │                                               │
│  ┌──────────────── React + TypeScript UI ─────────┐                     │
│  │ Dashboard | Diagnose | Task Progress | Report  │                     │
│  │ History | Settings | Consent Dialog            │                     │
│  └──────────────────────┬─────────────────────────┘                     │
│                         │ HTTP/SSE @ 127.0.0.1 + session token           │
│  ┌──────────────────────▼─────────────────────────┐                     │
│  │ FastAPI Local Backend                          │                     │
│  │ API / Application Services / Task Orchestrator │                     │
│  └───────────────┬──────────────────────┬─────────┘                     │
│                  │                      │                               │
│  ┌───────────────▼────────────┐  ┌──────▼──────────────────────────┐    │
│  │ AI Agent Layer             │  │ Domain Services / Rule Engine  │    │
│  │ Brain / Planner / Memory   │  │ Scoring / Correlation / Redact │    │
│  │ Provider Adapters          │  └──────┬──────────────────────────┘    │
│  └───────────────┬────────────┘         │                               │
│                  │ structured tool call │                               │
│  ┌───────────────▼──────────────────────▼─────────┐                     │
│  │ Tool Runtime                                    │                     │
│  │ Registry | Policy | Validator | Executor        │                     │
│  │ Timeout | Cancellation | Result Normalizer      │                     │
│  └──────────────────────┬─────────────────────────┘                     │
│                         │                                               │
│  ┌──────────────────────▼─────────────────────────┐                     │
│  │ Windows Interaction Adapters                    │                     │
│  │ CIM/WMI | Event Log API | Registry | Win32      │                     │
│  │ psutil | network APIs | optional signed helper  │                     │
│  └──────────────────────┬─────────────────────────┘                     │
│                         │                                               │
│  ┌──────────────────────▼─────────────────────────┐                     │
│  │ Local Data                                      │                     │
│  │ SQLite | encrypted secrets via Windows DPAPI    │                     │
│  │ rotating app logs | exported reports            │                     │
│  └─────────────────────────────────────────────────┘                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                      │ only when user enables cloud model
                      ▼
        OpenAI Compatible / DeepSeek / Gemini / future Ollama
```

### 8. Tauri 前端结构

#### 8.1 职责

- 管理窗口、托盘、单实例、安装更新与 sidecar 生命周期。
- 展示设备概览、诊断输入、执行计划、工具进度、报告和历史。
- 展示权限请求与危险操作确认；确认文本不能由模型任意伪造。
- 维护短期 UI 状态，不在浏览器存储中保存 API Key 或原始系统日志。
- 使用 SSE 接收任务事件；普通请求使用 REST。MVP 不必引入 WebSocket。

#### 8.2 前端分层

- `app`：路由、布局、全局 Provider、启动状态。
- `features`：按业务能力组织，如 diagnose、dashboard、history、settings。
- `components`：无业务耦合的共享 UI。
- `services`：类型安全 API Client、SSE Client、Tauri command 封装。
- `stores`：仅保存跨页面且短生命周期的客户端状态。
- `types`：由后端 OpenAPI 生成的 DTO 与前端视图模型。

#### 8.3 页面信息架构

- 首页：健康摘要、快速扫描、最近问题。
- 诊断：自然语言输入、推荐问题、范围与隐私提示。
- 任务：计划步骤、实时状态、取消按钮、工具执行摘要。
- 报告：问题摘要、严重程度、证据、建议、限制、导出。
- 历史：扫描和诊断任务筛选、详情、删除。
- 设置：模型 Provider、隐私、日志保留、外观、关于。

### 9. FastAPI 后端结构

#### 9.1 接口层

- `/health`：sidecar 就绪与版本检查。
- `/api/v1/system/*`：明确触发的系统采集接口。
- `/api/v1/tasks`：创建、取消、查询 Agent/扫描任务。
- `/api/v1/tasks/{id}/events`：SSE 任务事件流。
- `/api/v1/diagnoses`：诊断历史与报告。
- `/api/v1/settings`：非密钥配置；密钥通过专用 secret service。
- `/api/v1/providers/test`：模型连接和能力测试。

所有接口使用 Pydantic DTO；不直接返回 ORM 对象。API 通过 loopback、启动期随机 token、Origin 校验和请求体限制降低本机恶意网页访问风险。

#### 9.2 应用层

- 用例编排：快速扫描、问题诊断、报告导出、设置更新。
- 事务边界：应用服务负责，不由路由或工具自行提交数据库。
- Task Manager 管理后台任务、取消信号、进度事件和并发上限。
- Rule Engine 先形成确定性 findings，再交给模型综合说明。

#### 9.3 生命周期

1. Tauri 选择可用随机端口并生成一次性启动令牌。
2. Tauri 启动签名/随包分发的 Python sidecar，传入端口和令牌句柄。
3. 前端等待 `/health`，校验协议版本。
4. 应用退出时先请求优雅关闭，超时后再终止自身创建的 sidecar。

### 10. AI Agent 层

- `Agent Brain`：将目标、策略、工具摘要和有限上下文组成模型请求。
- `Planner`：输出有限步骤的诊断计划；计划可在工具结果到来后修订。
- `Provider Adapter`：统一 Chat/Responses 风格、Tool Calling、流式输出、错误与用量。
- `Context Builder`：选择当前任务需要的摘要，不把全库历史塞入上下文。
- `Evidence Composer`：把结论绑定到 tool_call_id、字段路径和规则 finding。
- `Guardrails`：最大轮次、最大工具数、token/时间预算、重复调用检测、敏感字段脱敏。

### 11. Tool 调用层

Tool 不等同于脚本。每个 Tool 都是应用内注册的受控函数，具有稳定名称、版本、输入/输出 Schema、权限声明、风险级别、超时和数据敏感级别。

执行链：

```text
模型提出 tool_call
  → Registry 查找精确名称和版本
  → JSON Schema/Pydantic 参数校验
  → Policy Engine 检查权限、风险、任务预算和用户授权
  → 必要时生成由应用定义的确认卡片并暂停任务
  → Executor 执行（超时、取消、并发限制）
  → Result Normalizer 统一结果与错误
  → Redactor 脱敏
  → Audit Logger 持久化
  → 摘要结果返回 Agent，完整结果保留本地
```

### 12. Windows 系统交互层

- 优先使用稳定、结构化接口：Win32 API、Windows Event Log API、CIM/WMI、注册表读取和 `psutil`。
- PowerShell 只作为特定工具的受控适配器备选，命令模板固定，参数强类型校验，不接受模型生成命令。
- 每个 Adapter 返回统一领域模型，不让上层依赖 WMI 字段或 PowerShell 文本格式。
- 管理员权限不是应用默认运行模式。需要权限但未获得时返回 `permission_required`，而不是反复重试。
- 对不同 Windows 版本、语言和缺失计数器做能力探测；“不可用”是合法结果。

### 13. 数据存储层

- SQLite 使用 WAL、外键约束和显式迁移。
- Repository 隔离 SQL/ORM 与业务层，建议 SQLAlchemy 2 + Alembic。
- API Key 不以明文进入 SQLite；使用 Windows Credential Manager 或 DPAPI 加密后的密文，并记录密钥引用。
- 原始工具结果设置保留期限；大体积事件日志可压缩后存文件，数据库只存索引、哈希和路径。
- 应用运行日志采用结构化 JSON Lines、大小轮转，并禁止记录 API Key、Authorization Header 和完整模型请求。

---

## 第三部分：Agent 设计

### 14. Agent Brain

Agent Brain 接收 `用户目标 + 当前设备能力 + 策略 + 任务记忆 + 可用工具摘要`，输出下列动作之一：

- `request_tool_calls`：请求一个或多个相互独立的只读工具。
- `ask_user`：缺少关键范围或授权时询问用户。
- `propose_action`：提出会改变系统的动作，等待确认，不直接执行。
- `finalize`：生成带证据和置信度的最终报告。
- `abort`：无法安全继续或达到预算时结束并解释原因。

核心约束：最大推理轮次、最大工具调用数、任务总超时、单工具超时、重复调用熔断、并行只读调用上限、状态变更操作不可并行。

### 15. Tool Registry

每个 Tool 的元数据至少包含：

| 字段 | 含义 |
|---|---|
| `name` / `version` | 稳定标识，如 `system.memory.get_status@1` |
| `description` | 面向模型的准确用途和禁用场景 |
| `input_schema` / `output_schema` | 强类型结构 |
| `risk_level` | `read_only`、`network`、`state_change`、`destructive` |
| `required_privilege` | 普通用户、管理员或特定能力 |
| `sensitivity` | 是否包含身份、路径、IP、日志内容 |
| `timeout` / `concurrency_key` | 执行限制 |
| `confirmation_policy` | 无需确认、每次确认、二次确认 |
| `handler` | 实际执行器引用，不暴露给模型 |

Registry 启动时验证名称唯一、Schema 合法、Handler 存在；工具按 capability 查询，不允许模型动态注册工具。

### 16. Tool Executor

- 输入校验后创建不可变 `tool_call` 记录。
- 通过 Cancellation Token、超时和并发信号量运行工具。
- 统一捕获 `unsupported`、`permission_required`、`timeout`、`cancelled`、`partial`、`internal_error`。
- 工具应尽量幂等；状态变更工具必须声明前置状态、目标状态和验证器。
- 完整结果落本地，Agent 只接收字段白名单和摘要，避免上下文膨胀。
- 未来 privileged helper 仅接受签名、白名单化 action payload，不接受命令字符串。

### 17. Memory

Memory 分为四层：

- **Working Memory**：当前任务计划、已调用工具、关键观察和预算，任务结束后固化摘要。
- **Task Memory**：单次任务事件、用户确认、工具结果引用，用于恢复和审计。
- **Device Baseline**：用户同意后保存的历次扫描指标，用于比较“现在与以前”。
- **Preference Memory**：语言、Provider、隐私偏好、保留期限等显式设置。

MVP 不建立跨任务的自由文本“人格记忆”。历史诊断只有在用户打开或明确引用时进入上下文。所有 Memory 可查看、删除，并受保留期限控制。

### 18. Task Manager

任务状态机：

```text
CREATED → PLANNING → RUNNING_TOOLS → ANALYZING → COMPLETED
                         │                │
                         ├→ WAITING_CONFIRMATION → RUNNING_TOOLS
                         ├→ WAITING_USER_INPUT ──→ PLANNING
                         ├→ CANCELLING → CANCELLED
                         └→ FAILED / TIMED_OUT
```

Task Manager 负责：任务持久化、状态转移校验、任务级锁、并发上限、进度事件、取消、崩溃恢复和孤儿任务清理。应用重启后，未完成任务标记为 `interrupted`，不自动重放任何系统操作。

### 19. 工具规划

#### 19.1 `system_tools`

- `system.cpu.get_info`：型号、物理/逻辑核心、当前利用率、基础频率信息。
- `system.gpu.get_info`：适配器、驱动版本、显存信息；利用率按能力提供。
- `system.memory.get_status`：总量、可用、已用、提交量和压力等级。
- `system.disk.get_status`：卷容量、剩余空间、文件系统、介质类型和基础健康信号。

#### 19.2 `process_tools`

- `process.list`：分页、过滤后的进程快照。
- `process.find_high_usage`：在短采样窗口中识别持续高 CPU/内存/IO 进程。
- `process.terminate`：后续版本；状态变更、高风险、逐次确认，保护系统关键进程并验证 PID 创建时间，避免 PID 复用。

#### 19.3 `network_tools`

- `network.proxy.get_config`：WinHTTP 与用户代理配置，只读。
- `network.dns.check`：解析指定安全测试域名，返回 DNS 服务器与耗时。
- `network.ping`：限制目标、次数、包大小和超时，防止滥用。
- `network.diagnose`：编排适配器、IP、网关、DNS、外网连通性的确定性流程。

#### 19.4 `log_tools`

- `log.windows_event.query`：仅允许白名单日志通道、时间窗、级别、事件 ID 和数量上限。
- `log.crash.analyze`：聚合 Application Error/WER 事件，提取应用、模块、异常码和频次；MVP 不解析完整内存转储。

#### 19.5 `startup_tools`

- `startup.list`：读取常见 Run 注册表项、Startup 文件夹和可访问的计划任务来源。
- `startup.analyze`：结合发布者、路径、签名、频次和规则给出影响等级；未知不等于恶意。

#### 19.6 `service_tools`

- `service.list`：名称、显示名、状态、启动类型、账户和二进制路径。
- `service.analyze`：识别停止的关键服务、异常自动启动项和路径问题。
- `service.change_state`：后续版本；管理员权限、逐次确认、依赖检查、执行后验证。

### 20. 风险与确认模型

| 等级 | 示例 | 默认策略 |
|---|---|---|
| R0 只读低敏感 | CPU、内存、磁盘容量 | 任务范围内可自动执行并记录 |
| R1 只读敏感/联网 | 事件日志、进程路径、Ping | 首次说明数据范围；远端发送前脱敏 |
| R2 可逆状态变更 | 禁用启动项、停止非关键服务 | 展示目标、影响、恢复方式；每次确认 |
| R3 高风险/可能不可逆 | 终止关键进程、删除、注册表关键项 | 默认禁用；二次确认或不提供 |

确认记录必须绑定 `task_id + action_type + normalized_arguments_hash + expires_at`。任何参数改变、过期或应用重启都会使确认失效。

---

## 第四部分：数据库设计

### 21. 数据库约定

- 主键推荐 UUID 文本；时间统一保存 UTC ISO 8601。
- 可查询字段结构化存列，大体积/易变化结果存 JSON，但必须带 `schema_version`。
- 所有外键开启约束；敏感数据标记并支持清理。
- 数据库迁移只前进，发布前验证旧版本升级路径。

### 22. 核心表

#### 22.1 `user_settings`（用户配置）

| 字段 | 说明 |
|---|---|
| `id` | 固定单用户记录或配置项 ID |
| `locale`, `theme` | 界面语言、主题 |
| `provider_type`, `base_url`, `model_name` | 模型配置，不含明文密钥 |
| `secret_ref` | Credential Manager/DPAPI 密钥引用 |
| `privacy_mode` | 本地优先、允许远端摘要等策略 |
| `retention_days` | 历史保留天数 |
| `created_at`, `updated_at` | 时间戳 |

#### 22.2 `system_scans`（系统扫描记录）

| 字段 | 说明 |
|---|---|
| `id` | 扫描 ID |
| `scan_type`, `status` | 快速、专项；状态 |
| `started_at`, `finished_at` | 开始与结束时间 |
| `device_fingerprint` | 本地不可逆设备摘要，不用硬件序列号明文 |
| `summary_json` | 归一化摘要 |
| `finding_count`, `highest_severity` | 结果索引 |
| `error_summary` | 部分失败摘要 |
| `schema_version` | JSON 结构版本 |

建议配套 `scan_findings`：`scan_id`、`code`、`severity`、`title`、`evidence_json`、`recommendation_json`、`confidence`。

#### 22.3 `diagnoses`（AI 诊断历史）

| 字段 | 说明 |
|---|---|
| `id`, `task_id`, `scan_id` | 关联标识 |
| `user_question` | 用户问题，允许用户删除 |
| `provider`, `model` | 实际使用模型 |
| `status` | 生成状态 |
| `report_json`, `report_markdown` | 结构化报告与渲染文本 |
| `confidence`, `limitations_json` | 置信度和限制 |
| `prompt_tokens`, `completion_tokens` | 可选用量 |
| `created_at`, `completed_at` | 时间戳 |

不默认保存完整模型思维过程；只保存用户可见解释、模型请求摘要哈希和必要审计元数据。

#### 22.4 `app_logs`（应用日志记录）

| 字段 | 说明 |
|---|---|
| `id`, `timestamp`, `level` | 标识、时间、级别 |
| `component`, `event_type` | 来源组件和事件类型 |
| `message` | 已脱敏消息 |
| `context_json` | 结构化上下文 |
| `correlation_id`, `task_id` | 链路与任务关联 |
| `contains_sensitive_data` | 清理标记 |

高频运行日志更适合轮转文件；此表保存需要检索的业务/审计事件，不应无界增长。

#### 22.5 `agent_tasks`（Agent 任务记录）

| 字段 | 说明 |
|---|---|
| `id`, `type`, `status` | 任务标识、类型、状态 |
| `user_goal` | 用户目标 |
| `plan_json`, `working_summary_json` | 当前计划与任务摘要 |
| `current_step`, `progress` | 进度 |
| `budget_json` | 轮次、工具数、时间预算 |
| `cancel_requested` | 取消标记 |
| `created_at`, `started_at`, `finished_at` | 生命周期 |
| `failure_code`, `failure_message` | 失败信息 |

建议配套表：

- `tool_calls`：工具名/版本、参数脱敏副本及哈希、状态、耗时、结果摘要、错误、风险等级。
- `task_events`：用于恢复与 UI 时间线的追加式事件。
- `user_confirmations`：动作、参数哈希、确认/拒绝、时间、过期时间。
- `model_calls`：Provider、模型、耗时、用量、请求/响应摘要哈希，不保存密钥和隐藏推理。

### 23. 关系摘要

```text
agent_tasks 1 ── N task_events
agent_tasks 1 ── N tool_calls
agent_tasks 1 ── N user_confirmations
agent_tasks 1 ── N model_calls
agent_tasks 1 ── 0..1 diagnoses
system_scans 1 ── N scan_findings
system_scans 0..1 ── 0..N diagnoses
```

---

## 第五部分：开发路线

> 下述“涉及文件”是计划中的文件，不代表当前已创建。

### Phase 0：项目初始化

**目标**：建立可运行、可测试、可打包演进的前后端骨架和工程约束。

**功能**：Tauri/React/Vite 基础壳；FastAPI health；sidecar 生命周期协议；配置与日志骨架；SQLite 迁移；CI；版本协议。

**涉及文件**：

- `apps/desktop/src-tauri/tauri.conf.json`
- `apps/desktop/src-tauri/src/lib.rs`
- `apps/desktop/src/app/*`
- `services/backend/src/sysmind/main.py`
- `services/backend/src/sysmind/core/config.py`
- `services/backend/src/sysmind/api/routes/health.py`
- `services/backend/alembic/*`
- `contracts/openapi/*`
- `.github/workflows/ci.yml`

**测试方式**：前端 lint/typecheck/unit；后端 lint/typecheck/pytest；数据库迁移升级/回滚测试；Tauri 启动 sidecar 冒烟测试；异常退出与端口占用测试。

### Phase 1：系统信息采集

**目标**：形成稳定、归一化、只读的 Windows 系统采集链路。

**功能**：OS、CPU、GPU、内存、磁盘；进程快照与高占用采样；快速扫描 API；前端设备概览与进度；结果持久化。

**涉及文件**：

- `services/backend/src/sysmind/windows/{system,process}_adapter.py`
- `services/backend/src/sysmind/tools/system/*`
- `services/backend/src/sysmind/tools/process/*`
- `services/backend/src/sysmind/domain/system_models.py`
- `services/backend/src/sysmind/application/scan_service.py`
- `services/backend/src/sysmind/api/routes/scans.py`
- `apps/desktop/src/features/dashboard/*`
- `apps/desktop/src/features/scans/*`

**测试方式**：Adapter 单元测试；固定样本 contract test；真实 Windows 10/11 冒烟；无 GPU、多个 GPU、网络盘、权限不足、进程瞬时退出等边界测试；扫描取消和性能测试。

### Phase 2：Windows 日志分析

**目标**：安全、受限地读取事件日志，并把原始事件转为可解释 findings。

**功能**：日志白名单查询；时间窗/数量限制；Application/System 常见错误聚合；应用崩溃分析；隐私脱敏；日志分析 UI。

**涉及文件**：

- `services/backend/src/sysmind/windows/event_log_adapter.py`
- `services/backend/src/sysmind/tools/log/*`
- `services/backend/src/sysmind/rules/events/*`
- `services/backend/src/sysmind/application/log_analysis_service.py`
- `apps/desktop/src/features/logs/*`
- `tests/fixtures/event_logs/*`

**测试方式**：脱敏后的 `.evtx`/结构化 fixture 回归；不同系统语言；损坏事件、访问拒绝、超大结果、时间过滤；规则准确率样本评审；UI 虚拟列表性能测试。

### Phase 3：AI Agent 框架

**目标**：实现供应商无关、预算受控、工具白名单化的 Agent Runtime。

**功能**：Provider Adapter；Agent Brain；Tool Registry/Policy/Executor；Task Manager；SSE 事件；Memory；审计；模拟模型。

**涉及文件**：

- `services/backend/src/sysmind/agent/{brain,planner,context,memory}.py`
- `services/backend/src/sysmind/agent/providers/*`
- `services/backend/src/sysmind/tools/{registry,policy,executor}.py`
- `services/backend/src/sysmind/tasks/*`
- `services/backend/src/sysmind/api/routes/tasks.py`
- `apps/desktop/src/features/tasks/*`

**测试方式**：使用 Fake Provider 的确定性循环测试；Schema 非法、未知工具、重复调用、超预算、超时、取消、Provider 限流/断流；SSE 重连；审计完整性；prompt injection 工具越权测试。

### Phase 4：自然语言诊断

**目标**：将用户问题可靠映射到诊断计划，并输出带证据的报告。

**功能**：问题分类；计划模板；网络/性能/崩溃专项流程；规则 findings 与模型综合；证据引用；置信度和限制；报告导出；用户反馈。

**涉及文件**：

- `services/backend/src/sysmind/diagnosis/*`
- `services/backend/src/sysmind/prompts/*`
- `services/backend/src/sysmind/reports/*`
- `services/backend/src/sysmind/tools/network/*`
- `services/backend/src/sysmind/tools/startup/*`
- `services/backend/src/sysmind/tools/service/*`
- `apps/desktop/src/features/diagnose/*`
- `apps/desktop/src/features/reports/*`

**测试方式**：典型问题 golden dataset；报告必须引用真实 tool_call；多 Provider contract test；离线/超时降级；敏感数据泄漏测试；人工可用性评审。

### Phase 5：自动修复能力

**目标**：只加入可明确解释、可验证、尽可能可恢复的受控修复动作。

**功能**：Action Plan；风险分级；确认卡片；短期授权票据；可选 privileged helper；状态变更工具；执行前快照；执行后验证；失败恢复。

**涉及文件**：

- `services/backend/src/sysmind/actions/*`
- `services/backend/src/sysmind/security/consent.py`
- `services/backend/src/sysmind/security/privilege.py`
- `services/backend/src/sysmind/tools/process/terminate.py`
- `services/backend/src/sysmind/tools/service/change_state.py`
- `apps/desktop/src/features/consent/*`
- `apps/desktop/src/features/recovery/*`
- `helpers/windows-privileged/*`（若确有必要，独立签名）

**测试方式**：Windows Sandbox/虚拟机快照；拒绝确认、确认过期、参数篡改、UAC 取消、执行中断、回滚失败；系统关键进程保护；每个 action 的前后状态验证；禁止在真实开发机自动运行破坏性集成测试。

### Phase 6：打包发布

**目标**：生成普通用户可安装、可升级、可卸载的可信 Windows 安装包。

**功能**：Python 冻结 sidecar；Tauri bundle；代码签名；安装/卸载；数据迁移；自动更新；崩溃恢复；隐私与许可文档；发布流水线。

**涉及文件**：

- `services/backend/packaging/*`
- `apps/desktop/src-tauri/tauri.conf.json`
- `apps/desktop/src-tauri/capabilities/*`
- `scripts/package.ps1`
- `.github/workflows/release.yml`
- `docs/privacy.md`, `docs/security.md`, `docs/release-checklist.md`

**测试方式**：干净 Windows 10/11 虚拟机安装；无 Python/Node 环境启动；普通用户/管理员账户；升级与数据库迁移；卸载保留数据选项；签名验证；杀毒误报扫描；sidecar 单实例、防火墙、离线启动和崩溃恢复。

---

## 第六部分：开发规范

### 24. 架构规范

- 依赖方向固定为 `presentation → application → domain`，基础设施实现领域接口。
- 每个 Tool 单一职责，输入输出稳定，禁止跨 Tool 隐式共享可变状态。
- Windows 特有实现集中在 adapter 层，领域模型不包含 WMI/注册表细节。
- Provider Adapter 不参与业务判断；Agent 核心不出现供应商专用字段。
- 公共契约版本化；前端 DTO 从 OpenAPI 生成，减少手写漂移。

### 25. 安全规范

- 默认普通用户、只读、最小权限、最少数据。
- 所有危险操作必须由应用生成确认界面并由用户明确确认。
- 不允许静默修改系统，不允许模型直接执行任意命令。
- 提权动作与普通后端进程隔离；授权短期、单次、参数绑定。
- API Key 使用 Windows 安全存储，日志和数据库不得出现明文密钥。
- 本地 API 只监听 loopback，并校验启动会话令牌和 Origin。
- 日志、路径、用户名、IP 等在发给云模型前按策略脱敏。

### 26. 日志与审计规范

- 使用 correlation ID 串联 UI 请求、任务、模型调用和工具调用。
- 记录谁/何时/为何请求动作、规范化参数哈希、用户决定、执行结果和验证结果。
- 不记录隐藏思维过程、密钥、认证头和未经脱敏的完整 prompt。
- 日志必须轮转、可清理、可导出；保留期限由用户配置。

### 27. 质量规范

- Python：格式化、静态检查、类型检查、pytest；领域和策略层优先单元测试。
- TypeScript：严格模式、lint、组件/Hook 单测、关键流程端到端测试。
- 每个 Tool 必须有 Schema 测试、权限测试、超时/取消测试、错误映射测试。
- Bug 修复先补回归测试；跨层契约使用 contract test。
- Windows 集成测试在 VM/Sandbox 运行，危险测试不得默认执行。

### 28. Tool 扩展规范

新增 Tool 必须同时提交：Tool 元数据、输入/输出 Schema、Handler、权限与风险说明、脱敏规则、测试、用户可见说明和版本变更记录。注册成功即可被 Agent 发现，不允许通过修改 Agent 主循环添加特殊分支。

---

## 29. 推荐项目目录结构

```text
SysMind AI/
├─ apps/
│  └─ desktop/
│     ├─ src/
│     │  ├─ app/
│     │  ├─ features/
│     │  │  ├─ dashboard/
│     │  │  ├─ diagnose/
│     │  │  ├─ tasks/
│     │  │  ├─ reports/
│     │  │  ├─ history/
│     │  │  ├─ logs/
│     │  │  └─ settings/
│     │  ├─ components/
│     │  ├─ services/
│     │  ├─ stores/
│     │  └─ types/
│     ├─ src-tauri/
│     │  ├─ capabilities/
│     │  ├─ src/
│     │  └─ tauri.conf.json
│     └─ tests/
├─ services/
│  └─ backend/
│     ├─ src/sysmind/
│     │  ├─ api/
│     │  ├─ application/
│     │  ├─ domain/
│     │  ├─ agent/
│     │  │  └─ providers/
│     │  ├─ tools/
│     │  │  ├─ system/
│     │  │  ├─ process/
│     │  │  ├─ network/
│     │  │  ├─ log/
│     │  │  ├─ startup/
│     │  │  └─ service/
│     │  ├─ windows/
│     │  ├─ diagnosis/
│     │  ├─ rules/
│     │  ├─ reports/
│     │  ├─ tasks/
│     │  ├─ storage/
│     │  ├─ security/
│     │  ├─ observability/
│     │  └─ core/
│     ├─ alembic/
│     ├─ packaging/
│     └─ tests/
├─ contracts/
│  ├─ openapi/
│  └─ schemas/
├─ helpers/
│  └─ windows-privileged/       # Phase 5 才评估创建
├─ docs/
│  ├─ SysMind-AI-PRD-and-Architecture.md
│  ├─ adr/
│  ├─ privacy.md
│  └─ security.md
├─ scripts/
├─ tests/
│  ├─ fixtures/
│  ├─ integration/
│  └─ e2e/
├─ .github/workflows/
├─ README.md
└─ AGENTS.md
```

---

## 30. 第一阶段具体开发任务列表

这里的“第一阶段”按路线定义为 **Phase 0：项目初始化**；完成后再进入 Phase 1 系统采集。

1. 记录 ADR：单仓库结构、Tauri + Python sidecar、REST + SSE、SQLite、密钥存储策略。
2. 初始化 Tauri 2 + React + TypeScript + Vite，开启 TypeScript strict。
3. 建立页面壳、路由、错误边界和基础主题，不追求最终视觉稿。
4. 初始化 Python 包、FastAPI 应用工厂、配置加载和结构化日志。
5. 实现 `/health`，返回后端版本、API 协议版本和 readiness。
6. 设计 Tauri sidecar 启停协议：随机端口、启动令牌、就绪等待、优雅退出、异常重启上限。
7. 实现前端 API Client 基础层，统一超时、错误 DTO 和 correlation ID。
8. 建立 SQLite、Repository 接口和 Alembic 首次迁移，只创建 Phase 0 必需表骨架。
9. 接入 Windows Credential Manager/DPAPI 抽象，先用 Fake 实现进行测试，禁止明文密钥落库。
10. 建立后端 lint/typecheck/test 与前端 lint/typecheck/test 命令。
11. 建立 CI，仅运行非 Windows 专属单元测试；另设 Windows runner 冒烟任务。
12. 增加启动、关闭、端口冲突、sidecar 崩溃、协议版本不匹配测试。
13. 编写本地开发说明、隐私基线和日志字段规范。
14. 建立提交前验收门：无密钥、测试通过、迁移可升级、前后端契约一致。

**Phase 0 完成定义**：开发者在全新环境可按 README 启动桌面应用；UI 能可靠识别后端就绪；关闭桌面端后 sidecar 正常退出；测试和 CI 通过；尚未实现任何系统诊断业务。

---

## 31. 给 Codex 执行的分阶段提示词模板

### 通用前缀（每个阶段都附加）

```text
你正在开发 SysMind AI。先阅读 docs/SysMind-AI-PRD-and-Architecture.md、AGENTS.md、现有 ADR 和相关测试，再检查工作区已有改动。不要覆盖用户的无关修改。

遵守以下硬约束：本地优先；默认只读和普通用户权限；模型只能调用注册工具，不能执行任意 Shell；危险操作必须由应用生成确认并完整审计；API Key 不得明文落库或写日志；前后端契约必须版本化。

本次只完成指定 Phase 的范围。先给出简短实施计划，然后实现、运行与风险相称的测试，并在结尾列出修改文件、验证结果、未完成项和架构决策。若发现必须扩大范围的决策，先停下说明。
```

### Phase 0 提示词

```text
执行 Phase 0：项目初始化。建立 Tauri 2 + React + TypeScript + Vite 前端、FastAPI Python sidecar、SQLite/Alembic、结构化日志和基础 CI。实现版本化 /health、随机 loopback 端口、启动会话令牌、就绪等待、优雅退出和错误展示。不得实现系统诊断或危险操作。为端口冲突、sidecar 崩溃、协议不匹配和迁移增加测试，并补齐 README 与 ADR。
```

### Phase 1 提示词

```text
执行 Phase 1：系统信息采集。实现 Windows Adapter 与 system/process 只读工具，覆盖 OS、CPU、GPU、内存、磁盘、进程快照和短窗口高占用识别。所有工具必须有版本化 Schema、超时、取消、错误映射、能力探测和审计。实现快速扫描用例、API、持久化、前端概览与进度。不得加入终止进程或任何系统修改。使用 fixture 单测并在 Windows 10/11 环境做冒烟测试。
```

### Phase 2 提示词

```text
执行 Phase 2：Windows 日志分析。实现白名单通道、时间窗、级别、事件 ID 和数量上限约束的事件日志查询；实现 Application/System 常见错误及应用崩溃聚合规则；加入脱敏、部分失败和权限不足处理；提供日志分析 API 与 UI。不得读取无限范围日志或默认发送原始日志到模型。用脱敏 fixture 覆盖不同语言、损坏事件和大结果集。
```

### Phase 3 提示词

```text
执行 Phase 3：AI Agent 框架。实现 Provider Adapter、Agent Brain、Tool Registry、Policy Engine、Tool Executor、Task Manager、Memory 和 SSE 任务事件。Agent 必须受最大轮次、工具数、时间、重复调用和并发限制；未知工具和非法参数必须拒绝；完整工具结果留本地，仅摘要进入模型上下文。先实现 Fake Provider 和 OpenAI Compatible Adapter，并以确定性测试覆盖取消、超时、限流、断流、越权和崩溃恢复。
```

### Phase 4 提示词

```text
执行 Phase 4：自然语言诊断。实现性能、网络和应用崩溃三类诊断计划；补齐 proxy、DNS、Ping、network diagnose、startup 和 service 的只读工具；将本地规则 findings 与模型解释组合成结构化报告。每个结论必须引用真实 tool_call/finding，信息不足时明确说明，不得伪造数据。实现报告 UI、脱敏导出和反馈入口，并用 golden dataset 与多 Provider contract test 验证。
```

### Phase 5 提示词

```text
执行 Phase 5：受控自动修复。开始前先提交具体动作白名单和威胁模型供确认；只实现可解释、可验证、尽可能可恢复的动作。加入 Action Plan、风险分级、参数绑定的短期确认票据、执行前快照、执行后验证和审计。如需提权，使用独立最小权限 helper，绝不让模型或 UI 传入任意命令。所有破坏性集成测试只能在 Windows Sandbox/VM 中运行；默认测试命令不得改变开发机状态。
```

### Phase 6 提示词

```text
执行 Phase 6：打包发布。将 Python 后端冻结为受控 sidecar，配置 Tauri Windows 安装包、签名、升级和卸载流程；验证 API/数据库迁移兼容；完善隐私、安全、第三方许可和发布清单。使用干净 Windows 10/11 VM 验证无 Python/Node 环境安装、普通用户启动、离线启动、升级、卸载、sidecar 单实例、崩溃恢复和签名。不要在仓库中写入证书或签名密钥。
```

---

## 32. 建议优先确认的架构决策

进入编码前建议将以下内容写成 ADR 并冻结首版答案：

1. Python sidecar 的冻结工具与发布体积目标。
2. Tauri 与 FastAPI 的启动认证、端口发现和协议版本机制。
3. SQLAlchemy/Alembic 是否作为统一持久化方案。
4. API Key 使用 Windows Credential Manager 还是 DPAPI 封装。
5. MVP 支持的最低 Windows 版本、架构（x64/ARM64）和语言范围。
6. 云模型默认发送的数据字段及脱敏规则。
7. MVP 的日志保留期限和导出格式。
8. Phase 5 前 privileged helper 的语言、签名和通信协议。

