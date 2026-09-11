# TASK-010 真实浏览器验证

使用既有可信 HTTPS（localhost:5173 → 真实 Keycloak 127.0.0.1:8443），没有修改系统信任或关闭校验。PG/IdP/文件根均隔离。前置虚构API夹具建立签约订单SO-CON-001三台、三次完工DEL-0/1/2，原成本80/80/20；测试、发货、验收、退货由本轮真实浏览器点击完成，不预种。

## 操作与结果

1. alice真实登录→企业A→交付与验收；三台显示待测试。逐台保存测试通过。
2. 首批DEL-0/1保存草稿（不出库）→确认：累计发出2、待履约1、成本160。
3. 第二批DEL-2确认：累计3、待履约0、成本180。
4. 首批只选DEL-0验收：净验收1，其他仍待验收。见evidence/browser-partial-accept.txt。
5. 确认DEL-0实物退回：库存pending，累计发出3、退回1、净交付2、净验收0、待履约1、净出库成本100。见browser-returned.txt。
6. 退回未复测新建草稿再确认，后端DEVICE_TEST_REQUIRED，页面显示真实阻断。见browser-retest-block.txt。
7. 追加复测通过→原重发草稿确认→刷新重开：累计发出4、退回1、净交付3、待履约0、净成本180。稳定设备4dfc108c-b135-4633-95d5-5f1c5e924351仍相同，原发货/验收/退回和新发货均在履历。见browser-refreshed.txt。
8. 企业B无A设备或发货，写控件禁用；退出经IdP确认后重开要求登录。见browser-enterprise-b.txt、browser-logout-final.txt。

会话自然到期后通过正常SSO重新登录，未绕过认证。开发固定前端时钟2026-09-08、字体和禁动画沿用现有基线；输入执行日期是虚构人工登记时间，服务器接收顺序另存，不据回填时间覆盖最新测试。源码样式热更新曾使页面返回客户入口，重开后原草稿仍在，未重建数据。

## 视觉

1440×900：delivery-desktop-final.jpg；390×844：delivery-mobile-data.jpg、batch-mobile.jpg。保留原浅灰背景、深绿汇总卡、侧栏/窄屏导航、圆角及表单。首次截图delivery-desktop.jpg为未补齐表单样式的中间状态；delivery-mobile.jpg为视口切换后的中间缩放截图，delivery-mobile-final.jpg为企业切换尚未完成的中间状态，均不能当最终通过截图。最终选择上述-data/-final和batch文件。截图工具实际输出桌面1425×891、移动375×812像素（含浏览器捕获缩放/滚动条差异）；测试CSS视口设置为1440×900和390×844，移动DOM读回innerWidth=390、innerHeight=844、scrollWidth=375，无横向溢出。未盲目替换原Demo基线；原Demo没有这套真实状态，新增进度、测试及退货控件是明确的本轮变化。

真实浏览器完成核心闭环；追加的设备档案内同源履约列表及对账API在之后的小改动由类型/构建/PG覆盖，未再次重跑完整浏览器闭环。其他浏览器/容器/远程CI未执行或未核实。

## 组件证据与复现

/tests/delivery-component.html 使用实际React、HTTP替身，仅验证创建响应丢失重试、新建意图隔离及旧企业延迟成功响应。2项通过，见evidence/component.txt，不冒称PG或真实OIDC。

从仓库根：设置SILICON_TEST_PG_BIN和SILICON_TEST_KEYCLOAK_HOME；已有合法字体/可信证书后执行：

```bash
SILICON_BROWSER_DELIVERY=1 SILICON_BROWSER_CONTRACTS=1 SILICON_BROWSER_CATALOG=1 .venv/bin/python infra/browser_stack.py
```

浏览器 https://localhost:5173，虚构alice / Fictional-alice-17!，企业A。上述顺序可重复；SIGTERM/Ctrl-C只清理该栈自己的进程/临时目录。结束日志BROWSER_STACK_CLEANED已确认。
