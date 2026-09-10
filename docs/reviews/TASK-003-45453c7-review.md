# TASK-003 独立审查

结论：**changes_requested**。

实际审查提交：`45453c72ac2ab52a1e1375982256b1da70c0ef09`。发现 1 项 P1、1 项 P2，均有实际复现。完整仓库测试通过不覆盖这两个并发场景，不能据此验收。未标记 accepted，未开始 TASK-004。

## 范围与提交核对

- 已验收 TASK-002：`99367439f175c1b749395b40f7a0d4a0af068afb`。
- 交接：`cfb1b1f465724af733f07bd2fc8339a5b724db7d`。
- TLS 维护／TASK-003 实现基线：`4133b86b330a5f1fda776bc3625b8fac8d6c857e`。
- 实现：`0bc4d23d46ff34721993c02683432aeebcac1fa7`。
- 最终 HEAD：`45453c72ac2ab52a1e1375982256b1da70c0ef09`。

上述提交构成连续祖先链。审查完整 `99367439..45453c7` 差异，并分别核对交接、TLS、实现和收尾。开始及完成验证时 HEAD 一致，初始工作树干净；本次仅新增本报告。

`cfb1b1f..4133b86` 仅改 OIDC 集成测试、TLS 维护说明和证据，共 3 文件。`4133b86..0bc4d23` 为 TASK-003 实现。`0bc4d23..45453c7` 仅改 result、task 状态、backlog、runtime 状态、changed-files 和 finalization-checks，共 6 文件，没有隐藏的实现变更。对照已验收基线／交接任务书，TASK-003 验收正文未降低，仅推进任务状态。

已读取适用 AGENTS.md、runtime、TASK-003 task/result、ADR-007、设计基线、视觉差异说明、浏览器验收记录、截图清单及相关架构、迁移、权限与交付证据。原报告及历史证据未修改。代码规范／数据不变量与任务符合性分别检查；以下分别归入数据一致性和任务行为发现，不将风格偏好列为缺陷。

## 发现

### R1 — P1：共享会话切企业后，旧标签可将客户保存到错误企业

位置：`apps/web/src/main.tsx:36–47`、`apps/web/src/api.ts:18–24`；相关既有会话机制为 `apps/api/src/silicon/identity/routes.py:141–151`。

页面只在初始化及本标签切企业时读取 session。CRM 请求未携带并校验页面预期企业；另一标签切企业会原地更新同一 session 的 tenant_id。旧标签没有跨标签失效机制，继续用旧企业标题和表单发请求，服务端则按新企业执行。单标签 epoch 与 AbortController 不能解决这一问题。

实际浏览器复现（真实 Keycloak、受信任 HTTPS、临时 PG、同一虚构用户具有 A/B membership）：

1. 标签一选择虚构企业 A，打开新增客户，填编号 `REVIEW003-CROSS`、名称“审查虚构跨标签客户”，内部负责人留空。
2. 标签二打开同源页面并切换虚构企业 B。
3. 标签一点击保存。页面显示“客户已保存，可刷新查询”；关闭弹窗后，其企业选择器仍为 A，列表却为 1 家且包含该客户。
4. 标签二刷新，企业 B 下实际存在该客户。原 B 数据为空，A 原有的 7 个客户未出现在该列表中。

影响：有多企业权限的正常用户可把原本为 A 编辑的新客户落入 B；同时出现标题 A、数据 B 的混合 UI。不是无 membership 的 RLS 越权，但属于错误业务数据归属，阻碍客户纵切验收。此风险由新 CRM 页面使用既有共享 session 方式触发，不能仅以 session 机制来自 TASK-002 排除。

建议：将每个 CRM 请求绑定到页面的预期租户／会话上下文版本，服务端在同一授权事务内校验，不匹配时拒绝并要求重新选择；配合跨标签通知清除列表、详情、表单及在途状态。不能只增加一次保存前 session 查询，因为查询和写入之间仍可切换。补充双标签创建、编辑、查询和延迟请求回归，断言企业标题、请求上下文和实际落库一致。

### R2 — P2：详情可拼接不同提交版本的客户聚合

位置：`apps/api/src/silicon/crm/service.py:16–26`，生产 GET 调用点 `apps/api/src/silicon/crm/routes.py:24–26`。

详情在默认 READ COMMITTED 下分别读取客户、联系人、项目、地点、责任人、历史及项目人员；普通 GET 不锁客户行。这些 SELECT 可看到不同的已提交状态。保存路径有客户行锁，不能保护未取得锁的读者。

真实 PG 定向探针实际复现：使用 `silicon_app`、本次临时集群及生产 `tenant_transaction`、`service.detail/save`。创建独立虚构客户，包含 old contact／old project；通过 SQLAlchemy 执行事件在读完 contacts、读取 projects 前暂停读线程；另一个事务用正常 save 替换联系人和项目并提交，再继续读取。

实际结果：`returned_version=1`、`committed_version=2`；返回 contacts 为 `old contact`，projects 却为 `new project`，项目人员引用 UUID `a61c1448-22d3-4cdd-b43b-5819c2162f47` 不在返回 contacts 中。探针断言此不一致并以退出码 0 完成。实际导入路径为 `/tmp/silicon-review-003-m12q4epg/apps/api/src/silicon/crm/service.py`；探针位于 `/tmp/crm_snapshot_probe.py`，不依赖该临时文件才能理解或重建上述复现。

影响：API 返回一个数据库从未提交过的聚合；详情可能显示缺失姓名，编辑表单可能携带不完整关联。expected_version 可阻止随后覆盖新版本，但不能让已返回详情自洽。

建议：以一致性快照读取整个聚合，或读取客户时先取得合适的共享锁，再读取关联；注意锁顺序与保存事务一致。增加真实 PG 并发“详情读取＋关联替换”回归，断言版本、联系人及项目角色属于同一状态。

## 实际执行的验证

将最终提交通过 git archive 导出至 `/tmp/silicon-review-003-m12q4epg`，测试、生成和构建在该副本执行。复用仓库 Python 环境中的依赖，但显式以该副本 `apps/api/src` 作为 PYTHONPATH；定向探针也输出确认导入该副本生产 service。没有通过旧 editable 源码替代待审查代码。浏览器服务亦从该副本启动。

| 检查 | 本次实际结果 |
| --- | --- |
| 完整 pytest，`-v --tb=short` | **收集 45 项，45 passed，0 skipped，2 warnings，37.99 秒，退出 0** |
| 真实 PG CRM 7 项 | 全部通过；CRUD／历史／审计、并发幂等与版本、租户权限、搜索分页、跨客户关联及 0002 升级均实际执行 |
| 既有 PG/RLS/Worker 回归 | 随完整集合执行；含 TASK-001 有界耗尽清理、锁定任务不阻塞、租约 fencing、重启持久化，以及 TASK-002 授权回归 |
| 真实 Keycloak＋HTTPS API | 完整集合中的真实 IdP 登录回调、退出和过期集成通过；JWT 替身参数测试另列，未冒充真实 IdP |
| `npm ci` | 退出 0；干净副本安装 56 packages |
| `npm run typecheck`、`npm run build` | 均退出 0，Vite 构建成功 |
| `infra/export_openapi.py`＋`npm run api:types` | 退出 0；生成的 openapi.json 和 schema.d.ts 与最终提交逐字节一致 |
| `infra/check_docs.py` | 退出 0，110 个本地链接，状态／相对路径／历史报告校验通过 |
| `git diff --check 99367439 HEAD` | 退出 0 |
| `infra/check_visual_evidence.py` | 仅在隔离副本运行，17 张尺寸／hash 通过；生成清单与原清单一致，原证据未写入 |
| 定向并发聚合探针 | 实际复现 R2，见上文；不计入仓库 45 项 |

完整测试命令的关键设置：`PYTHONPATH=<审查副本>/apps/api/src`，`SILICON_TEST_PG_BIN=/opt/homebrew/opt/postgresql@17/bin`，`SILICON_TEST_KEYCLOAK_HOME=<仓库>/.tools/keycloak/keycloak-26.7.3`，使用仓库 `.venv/bin/python -m pytest -v --tb=short`。实际 Python 3.12.7、pytest 9.1.1、PostgreSQL 17.11、Vite 8.2.2。两条警告分别是 Starlette TestClient 的 httpx 弃用提示及 anyio BlockingPortal 别名弃用提示；不是测试失败。

TLS 维护确实使用测试夹具 CA 建立 SSLContext，保持 CERT_REQUIRED 和 check_hostname；没有 verify=False 回退，也不引用旧 Reviewer CA 路径。浏览器使用仓库现有开发证书，未关闭 TLS 校验、忽略证书错误或新增／修改证书信任。

代码层面确认：8 张 CRM 表 FORCE RLS；租户／客户复合外键约束关联；真实 CRM 路由复用生产授权；内部负责人校验有效 membership；子项 UUID 挪用与非法重复受约束；角色变更关闭旧任期并保留快照。保存、版本、幂等结果和成功审计处于同一事务。空库安装及从 0002 升级已随测试复跑，身份与队列数据保留；readiness 对应新迁移。未提前加入合同、报价、库存业务。上述正向结果不消除 R1、R2。

## 实际浏览器与视觉审查

本次使用 Codex In-app Browser，真实登录 `https://localhost:5173/`，真实 IdP 位于临时 `https://127.0.0.1:8443`。API 为脚本创建的独立进程；PG 为脚本创建的随机端口临时集群，未连接常驻 PostgreSQL。浏览器过程使用虚构账号／数据，未依赖关闭证书验证。

实际操作结果：

- 登录经过 Keycloak 凭据页、回调进入企业选择；选择 A 成功。
- 新建客户实际保存并刷新可查，但跨标签流程发现 R1，不能笼统记为企业切换隔离通过。
- 编辑名称后刷新保持新值；双标签编辑同一旧版本，一方保存后另一方显示明确冲突及“重新载入最新版本”，旧输入保留，没有假成功。
- 重复编号显示“该客户编号已存在”，焦点落在错误容器；Tab 可从关闭按钮进入编号输入，Escape 关闭弹窗，详情关闭后焦点返回原客户按钮。
- 退出先清除应用会话，再经 IdP Logout 确认返回登录页；另一旧标签发起查询后显示“登录已失效”，客户列表与弹窗清空。本次此浏览器失效证据来自退出撤销；时间到期另由真实 HTTPS 集成测试覆盖，未写成浏览器已等待自然过期。
- 390×844 下实测 document 宽度 390，无页面级横向溢出；详情弹窗宽约 366.6、高约 759.6。表格容器宽 320、内容宽 687，可聚焦，ArrowRight 后 scrollLeft 实际变为 40。
- 受控延迟尝试：临时集群锁住 crm_contacts，旧详情请求在切企业期间等待；释放后没有重新弹出旧详情。但生产连接有 3 秒 statement_timeout，此尝试触发超时，**不能作为旧请求成功延迟返回的通过证据**。该成功返回竞态尚未完整实测；单标签 epoch／abort 保护仅作代码判断。

实际打开并逐张查看全部 17 张历史 JPEG（不是仅运行清单检查），均位于 `docs/tasks/TASK-003/evidence/screenshots/`：

- original-customers-1440、original-customers-390；migrated-customers-1440、migrated-customers-390。
- original-detail-1440、original-detail-390；migrated-detail-1440、migrated-detail-390。
- original-quote-1440、original-quote-390。
- migrated-create-390；browser-duplicate-error-390；browser-version-conflict-390。
- browser-keycloak-login-390；browser-logged-out-390；browser-tenant-b-390；browser-persisted-edit-1440。

同时实际截图查看本次运行的 1440×900 列表、详情、退出页，以及 390×844 详情和可横向滚动表格；本次临时截图未替换历史基线。按任务要求阅读并对照 visual-comparison、browser-acceptance 与 screenshot-manifest。

视觉判断：桌面保留 215px 侧栏、77px 页头、浅灰背景、白色圆角面板和深绿首卡／主按钮，标题与辅助文字层级可辨。统计由金融演示口径改为真实客户／联系人／项目／地区，未实现导航禁用、去除无后端过滤器，均属于已说明的有意变化。移动端把原 Demo 长竖导航改成紧凑换行导航，减少首屏占用，属于明确说明的适配变化。详情改为真实联系人／项目／历史，正文留白更大、长客户名在窄屏换行，但未见控件越界或无法关闭。新建／编辑／错误／冲突是新增状态，不能声称原 Demo 有逐像素对应页面。原报价截图只用于共享视觉语言，不代表已实现报价。未发现需另列的意外视觉回归；不构成产品负责人 accepted。

## 未验证事项、证据限制与清理

- 成功响应在切企业后延迟返回的完整浏览器场景未证实，原因与超时尝试见上；建议修复 R1 时一并补充确定性回归。浏览器未逐一遍历全部联系人／项目增删组合，关联语义主要由真实 PG 测试和代码审查覆盖。
- 403 权限拒绝由实际生产 CRM 路由测试覆盖；未在本次浏览器另行撤权来重复所有错误组合。测试中身份注入与真实 OIDC 浏览器流程明确分开。
- 远程 CI、Compose 容器整栈和远程 IdP 主动撤销本次未运行；没有把本地结果写成远程或容器通过。当前 task 要求真实 PG、E2E 和视觉，不将这些后续环境能力自行扩大为本次新增缺陷。
- 未修改或重新部署原 Demo，原 Demo 的 dist 未当构建产物删除。原页面基准来自已打开的固定截图及设计记录；本次没有重新启动原 Demo 来重演其全部交互。
- 脚本测试依赖现有本机 PG/Keycloak/字体/受信任开发证书；本次能够使用且实际运行成功，不据此宣称任意全新机器已完成浏览器证书准备。
- 本次只停止经 PID 与 cwd 核实属于 `/tmp/silicon-review-003-m12q4epg` 的验收栈。脚本返回 `BROWSER_STACK_CLEANED`、退出 0；临时 PG、IdP、API、Vite 清理，任务创建的两个浏览器标签已关闭，视口已恢复。未读取、停止或修改常驻 PostgreSQL；临时探针不在实现目录。

最终结论仍为 **changes_requested**：请修复 R1 的请求租户绑定和 R2 的聚合一致性读取，再做针对性独立复核。
