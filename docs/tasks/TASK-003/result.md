# TASK-003 原 UI 壳迁移与客户纵切交付

以下原始交付记录保留；本轮 R1/R2 修复、提交与最新验证见文末“独立审查修复”部分。

```yaml
task_id: TASK-003
status: review_ready
accepted_baseline: 99367439f175c1b749395b40f7a0d4a0af068afb
handoff_commit: cfb1b1f465724af733f07bd2fc8339a5b724db7d
maintenance_commit: 4133b86b330a5f1fda776bc3625b8fac8d6c857e
base_commit: 4133b86b330a5f1fda776bc3625b8fac8d6c857e
head_commit: 0bc4d23d46ff34721993c02683432aeebcac1fa7
head_scope: implementation_and_test_evidence
next_task: TASK-004 (planned, not authorized)
```

## 交接与维护

开始时 main 的 HEAD 与已审查 9936743 基线一致，工作树只有未跟踪的 [TASK-002 审查报告](../../reviews/TASK-002-9936743-review.md)，无已跟踪用户修改。报告原样纳入独立交接提交；TASK-002 accepted、TASK-003 executing，保留历史测试与审查结论，并记录真实浏览器、远程 CI、容器及生产准备限制。

先完成独立 TLS 维护提交 4133b86：测试 HTTP 客户端使用夹具生成的 CA 创建 SSLContext，CERT_REQUIRED 与 hostname 验证均开启；缺失/加载失败直接报错，没有 verify=False 回退。夹具负责独立证书、CA 上下文与进程清理，不使用 Reviewer 私有路径，不改变产品认证语义。维护时真实 OIDC + 相关认证测试 **26 passed，2 warnings，31.63s**，详见 [维护记录](tls-maintenance.md) 和 [原始输出](evidence/tls-maintenance.txt)。

## 实现范围

- 原 Demo 固定来源、全部 12 个文件/对应 blob/SHA-256/项目身份重新核对；按 OD-018 创建无硬链接独立克隆，完整 fsck 成功。原 Demo 与其磁盘元数据未修改。
- 从工作空间原 CSS 提取适用 UI 壳、侧栏、页头、指标、表格和 dialog 风格；前端只启用客户，其他导航明确未启用。没有引入新模板、报价/合同/库存模块或业务 Agent。
- 0003_crm 新增客户聚合：联系人、项目、客户侧项目负责人/关键人、内部销售/售后负责人、装机地点及角色历史。客户身份独立于合同，将来多个合同可引用同一客户复合键，本次不建立合同业务表。
- 真实客户列表/搜索/稳定分页/详情/新建/编辑；后端事务保存与刷新查询。租户内编号唯一；Idempotency-Key 持久化防重，客户行锁 + expected_version 拒绝覆盖；非法输入/关系/权限/会话状态给出明确错误。
- 沿用会话、CSRF、membership、own/all 权限、事务租户上下文与审计；八张 CRM 表 FORCE RLS，复合外键禁止跨租户/跨客户关系。审计不记录正文；原 Worker 领取、租约、重试不变。
- 原生 dialog 的 Esc/返回焦点、键盘表格横滚、手机导航宽度，以及错误自动聚焦/滚入视口已实际验证；会话过期后的详情/保存清除旧客户内容。
- OpenAPI 和生成客户端已同步；README 指向 0003_crm head、客户操作与本地浏览器验收说明。依赖锁文件未变化。生产启动拒绝保留，身份和客户纵切不等于生产上线就绪。

架构说明见 [ADR-007](../../architecture/adr/ADR-007.md)，完整实现变更文件见 [清单](evidence/changed-files.txt)。

## 实际验证

环境沿用 Node 24.15.0 / npm 11.12.1、Python 3.12.7、PG 17.11 Homebrew、Keycloak 26.7.3、Java 21.0.6；具体命令退出码见 [验证记录](evidence/verification.json)。所有 PG 测试仅创建独立临时集群，真实 IdP 使用自己的复制目录/H2；没有连接、写入或停止常驻 PostgreSQL。

以下命令从仓库根执行，PG 参数本次实际为 `/opt/homebrew/opt/postgresql@17/bin`：

```bash
SILICON_TEST_PG_BIN="$(pg_config --bindir)" SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3" .venv/bin/python -m pytest apps/api/tests/test_crm.py -v --tb=short
SILICON_TEST_PG_BIN="$(pg_config --bindir)" SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3" .venv/bin/python -m pytest -v --tb=short
.venv/bin/python infra/export_openapi.py
npm run api:types
npm run typecheck
npm run build
python3 infra/prepare_demo_baseline.py --output /tmp/silicon-demo-source-check.json
python3 infra/check_visual_evidence.py
.venv/bin/python infra/check_docs.py
docker compose --env-file .env.example -f infra/compose.yaml config --quiet
git diff --check
```

| 检查 | 结果 | 证据/覆盖 |
|---|---|---|
| 新增 CRM PG/API 测试 | passed，7 tests，3.33s，exit 0 | [crm-tests.txt](evidence/crm-tests.txt)：CRUD/关联/历史/审计、并发编辑和幂等、同编号跨租户、CSRF/权限、搜索分页/own、非法内部成员/跨客户关系、002 升级 |
| 全套回归 | passed，45 tests，2 warnings，36.42s，exit 0；无 skip | [full-tests.txt](evidence/full-tests.txt)：真实 OIDC、无效认证、identity/RLS/字段与附件探针、API health/ready/DB 故障恢复、Worker 领取/重试/租约/持久化及客户 |
| 空库迁移 | passed | 每次测试 fixture 从空库 upgrade head 至 0003_crm，迁移角色与应用角色分离 |
| TASK-002 升级 | passed | 临时集群第二数据库先迁移 0002_identity、插入真实用户/membership/租户 job，再升 head；验证 CRM 权限、原身份/任务保留且 Worker 完成原任务 |
| OpenAPI/客户端 | passed | 重新生成后与生成前 hash 一致；生产 OpenAPI 仅新增 CRM 路由，没有测试/附件/报价接口 |
| 类型与构建 | passed，exit 0 | [typecheck.txt](evidence/typecheck.txt)、[build.txt](evidence/build.txt)，最终错误焦点修复后重跑；生产构建没有视觉冻结注入 |
| Demo 源码 | passed | [最终核验](evidence/demo-source-final-check.json)，完整 4+8 文件、身份与 fsck |
| 浏览器 E2E | passed，真实点击 | [复现步骤与观察](browser-acceptance.md)：真实 IdP 登录、选择企业、新建/编辑/刷新、隔离、退出/会话失效、键盘/错误/冲突；不以协议测试替代 |
| 视觉 | 已捕获并逐图检查，待独立差异复核 | [17 张截图清单](evidence/screenshot-manifest.json)、[同视口对照](../../design/task003-visual-comparison.md)；原图/迁移图均有 1440×900、390×844 |
| 文档/状态/历史报告 | passed | infra/check_docs.py 检查相对路径、状态、所有历史审查报告 hash 与链接 |
| Compose 配置 | passed，exit 0 | config --quiet；未强制启动 Docker，不等于容器验收 |
| git diff --check | passed，exit 0 | 提交前实际执行；[收尾检查](evidence/finalization-checks.json) |

认证单元测试使用替身/会话注入的部分仍明确标注，不能据此冒称真实登录；真实 Keycloak 集成单独执行且没有跳过。两个 warnings 来自现有 Starlette/httpx TestClient 与 AnyIO 弃用提示，没有为消除提示升级依赖。

## 浏览器修正与限制

浏览器验收期间修复了导航撑宽、401 后旧页面保留、长表单错误不可见三处问题；都用真实 UI 复测。首次 CRM 测试历史数量断言错误地假设随机 UUID 顺序，改为按项目名称选择待保留项后通过，不修改历史业务行为以迎合测试。截图采集早期误用视口目标/扩展名，已检查实际 JPEG 尺寸后重采，不缩放图片或静默接受整体差异。

开发证书经用户明确授权加入当前用户登录钥匙串，仅 SSL 信任；用户要求保留，未导入私钥/修改系统钥匙串。该证书至 2026-10-09，之后须生成新证书并重新取得信任授权。协议测试继续使用自己的临时 CA。浏览器栈/源码服务和本次标签已停止，viewport 已恢复，常驻 PG 未操作。

| 未验证/待确认 | 状态与恢复条件 |
|---|---|
| 独立代码/视觉验收 | 等待 Reviewer；上述有意 UI 差异须复核，不自行 accepted |
| 远程 CI | not_run，无远程；配置授权的远程与 runner 后单独执行，不能用本地通过代替 |
| Compose 容器运行 | not_run，本次无需启动 Docker；有容器运行环境后在独立卷执行初始化/迁移/API ready |
| 其他浏览器/其他视口 | not_run，本次只要求且只实际验证上述本机浏览器与两视口 |
| 生产运维/IdP 即时远端撤销 | not_run，沿用 TASK-002 限制；后续单独授权备份恢复、密钥轮换、入口防护、back-channel 等工作，保留 production 拒绝 |
| 地图素材许可 | 尚未进入地图生产化，本次不用地图；后续核实来源/许可/坐标系 |

未部署、未创建远程、未开始 TASK-004。head_scope 仅指实现及测试证据 commit；本结果/状态收尾作为其后的文档 commit，避免把文档自身 hash 伪写进自身。

## 独立审查修复（2026-09-10）

```yaml
task_id: TASK-003
status: review_ready
repair_base_commit: 45453c72ac2ab52a1e1375982256b1da70c0ef09
repair_head_commit: 005ea46446d6d6d140ce261e207901fbd8c4362a
repair_head_scope: R1_R2_implementation_contract_tests_and_evidence
review: docs/reviews/TASK-003-45453c7-review.md
```

开始时 main/HEAD 与指定基线完全一致；只有未跟踪的原独立审查报告，没有已跟踪用户修改。报告原样纳入修复提交，未改其 changes_requested 结论；文档检查新增该报告 SHA-256 断言。既有报告、测试输出和视觉基线均保留。上文 45 项通过属于原交付历史，不代表覆盖本轮竞态。此节作为修复实现 commit 之后的独立文档提交，不将该文档自身 hash 写成实现 hash。

### R1：绑定页面预期企业和会话上下文

- 新增 0004_session_context，为既有会话填充 context_id；每次显式选择企业轮换，包括 A→B→A。CRM 成员、列表、详情、新建和编辑统一要求 X-Expected-Tenant / X-Session-Context。声明不授予权限，服务端仍验证真实会话、CSRF、有效 membership、操作权限和 RLS。
- CRM 与切企业在同一 sessions 行锁下排序，校验和业务使用同一事务。保存先获得锁则只提交至 A，再切 B；切企业先获得锁则旧保存返回 409/CONTEXT_CHANGED。缺失声明返回 428/CONTEXT_REQUIRED，不改投、不自动重试。
- 前端按请求捕获上下文和代次，跨标签通知及窗口重新激活检查发现变化后清除列表、详情、表单及在途状态，要求重新选择企业；不转移旧草稿。取消之外还在成功 JSON 返回后验证代次，列表、详情和两种保存全部覆盖。选择企业的 POST 与后续 session 响应也受代次和返回 context_id 校验。
- 可重复回归在 `apps/api/tests/test_crm_context.py` 与 `apps/web/tests/context-race.test.ts`：无通知旧请求拒绝、A/B 不误新增、旧编辑不能改可见的 B 记录、缺失/ABA、保存和切企业的两个真实锁顺序，以及明确延迟 HTTP 200 成功返回的四种客户端请求。后者标注 fetch 传输替身，不以超时或失败代替成功竞态。

### R2：完整客户聚合的一致性读取

详情先以独立查询取得客户父记录 FOR SHARE，再读取版本、计数、联系人、项目及人员、地点、内部负责人和历史；保存沿用父记录 FOR UPDATE 后整体替换，事务提交前持锁。所有现有生产关联写路径由 save 进入并遵守该顺序；没有只补写 version。设计及未来子项写路径约束见 [ADR-008](../../architecture/adr/ADR-008.md)。

真实 PG 回归在 contacts 查询后暂停读者，另一事务走正常 save 替换联系人和项目，以 pg_blocking_pids 确认写者正在等待；读者提交后才允许写者完成。断言完整旧版本的计数、联系人引用、项目、地点、内部负责人和历史，以及写后的版本 2。同步事件均有有限等待，finally 释放门控；未延长产品超时。

### 本轮实际验证

命令均从仓库根执行。PG 参数仍为 `/opt/homebrew/opt/postgresql@17/bin`；真实 IdP 使用 `.tools/keycloak/keycloak-26.7.3` 的独立夹具副本。没有连接、停止或写入常驻 PG，未修改 TLS 校验或证书信任。

```bash
SILICON_TEST_PG_BIN=/opt/homebrew/opt/postgresql@17/bin SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3" .venv/bin/python -m pytest -v --tb=short
node --test apps/web/tests/context-race.test.ts
.venv/bin/python infra/export_openapi.py
npm run api:types
npm run typecheck
npm run build
.venv/bin/python infra/check_docs.py
docker compose --env-file .env.example -f infra/compose.yaml config --quiet
git diff --check
git diff --cached --check
```

| 检查 | 实际结果 |
|---|---|
| 全部后端 | **52 passed，0 skipped，2 warnings，37.26s，exit 0**；[最终复跑输出](evidence/revision/full-tests-rerun.txt)，包括真实 Keycloak、会话/CSRF/租户切换、RLS、Worker 授权/租约/重试/持久化及全部客户回归 |
| R1/R2 真实 PG 竞态 | 6 项（包含参数化的两个切换/保存顺序）随全套通过；新测试修复前各自失败，保留 [R1 red](evidence/revision/r1-red.txt)、[R2 red](evidence/revision/r2-red.txt) |
| 空库及升级迁移 | passed，fixture 从空库至 0004；另外从 0002、0003 升级，既有会话得到非空 context_id、身份/membership/租户 job 保留并可被 Worker 完成 |
| 延迟成功响应 | **5 passed，0 skipped，exit 0**；[原始输出](evidence/revision/frontend-races.txt)，使用生产请求边界，测试传输替身明确标注；已加入 CI 配置 |
| 契约、类型、构建 | passed；OpenAPI/客户端重复生成 hash 一致，类型检查与 Vite 构建成功；[命令与 hash](evidence/revision/checks.json)、[验证记录](evidence/revision/verification.json) |
| 双标签真实浏览器 | passed，仅指 [逐步实测记录](evidence/revision/browser-validation.md) 中场景：新建/编辑失效、明确重选后正常 CRUD/刷新、B 无误写、退出后受保护内容清除 |
| 文档、Compose 配置、diff | passed，exit 0；文档检查含历史审查 hash、状态和相对链接，提交前检查暂存差异；Compose 未启动容器 |

补强 R2 断言后的第一次全套复跑出现 **51 passed / 1 error**：同时运行的浏览器测试栈与 OIDC 夹具冲突于 Keycloak HTTP 8080。[该次输出](evidence/revision/full-tests-final.txt) 和 [端口冲突日志](evidence/revision/oidc-port-conflict.txt) 原样保留。正常关闭本次 browser_stack（BROWSER_STACK_CLEANED，exit 0）后完整复跑得到上述 52 passed；没有通过禁用 TLS、跳过真实 IdP、修改常驻服务或升级依赖消除失败。两条既有 Starlette/AnyIO 弃用提示保留。

### 文件、截图与限制

完整 [变更文件清单](evidence/revision/changed-files.txt) 包含相关 API/身份/CRM 事务、0004 迁移、前端状态、契约、测试、ADR/README、原审查报告及新证据。依赖锁文件、原 Demo、视觉 CSS/token、TASK-004 范围均未变更。

[本轮截图清单](evidence/revision/screenshots.json) 为 3 张原始 1280×720 图片，已查看；不替换历史两视口基线。新增失效提示及重新选择状态为有意变化，没有新模板。浏览器测试标签和独立栈已关闭。

- 远程 CI：**not_run**，无远程；本地通过不等于远程通过。
- Compose 容器实测：**not_run**，本轮只验证配置，没有强制启动 Docker。
- 浏览器网络层延迟成功响应拦截：**not_run**；该竞态已有仓库确定性 Node 测试，未冒称浏览器拦截测试。
- 浏览器通知全丢失故障注入：**not_run**；窗口激活检查已实现，服务端无通知拒绝已由真实 PG/API 测试覆盖。后续可在受信浏览器测试能力下补充该体验层故障注入。
- 生产启动拒绝仍保留；不部署、不更改证书信任，不开始 TASK-004。状态保持 **review_ready**，等待独立审查，不自行 accepted。
