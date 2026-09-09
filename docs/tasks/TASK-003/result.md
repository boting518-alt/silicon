# TASK-003 原 UI 壳迁移与客户纵切交付

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
