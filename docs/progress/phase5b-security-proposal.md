# Phase 5B 进程与服务动作安全复审记录

记录日期：2026-08-20
状态：**Superseded by ADR-011 — 用户已要求连续完成 Phase 5；最终白名单与拒绝项以 ADR-011 为准**

> 本文保留为威胁模型历史记录。最终实现包含 B1，以及只能从 `close_pending` 创建、双重确认
> 的 B2。B3 因服务白名单为空而正式拒绝，不创建 helper。真实状态变更验收仍不得在开发机
> 运行，尚待一次性 Sandbox/VM 执行。

## 1. 复审结论

不建议把“强制终止进程”和“服务启停”作为一个增量实现：前者不可恢复且可能丢失未保存数据，
后者引入管理员 helper、UAC 和新的高权限 IPC 攻击面。建议拆为三个独立关卡：

1. **Phase 5B1（本次建议批准）**：仅实现 `process.request_close_current_user@1.0`，向当前
   用户、当前会话、带顶层窗口的普通 GUI 进程发送受控关闭请求；不调用
   `TerminateProcess`，不杀进程树，不提权。
2. **Phase 5B2（默认拒绝，另行复审）**：候选 `process.terminate_current_user@1.0`，强制
   终止普通用户进程。必须在 B1 的 Sandbox/VM 数据证明“请求关闭不足”后才能讨论。
3. **Phase 5B3（仅设计，不实现）**：候选 `service.change_state@1.0`。只有独立 helper 的
   签名、UAC、IPC、服务白名单和恢复策略全部通过安全评审后，才能开始编码。

批准 B1 不等于批准 B2/B3。Phase 5A 的真实 Sandbox/VM 验收仍是 B1 编码的硬前置条件。

## 2. Phase 5B1 唯一动作白名单

| Tool | 风险/确认 | 固定输入 | 允许目标 | 执行与验证 |
|---|---|---|---|---|
| `process.request_close_current_user@1.0` | `state_change` / `each_time` | 不透明 `process_item_id`、`observed_revision` | 最近一次受控进程采样中，属于当前交互用户 SID、当前 Session、至少有一个可见顶层窗口、不是 SysMind/系统保护对象的单个进程 | 重新核验 PID、创建时间、用户 SID、Session、映像身份和窗口归属；仅向该 PID 的顶层窗口发送 `WM_CLOSE`；最多等待 8 秒；重新读取进程状态，区分 `closed`、`close_pending`、`declined`、`target_changed` |

### 2.1 B1 计划来源

- Action Plan 必须关联已完成/partial 的性能诊断。
- 诊断必须包含成功的进程快照或高占用采样，并有 finding 直接引用目标进程证据。
- 候选项由 application 层用最新本地进程枚举与原 finding 交集生成；模型只能解释，不能增加候选。
- 候选有效期最多 30 秒。超时、窗口变化、PID 重用或进程身份变化都要求重新生成计划。
- API/UI 只接收应用生成的不透明 ID，不接收任意 PID、窗口句柄、路径、命令或进程名。

### 2.2 B1 用户确认内容

确认卡片必须逐项展示：

- 应用显示名与可执行文件名；完整路径默认不显示。
- 当前 CPU/内存证据及采样时间。
- “应用可能提示保存；SysMind 不会替你确认放弃未保存内容”。
- “请求可能被应用拒绝或暂缓；系统不会升级为强制终止”。
- 目标身份重新核验、8 秒验证窗口和确认票据两分钟有效期。

拒绝与确认都写入现有动作审计。不得批量确认、记住决定或后台自动关闭。

## 3. B1 进程身份与保护策略

### 3.1 稳定身份 revision

revision 至少绑定：

- PID 与进程创建时间（防 PID 重用）；
- 进程访问令牌的用户 SID；
- Windows Session ID；
- 规范化映像路径的本地哈希；
- 可取得时的卷序列号 + 文件 ID；
- 顶层窗口句柄集合的排序哈希；
- 采样时间与 Schema 版本。

路径、SID 和窗口句柄不进入前端、模型或普通日志；只保存脱敏显示值与 revision 哈希。

### 3.2 必须拒绝的目标

- PID 0、4、当前动作执行进程，以及 SysMind Tauri、sidecar、未来 helper 的完整进程树。
- 不属于当前交互用户 SID，或不在当前 Windows Session 的进程。
- Windows 报告为 critical/protected/PPL 的进程，或无法安全读取身份的进程。
- 提权级别高于调用方、AppContainer/安全边界不明、正在退出或身份变化的进程。
- 没有可见顶层窗口的后台进程、服务宿主、驱动相关进程和控制台-only 进程。
- Windows 登录、Shell、桌面合成、安全、凭据、会话、任务管理和系统恢复关键组件。
- 固定保护名至少包含：`System`、`Registry`、`smss.exe`、`csrss.exe`、`wininit.exe`、
  `services.exe`、`lsass.exe`、`winlogon.exe`、`dwm.exe`、`fontdrvhost.exe`、
  `sihost.exe`、`taskhostw.exe`、`explorer.exe`、`taskmgr.exe`、安全软件和 SysMind 自身。

名称列表只是第二道防线；系统 critical/protected 状态、SID/Session、进程树和窗口归属核验才是
主要控制。任何探测失败都按不可操作处理。

### 3.3 Windows adapter 边界

- 使用 Win32 进程/令牌/窗口 API，不调用 Shell、PowerShell、CMD、taskkill 或任意命令。
- 枚举由目标 PID 拥有的可见顶层窗口，只发送固定 `WM_CLOSE`，不接受消息 ID或窗口句柄输入。
- 每个窗口最多发送一次，调用有界；不注入 DLL、不写进程内存、不附加调试器。
- 8 秒内轮询只读进程状态。应用仍存在时返回明确非成功状态，不追加其他动作。
- 关闭后不自动重启应用。B1 没有可靠恢复动作，UI 必须明确这一限制。

## 4. Phase 5B2 强制终止候选（不批准实现）

`process.terminate_current_user@1.0` 暂不注册。未来若复审，至少增加：

- 风险等级 `destructive`、`double` 确认；第二次确认必须明确“未保存内容会丢失”。
- 只能基于一个刚刚返回 `declined/close_pending` 的 B1 动作创建，不能直接从诊断创建。
- 重新绑定 PID、创建时间、SID、Session、映像身份；任一变化立即拒绝。
- 仍然拒绝进程树、跨会话、提权、保护/关键进程和 SysMind 进程树。
- 只允许固定 `TerminateProcess`，不接受退出码或其他参数；执行后必须验证目标 identity 消失。
- 明确 `recovery_unavailable`，不得把“可重新启动”伪装成回滚。

在 B1 尚未完成隔离环境可用性评审前，不应请求批准 B2。

## 5. Phase 5B3 服务控制与 privileged helper（仅设计）

### 5.1 为什么暂不批准服务动作

当前服务枚举只提供名称、状态、启动类型、账户和二进制文件名，尚不足以证明某服务可安全停止。
Windows 核心、安全、更新、网络和第三方驱动服务的依赖关系会随版本与设备变化。使用“黑名单”
无法构成可靠安全边界，因此生产版本必须采用**空默认 + 版本化内置白名单**；在没有经评审的具体
服务名单前，用户可执行白名单为空。

### 5.2 候选 helper 架构

若未来批准，helper 必须：

- 独立最小 Rust/Windows 二进制、代码签名、短生命周期、每次动作单独 UAC；不得常驻。
- 只接受版本化二进制/结构化协议中的动作枚举、内置 `service_id`、期望状态和 revision；不得
  接受命令、脚本、服务名、路径、注册表、环境变量或任意参数。
- 使用随机命名管道，DACL 限定发起用户 SID 与 Administrators；拒绝网络管道。
- 每次启动生成 challenge。普通后端用进程内临时签名密钥签署 action envelope；helper 绑定
  protocol version、action ID、service ID、期望状态、配置 revision、nonce、过期时间和当前
  Windows 登录会话，并执行单次后退出。
- 独立重新读取服务配置、依赖、状态、服务 SID/账户和二进制身份；不能信任 UI/SQLite 快照。
- helper 自身再次执行服务白名单和保护规则，即使普通后端被绕过也不能扩大目标。
- 不保存 sidecar session token、确认票据或签名私钥；不记录完整路径或敏感服务参数。

### 5.3 服务动作未来最低规则

- 只允许 `running -> stopped` 或 `stopped -> running`，不修改启动类型、账户、恢复策略或配置。
- 每个 `service_id` 单独列出支持的方向、已知依赖、最长等待、验证方式和反向动作。
- 拒绝驱动服务、共享宿主关键组、存在未评审活动依赖的服务，以及安全、凭据、更新、网络核心、
  存储、事件日志、RPC、WMI、安装、备份与恢复相关服务。
- 停止前保存状态/配置哈希；验证失败时不自动连续重试。反向动作是新的计划、UAC 和确认。
- UAC 取消、helper 签名不可信、IPC 断开、超时和 sidecar 重启都标记为不确定/失败，绝不重放。

## 6. Phase 5B 威胁模型

| 威胁 | 影响 | B1/B2/B3 必须控制 |
|---|---|---|
| PID 重用/进程替换 | 关闭了用户未确认的另一个进程 | 创建时间、SID、Session、映像/文件身份、窗口集合 revision，执行前重读 |
| 模型或 API 注入任意 PID | 将受控动作变成通用进程管理器 | 仅应用候选不透明 ID；模型不进入动作执行路径；任意 PID/句柄字段不在 Schema 中 |
| 关闭系统/安全组件 | 会话崩溃、凭据或防护受损 | critical/PPL 检查、固定保护集、SID/Session/完整性级别和 fail-closed 探测 |
| 未保存数据丢失 | 用户工作不可恢复 | B1 仅 `WM_CLOSE`、明确说明、应用自己决定保存；B2 默认不批准且要求 double 确认 |
| 窗口句柄复用/跨进程窗口 | 消息发给错误窗口 | 发送前再次用 `GetWindowThreadProcessId` 验证 PID，固定消息，仅一次、有界等待 |
| 自杀或审计中断 | sidecar/UI 被关闭后状态不可追溯 | SysMind 完整进程树永久保护；动作状态先持久化；执行后独立验证 |
| helper confused deputy | 普通调用借管理员权限操作任意服务 | helper 内置空默认白名单、固定协议、独立策略重验、随机管道/DACL、挑战签名、单次退出 |
| helper 替换/降级 | 运行恶意或旧协议二进制 | Tauri 固定资源路径、代码签名与版本校验、协议版本锁定、禁止 PATH 搜索 |
| UAC/IPC 中断后重放 | 不确定状态下重复服务动作 | nonce、短期 envelope、单次 helper、动作幂等键、重启标记 interrupted、不自动重放 |
| 服务依赖竞态 | 停止关键依赖或恢复覆盖新状态 | helper 执行前重算依赖/config revision；变化即拒绝；恢复为新动作 |
| 审计泄密 | 暴露路径、SID、令牌或票据 | 保存哈希和脱敏显示值；票据/私钥/完整路径不落库、不进日志 |
| 本地同用户恶意进程 | 抢占 pipe 或仿造 UI 请求 | loopback session/Origin、随机 pipe、DACL、challenge/signature；承认同用户完全失陷不在强隔离能力内 |

## 7. 分阶段验收门

### Phase 5B1 编码前

- Phase 5A `destructive_sandbox` 两项测试必须在一次性 Sandbox/VM 中通过，并保存输出摘要。
- 明确批准本文件第 2、3 节；B2/B3 仍保持拒绝。

### Phase 5B1 交付前

- Fake adapter：确认过期/篡改/重放、重复点击、取消、重启、不确定验证。
- Windows Sandbox/VM：正常关闭、应用弹出保存、应用拒绝关闭、窗口消失、PID 重用模拟、跨
  Session/不同 SID、提权进程、保护列表和 SysMind 自身保护。
- Agent 安全回归：模型、只读 Registry/Executor 和诊断 API 均无法调用 B1。
- UI：明确非强制、无自动升级、逐项确认、8 秒验证结果及不可恢复限制。
- 完整 lint/typecheck/test/build、迁移升级/回滚、OpenAPI、审计脱敏检查。

### Phase 5B2/B3 编码前

- 分别提交新的动作白名单和威胁模型差异并再次确认。
- B3 必须先冻结具体服务白名单；白名单为空时不得创建 helper 占位模块。
- 所有状态变更集成测试仅在 Sandbox/VM 快照中运行。

## 8. 需要确认的结论

建议在取得 Phase 5A 隔离测试通过结果后，仅确认：

1. Phase 5B1 唯一动作是 `process.request_close_current_user@1.0`。
2. B1 仅作用于当前用户、当前 Session、带可见顶层窗口、非保护的单个 GUI 进程。
3. B1 只发送固定 `WM_CLOSE`，不会自动升级为强制终止，也不提供批量或后台执行。
4. `process.terminate_current_user@1.0` 继续不实现，等待 B2 单独复审。
5. `service.change_state@1.0` 与 privileged helper 继续不实现；具体服务白名单为空，等待 B3
   单独复审。
