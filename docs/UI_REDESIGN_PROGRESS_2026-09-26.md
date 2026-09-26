# UI 改造进度（暂停点）

对应 [UI_WINDOW_REDESIGN_PROTOCOL_2026-09-26.md](UI_WINDOW_REDESIGN_PROTOCOL_2026-09-26.md)。

## 已完成（源码，已提交）

- 协议第 1–3 步的实现：`bd8a300`（窗口行为、阅读浮窗、菜单与设置），以及本次暂停提交
  （原生监听 selector 修复、自检扩展、版本号 0.3.0）。
- 回归：offscreen 197 项通过；Cocoa 后端 `tests/ui tests/integration` 95 项通过；Ruff 通过。
- 源码进程的原生自检（`python -m lingoflow.diagnostics <dir>`，Cocoa）：20 次固定切换
  NSWindow level 在 8/0 间切换、同一原生窗口、0 次 Hide/Show/WinIdChange，几何、滚动和选区不变；
  旧 `pinned=true` 状态文件不再固定新窗口；每个窗口注册 2 个原生监听（全局点击＋应用激活），关闭后为 0。
- 自检发现并修复：应用激活监听曾用错 PyObjC selector（`..._handler_`），导致监听整体安装失败；
  单测的假对象沿用了同一错误名称，所以没能发现。现已新增对真实 AppKit 注册的回归。

## 尚未完成（下次从这里继续）

1. 构建签名 0.3.0 `.app`（建议 `dist/ui-redesign-20260926/`），运行包内 `--self-check`。
2. 备份 `/Applications/LingoFlow.app` 与 `~/Library/Application Support/LingoFlow/` 后替换安装，
   正常方式启动并核实版本、模型与用户偏好。**本机已安装的仍是 0.2.1，未被改动。**
3. 真实交互验收（协议第 7 节）：About 首次单击（后台/前台/有固定窗）、Settings；
   在浏览器/PDF/编辑器中各状态外部点击与 ⌘Tab；固定窗保持；冷启动关窗重开；
   阅读布局、浅深主题、小窗口。About 的“点两次”根因尚未实测确认：当前做法是菜单命令在
   菜单关闭后的下一轮事件循环执行、统一激活并前置，需要真实点击验证。
4. 更新 `manual_tests/README.md`（仍是 0.2.0 路径与旧窗口规则）、架构文档与验收记录，
   源码测试与安装包验证分开写明。
