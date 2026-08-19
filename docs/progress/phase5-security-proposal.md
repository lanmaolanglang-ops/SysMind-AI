# Phase 5 受控修复安全提案（历史记录）

记录日期：2026-08-19
状态：**Superseded by ADR-010 and ADR-011 — 白名单实现与拒绝项以已接受 ADR 为准**

## 1. 决策请求

Phase 4 已完成只读诊断。根据 PRD 的 Phase 5 前置要求，本文件提交首批动作白名单和威胁模型供确认。

建议按两个可独立验收的增量推进：

1. **Phase 5A（建议先批准）**：先建立 Action Plan、风险分级、参数绑定短期确认票据、执行前快照、执行后验证、恢复和完整审计；首个且唯一可执行动作是“禁用/恢复当前用户启动项”。
2. **Phase 5B（另行复审）**：在 5A 通过 Windows Sandbox/VM 验证后，再评估当前用户进程终止与 Windows 服务状态切换。5A 不创建管理员 helper，也不包含 UAC。

批准 5A 不等于批准 5B。以下白名单中，只有标记为 `5A` 的动作会在首个实现增量中注册为可执行工具。

## 2. 不可突破的边界

- 模型不生成、持有或提交确认票据，不直接调用任何状态变更工具。
- UI 不传入命令、脚本、注册表路径、服务控制参数或任意可执行文件路径。
- Action Plan 只能由 application 层根据已完成且仍有效的本地证据生成；计划中的动作必须来自版本化白名单。
- 每个状态变更逐项展示、逐项确认；不提供“全部允许”、长期授权或后台静默执行。
- 确认票据短期、单次、参数绑定、会话绑定；拒绝、过期、重放、篡改均 fail closed。
- 执行前重新读取目标身份和状态，不能只依赖诊断时快照；身份或状态变化即停止并要求重新生成计划。
- 执行后必须用独立只读探针验证。无法验证不能显示成功。
- 默认普通用户权限。5A 不提权；未来 helper 必须是独立、短生命周期、固定协议、最小权限并单独评审。
- SQLite、日志、前端存储均不得保存 API key、会话令牌、Authorization header 或确认票据明文。
- 不允许 Shell、PowerShell、CMD、任意命令、任意注册表修改或通用文件操作工具。

## 3. 具体动作白名单

### 3.1 Phase 5A：允许实现

| Tool | 风险/确认 | 固定输入 | 允许目标 | 快照、验证与恢复 |
|---|---|---|---|---|
| `startup.disable_current_user@1.0` | `state_change` / `each_time` | `source_kind`、不透明 `item_id`、`observed_revision` | 仅当前用户 `HKCU\\...\\Run` 值，或当前用户 Startup 文件夹中的单个普通文件；目标必须由最近一次只读枚举产生 | 快照保存原值/文件元数据的受限恢复资料；执行后重新枚举确认目标不再启用；生成一次性恢复动作 |
| `startup.restore_current_user@1.0` | `state_change` / `each_time` | `recovery_id`、`observed_revision` | 仅由 SysMind AI 成功执行的 disable 记录，且恢复资料完整、未使用 | 执行前验证恢复记录和目标槽位未被占用；执行后重新枚举确认；恢复记录标记已消费，不覆盖第三方的新配置 |

5A 额外限制：

- 注册表路径、值名、文件源/目标路径均由 Windows adapter 根据 `item_id` 在本地解析，API 和模型不可提供。
- Startup 文件夹动作只能在应用自有隔离目录与当前用户 Startup 目录之间移动单个普通文件；拒绝目录、链接、reparse point、UNC、设备路径和越界路径。
- 注册表恢复资料和隔离文件留在本地受限目录；数据库只保存引用、哈希、状态和必要审计元数据，不保存任意敏感完整路径。
- 若原项已变化、删除、被占用或身份不一致，返回 `target_changed`，不覆盖当前状态。
- 不处理 `HKLM`、所有用户 Startup、计划任务、服务、驱动、Explorer 扩展或其他自动启动机制。

### 3.2 Phase 5B：候选，默认不实现/不注册

| 候选 Tool | 进入条件 | 核心限制 |
|---|---|---|
| `process.terminate_current_user@1.0` | 5A 安全闭环通过后单独批准 | 仅当前交互用户的非关键普通进程；绑定 PID、创建时间和可执行文件身份；拒绝系统/受保护/关键进程、SysMind AI 进程树、跨会话、进程树终止和强制提权；不可恢复属性必须在确认卡片中突出显示 |
| `service.change_state@1.0` | helper 威胁模型、签名和 IPC 协议另行批准 | 仅应用内置服务名白名单；只允许 `running <-> stopped`；拒绝驱动、系统关键/安全/更新/网络核心服务和启动类型修改；绑定当前配置摘要；执行后验证，可能时提供反向动作 |

`process.terminate_current_user` 不属于“可恢复动作”，因此不应和 5A 一起上线。`service.change_state` 涉及提权边界，也不能在 helper 方案获批前实现。

### 3.3 明确永久拒绝的通用能力

- 任意 Shell、PowerShell、CMD、脚本、命令行或“执行程序并传参”。
- 任意注册表键/值写入、任意文件删除/移动/覆盖、任意服务名或 PID 操作。
- 杀进程树、系统关键进程、受保护进程、跨用户/跨会话进程。
- 修改防火墙、DNS、代理、路由、hosts、驱动、Windows Update、安全软件或账户权限。
- 清理磁盘、卸载软件、安装驱动、下载并执行程序。
- 模型自定义动作、模型自定义参数、批量确认、永久授权和无人值守修复。

新增任何动作都必须单独更新此白名单、威胁分析、用户可见说明、Schema、脱敏规则和测试，并再次确认。

## 4. 建议的状态机与信任边界

```text
completed diagnosis
        |
        v
application-authored action plan (proposed)
        |
        v
UI displays exact target / effect / risk / recovery
        |
  reject + audit <--- explicit per-action confirmation
        |                         |
        |                         v
        |              single-use consent ticket
        |                         |
        |                         v
        |              re-read target + compare revision
        |                         |
        |               mismatch | valid
        |                  ------ + ------
        |                  v             v
        |          stop + re-plan    execute adapter
        |                                |
        |                                v
        |                         read-only verify
        |                                |
        +---------------------- audit final state
                                         |
                              recovery offered when valid
```

建议动作状态：

`proposed -> awaiting_confirmation -> confirmed -> executing -> verifying -> succeeded | verification_failed | failed | cancelled | expired | target_changed`

恢复动作是新的 Action Plan 和新的确认，不复用原票据。

## 5. 确认票据约束

票据由后端 application/security 组件生成和消费，使用进程内随机密钥进行认证；只把不透明票据交给前端。至少绑定：

- `action_id`、tool 名称和版本；
- 规范化参数哈希；
- 执行前目标 revision/identity 哈希；
- 当前 sidecar session ID 摘要；
- 创建时间、最迟 2 分钟过期时间；
- 随机 nonce；
- 单次消费状态。

规则：

- 票据不能跨 sidecar 重启、动作、参数或目标复用。
- 数据库只记录票据摘要、用户决定、原因、时间和消费结果，不记录可重放票据。
- UI 确认 API 只接受后端返回的不透明计划动作；请求中的展示文案不参与授权。
- 消费票据和把动作置为 `executing` 必须原子化，避免双击或并发请求重复执行。
- 重启时，`confirmed/executing/verifying` 一律标记为 `interrupted`，不得自动重放；先通过只读探针判断实际状态，再决定是否提供恢复或人工处理说明。

## 6. 威胁模型

### 6.1 保护资产

- Windows 系统与用户会话的完整性、可用性和可恢复性。
- 用户对具体目标、具体影响和执行时机的控制权。
- 确认票据、sidecar 会话令牌、恢复资料和审计链的完整性。
- 用户名、路径、启动项内容等本地敏感信息。

### 6.2 攻击者与不可信输入

- 恶意或被 prompt injection 污染的模型输出、诊断文本和工具证据。
- 本机恶意网页或进程对 loopback API 的伪造/重放请求。
- 已变化的 PID、注册表值、文件或服务造成的 TOCTOU。
- 并发点击、网络重试、进程崩溃和应用重启导致的重复或不确定执行。
- 被篡改的 SQLite 审计/恢复记录或隔离目录内容。
- 未来被攻陷或协议过宽的 privileged helper。

### 6.3 主要威胁与控制

| 威胁 | 失败方式 | 必须控制 |
|---|---|---|
| 模型越权 | 模型选择危险工具或构造参数 | 模型只输出解释；Action Plan 由应用固定映射生成；状态变更 Registry 与只读 Agent Runtime 隔离 |
| CSRF/本地 API 冒用 | 恶意页面调用确认或执行 API | loopback、短期会话令牌、严格 Origin、JSON content type；确认票据额外绑定当前 sidecar session |
| 票据篡改/重放 | 换目标、换参数、重复执行 | 认证票据、参数/目标哈希、短 TTL、nonce、原子单次消费、只存摘要 |
| TOCTOU / PID 复用 | 用户看到 A，实际操作 B | 执行前重读稳定身份和 revision；不一致停止；进程绑定创建时间与映像身份 |
| 路径穿越/链接替换 | 隔离动作触及白名单外文件 | adapter 自行解析已枚举 item；规范化绝对路径；拒绝 reparse point/链接/UNC/设备路径；操作前后重新校验根目录 |
| 权限扩大 | 普通动作借 helper 执行任意操作 | 5A 无 helper；未来 helper 只接受固定二进制协议和内置动作 ID，不接受命令/路径；调用方认证、签名和生命周期另审 |
| 重复/部分执行 | 双击、超时、崩溃后状态不确定 | 幂等键、事务状态转换、执行后独立验证、重启不重放、显式 `interrupted/verification_failed` |
| 恢复覆盖新状态 | 回滚抹掉用户/第三方后续修改 | 恢复前比较 revision 和目标槽位；冲突时拒绝自动恢复并提供人工说明 |
| 审计泄密或被伪造 | 日志含路径/令牌，或记录与实际不符 | 参数哈希与脱敏摘要；禁止票据/令牌入日志；追加式动作事件；验证结果独立记录 |
| 资源滥用 | 大量计划/确认拖垮 sidecar | 每会话活动动作上限、每目标互斥、短超时、取消仅在尚未改变状态时生效 |

### 6.4 剩余风险

- 禁用启动项可能使用户依赖的软件不再自动启动；恢复仅在原状态未被其他程序改写时可靠。
- 杀进程会丢失未保存数据，无法真正回滚，因此 Phase 5B 必须单独批准。
- 服务状态改变可能影响系统稳定性或网络/安全能力，并引入 helper 攻击面，因此 5A 不实现。
- 本机已被高权限恶意软件控制时，普通用户进程内票据与审计不能构成强安全边界；本设计防止的是产品自身越权和常见本地请求伪造，不替代 EDR。

## 7. Phase 5A 实施边界

确认后才进行以下工作：

- 新增 domain Action Plan/Action/Recovery 模型及 application ports；依赖方向保持 `presentation -> application -> domain`。
- 新增 consent service、动作专用 policy/executor、当前用户启动项 Windows adapter。
- 新增 `action_plans`、`actions`、`user_confirmations`、`action_events`、`recovery_records` 迁移；不保存可重放票据。
- 新增计划、确认/拒绝、状态、恢复 API；所有接口继续使用现有 loopback 会话认证和 correlation ID。
- 新增逐项确认卡片、进度、验证失败和恢复 UI；不提供批量确认。
- 只注册 3.1 的两个工具；3.2/3.3 的能力在代码、Schema 和 UI 中均不存在。

## 8. 质量与安全验收

- 单元/契约：未知动作、非法 Schema、风险级别、权限、过期、重放、参数篡改、会话变化、并发消费全部拒绝。
- Windows adapter：注册表值变化、Startup 文件被替换、链接/reparse point、路径越界、访问拒绝、目标消失和恢复冲突。
- 生命周期：确认前取消、执行中断、验证失败、sidecar 崩溃/重启、恢复成功/冲突；重启绝不自动重放。
- 审计：每个动作都有计划来源、规范化参数哈希、确认决定、执行结果、验证结果和恢复状态；敏感值与票据不落日志/SQLite。
- 安全回归：只读 Agent Runtime 继续拒绝 `state_change/destructive` 与 confirmation 工具；模型无法获得动作执行入口。
- 危险集成测试仅在 Windows Sandbox/VM 运行；默认开发机测试只使用 fake adapter 和临时测试配置，不修改真实启动项。
- 完整门禁：后端 Ruff/mypy/pytest，前端 lint/typecheck/Vitest/build，Tauri fmt/test，Alembic 单 head 与升级/回滚，OpenAPI 重导出和契约检查。

## 9. 需要确认的结论

建议确认以下范围后再编码：

1. Phase 5 首个增量仅实现当前用户启动项的禁用与恢复。
2. 每个动作逐项确认，票据有效期最多 2 分钟、单次且绑定参数/目标/sidecar 会话。
3. Phase 5A 不创建 privileged helper，不终止进程，不切换服务，不修改网络或代理。
4. Phase 5B 的进程和服务动作必须在 5A 验收后另行安全复审和确认。
