# TASK-008 R1/R2 定向浏览器证据

真实Codex IAB + Keycloak登录 + 自建PostgreSQL，沿用已获信任的本机TLS与原字体；无证书绕过、无系统信任更改。初次打开早于栈就绪，连接拒绝；等待BROWSER_STACK_READY后正常进入，不是安全警告绕过。

从仓库根设置 SILICON_TEST_PG_BIN、SILICON_TEST_KEYCLOAK_HOME 后运行：

```bash
SILICON_BROWSER_INVENTORY_REPAIR=1 SILICON_BROWSER_INVENTORY=1 SILICON_BROWSER_CONTRACTS=1 SILICON_BROWSER_CATALOG=1 SILICON_BROWSER_CATALOG_SEED=1 .venv/bin/python infra/browser_stack.py
```

PG17.11/Keycloak26.7.3/Java21.0.6及TLS/字体准备沿用TASK008原browser-acceptance与README。测试前置由infra/inventory_review_examples.py通过仓库API/session替身准备：一个已生效采购合同/订单/收货草稿、一个REPAIR-ATTACH待测草稿，以及一件成本10.00的已导入期初库存，期初已关闭。这些是明确虚构前置，不计作本轮浏览器业务录入。浏览器实际认证为alice/Fictional-alice-17!，企业A；非生产认证路径。

## 实际操作

1. 真实登录/选择A，打开采购、REPAIR-ATTACH。文件选择器上传fixtures/invalid.pdf，明确显示“附件不是可读的 PDF/JPEG/PNG。”；然后上传仓库TASK007的fictional-proof.pdf，实际显示保存成功，查询附件出现下载按钮。
2. 浏览器确认测试合同生效，页面变为已生效、上传入口禁用。此为隔离虚构合同，不是外部签约。
3. 使用测试栈自有.tools/browser-runtime.json定位唯一临时PG/文件根，仅在该根将PDF和CSV设为超过24小时，同时创建一个虚构孤儿。真实clean dry-run/apply均为1，两个有效原件及SHA256不变。browser-cleanup.json保留结果；不操作常驻DB或用户文件。
4. 实际点击“fictional-proof.pdf · 下载”，页面无错误；真实服务端file-object审计确认allowed。自动化等候下载事件10秒超时，未获得落盘产物，因此**浏览器下载文件校验not_run**。不把服务端文件/hash或PG/API字节回归冒充落盘验证。初次审计探针遗漏租户上下文/混入通用权限检查，修正后只检查file-object记录，见browser-download.json。
5. 打开前置已生效PC-72f06ffd，最终采购时间线显示关联PO-82c390b6与一件收货草稿；已保存DOM及桌面截图。切期初导入，确认当前关闭、预校验CSV按钮禁用。
6. 库存对账显示一件合格自有、已知成本10.00、未知0，台账与投影差异0。桌面1440×900、移动390×844实际查看；导出1425×891/375×812，未缩放图片。移动表格按原设计横向滚动。
7. /tests/inventory-component.html 实际React+HTTP替身2项passed：同意图丢响应重试、旧企业成功响应不污染新企业。不是PG或真实采购验收替代。

本轮无视觉代码变更。人工核对沿用既有奶白、深绿、留白、侧栏和圆角卡片；不更新旧截图、不将前置演示称为真实供应商业务。screenshots.json记录新图原始尺寸/哈希。浏览器视口已reset，栈由SIGTERM正常退出，browser-stack.txt包含BROWSER_STACK_CLEANED。

未重跑前次完整两批收货流程或其他浏览器；本轮针对修复与先前缺失的最终界面细节。流式无Content-Length/超过限额停止由ASGI+真实PG测试验证，未在浏览器制造大规模上传流量。自动化未返回下载产物为已知限制。
