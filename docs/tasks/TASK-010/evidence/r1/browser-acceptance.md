# TASK-010 R1 真实浏览器与组件验证

2026-09-11，Codex in-app Chromium，真实 HTTPS / Keycloak / FastAPI / 临时 PostgreSQL17.11。沿用可信 localhost 证书，无关闭 TLS、信任变更、常驻库或原 Demo 写入。虚构 alice / Fictional-alice-17!；企业A预置已签订单及三台完工 DEL-0/1/2，无交付/测试预置。

## 启动与复现

从仓库根设置 `SILICON_TEST_PG_BIN` 为 PostgreSQL17.11 bin，`SILICON_TEST_KEYCLOAK_HOME` 为已验证 Keycloak26.7.3 目录（准备脚本与要求见README、审查包）。Java21；现有 `.tools/tls` 可信本地证书/私钥及 `.tools/visual/PingFang.ttc` 为外部准备材料，不打包。不要在 Reviewer 机器照抄原始日志中的本机目录。启动：

```bash
SILICON_BROWSER_DELIVERY=1 SILICON_BROWSER_CONTRACTS=1 SILICON_BROWSER_CATALOG=1 .venv/bin/python infra/browser_stack.py
```

1. 打开 https://localhost:5173，真实 IdP 登录，选择企业A。交付页选择 DEL-0，保存虚构测试通过；未执行发货。
2. 设备查询 → DEL-0详情：基础资料、安装来源、测试通过历史同时显示。
3. 保持页面，另终端执行 `.venv/bin/python infra/device_permission_fixture.py revoke`。仅改活动临时集群 admin 的 delivery.read，不影响 device.read 等原授权。
4. 不刷新权限元数据，重新点击 DEL-0详情：真实交付请求403，原测试通过历史消失，基础品牌/订单/实物/安装数据仍可见，明确提示“交付查询权限不足或已撤销”。见 browser-revoked-dom.txt 和 desktop-revoked-detail.jpg。
5. 装配工单正常列出3台已完工工单，可打开并运行工单数量与成本对账；结果一致（browser-assembly-dom.txt）。设备页搜索 DEL-0，只返回对应设备并可打开基础详情，无交付历史。此时新元数据已反映无权，提示“未授权查看交付历史”。
6. 移动390×844刷新整个页面，重新进入设备查询、搜索DEL-0、打开详情，持久化基础数据仍存在；未授权提示仍在。安装表保留原有横向滚动容器，页面不横向溢出。
7. `.venv/bin/python infra/device_permission_fixture.py restore`，刷新查询并打开DEL-0，原真实测试记录重新显示（browser-restored-dom.txt）。切换企业B无A设备/历史；退出并确认IdP Logout，回到要求登录页（对应DOM证据）。
8. SIGTERM仅发送给本次browser_stack进程，日志 BROWSER_STACK_CLEANED；其finally清理临时PG、IdP、API、文件和Vite，`.tools/browser-runtime.json`删除。没有残留测试角色变更到其他数据库。

## 实际结果与范围

以上步骤通过。记录桌面1440×900和移动390×844 CSS视口；最终截图工具实际输出1425×891 /375×812；desktop-revoked.jpg为视口刚切换时1425×802中间捕获，保留但不作为最终尺寸证据（滚动条和缩放），不是宣称物理截图像素等于CSS视口。移动实测innerWidth390、innerHeight844、scrollWidth375。screenshots.json列文件尺寸及哈希。

沿用既有硅屿浅绿/灰底、圆角卡片、侧栏和移动导航；本次不改CSS或字体。意图变化：列表显示基础设备资料并引导详情查询交付状态，避免未授权时误标“待测试/未发货”；详情新增加载/失败/无权提示。对照既有TASK-009/010设备和交付证据及 docs/design/demo-baseline.md，不更新历史视觉基线，也不冒称原Demo已有权限状态。

组件页面 `/tests/device-permissions.html`：实际React和HTTP替身，3 passed，覆盖无交付权限的设备/工单交互、真实组件403清除、显式延迟成功history后关闭详情及切企业的竞态。`assembly-component.html`和`delivery-component.html`各2 passed，保留创建重试幂等意图及跨企业迟到成功响应。首次新组件在旧实现下失败，component-red.txt记录真实浏览器观察；不是PG红灯。本次PG权限检查用于固定已有后端授权，后端生产实现未改变。

首次访问组件时服务尚未就绪，连接拒绝；等日志 READY 后重试成功，未绕过浏览器安全。权限辅助脚本首次尝试由迁移角色读取 data_directory，被PG正确拒绝；改为连接前校验既有临时集群postmaster标记端口，不提高数据库角色权限。该错误保留browser-permissions.txt，非产品缺陷或通过证据。

本轮未重跑完整发货/退货业务浏览器流程（R1不改交付业务，只验证查询权限），历史TASK-010全流程证据保留。成本隐藏和delivery-only的精确字段规则由真实PG/API覆盖；本轮真实浏览器使用admin成本可见身份。其他浏览器、Docker、远程CI、生产环境未验证。
