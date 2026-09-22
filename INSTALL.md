# 安装 SysMind AI v0.1.0-preview

SysMind AI v0.1.0-preview 是面向 Windows 10/11 x64 的单机预览版。安装后的桌面程序已包含
本地后端，普通用户不需要另外安装 Python、Node.js 或数据库。

## 下载与校验

1. 从项目的 [GitHub Releases](https://github.com/lanmaolanglang-ops/SysMind-AI/releases) 页面下载
   `SysMind AI_0.1.0_x64-setup.exe` 和对应的 `SHA256SUMS.json`。
2. 在 PowerShell 中计算安装包校验值：

   ```powershell
   Get-FileHash -Algorithm SHA256 -LiteralPath '.\SysMind AI_0.1.0_x64-setup.exe'
   ```

3. 确认输出与该 Release 附带的 `SHA256SUMS.json` 完全一致。

当前 Local Validation Build 尚未进行 Windows 代码签名，Windows 可能显示“未知发布者”或
SmartScreen 提示。它只能作为预览构建使用。不要从第三方下载站获取或运行校验值不一致的
安装包。

## 安装与首次启动

1. 运行安装包并按界面提示完成当前用户安装；不需要管理员权限。
2. 从开始菜单或桌面快捷方式打开 SysMind AI。
3. 首次启动会创建本地数据目录并执行数据库迁移，所需时间可能比后续启动稍长。
4. 看到“本地服务已连接”后即可开始诊断。

安装程序默认安装到 `%LOCALAPPDATA%\SysMind AI`。应用数据默认保存在
`%LOCALAPPDATA%\ai.sysmind.desktop`，其中可能包含诊断历史、脱敏事件摘要、报告、操作审计
和恢复记录。

默认诊断使用本地确定性 Planner，不需要 API Key。只有用户主动配置远程 Provider 后，才会
产生相应的远程模型请求；发送范围见 [隐私说明](docs/privacy.md)。

## 升级与卸载

- 升级会保留本地数据库并向前执行迁移。
- 数据库迁移不支持降级。不要用旧版本直接打开已升级的数据目录。
- 静默卸载会保留 `%LOCALAPPDATA%\ai.sysmind.desktop`。
- 交互式卸载提供单独的数据删除选项；只有明确选择后才会删除应用数据。
- v0.1.0-preview 的交互式删除路径尚未在一次性虚拟机中完成验证。删除前请先导出需要保留的报告。

## 开发者从源码运行

源码环境、测试与本地打包命令见 [README](README.md#development-requirements)。不要把开发目录、
`.sysmind-data`、虚拟环境或构建缓存作为源码发布包上传。
