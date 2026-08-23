# RC2：Local Validation Build 单机验证记录

记录日期：2026-08-23

## 验证范围与环境

- 定位：单机真实环境验证版，不声称完成正式发行验证。
- 系统：Microsoft Windows 11 家庭版 中文版，x64，版本 `10.0.26200`，约 16 GB 内存。
- 权限：普通当前用户；没有使用管理员权限、Windows Sandbox、虚拟机或代码签名环境。
- 安全边界：未运行 Phase 5 状态变更隔离测试，未执行 Shell/PowerShell 型 Agent 工具、注册表修改、服务修改或自动修复。

## 当前设备真实诊断

所有诊断均使用新建临时数据库、生产 Windows 适配器和 Fake Planner；网络诊断只访问应用固定目标。

| 用户问题 | 结果 | 真实工具状态 | 报告行为 |
| --- | --- | --- | --- |
| 电脑最近很卡 | completed / evidence_sufficient / 0.78 | CPU、内存、磁盘、高占用进程全部完成 | 检测到高占用进程；证据、时间和指标可追溯 |
| 游戏突然掉帧 | partial / evidence_sufficient / 0.60 | CPU、内存、磁盘、GPU 元数据、高占用进程全部完成 | 明确没有 GPU 实时负载/显存压力，当前快照不能单独确定掉帧原因 |
| 无法联网 | partial / evidence_sufficient / 0.65 | 代理和有界网络诊断全部完成 | 固定目标连通性较差，但明确 ICMP 不能单独确定无法联网原因 |
| 软件一直闪退 | partial / evidence_sufficient / 0.65 | 崩溃日志和进程快照全部完成 | 找到近期崩溃记录；因未提供应用名，明确记录可能与用户描述无关 |
| 电脑开机很慢 | partial / evidence_sufficient / 0.60 | CPU、内存、磁盘、高占用进程、启动项全部完成且无重复 | 启动项未形成异常结论，明确当前高占用快照不能证明开机慢原因 |

独立 Event Log 分析结果：Application 与 System 两个频道均成功，24 小时窗口内读取 22 条事件，形成 8 个事件组和 1 个崩溃组，无频道失败。数量只描述本次设备快照，不作为产品普遍结论。

## 异常与降级验证

- 单工具失败：保留其他成功证据，生成降权 partial 报告。
- Event Log 权限不足：单频道 `permission_required` 不丢弃另一频道结果。
- 数据为空/未达到阈值：输出“当前证据不足，无法确定原因。”，置信度为 0。
- 网络能力不可用：显示能力限制，不把读取失败写成“没有默认路由”。
- GPU 不存在或读取不可用：Quick Scan 保留其余结果并记录 `capability_unavailable`。
- 应用关闭：SQLite 不再保留空闲连接，数据库文件可立即移动或清理。

上述降级场景使用可重复故障夹具在当前 Windows 设备执行；当前物理设备的真实只读工具本次均成功，不能伪称已经自然遇到所有权限/硬件故障。

## 安装与生命周期验证

- 生成未签名 NSIS：`SysMind AI_0.1.0_x64-setup.exe`，22,325,280 bytes。
- SHA-256：`427387030a693507871d03ab77d39047231e5a7071a8d22d6f4440a4b233df30`，与 `SHA256SUMS.json` 一致。
- 静默当前用户安装成功，安装目录为 `%LOCALAPPDATA%\SysMind AI`；安装包和桌面可执行文件状态均为 `NotSigned`。
- 使用全新临时数据目录启动已安装桌面：目录和 `sysmind.db` 创建成功，Alembic 到达 `0010_phase32`。
- bundled backend 成功启动并只监听 loopback；命令行不含 session token。
- 第二实例退出且没有启动第二个后端；主窗口关闭后 owned backend 退出。
- 强制结束后端后桌面进程保持运行，失败可见；未发现遗留 SysMind 进程。
- 静默卸载成功，安装目录移除；`%LOCALAPPDATA%\ai.sysmind.desktop\sysmind.db` 被保留且哈希未变化。随后重新安装最终 RC2 构建，当前设备保留已安装状态。

未执行交互式卸载的“主动删除数据”选项，因为当前环境没有快照，删除真实用户数据不符合单机验证的安全边界。

## 最终质量门

- Backend Ruff：通过。
- Backend mypy：通过，120 个源文件无问题。
- Backend pytest：145 passed；4 个需要 Windows Sandbox/一次性 VM 明确授权的状态变更测试跳过。
- 真实 Windows 只读冒烟：6 passed。
- Frontend typecheck、ESLint、production build：通过；Vitest 34 passed。
- Impeccable UI detector：无发现。
- Rust fmt：通过；Rust tests 5 passed。
- Alembic：`0010_phase32 (head)`，RC2 无数据库迁移。
- `git diff --check`：通过；工作区仍保留此前未提交的 Phase 3.1–RC1 修改，没有覆盖或回滚。

## 现场发现并修复

1. 应用生命周期结束后 SQLite 连接池仍可能占用数据库文件。数据库引擎改用 `NullPool`，并增加退出后文件释放回归测试。
2. 进度区只显示“正在检查…”，用户不知道为何等待。现在直接显示 Planner 的中文步骤理由；等待补充信息时显示一次明确状态，不重复追问。
3. 开机慢、掉帧、泛化闪退和仅 ICMP 异常可能把“真实但场景关联不足”的证据表达得过于确定。现在增加场景限制并下调置信度，不把当前快照或不相关事件当作原因。
4. packaged desktop 脚本没有直接验证首次启动的数据目录和迁移 head。现在增加这两项检查，并确保验证脚本自身关闭 SQLite 连接。

## 单机 RC 判断

当前构建达到“个人 Release Candidate / Local Validation Build”标准：普通用户问题能够触发有限只读检查，真实本机证据可以形成可解释报告，缺失或弱关联证据会明确降级，安装后的本地后端和数据生命周期可运行。

它仍不是正式发布版。正式发布还需要外部的代码签名和更新签名凭据、多台 Windows 10/11 干净环境、不同硬件/权限策略、交互式安装升级卸载、杀毒软件兼容以及真实用户可用性复核。
