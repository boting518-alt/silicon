# TASK-008 真实浏览器验收与复现

本次使用 Codex IAB、真实 Keycloak 登录、隔离 PostgreSQL 和页面点击。HTTP 替身仅用于另一个组件页，不作为采购闭环证据。已有 localhost 开发证书与字体未修改；没有忽略 TLS 错误。原 Demo 未修改。

## 准备

从仓库根设置 `SILICON_TEST_PG_BIN="$PG17_HOME/bin"`、`SILICON_TEST_KEYCLOAK_HOME="$KEYCLOAK_HOME"`；PG17.11、Keycloak26.7.3、Java21.0.6，准备步骤见 README 及审查包 manifest。浏览器前先结束后端集成测试，避免 IdP 端口争用。仓库 `.tools/tls/localhost.crt` 和 `.key` 需是本机已获授权信任的 localhost/127.0.0.1 证书；不得复制其他机器私钥或关闭校验。缺少信任时先取得授权，本任务没有修改系统信任。字体按 `infra/browser_stack.py` 校验，使用合法可用的 PingFang.ttc，不偷偷换字体。

```bash
SILICON_BROWSER_INVENTORY=1 SILICON_BROWSER_CONTRACTS=1 SILICON_BROWSER_CATALOG=1 SILICON_BROWSER_CATALOG_SEED=1 .venv/bin/python infra/browser_stack.py
```

打开 https://localhost:5173 。虚构 alice / Fictional-alice-17! 是 A 管理员、B viewer。carol / Fictional-carol-17! 由本测试标志明确设为 A 仓库 member；其旧显示名“虚构只读用户”不代表当前权限。种子只准备身份、客户及已有目录，无采购或库存预置。此配置不开放生产认证替身。

## 已实际完成的闭环

1. 登录 alice，选择 A，采购与库存 → 基础资料。新增虚构北辰硬件供应商、虚构测试仓 A-01/B-02；DEMO-BARE 配 batch，DEMO-HOST 配 SN。
2. 开启期初。第一次未知 SKU 文件预校验拒绝，库存未增加。最初日期控件显示与 React 状态不同，实际保存截止日是 2026-09-08；随后 2026-01-01 文件明确 CUTOFF_MISMATCH，未入账。保留两次错误证据，未改数据库截止日。
3. 使用实际库位 UUID 和实际保存截止日生成正确 CSV：DEMO-BARE，2 件自有合格，批号 FICTIONAL-OPEN，单位成本20.00。预览通过后明确提交，库存2、已知成本40.00。关闭期初。仓库含精确实际上传文件，但其 UUID 仅属当次夹具，重现请用下面脚本替换。
4. 新建并生效采购合同 PC-DEMO-008，DEMO-HOST 数量5、单价100.00、税口径待确认；建立 PO-DEMO-008 并确认。
5. 原日期控件问题造成一张未过账收货草稿日期仍为09-08；尝试过账时真实会话过期，明确拒绝，不能计作过账成功。重新登录/选择 A 后修复控件 onInput，同样的浏览器日期操作已使新草稿保存09-11。旧草稿保留不计库存。
6. 两批新收货：2件 SN01/02，再3件 SN03/04/05，完整 SN 为 DEMO-SN-01 至05；单位成本80.00、confirmed、虚构确认依据。实际过账两次，未到5→3→0。
7. SN01～04逐件质检合格，SN05隔离，结论与原因真实提交；SN01从A-01移到B-02。原物理身份不变。
8. SN搜索、清空搜索、库存对账、刷新查询：台账/投影差异0，合格自有6（期初2+采购4），隔离1，已知成本440.00（40+400），未知0。
9. 切换B后无A库存，切回A刷新仍有原记录。退出真实IdP并以carol登录：数量与位置可见，成本表头/金额不存在。API不下发成本另由真实PG测试验证，不只凭截图。
10. 1440×900和390×844检查、截图。IAB导出分别1425×891和375×812，原图保留未缩放；窄屏表格有受控横向滚动，文档无整体横向溢出。

```bash
.venv/bin/python infra/create_inventory_test_csv.py "$TMPDIR/task008-opening.csv" --location-id "$TEST_LOCATION_ID" --cutoff "$OPENING_CUTOFF"
```

该脚本只写虚构CSV，不连接数据库，不覆盖已有文件。日期使用已保存截止日。错误场景可复制新文件并将SKU改为不存在编号。上传/预览/明确提交均由页面执行。

## 组件与视觉证据边界

`/tests/inventory-component.html`：实际React、HTTP替身，2项通过：响应丢失重试保持同键且不假成功；旧企业成功响应延迟不能污染新企业。生产构建不把测试页作为入口。原Node19项测试单独记录。

[evidence/screenshots.json](evidence/screenshots.json)记录图片校验和、视口及导出尺寸。`inventory-desktop-layout-diagnostic.jpg`为初始排版诊断，最终卡片补回原有留白、按钮宽度与移动表格滚动；不是新模板。对照资料在[原Demo基线](../../design/demo-baseline.md)及TASK003历史图片，本轮为人工视觉对照，未执行自动像素阈值比对。

最终追加的采购来源时间线（以真实订单/收货/移动关系派生）、关闭期初预览按钮、成本对账金额明细已通过最终类型/构建或PG验证；上述浏览器完整闭环发生于这些收尾修改之前，未重演整套浏览器操作，不把旧截图称为这些新细节的实测。

`browser-stack.txt`记录 BROWSER_STACK_CLEANED。验收后仅停止本测试栈，恢复浏览器视口；未停止常驻数据库。Docker容器、其他浏览器及生产场景 not_run。
