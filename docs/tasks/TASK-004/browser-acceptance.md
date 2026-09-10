# TASK-004 浏览器与视觉验证

日期：2026-09-10。实际使用 Codex 内置浏览器、真实 Keycloak、独立临时 PostgreSQL、https://localhost:5173。沿用已获授权并已安装的开发证书信任，本次未修改信任、未忽略证书错误。浏览器登录不是 httpx 或身份替身。

## 可重复环境

在仓库根执行（先结束占用测试 IdP 端口的 pytest）：

```bash
SILICON_BROWSER_CATALOG=1 \
SILICON_TEST_PG_BIN=/opt/homebrew/opt/postgresql@17/bin \
SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3" \
.venv/bin/python infra/browser_stack.py
```

PG 路径按已安装 17 的实际位置配置；脚本只创建并清理自己的临时集群。需要已有 .tools/tls/localhost.crt、私钥及浏览器认可的该开发证书，以及已记录 SHA-256 的 PingFang 字体；缺失直接失败，不回退 TLS 或字体。测试身份 alice / Fictional-alice-17! 为虚构专用账户，企业 A admin、B viewer。生产没有快捷身份入口。Ctrl-C 后两个实际测试栈均输出 BROWSER_STACK_CLEANED 并退出 0。

第一轮目录为空，以下数据全部经浏览器创建。最终视觉复测可在上述命令增加 SILICON_BROWSER_CATALOG_SEED=1，使用仓库 infra/catalog_examples.py 的固定虚构 3 SKU、2 包件、规则及价格；夹具仅在测试栈启动前运行，不是生产 API。固定 UUID/字段/价格期间，字体与现有视觉时钟沿用基线；页面无自动变化的时间字段，截图时无加载/动画过程。

## 实际操作结果

1. 真实 IdP 登录、回调、选择 A。创建 DEMO-HOST、DEMO-PSU（1200 W）、DEMO-BARE，保存刷新可查。重复编号得到明确错误且错误区获焦点（evidence/duplicate-error-ax.txt）。
2. 建立已含两个电源包件，创建并绑定带虚构来源的版本化平台规则，发布；另建不含电源包件并发布，保留缺电源 BLOCK。含电源条目仅显示包含，不生成额外收费。规则有单项 PASS，也持续显示未知覆盖范围，未显示整体认证通过。
3. 创建 DEMO-CONFIG 和“虚构BOM·外选电源”，引用不含电源包件并另选两个电源，发布 revision 1；修订为一个电源并发布 revision 2，显示 N+1 WARN。刷新原版本仍有两个电源（bom-original-after-revision-ax.txt）。
4. 创建零售含税 CNY 价格：2026-01-01～2027-01-01 UTC、10000.50，发布后当前价为 KNOWN。修订 11000.75 使用重叠期间时发布被拒绝（price-overlap-ax.txt）；改为 2027～2028 UTC 后发布成功。刷新原版仍为 10000.50、原期间，当前价仍选原有效版本（price-revision-published-ax.txt、price-final-old-version-ax.txt）。
5. 本轮实际暴露日期编辑问题：带 +08:00 的数据库返回不能直接截字符串作为 UTC；原日期事件未更新编辑状态。已改为显式 UTC 转换和 onInput，重新保存/发布未来期间通过，并增加 3 项日期边界测试。保留修复前日志，不将中间 draft 截图当最终成功证据。
6. 两标签同会话：A 标签填写完整未保存 SKU，另一标签切 B。A 旧表单和列表清除并要求重新选企业（cross-tab-invalidated-ax.txt）；B 三页面为空且写按钮禁用（tenant-b-*.txt）。返回 A 仍仅原 4 个 SKU，新表单没有旧草稿（tenant-a-restored-dom.txt；原 AX 在恢复时不完整，以 DOM 为准）。
7. 会话自然到期时受保护内容清除；重新登录可继续。最后退出并刷新显示登录入口（session-expired-ax.txt、logout-dom.txt）。
8. 手机 SKU 表单 Tab 从编号到名称，取消关闭表单。390 宽页面无页面级横向溢出；表格保留局部横向滚动，键盘横向滚动有实际位移。错误和未知价/兼容提示没有被隐藏。

## 最终视觉证据与有意变化

最终 6 张图及 SHA-256/尺寸见 [清单](evidence/screenshot-manifest.json)。三类页面各有 1440×900、390×844；均已实际查看。最终复测使用固定夹具，不冒称与第一轮手工创建的修订历史完全相同。

新增侧栏商品、包件/BOM、价格入口；继承硅屿背景、绿色、卡片、边框、排版与留白。表单桌面双列/手机单列，包含行、版本和 BLOCK/WARN/UNKNOWN 为新业务所需。原 Demo 无这些完整维护状态，因此是沿用风格的新页面，不是原始截图基线。没有更新原 Demo 或旧基线来消除差异。初轮截图保留为过程证据，final-* 才是最终布局（初轮原生输入框样式不足已修正）。不重做服务器 SVG。

## 验证边界

双标签真实点击验证通知后的清理与只读状态；未在浏览器做网络拦截来延迟成功响应。可重复的确定性成功响应竞态由 apps/web/tests/context-race.test.ts 执行生产请求包装器（传输替身，明确交付 200，非超时/失败），覆盖目录列表/详情/创建/编辑/发布/修订。通知未到达时服务端拒绝旧上下文、并发保存顺序和聚合一致性由真实 PG/API 回归覆盖。自动化测试与实际浏览器证据分别报告。

新采集的文本证据仅规范化行尾空白和文件末尾空行，以通过 diff --check；内容、测试失败与成功结果均保留。历史审查报告未修改。
