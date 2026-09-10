# TASK-003 R1/R2 增量复核

结论：**passed**。原报告 R1、R2 已解决；本次相关差异中未发现新的需修复问题。此结论为独立增量复核，不自行标记 accepted，不开始 TASK-004。

## 实际范围

- Base：`45453c72ac2ab52a1e1375982256b1da70c0ef09`。
- 修复提交：`005ea46446d6d6d140ce261e207901fbd8c4362a`。
- 实际最终 HEAD：`a6b640e6dd7f5ac1ecff40fa7f43cc5afe241d47`。
- 依据：[原独立报告](TASK-003-45453c7-review.md)。保留原文及 changes_requested 历史结论，不覆盖历史证据。

已核对连续提交关系、完整 `45453c7..a6b640e` 差异及工作树。开始时工作树干净。`005ea46..a6b640e` 仅在 result.md 追加 69 行修复说明，没有收尾实现变化。原报告在修复提交首次纳入版本控制，文档检查中的 hash 校验通过。TASK-003 任务书未改动，验收要求未降低。

读取适用 AGENTS.md、任务书、原报告、result 修复节、ADR-008、修复测试和证据；重点审查上下文事务、前端失效、聚合锁、0004 迁移、readiness、契约及身份回归。未重复全部历史 Demo／视觉基线审查。

## R1 复核：passed

位置：`apps/api/src/silicon/identity/routes.py` 的 authenticated、request_tenant、select_tenant；`apps/api/src/silicon/crm/routes.py`；`apps/web/src/api.ts`、main.tsx、CustomerEditor.tsx。

服务端不是先查询 session 再另开事务执行业务。authenticated 的 `FOR UPDATE OF s` 在 request_tenant 的同一 `engine.begin()` 内取得会话行锁；锁内校验 X-Expected-Tenant 和 X-Session-Context，再校验 membership、权限、设置租户上下文并 yield 同一个连接执行 CRM，直到提交／回滚才释放。切企业取得同一会话锁，更新 tenant_id 并轮换 context_id。Header 只是预期上下文声明，不替代会话 Cookie 或授权。

全部生产 CRM 路由，包括 members、列表、详情、创建、更新，均要求上下文。缺失返回 428，不匹配返回 409；写请求仍验证 CSRF/Origin。每次选择企业轮换随机 context_id，A→B→A 不能重新激活旧表单。拒绝不会改投另一企业或自动重试。

真实 PG/API 回归实际通过：

- 不依赖前端通知，旧 members、列表、详情、创建、更新均返回 `409 CONTEXT_CHANGED`；B 无新增，A 原记录版本保持。
- 缺失 Header 返回 428；A/B/A 的旧请求被拒绝。
- 旧 A 上下文即使指向用户有权访问的 B 客户，也不能修改 B 的名称／版本。
- 保存先持锁：正常提交 A 后才能切 B；切企业先持锁：旧保存等待后返回 409。测试实际使用 `pg_blocking_pids` 确认阻塞顺序，不只检查最终状态。

前端请求捕获不可变上下文和代次，在发送前以及成功 JSON 返回后检查。失效时清除数据、详情、表单及请求，要求重选；广播和窗口激活检查为体验补充，不是服务端安全前提。

### 本次真实浏览器复现

使用 Codex In-app Browser、现有受信任开发证书、真实 Keycloak、隔离 PG/API/Vite，虚构 alice 账号。没有关闭 TLS 校验或改变证书信任。

1. 标签 A 选择企业 A，打开新建，填写 `REPAIR-CREATE`／“旧A草稿不应落B”；标签 B 切企业 B。旧标签表单消失、企业选择置空，并显示“企业上下文已变化，旧表单已失效……”。B 为 0 家客户，没有误创建。
2. A 重选企业，打开 CUS-001 编辑名称为“旧编辑不应提交”；B 再切企业。A 编辑同样失效；没有保留可提交的旧表单。
3. 明确重选 A 后正常创建 `REPAIR-OK`，再编辑为“重选企业后编辑保持”；刷新后详情仍是新名称、版本 2。
4. 隔离浏览器探针记住 A 的真实 session 上下文，另一标签切 B 后，使用原 Header 对真实 CRM 列表发起读取；实际返回 **409 CONTEXT_CHANGED**。这一步直接检查服务端，未由前端通知拦截请求来代替。
5. 完成应用退出和 Keycloak Logout；旧标签刷新后回到登录提示，不显示客户数据。

### 延迟成功响应：本次补充实际验证

在 `/tmp/silicon-review-003-a6b640e/apps/web/review-delay.html` 放置独立测试入口，导入最终提交未经修改的 `/src/main.tsx`。测试入口仅提供“暂存／释放”控制：对下一次详情调用使用真实 HTTPS fetch，读完真实响应正文，确认状态 **200**，然后等待人工点击释放；故意不传该次 AbortSignal，以模拟取消已经来不及阻止成功响应的情形。没有替换客户正文、会话、认证、CRM 代码或服务端结果。

浏览器先在 A 点击 CUS-001；探针显示“已暂存真实响应 200”。随后在同一页面切 B，再释放旧成功响应。释放后实际 DOM 为：企业 B、0 家客户、无详情弹窗、无保存成功提示。旧 A 详情没有污染当前页面。这次是已成功响应的延迟交付，不是原复核中的数据库超时。

此为明确的受控传输探针，不宣称原生网络恰好发生了同样延迟。仓库 Node 测试另外覆盖列表、详情、新建、编辑四种成功响应及 A/B/A 旧 ticket；这些测试使用传输替身和生产 CrmRequests，不能单独等同完整 React 浏览器测试。本次真实浏览器补充覆盖了详情成功返回与实际页面状态。

## R2 复核：passed

位置：`apps/api/src/silicon/crm/service.py:16` 起。

普通 detail 首先以独立 SELECT 对客户父记录取得 FOR SHARE，然后才查询 BASE 的版本／计数及全部关联；保存走同一入口 FOR UPDATE，并在同一事务替换关联和写历史。这也避免把取得锁的查询与关联计数放在同一条等待中的语句里，出现等待前后快照混用。现有生产关联写入口均遵循父锁顺序。

实际复跑 `test_detail_is_one_committed_aggregate_during_replacement`：联系人读取后暂停读线程；另一事务通过正常 service.save 替换聚合，`pg_blocking_pids` 证实写者等待父记录共享锁。释放读者后，旧结果版本 1、计数、联系人引用、项目、地点、内部责任人和当前角色历史均自洽；随后新提交版本 2。没有通过补写 version 或事后修补响应伪造一致性。测试有有限等待和 finally 释放，不靠超时取得通过。

写先取得父锁的路径已检查锁及独立查询顺序；本次没有另写第二个写先／读后 PG 探针。当前读先／写后真实回归已直接覆盖原 R2 复现条件。

## 实际验证结果与身份回归

从最终 HEAD 导出干净副本 `/tmp/silicon-review-003-a6b640e`。测试使用仓库 Python 环境的依赖，显式设置 PYTHONPATH 指向副本 apps/api/src；实际打印 `silicon.crm.service.__file__` 为该副本路径，避免旧 editable 安装源码。生成和构建也在副本进行，不改用户实现。

| 本次执行 | 结果 |
| --- | --- |
| 完整 `python -m pytest -v --tb=short` | **52 collected，52 passed，0 skipped，2 warnings，38.75 秒，exit 0** |
| R1/R2 真实 PG 上下文／并发回归 | 6 项随上述全套通过，含参数化两个会话锁顺序 |
| `node --test apps/web/tests/context-race.test.ts` | **5 passed，0 failed，0 skipped，exit 0** |
| `npm ci`、typecheck、build | 均退出 0 |
| export_openapi.py、api:types | 退出 0；生成 JSON／schema.d.ts 与最终提交逐字节一致 |
| check_docs.py | 退出 0，131 个本地链接、相对路径、状态和原报告 hash 通过 |
| `git diff --check 45453c7 HEAD` | 退出 0 |

环境：Python 3.12.7、pytest 9.1.1、PostgreSQL 17.11、Keycloak 26.7.3、Vite 8.2.2。测试 PG 指向 `/opt/homebrew/opt/postgresql@17/bin`，Keycloak 使用仓库工具目录的临时副本。先完成全套再启动浏览器栈，避免同时争用 IdP 端口。

完整集合实际包含真实 Keycloak HTTPS 登录／回调／退出／过期，以及会话、CSRF、有效 membership、own/all、RLS、Worker 授权与租约等回归；不是仅阅读执行者证据。两条警告仍为 Starlette TestClient httpx 弃用和 AnyIO BlockingPortal 别名弃用，无新增测试失败。

0004 为已有 session 填充非空 context_id，不扩大运行角色权限；空库及从 0002、0003 升级测试通过，既有身份／membership／租户任务保留。readiness 已更新为 0004。OIDC 校验、Cookie、CSRF、生产模式拒绝和 Worker 机制未被放开。

## 视觉、限制与清理

仅查看本次修改涉及的实际失效提示、企业重新选择状态、表单移除及正常保存状态。实际截图中的提示完整换行、操作可见，未见新布局溢出或假成功；CSS/token 未改。不重复全部历史截图，也未修改基线。

- 原生浏览器通知全部丢失的故障注入未做；服务端无通知拒绝由真实 PG/API 测试和浏览器旧 Header 请求覆盖。
- 延迟成功响应的浏览器探针覆盖详情；列表和两种保存的受控成功延迟由 Node 测试覆盖，不夸大为四种浏览器全流程均做了网络门控。
- 本次没有复跑远程 CI、Compose 容器整栈、原 Demo 或部署；这些不影响本次 R1/R2 增量结论。
- 临时探针第一次加载有字符编码显示问题，已只在临时 HTML 加 UTF-8 声明后重新加载；与产品代码无关，未修改实现。
- 两个审查标签已关闭。经 PID 和 cwd 核实后，仅停止本次临时栈，脚本输出 `BROWSER_STACK_CLEANED`、退出 0。未连接、停止或写入常驻 PostgreSQL，未改变 TLS 信任。仓库仅新增本报告。

最终结论：**passed**。
