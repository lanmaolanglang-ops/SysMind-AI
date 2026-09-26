# 2026-09-26 工程改进与验收记录

## 基线与审查范围

- 分支：fix/rc-cross-machine-round2。开始时 DiagnosisPanel.tsx 的历史报告选择/导出入口及 styles.css 的高级工具层级已有未提交修改；本次复核后保留并纳入提交。未执行破坏性 Git 清理或覆盖。
- 当前技术栈：Tauri 2、React 19、TypeScript、Vite、FastAPI、SQLAlchemy、SQLite、Alembic。修改前核对 README、PRD、适用 ADR、依赖清单、启动与打包脚本；历史审计只作待复核线索。
- 清点后端第一方源文件 126 个、桌面前端 37 个、Tauri 4 个、脚本 9 个；覆盖七个页面、共享 API 客户端、任务状态、受控动作、数据库与迁移、Windows 适配、sidecar 和打包链路。采用源码抽查、静态搜索、门禁、定向回归及桌面运行。生成文件、第三方依赖、.venv、node_modules、dist、target 不逐行审查；生成的 OpenAPI 类型与版本另做一致性检查。此范围不保证发现全部缺陷。
- 实机只读运行使用隔离应用数据目录 .sysmind-data/validation-20260926；普通用户数据与真实凭据未用于验收。含本机设备或事件摘要的流程截图留在被 Git 忽略的验证目录。

## 覆盖清单

| 范围 | 审查与修改 | 验证 |
| --- | --- | --- |
| 问题诊断、证据、报告、受控动作 | 恢复任务/报告；改进证据摘要、首屏、文案与动作样式 | 12 项前端测试 PASS；真实只读诊断与重启恢复 PASS；危险执行 BLOCKED |
| 设备扫描 | 修复初始历史竞态；重构首屏与状态 | 3 项前端测试 PASS；打包桌面扫描、取消、重试 PASS，硬件采集结果 partial |
| 事件日志 | 修复 ID 校验、历史竞态；重构筛选布局 | 3 项前端测试 PASS；桌面只读查询 PASS |
| 历史与审计 | 单源失败时保留成功记录；统一列表与错误状态 | 3 项前端测试 PASS；重启后记录可见 PASS；删除执行 BLOCKED |
| 模型与隐私 | 修复表单竞态、清理范围提示；统一表单与确认 | 5 项前端测试 PASS；真实在线供应商 BLOCKED |
| 受限 Agent | 修复初始历史竞态；整理导航、标签与中文文案 | 3 项前端测试 PASS；真实在线 Agent 未执行 |
| 应用更新 | 保留真实更新入口并整理文案、状态与布局 | 4 项前端测试 PASS；签名更新 BLOCKED |
| 后端 API、任务、工具、数据库、安全 | 复核权限、CAS、事务、停止态和敏感字段；本轮无后端源码改动 | Ruff、MyPy、pytest PASS；4 项 Sandbox/VM 测试 SKIPPED |
| Tauri sidecar、契约、打包 | 修复进程竞态；收窄 Vite 文件监视 | Rust 16 项 PASS；契约/版本 PASS；本地打包与生命周期 PASS |

## 已确认缺陷与修复

| 编号/级别 | 位置、触发与影响 | 证据、修复和验证 |
| --- | --- | --- |
| SM-01 / 中 | DiagnosisPanel.tsx：离开再进入运行中的诊断，进度与取消入口消失 | 回归修复前 FAIL；恢复最近未完成任务并继续轮询，修复后 PASS |
| SM-02 / 中 | LogAnalysisPanel.tsx：事件 ID 含字母、超界或过多时被静默丢弃/截断，可能扩大查询 | 回归修复前 FAIL；明确报错、标记输入无效并禁用提交，修复后 PASS |
| SM-03 / 中 | 扫描、日志、Agent 页：迟到的初始历史响应覆盖新任务 | 扫描回归修复前 FAIL；初始响应只填空状态，卸载后忽略结果，修复后 PASS |
| SM-04 / 中 | DiagnosisPanel.tsx：返回已完成诊断时只加载列表，报告未自动选中 | 桌面复现、回归修复前 FAIL；默认选择最新报告且保留主动选择，回归与重启后实测 PASS |
| SM-05 / 低 | DiagnosisPanel.tsx：结构化证据显示长 JSON，普通数字显示“无法显示” | 桌面截图、回归修复前 FAIL；显示有限关键量与数字/单位，修复后 PASS |
| SM-06 / 中 | SettingsPanel.tsx：迟到的设置读取覆盖用户刚编辑的地址、模型或天数 | 回归修复前 FAIL；逐字段跟踪编辑并检查 abort，修复后 PASS |
| SM-07 / 高 | SettingsPanel.tsx：改了保留天数但未保存即可清理，界面所述范围可能与后端策略不一致 | 回归修复前 FAIL；只允许按已保存策略清理，确认文案显示确切天数，修复后 PASS |
| SM-08 / 中 | HistoryPanel.tsx：五个读取接口之一失败会隐藏全部成功数据；全部失败时错误与空态矛盾 | 两项回归修复前 FAIL；逐源显示成功数据，全部失败只显示错误，修复后 PASS |
| SM-09 / 高 | sidecar.rs：子进程退出后握手线程仍可能发布“已连接”；关闭收尾可能覆盖后来启动的状态 | 源码竞态审查；发布前检查代次、状态与进程存活，关闭收尾核对代次；新增 2 项 Rust 回归，16 项全通过 |
| SM-10 / 中 | vite.config.ts：开发中 Rust 重编译使 Vite 监视 target/debug DLL 报 EBUSY 并退出 | 实机复现；忽略 target 与 dist；桌面运行期间重跑 Rust 测试，Vite 保持运行 |

## 体验改进与视觉证据

- 用 ui-ux-pro-max 与 impeccable 核对信息层级。沿用绿灰品牌与 Windows 字体；七个真实页面纳入单一工作台导航。统一设计变量、表面、按钮、状态、焦点与响应式布局；版本和端口收在运行信息中，诊断入口移至首屏。所有页面继续连接原服务、任务和受控动作。
- 重构前：[问题诊断首屏](visuals/2026-09-26-before-diagnosis.png)。重构后：[问题诊断](visuals/2026-09-26-after-diagnosis.png)、[设备扫描](visuals/2026-09-26-after-scan.png)、[记录与报告](visuals/2026-09-26-after-history.png)、[事件日志](visuals/2026-09-26-after-logs.png)、[受限 Agent](visuals/2026-09-26-after-agent.png)、[模型与隐私](visuals/2026-09-26-after-settings.png)、[应用更新](visuals/2026-09-26-after-updates.png)。截图均来自真实 Tauri 窗口。
- 150% Windows 缩放下检查 1080×720 与约 760×600 逻辑像素窗口；[小窗口扫描](visuals/2026-09-26-small-scan.png)、[日志](visuals/2026-09-26-small-logs.png)、[设置](visuals/2026-09-26-small-settings.png)、[更新](visuals/2026-09-26-small-updates.png) 的导航、主操作、表单和滚动可用。长报告、日志需正常纵向滚动；未见横向截断或遮挡。样式支持可见焦点与减少动画；完整辅助技术人工验收未执行。
- 私有实机流程截图位于 .sysmind-data/validation-20260926/screens/，包括 diagnosis-evidence-final.png、logs-result.png、history-after-restart.png、packaged-scan-cancelled.png、packaged-scan-retry-final.png；因可能含设备或事件摘要，未加入 Git。

## 最终验收

| 检查 | 状态 | 结果与范围 |
| --- | --- | --- |
| 后端 Ruff / MyPy | PASS | Ruff 无问题；MyPy 126 个源文件无类型错误 |
| 后端 pytest | PASS | 223 passed、4 skipped、1 个 Starlette/httpx 弃用警告；跳过项不计入通过 |
| 前端 lint / typecheck / Vitest / build | PASS | 47 项测试全通过；Vite 生产构建完成 |
| Rust fmt / test | PASS | 16 passed；仅链接器生成库提示 |
| OpenAPI 类型 / 版本 / diff 格式 | PASS | 类型与版本同步；git diff --check 退出码 0 |
| 本地 NSIS 开发包 | PASS | 冻结后端 smoke、桌面打包生命周期、单实例、后端崩溃后桌面存活、退出清理通过。安装包位于 apps/desktop/src-tauri/target/release/bundle/nsis/SysMind AI_0.1.0_x64-setup.exe；SHA-256 为 cfb8dd4c1fd0e95be56a42723536681988e23a05ae7b1cbdb11b5f471201062a，与 SHA256SUMS.json 一致。未签名，非发布包 |
| 真实桌面只读旅程 | PASS | 启动连接、七页导航、扫描、诊断、日志、报告、历史与重启恢复均操作；扫描为 partial（GPU 不可用），诊断为 partial（证据不足），未计为完整成功 |
| 打包桌面取消、重试、重复点击 | PASS | 扫描取消为 cancelled；重试为 partial。快速双击前后数据库扫描数从 2 到 3，仅新建 1 个任务；关闭后所属 sidecar 与桌面进程均退出 |
| 实际系统修改、历史删除、安装/卸载 | BLOCKED | 缺少一次性 Windows Sandbox/VM；未在当前主机执行危险动作 |
| 真实在线供应商、签名更新 | BLOCKED | 无测试凭据与发布签名配置；模拟接口测试与真实联调分别记录 |

## 待验证风险与下一项工作

- 在一次性 Windows Sandbox/VM 中运行 scripts/run-phase5a-isolated-tests.ps1 -ConfirmIsolatedEnvironment，复核目标变化拒绝、停用/恢复、正常/强制关闭及审计；再用 scripts/run-phase6-isolated-tests.ps1 -InstallerPath <安装包路径> -ConfirmIsolatedEnvironment 做安装/卸载。隔离要求见 tests/integration/README.md。目前 BLOCKED。
- 在专用测试凭据环境中验证在线供应商连接、流式断流/限流与恢复；在受保护发布环境提供签名输入后验证真实更新及坏签名拒绝。目前 BLOCKED。
- 2026-09-22 已存在的打包产物精确备份在 .sysmind-data/validation-20260926/package-before-20260926；新包和备份均保留。下一项执行工作是上述隔离环境与真实凭据验收，随后再决定签名发布候选。
