# TASK-005 浏览器验收

日期：2026-09-10。实际交互完成；独立审查尚未进行，状态 review_ready。使用 Codex in-app browser / CUA 原生页面点击、输入、select、键盘、刷新与截图；不是 API 测试替代。沿用既有开发证书信任，本轮没有更改钥匙串、关闭 TLS 校验或忽略证书错误。

## 独立环境复现

从仓库根安装锁定依赖（README），准备 PostgreSQL 17.11 二进制、Java 21.0.6、Keycloak 26.7.3。后者可由 `infra/fetch_keycloak.py --destination .tools/keycloak` 下载并校验，PG 可由 `infra/build_test_postgres.py --prefix .tools/review-pg17` 编译；不启动常驻数据库。设 SILICON_TEST_PG_BIN 和 SILICON_TEST_KEYCLOAK_HOME 指向自己的安装目录。

准备 `infra/dev_tls.py` 生成的 localhost/127.0.0.1 证书；新机器必须自行获得用户授权建立浏览器信任，不能继承原机授权。原证书 SHA-256 45:A3:D2:BA:5C:17:0C:EC:C6:6A:D7:8D:F8:89:04:0C:9F:34:6F:A3:AD:65:5D:BD:56:98:BB:4F:64:75:85:46 有效至 2026-10-09，私钥不分发。字体 `.tools/visual/PingFang.ttc` 由合法本机字体提供，SHA-256 必须为 6bccdb1a967b2ae7e856927eb559591b2ce05656b0d4ad2764b9c9429f12c0b7；脚本缺失时失败，不回退其他字体。详见 [既有环境说明](../TASK-003/browser-acceptance.md)。

```bash
SILICON_BROWSER_CATALOG=1 SILICON_BROWSER_CATALOG_SEED=1 SILICON_BROWSER_QUOTES=1 .venv/bin/python infra/browser_stack.py
```

另设置上面的 PG/Keycloak 环境变量。脚本自行创建随机端口独立 PG、迁移到 0006、虚构企业/客户/目录/优惠和独立 Keycloak H2，然后启动 HTTPS 5173 / API 8000 / IdP 8443。不先执行 createdb/bootstrap，也不使用 .env 数据库。须先结束真实 OIDC pytest；端口冲突时不杀未知服务。Ctrl-C 后输出 BROWSER_STACK_CLEANED，清理自身 PG/子进程/临时数据；本轮该输出已保存。字体、证书和 Keycloak 安装包不随审查包提供。

真实 IdP 登录虚构 alice / Fictional-alice-17!，A 为 admin，B 为 viewer。种子 `infra/quote_examples.py` 仅测试栈开关显式调用；虚构型号和价格均标注非供应商资料，DEMO5=5% / 5000.00 CNY 上限，无次数限制/占用/核销。

## 实际交互与结果

| 检查 | 操作与观察 | 原始证据 |
|---|---|---|
| 登录、关联 | HTTPS Keycloak 登录，选择 A → 报价与利润 → 澄川大学 · 人工智能学院 / 科研平台 | saved-v1.txt 含真实页面关联 |
| 包件与 SVG | 已含电源 v1；CPU×1、GPU×2、内存×4、系统盘×1。点击 CPU 图形后对应型号字段获得焦点；SVG 数量随配置变化，展开/合拢可用 | svg-focus.txt、included-calculation.txt、桌面/手机 SVG 截图 |
| 权威计价 | 小计 84300.51，电源 included×2 不出现在商业收费行；缺资料 UNKNOWN，不是兼容通过 | included-calculation.txt |
| 折扣拒绝/应用/移除 | NOT-CONFIGURED 显示拒绝；DEMO5 优惠 4215.03、结果 80085.48；移除回到 84300.51；再应用后保存 | discount-rejected/applied/removed.txt、saved-v1.txt |
| 持久化 | 保存“虚构科研服务器报价”v1，刷新后从已保存草稿重新打开，客户/项目/部件/优惠仍在；修改整机数量 2 时旧试算立即隐藏，保存 v2 | saved-v1.txt、unsaved-quantity.txt、saved-v2.txt |
| 再次恢复 | 再次刷新/重新打开 v2；小计 168601.02，折扣受上限约束为 5000.00，总额 163601.02。随后企业切回 A 再打开与移动截图仍为 v2 | mobile-dom.txt、quote-mobile-summary-390.jpg |
| 不含电源 | 在恢复后的配置改选不含电源 v1，未追加时 BLOCK/缺电源；追加×2 明确商业金额 3600.00，无基价抵扣；本次未保存该编辑 | bare-missing-power.txt、bare-added-power.txt |
| 企业与权限 | 带未保存修改切 B，旧草稿/客户/部件/优惠清空，B 空且表单/保存只读；切回 A 需重新打开 v2，未迁移旧编辑 | tenant-b-empty-readonly.txt、mobile-dom.txt |
| 失效与重算 | 开发短期会话自然过期后 API 拒绝，页面清空并要求登录；重新经 IdP SSO 选择企业。窗口重新激活时旧试算隐藏，重算后恢复 | session-expired.txt、focus-reprice-required.txt |
| 状态样式 | PASS 绿色、UNKNOWN 中性灰，WARN/BLOCK 暖色；不含电源包件只追加一只电源时 N+1 WARN，SVG PSU 橙色异常 | svg-warning.txt、quote-desktop-warning-1440.jpg、quote-mobile-checks-390.jpg |
| 退出 | 应用退出 → Keycloak Logout 确认 → 返回；报价入口不展示受保护草稿，只显示重新登录 | logout-protected.txt |
| 两视口 | 1440×900 三栏、390×844 单栏；手机 document.scrollWidth=innerWidth=390；输入、select、金额/保存均可滚动到达 | screenshot-manifest.json、原始 JPEG |

证据均在 [evidence](evidence/)。reopened-v1.txt/reopened-v2.txt 抓到了请求中的加载过渡，不能单独作为加载完成证据；完成结果由后续修改/保存、mobile-dom 和截图证明。没有为了截图延长会话、修改后台时钟或把加载失败冒充成功。

截图由 `tab.screenshot()` 原样保存 JPEG，通过 viewport capability 设置实际视口；已逐图检查，结束恢复 viewport 并关闭本轮标签。固定字体/页面展示日期与静止动画沿用既有视觉插件；后台认证/价格时钟不冻结，试算时间为真实观察值。不是逐像素相等断言，差异见 [视觉说明](../../design/task005-visual-comparison.md)。

## 测试边界

本轮没有浏览器双标签人工保存竞态重演；新增五条确定性延迟成功响应的前端自动测试覆盖 quote list/detail/evaluate/save/discount，使用生产请求层，明确为传输替身。真实 PG/API 另外覆盖旧企业请求拒绝和并发编辑/锁等待。真实 IdP/OIDC、原 CRM 双标签协议不变量在完整回归中保留。未验证其他浏览器/字体、真实销售政策、远程 CI 或生产部署。
