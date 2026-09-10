# 硅屿 SILICON

TASK-000～TASK-005 已由产品/架构负责人确认 accepted。当前 TASK-006 已实现审批、发布快照与合同草稿，状态 review_ready；TASK-004 在原硅屿 UI 壳上增加商品目录、准系统包件/BOM 与销售价格版本；保留独立客户档案；沿用 Keycloak OIDC、租户权限和审计。仅系统内报价发布与来源合同草稿启用，签约、库存等入口未启用，生产模式仍拒绝启动。最终任务状态见 [backlog](docs/tasks/backlog.md)。

## 入口与边界

先读 [AGENTS.md](AGENTS.md)、[runtime/project.json](runtime/project.json)、[TASK-006](docs/tasks/TASK-006/task.md)。产品/架构基线见 [scope](docs/product/scope.md)、[架构](docs/architecture/architecture.md)、[ADR-006](docs/architecture/adr/ADR-006.md)、[客户决策 ADR-007](docs/architecture/adr/ADR-007.md)、[版本依据](docs/architecture/dependencies.md)；[原 Demo](docs/design/demo-baseline.md) 为独立只读参考。

所有以下命令从仓库根执行。路径均相对仓库；不要把历史指南的会话路径写成依赖。当前无远程仓库或部署配置，CI 文件已提供，未运行远程 CI。TASK-006 已明确分配；不自动开始 TASK-007。

## 安装锁定依赖

需要 Node 24.15.0 / npm 11.12.1、Python 3.12.7、uv 0.12.11、PostgreSQL 17.11。版本分别记录于 .node-version、.python-version 和锁文件。已有 uv 0.12.11 可跳过工具环境步骤：

```bash
python3 -m venv .tools
.tools/bin/python -m pip install uv==0.12.11
export PATH="$PWD/.tools/bin:$PATH"
npm ci --ignore-scripts
uv sync --locked
cp .env.example .env
```

.env 仅本地，示例密码不是生产凭据；不要提交 .env。已有配置先核对，不覆盖。Python 应用只读取 DATABASE_URL，迁移只读取 MIGRATION_DATABASE_URL，发布时必须分别注入。SILICON_ENV=production 目前会拒绝启动。

## 数据库初始化（两条路线二选一）

### 本机 PostgreSQL（默认）

本机已按用户要求从 14 升为 Homebrew PostgreSQL 17.11；14 停止并保留原数据，备份在本机用户目录，不入 Git。统一使用 17 的命令和服务。其他机器安装对应版本后再执行。检查服务：

```bash
postgres --version
pg_isready
```

首次建立本项目专用开发库，使用本机管理员身份（不要对已有同名库或角色重复执行）。以下值与 .env.example 对应，修改 .env 密码时必须同步 bootstrap 参数：

```bash
createdb silicon
psql -X -d silicon -v ON_ERROR_STOP=1 -v migration_password=local_migration_only -v app_password=local_app_only -f infra/bootstrap.sql
```

silicon_migrator 拥有迁移对象；silicon_app 非 owner/非 superuser/无 BYPASSRLS，只有所需 DML。全局身份表与租户作用域表的划分见 ADR-006。原生 Homebrew 本地信任认证沿用原配置，仅监听回环；本地角色权限测试不等于已实现用户登录。

### Compose PostgreSQL（可选）

与本机服务二选一，不能同时占 5432：

```bash
docker compose --env-file .env -f infra/compose.yaml up -d --wait db
```

使用 postgres:17.11-bookworm；全新卷由容器初始化脚本执行 bootstrap.sql 创建角色和权限，**不要再执行本机路线的 createdb/bootstrap**。`up --wait` 仅说明数据库通过 pg_isready，不表示 Alembic 迁移完成。当前仅验证 Compose 配置语法，容器启动仍为 not_run；初始化失败时检查该开发卷和容器日志。

## 两条路线都必须执行迁移

完成所选数据库初始化后，先确认根目录 `.env` 中 `DATABASE_URL` 和 `MIGRATION_DATABASE_URL` 的主机、端口、库名及各自角色密码均指向该数据库。API/Worker 使用前者，迁移使用后者。为避免终端已有变量覆盖 `.env`，在迁移及应用启动终端先执行下面的 unset。

默认连接为 `127.0.0.1:5432/silicon`。若 Compose 改为 `127.0.0.1:55432:5432`，同时将 `.env` 中两条连接 URL 的主机端口改为 `127.0.0.1:55432`，容器内部仍用 5432。本机使用其他端口时，也同步两条 URL，并给该路线的 createdb/psql 指定对应 `-h` 与 `-p`；不能让迁移和 API 连接不同实例。

```bash
unset DATABASE_URL MIGRATION_DATABASE_URL
uv run --locked --env-file .env python infra/migrate.py upgrade head
uv run --locked --env-file .env python infra/migrate.py current
```

必须确认 upgrade 成功且 current 显示 `0006_quotes (head)`，再启动下面的 API/Worker。三步分别验收：数据库启动成功 → 迁移到 head → API 启动后 `/api/v1/ready` 返回 200/ready；数据库健康检查不能代替后两步。

## 本地真实 IdP 与 HTTPS

需要 Java 21（本次实际为 21.0.6），固定 Keycloak 26.7.3。以下生成的是虚构开发 realm、证书和用户，不用于生产。已有 `.tools/keycloak/keycloak-26.7.3` 时不重复下载；脚本拒绝覆盖已有目录。证书脚本也拒绝覆盖已有私钥。

```bash
uv run --locked python infra/fetch_keycloak.py --destination .tools/keycloak
uv run --locked python infra/dev_tls.py
uv run --locked python infra/keycloak_realm.py .tools/keycloak/keycloak-26.7.3/data/import/silicon-dev-realm.json
.tools/keycloak/keycloak-26.7.3/bin/kc.sh start-dev --http-host=127.0.0.1 --http-enabled=false --https-port=8443 --https-certificate-file="$PWD/.tools/tls/localhost.crt" --https-certificate-key-file="$PWD/.tools/tls/localhost.key" --import-realm --cache=local
```

保持该终端运行；Keycloak 使用自己目录内的开发 H2 存储，不连接本机 PostgreSQL。浏览器访问 `https://localhost:8443/realms/silicon-dev/.well-known/openid-configuration` 可确认 IdP discovery；本地自签名证书需由设备用户明确授权加入开发浏览器认可的证书信任，再访问前端；不能忽略证书错误或关闭主机名验证。脚本不修改系统证书信任。API 通过 `OIDC_CA_BUNDLE=.tools/tls/localhost.crt` 验证 IdP 证书，不关闭 TLS 校验。

根目录 `.env` 中设置（与 `.env.example` 一致）：

```dotenv
OIDC_ISSUER=https://localhost:8443/realms/silicon-dev
OIDC_CLIENT_ID=silicon-web
OIDC_CLIENT_SECRET=fictional-dev-client-secret
OIDC_CA_BUNDLE=.tools/tls/localhost.crt
PUBLIC_ORIGIN=https://localhost:5173
```

迁移成功后，在另一终端为虚构用户配置两个开发企业：

```bash
unset DATABASE_URL MIGRATION_DATABASE_URL OIDC_ISSUER OIDC_CLIENT_ID OIDC_CLIENT_SECRET OIDC_CA_BUNDLE PUBLIC_ORIGIN SILICON_ENV
uv run --locked --env-file .env python infra/provision_dev_identity.py
```

该显式脚本使用迁移角色，仅接受上述 development realm；它不建立会话，也不提供快捷登录接口。浏览器仍须在 Keycloak 输入虚构账户 `alice` / `Fictional-alice-17!`。新 OIDC 用户默认没有 membership，不能自动加入企业。企业、角色和 membership 管理界面未在本任务建设；开发配置由该脚本提供。

端口或域名变化时，同步 `.env` 的 issuer/origin、realm 的精确回调与退出 URI、Vite 配置和本地证书 SAN；不要使用通配回调。Keycloak 只在 realm 首次导入时读取文件，已有开发 realm 的更改须通过 IdP 管理流程处理，不能假定重新启动会覆盖导入。

## 启动 Web、API、Worker

在三个终端分别执行（均须能找到 uv）：

```bash
npm run dev
```

```bash
uv run --locked --env-file .env uvicorn silicon.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

```bash
uv run --locked --env-file .env python apps/worker/main.py
```

Web 为 https://localhost:5173，Vite 使用本地证书并将 /api 代理到回环 8000；API 本身不对外监听。会话 Cookie 始终 Secure/HttpOnly，写请求要求同源 Origin 和 CSRF token。API 关闭访问日志以避免回调 code/state 进入 URL 日志。端口冲突时修改已知配置，不终止未知服务。

```bash
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:8000/api/v1/ready
uv run --locked --env-file .env python apps/worker/main.py --enqueue local-smoke-001
uv run --locked --env-file .env python apps/worker/main.py --once
```

health 返回 200/ok；ready 验证数据库和迁移版本，成功 200/ready，数据库不可用或未迁移为 503/DATABASE_NOT_READY。每个响应有 X-Request-ID。Worker 完成 smoke 后 result 持久化为 smoke completed；相同 dedupe key 不重复创建。smoke 仅为无租户的命令行开发任务；租户 identity.check 只能由已授权的内部服务入队，执行时重查 membership。没有业务处理器、任意 payload、通知或外部副作用。

## 商品、包件/BOM 与价格

选择企业后，管理员可进入商品目录、包件/BOM 和价格维护；成员/viewer 只读。目录写入与客户一样要求页面预期企业/context_id、CSRF、幂等键与 expected_version。目录是企业共享主数据，不按客户 owner 限制。制造商、销售品牌独立，不包含供应商管理或成本字段。

先建主机和部件 SKU，再建立包件（包含行）或 BOM（可含另计价行），选择版本化规则资料；缺资料显示 UNKNOWN。发布冻结快照，修订创建新草稿，旧版不变。发布仅冻结目录，不表示兼容通过。包含件不重复收费，目录不计算替换折价；草稿总额由 TASK-005 后端计算。

价格表输入 CNY 十进制金额、明确范围、含税口径、来源和 UTC 期间；先保存再发布。当前价只使用已发布且处于左闭右开期间的条目；未知/过期不是零价。同范围/SKU/税口径的已发布期间重叠会拒绝，修订须改到不重叠期间，不缩短原版期间。没有税率或汇率换算。设计与 API 见 [ADR-009](docs/architecture/adr/ADR-009.md)。

本机/Compose 都先迁移到 0006 再验证 ready。浏览器复现仍使用独立 `infra/browser_stack.py`；设置 `SILICON_BROWSER_CATALOG=1` 时虚构用户在企业 B 为只读、A 为管理员，用于权限验证。请先结束真实 OIDC pytest 再启动浏览器栈，避免现有 IdP HTTP 8080 监听冲突。不改变证书信任。目录测试：`SILICON_TEST_PG_BIN="$(pg_config --bindir)" .venv/bin/python -m pytest apps/api/tests/test_catalog.py -v`。

## 配置报价草稿

选择“报价与利润”后，选择客户/项目、已发布包件或 BOM、整机数量与部件；点击原等距 SVG 可定位配置字段。包含件明确不另收费，取消包含件不会抵扣根包件基价；替换件另行计价。利润、正式发布与审批未启用。admin/member 可维护有权访问客户的草稿，viewer 只读；折扣应用另外要求 quote.discount（首期 admin）。

“重新计价”只试算；“保存草稿”始终重新核验并持久化，刷新后从已保存列表打开。页面区分未保存配置、保存时金额和当前试算；配置改变或窗口重新激活会隐藏旧试算，要求重新计价。当前价格查询记录来源/版本/期间，未知价不当零元。金额可计算不等于可销售，真实销售/发布政策未配置，UNKNOWN 不代表兼容通过。所有请求仍绑定企业和会话上下文，切企业清空旧草稿与异步结果。

开发政策见 [ADR-010](docs/architecture/adr/ADR-010.md)：CNY 原税口径、HALF_UP 到分，单码百分比/最低额/最高优惠，无税率推定、次数配额、预占或核销。未配置政策不能使用优惠。测试种子 DEMO5 为虚构 5% 优惠、5000.00 CNY 上限，只由独立测试启动脚本植入，不自动成为应用的业务配置；没有折扣维护生产接口。

独立浏览器复现（已准备同版本 PG/Keycloak、可信证书和固定字体后；不执行本机 createdb/bootstrap）：

```bash
SILICON_TEST_PG_BIN="$(pg_config --bindir)" SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3" SILICON_BROWSER_CATALOG=1 SILICON_BROWSER_CATALOG_SEED=1 SILICON_BROWSER_QUOTES=1 .venv/bin/python infra/browser_stack.py
```

准确操作、限制及两视口截图见 [TASK-005 浏览器验证](docs/tasks/TASK-005/browser-acceptance.md)。报价关联项目后，CRM 保留相同项目 ID 的正常编辑可继续；直接移除被引用项目会原子拒绝，需先将草稿改关联到其他项目。最小 UI 每类别支持一个追加型号（数量可变），客户/草稿选择当前最多 100 条；更大目录检索与复杂配置器不在本任务扩展。

## 客户管理

CRM 列表、详情、新建、编辑和成员查询均要求 `X-Expected-Tenant` 与 `X-Session-Context`，分别来自当前页面绑定的 tenant_id 和 GET /session 的 context_id；它们只用于错配检查，不授予访问权限。缺失返回 428/CONTEXT_REQUIRED，不一致返回 409/CONTEXT_CHANGED。切企业每次轮换 context_id（包括切回原企业）；其他标签的旧表单失效，必须明确重新选择，不自动迁移草稿或重试保存。更新到 0004 后旧页面须刷新加载新客户端。详见 [ADR-008](docs/architecture/adr/ADR-008.md)。

登录并选择企业后可搜索、分页、打开档案、新增和编辑客户。客户编号在企业内唯一；联系人、项目角色、内部负责人和装机地点一起保存，刷新后仍可查询。viewer 不能保存；其他企业不可见；并发编辑冲突时先重载最新版本再合并。合同、设备与正式报价发布入口禁用，不返回演示成功。

浏览器真实验收与固定视觉夹具的复现方法见 [浏览器验收](docs/tasks/TASK-003/browser-acceptance.md)，原始截图及有意变化见 [视觉对照](docs/design/task003-visual-comparison.md)。浏览器测试栈只创建独立临时 PG/Keycloak；不要先执行本机 createdb 或连接常驻数据库。测试客户端显式信任夹具生成的 CA 并启用主机名验证，缺失证书直接失败。

## 验证

```bash
uv run --locked python infra/export_openapi.py
npm run api:types
node --test apps/web/tests/*.test.ts
npm run typecheck
npm run build
SILICON_TEST_PG_BIN="$(pg_config --bindir)" SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3" uv run --locked pytest -v
uv run --locked python infra/check_docs.py
git diff --check
```

真实 OIDC 测试将指定 Keycloak 分发包复制到临时目录，启动独立 HTTPS IdP/API，用真实表单完成授权码交换、退出与会话失效；不读写上述手工开发 IdP 的 data。缺少 SILICON_TEST_KEYCLOAK_HOME 会明确 skip/not_run，不能据其余测试通过宣称 OIDC 通过。test_oidc_validation.py 的 HTTP 替身与 test_identity.py 的会话夹具单独标注；测试资源和附件探针只在测试模块注册，不在生产路由或迁移中。

测试强制 PostgreSQL 17.11；使用该程序建立临时独立集群、随机空闲端口和虚构 smoke job，不读取 DATABASE_URL 指向的库。测试覆盖空库迁移、角色权限、实际 HTTP 服务、停止/重启数据库后的 200/503/恢复、Worker 独立进程和重启持久化、并发领取、防重、过期租约/旧执行者隔离、重试/failed。结束后停止并清理测试自己创建的临时集群。

没有原生 17.11 的 CI/机器可先运行 `python3 infra/build_test_postgres.py --prefix /tmp/silicon-pg17`（需要编译器/make/bison/flex），再用该目录的 bin 作为 SILICON_TEST_PG_BIN；源码下载校验固定官方 SHA-256。已有目录不会覆盖。

OpenAPI JSON 和 schema.d.ts 均为生成物，不手改。TASK-000/verify.py 是历史基线验证脚本，固定当时任务状态；当前状态检查使用 infra/check_docs.py。本次实际证据和限制见 [TASK-005/result.md](docs/tasks/TASK-005/result.md)，目录历史证据见 [TASK-004/result.md](docs/tasks/TASK-004/result.md)，客户历史证据见 [TASK-003/result.md](docs/tasks/TASK-003/result.md)，身份历史证据见 [TASK-002/result.md](docs/tasks/TASK-002/result.md)，历史骨架证据保留于 [TASK-001/result.md](docs/tasks/TASK-001/result.md)。

## 停止、清理和恢复

Keycloak/Web/API/Worker 分别 Ctrl-C，Worker 也响应 SIGTERM。本机常驻 PostgreSQL 保持运行，只有需要停止时执行 `brew services stop postgresql@17`；不要为单个项目清理而删除本机数据目录。可选容器使用 `docker compose --env-file .env -f infra/compose.yaml down`，保留卷；`down -v` 会删除该专属开发卷，仅确认数据可丢弃时手工执行。

构建产物只在 apps/web/dist，依赖环境在 node_modules/.venv/.tools；均被忽略，按需重装。两个原 Demo 的 dist 是源码，禁止删除。迁移运行器自动在临时目录排除 ._*，不清理仓库或参考仓库的磁盘元数据。测试库可重建；持久开发库降级须先备份，0006 降级会删除所有报价草稿、选择、优惠配置和幂等结果；0005 降级会删除全部目录、BOM/规则/价格版本和目录命令记录；0004 降级会移除上下文版本列，不与新客户端兼容；0003 降级会删除全部 CRM 数据、角色历史和幂等结果；0002 降级会删除身份、membership、会话与审计；0001 降级会删除 jobs/outbox，不自动降级。

TASK-004 浏览器复现及固定虚构目录夹具见 [历史浏览器验证](docs/tasks/TASK-004/browser-acceptance.md)。TASK-004 已 accepted；其历史 result 的 review_ready 与验证限制保持原样。当前 TASK-005 为 review_ready，不自动开始 TASK-006。

## TASK-006 审查入口

[任务与发布边界](docs/tasks/TASK-006/task.md)、[ADR-011](docs/architecture/adr/ADR-011.md)、[验证结果](docs/tasks/TASK-006/result.md)、[两身份浏览器准备](docs/tasks/TASK-006/browser-acceptance.md)。开发政策只在独立测试栈显式种入；真实企业无政策阻断发布。所有报价须双人审批，确定性BLOCK不可绕过。已发布正文不可修改，合同只是来源草稿，不代表签约或核销。

当前工作：[TASK-007 合同完善与签约登记](docs/tasks/TASK-007/task.md) executing；TASK-006 已由负责人接受，见 [交接](docs/tasks/TASK-007/handoff.md)。不开始 TASK-008。
