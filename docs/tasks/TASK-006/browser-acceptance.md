# TASK-006 真实浏览器验收

日期：2026-09-10。执行者验证，非独立审查结论。全部业务数据、身份、硬件、价格和政策均为虚构。没有改 TLS 信任、绕过证书校验或访问常驻 PG。

## 可重复准备

仓库根先按 README 安装锁定依赖。设置 `SILICON_TEST_PG_BIN` 指向 PostgreSQL17.11 程序目录，`SILICON_TEST_KEYCLOAK_HOME` 指向脚本下载校验后的26.7.3，Java21在PATH。沿用 [原浏览器准备](../TASK-005/browser-acceptance.md) 的合法固定字体与可信开发证书；新设备需自己授权信任，不能使用 verify=False。

```bash
SILICON_BROWSER_PUBLICATION=1 SILICON_BROWSER_CATALOG=1 SILICON_BROWSER_CATALOG_SEED=1 SILICON_BROWSER_QUOTES=1 .venv/bin/python infra/browser_stack.py
```

该脚本从空库迁移独立 PG、独立 Keycloak，并显式加载 `infra/publication_examples.py`。不执行常驻 createdb/bootstrap，不需要 .env。甲 alice / Fictional-alice-17!，乙 bob / Fictional-bob-17!；甲在A为admin/B为viewer，乙只在A为admin。仅此测试栈增加乙和开发发布政策，正常产品启动不会种入政策/用户。

打开 https://localhost:5173。固定1440×900与390×844，字体沿用原PingFang hash。前台日期/字体/动画由既有视觉配置固定；服务端业务时间真实，用户明确设置报价有效期。

## 本轮实际步骤及证据

1. alice真实OIDC登录→A→报价工作室→打开“虚构 TASK-006 发布验收 v1”；49660.01 CNY，GPU×1。设未来有效期并提交。`browser-submitted.txt`。
2. 退出（包括Keycloak Logout）→bob登录→A→报价审批。查看冻结配置、技术行、金额/来源、提交人和四项UNKNOWN；逐项填说明和依据，批准v1。`browser-approved-v1.txt`、approval-1440.jpg。
3. 保留批准页，在第二标签使用同一bob会话打开工作室，排除原GPU行并追加同款GPU×2，保存v2。回第一标签保持的旧批准页勾选人工确认并点击发布，**真实POST被APPROVAL_INVALIDATED拒绝**。`browser-gpu-edit.txt`、`browser-old-approval-rejected.txt`、invalidated-1440.jpg。不是只刷新隐藏按钮，也不是协议测试替代。
4. bob在编辑标签重新提交v2；退出。alice重新登录，页面显示v2提交人为2222…（bob），当前用户甲（alice）。自动安全检查最初误把v2当alice提交而拦截；只读核对页面不同身份并保存证据后原操作获准继续，未绕过服务端自批限制。`browser-v2-distinct-identities.txt`。
5. alice逐项批准bob的v2，勾选人工确认发布。生成Q-000001，总额77660.01 CNY，GPU×2；持久开发标记及UNKNOWN保留。`browser-published.txt`、published-1440.jpg。
6. 点击转合同草稿，返回来源，再次转合同；只产生一份。刷新/从侧栏合同管理重新打开，来源id/hash/审批/复制时间可追溯。`browser-contract-first.txt`、`browser-contract-repeat.txt`、`browser-contract-reopened.txt`。
7. 在价格维护页面修订GPU价格为30000.00 CNY，发布非重叠未来期间 `[2028-01-01,2030-01-01)` 的v2；不改写旧28000价格。刷新并打开历史报价，GPU行仍56000、总额77660.01、hash仍433f551c…35c81。`browser-new-price.txt`、`browser-history-after-price.txt`。**本轮浏览器验证未来价格版本新增，不声称修改了当前期间有效价或系统时钟**；真实PG价格时钟用例另测跨界变价会使审批失效。
8. 从发布页建立独立修订草稿，未继承审批。浏览器只验证建立修订；最终R2编号生成由新增真实PG用例验证。`browser-revision-created.txt`。
9. 390×844查看来源合同/发布详情并撤回源报价，合同保持，显示来源已撤回警示。`browser-contract-source-withdrawn.txt`、contract/published/contract-warning-390.jpg。只读PG核对一份quote_version/一份contract、内容完全一致及GPU新价格版本，`browser-pg-crosscheck.json`。
10. 会话自然失效时页面要求重新登录；正常OIDC恢复后选B，合同为空，不显示A内容。`browser-session-expired.txt`、`browser-tenant-b.txt`。

日期控件在本IAB中的fill没有单独触发React change；使用实际键盘ArrowUp并核对最终显示值后提交，未通过脚本改React状态或跳过校验。实际报价有效期见冻结证据（v2为2028-11-01T04:00Z）；不把尝试输入值当实际保存值。

## 组件及视觉

`/tests/publication-component.html` 挂载真实 PublicationDesk，用实际按钮/表单事件，只有HTTP边界为替身：4项通过，覆盖刷新失效、发布成功但响应丢失重试、服务端失效错误后立即移除按钮、旧企业迟到成功响应。不是PG/OIDC验收。原 `/tests/quote-component.html` 3项继续通过。Node原19项另列，不能混合计数。

截图共7张原始JPEG，见 [清单](evidence/screenshots.json)。沿用原侧栏、绿色、字体、留白和卡片/SVG。新增审批/冻结详情不是原Demo已经存在的真实业务状态；有意变化为版本列表、风险输入、只读详情、开发标记和源失效警示；未覆盖旧截图或改变token。移动端宽度390、document375（滚动条），无横向溢出。截图捕获于核心链路代码；最后文案和失效后按钮移除补充由真实组件重跑验证，没有冒称逐像素相同。

## 清理与限制

关闭临时浏览器标签、恢复viewport；SIGTERM发送到本次栈已核对PID，脚本完成 `BROWSER_STACK_CLEANED` 并移除自己的临时PG/IdP/API/Web。原证书/字体保留不动。

未执行正式政策商务验收、远程CI（无远程）、容器运行（本地原生栈）、其他浏览器/字体。没有外发、部署或TASK-007。浏览器原完整TASK-005折扣流程未全量重跑，原组件和完整PG报价回归均通过。

### 截图导出补记

页面在 1440×900、390×844 视口验证；IAB 的 screenshot 和原始 getScreenshot 两个接口均缩小导出为 1425×891、375×812（滚动条区域）。没有重采样伪装尺寸。补拍第二独立栈的提交页面仍有相同限制；final-login 是设置视口前的 1280×720。实际尺寸与哈希见 screenshots.json，不能称为指定像素的未缩放截图。第二栈只补拍提交，不替代第一栈完整两人审批流程；两栈均已清理。
