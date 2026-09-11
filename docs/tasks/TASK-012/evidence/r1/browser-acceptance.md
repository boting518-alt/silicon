# TASK-012 R1 浏览器复现

仅在隔离开发栈使用虚构数据，沿用既有可信 localhost 证书；不修改系统信任、不关闭校验。

## 准备

在仓库根设置 `SILICON_TEST_PG_BIN` 为 PG17 的 bin、`SILICON_TEST_KEYCLOAK_HOME` 为已验证的 Keycloak26.7.3 目录。Java21、既有 `.tools/tls/localhost.crt`/`.key` 与 `.tools/visual/PingFang.ttc` 要求同原任务说明。

```bash
SILICON_BROWSER_SERVICE_REPAIR=1 .venv/bin/python infra/browser_stack.py
```

夹具通过真实 API 生成订单、含两件批次内存的设备、发货、售后换件和已送出的 R1-RMA。**不预置返回、检验和处置**。夹具认证替身仅用于生成前置数据；下述页面使用真实 IdP 登录。

1. 打开 https://localhost:5173，以虚构 alice / Fictional-alice-17! 登录并选择企业 A。
2. 售后与部件 → R1-BATCH 对应工单 → 当前 RMA 选择 R1-RMA。
3. 数量 1、库位“虚构原料 A”、原件修复；登记第一批返回，检查后去向选“继续隔离”，确认。
4. 同行同库位再返回 1 件，再次选择继续隔离；两条记录均显示最终处置入口。
5. 第一条确认隔离件归还客户，另一条确认隔离件有据报废；处置依据使用虚构客户确认。
6. 刷新重新打开工单及 RMA，确认在外/待检为 0、旧件为分批不同处置且没有未处置入口；库存台账中客户层不再有隔离余额，自有成本不受两次处置影响。
7. 1440×900 和 390×844 检查与截图，记录 CSS 视口与实际图片像素差异。退出后关闭本次测试页面；停止栈并核对 BROWSER_STACK_CLEANED。

## 实际执行结果

2026-09-12，Codex IAB，真实 Keycloak 登录、API 与独立 PG。两批各 1 件通过页面返回、hold；页面排序中先选第二批“归还客户”，再将第一批“有据报废”。刷新后当前 RMA 在外 0、待检 0、旧件“分批不同处置”，没有未处置入口。库存页面隔离 0、自有已知成本 0.00，库存对账显示“台账与当前余额投影一致 · 差异 0”。逐阶段库存 2→1→0 和客户所有权/成本不变的精确断言由真实 PG/API 回归负责，不能将其冒充页面直接显示的数值。

[双隔离记录](browser-two-held.txt)、[剩余一条](browser-one-held.txt)、[处置完成](browser-disposed.txt)、[刷新后](browser-refreshed.txt)、[库存](browser-stock-final.txt)、[对账](browser-reconciliation.txt)、[退出](browser-logout.txt)。[截图清单](screenshots.json) 保留桌面与移动原图；CSS 视口实读1440×900和390×844，工具输出像素1425×891和375×812，未修改图片补齐尺寸。沿用原硅屿样式，产品前端源码/CSS未改，无新设计差异；本次新业务状态截图不是替换原始Demo基线。

首次在栈尚未就绪时打开页面发生 CONNECTION_REFUSED；等待 READY 后新开页面正常登录，无 TLS 错误或校验绕过。原错误页的 data URL 被浏览器工具拒绝读取，不作为验收证据。结束时退出登录、恢复视口并关闭验证页面；栈日志确认 BROWSER_STACK_CLEANED。

原 React 组件回归在 /tests/service-component.html 实际运行4项通过，见 [组件输出](react-components.txt)；此页使用 HTTP 替身，单独报告，不替代上述真实业务流程。浏览器不复放所有并发与权限分支，这些由 PG/API 覆盖。
