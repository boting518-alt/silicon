# TASK-003 浏览器验收

执行日期：2026-09-10。状态：实际交互 passed；视觉有意差异待独立 Reviewer 复核，不等于 accepted。

## 环境与信任

使用 Codex In-app Browser（实际浏览器页面，macOS），通过 CUA 点击、输入、原生 select、键盘和截图完成。不是 httpx 替身，不关闭 TLS 或忽略浏览器证书错误。API/Keycloak 固定版本沿用锁文件；PG 17.11 为独立随机端口临时集群。

用户明确授权“保留此本地开发证书信任”：将 `.tools/tls/localhost.crt` 加入当前用户 login.keychain-db，仅 SSL trustRoot；没有私钥导入，也没有更改系统钥匙串。SHA-256 为 `45:A3:D2:BA:5C:17:0C:EC:C6:6A:D7:8D:F8:89:04:0C:9F:34:6F:A3:AD:65:5D:BD:56:98:BB:4F:64:75:85:46`，SAN localhost/127.0.0.1，有效至 2026-10-09。首次使用 trustAsRoot 因证书为自签名返回参数错误；核对后改为 trustRoot 成功。浏览器实际无证书拦截页，真实登录和跳转成功。其他机器或新证书必须重新取得用户授权，不能沿用此次授权自动修改信任。

协议 OIDC 测试使用自己临时生成的 CA、证书、私钥和 SSLContext，与浏览器持久开发证书分开；维护实现和结果见 [TLS 维护](tls-maintenance.md)。不依赖审查者临时目录或适配器。

## 可复现启动

以下从仓库根执行，已有锁定依赖和 Keycloak 分发包即可。测试字体使用有合法本机使用权的 PingFang.ttc，放到忽略目录 `.tools/visual/PingFang.ttc`，SHA-256 必须为 `6bccdb1a967b2ae7e856927eb559591b2ce05656b0d4ad2764b9c9429f12c0b7`；不提交或分发系统字体。没有同一字体时停止视觉对照，恢复条件为提供同 hash 字体，不能悄悄降级。

```bash
python3 infra/prepare_demo_baseline.py --output /tmp/silicon-demo-source-check.json
```

命令输出新克隆目录；把它赋给当前终端的 DEMO_BASE。原参考仓库只读，按 OD-018 独立克隆并逐 blob 核验，不清理其 ._*。两个参考服务各开一个终端：

```bash
python3 infra/visual_server.py --directory "$DEMO_BASE/workspace/dist" --font .tools/visual/PingFang.ttc --port 4172
python3 infra/visual_server.py --directory "$DEMO_BASE/quote/dist" --font .tools/visual/PingFang.ttc --port 4171
```

两个命令是两个长期运行服务，不是在同一终端串行等前一个退出。浏览器测试产品栈另开终端：

```bash
SILICON_TEST_PG_BIN="$(pg_config --bindir)" SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3" .venv/bin/python infra/browser_stack.py
```

该脚本复制独立 Keycloak/H2、创建临时 PG、空库迁移、种入固定虚构企业和客户，启动 HTTPS IdP/Vite 与回环 API。不要先执行 createdb/bootstrap/provision_dev_identity；不会读取 `.env` 数据库。端口 5173/8000/8443 被占用时失败，不终止其他进程。Ctrl-C/SIGTERM 只清理本栈，输出 BROWSER_STACK_CLEANED；源码服务 Ctrl-C 关闭。不会移除用户要求保留的证书信任。

## 浏览器检查步骤与实际结果

CUA 入口为 `await cua.createBrowserTab('iab','https://localhost:5173/',{visible:false})`；随后通过该 tab 的 `playwright.getByRole(...).click/fill/selectOption/press` 操作，`getAXState()` 核对页面，`getScreenshot({emit:false})` 保留原始 JPEG 字节。具体操作顺序如下，所有数据均虚构：

| 检查 | 实际操作与观察 |
|---|---|
| 真实登录 | 点击“使用企业身份登录”，进入 HTTPS Keycloak；alice / Fictional-alice-17! 提交后真实 callback 返回；页面显示虚构用户甲与“请选择企业”。新 IdP 启动后再次实际输入登录成功 |
| 企业选择 | 原生“当前企业”选择虚构企业 A，显示 7 客户/14 联系人/7 项目/7 地区；数据来自 PG，非前端数组 |
| 键盘/弹窗 | Enter 打开“新增客户”，Tab 从关闭按钮到客户编号；Esc 关闭并返回“新增客户”。客户详情 Esc 返回原客户按钮 |
| 输入错误 | 空表单保存被浏览器必填校验拦住，焦点在客户编号；重复编号后端拒绝并显示中文错误，修复后 alert 自动聚焦/滚入视口 |
| 创建 | E2E-003 / 浏览器验收客户；2 联系人，2 项目，项目负责人/关键人各关联对应联系人；内部销售和售后均选当前有效成员；增加虚构机房地点，保存为版本 1 |
| 编辑/刷新 | 改名“浏览器验收客户 · 已编辑”、备注“编辑后刷新仍可查询”，保存版本 2；reload 后搜索 E2E-003，打开详情仍为版本 2，2 联系人/2 项目/地点/备注均保留 |
| 并发编辑 | 两标签打开同一版本；第二标签先保存，第一标签保存返回 VERSION_CONFLICT；重载显示对方内容/版本 3，旧修改未覆盖。末次错误焦点修复复测使用固定 CUS-001，重载显示“并发保存的新版本” |
| 企业隔离 | 切 B 并搜索 E2E-003，0 结果；切 A 后原编辑客户仍在。第二次固定夹具 B 仍空，用于移动截图 |
| 退出保护 | 点击退出→真实 Keycloak Logout 确认→返回登录页；reload 没有客户表格。另一标签尝试保存旧档案，401 后清除客户与 dialog，出现重新登录入口 |
| 自然会话过期 | 开发 realm 的短期 ID token 到期后，详情/保存请求拒绝；修正详情与表单的 401 处理，清除旧内容。重新经 IdP SSO 登录后才能继续，没有延长产品会话寿命 |
| 窄屏 | 实际 innerWidth=390/innerHeight=844；修复导航溢出后 document.scrollWidth=390。表格独立滚动区域宽 320/content 641，键盘操作后 scrollLeft=40；页面不被表格撑宽 |
| 截图 | 17 张原始 JPEG，文件尺寸由检查脚本逐张核验。产品列表/详情和两个 Demo 均包含指定两视口。列表基线使用重新启动的固定 7 客户夹具，交互证据单独保存 |

错误可见性最终 DOM 实测：重复编号 alert top=525.39/bottom=607.78；冲突 alert top=461.58/bottom=607.77；视口高 844，焦点 role=alert。之前提示存在于长表单下部而不在视口内，现已修正并复测。浏览器 `getByLabel(exact)` 对含 select/textarea 的包装标签匹配失败时，改用实际无障碍名称 getByRole；未更改业务值绕过验证。

截图控制通过 `(await browser.capabilities.get('viewport')).set({width:1440,height:900})` 或 390×844；该环境设置作用于当前选中标签，不保证作用于后台标签。每次必须读取目标页面 innerWidth/innerHeight，并检查截图实际尺寸。早期误标尺寸及 `.png` 后缀已在提交前纠正，未缩放图片冒充目标视口。获取列表顶部截图通过点击“硅屿首页”回到顶部（Home 快捷键未改变当时滚动位置），详情则点击第一客户并保持 dialog 顶部。结束调用 viewport.reset()，关闭本任务标签。

```bash
python3 infra/check_visual_evidence.py
```

这是尺寸/hash 检查，不替代点击验收或视觉人工对照。截图与差异见 [视觉对照](../../design/task003-visual-comparison.md)。不宣称远程 CI、容器浏览器或其他浏览器已通过；重跑浏览器需上述本地可信 HTTPS 条件及 CUA/人工交互环境。
