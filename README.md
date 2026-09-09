# 硅屿 SILICON

TASK-000 已由产品/架构负责人确认 accepted。当前 TASK-001 工程骨架：React/TypeScript/Vite 最小应用壳、FastAPI 健康检查、PostgreSQL 迁移和独立 Worker；未实现业务功能或生产身份体系。最终任务状态见 [backlog](docs/tasks/backlog.md)。

## 入口与边界

先读 [AGENTS.md](AGENTS.md)、[runtime/project.json](runtime/project.json)、[TASK-001](docs/tasks/TASK-001/task.md)。产品/架构基线见 [scope](docs/product/scope.md)、[架构](docs/architecture/architecture.md)、[ADR-005](docs/architecture/adr/ADR-005.md)、[版本依据](docs/architecture/dependencies.md)；[原 Demo](docs/design/demo-baseline.md) 为独立只读参考。

所有以下命令从仓库根执行。路径均相对仓库；不要把历史指南的会话路径写成依赖。当前无远程仓库或部署配置，CI 文件已提供，未运行远程 CI。TASK-002 必须另行明确分配，不自动开始。

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

silicon_migrator 拥有迁移对象；silicon_app 非 owner/非 superuser/无 BYPASSRLS，只有所需 DML。完整租户权限留给 TASK-002。原生 Homebrew 本地信任认证沿用原配置，仅监听回环；本地角色权限测试不等于已实现用户登录。

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

必须确认 upgrade 成功且 current 显示 `0001_platform (head)`，再启动下面的 API/Worker。三步分别验收：数据库启动成功 → 迁移到 head → API 启动后 `/api/v1/ready` 返回 200/ready；数据库健康检查不能代替后两步。

## 启动 Web、API、Worker

在三个终端分别执行（均须能找到 uv）：

```bash
npm run dev
```

```bash
uv run --locked --env-file .env uvicorn silicon.main:create_app --factory --host 127.0.0.1 --port 8000
```

```bash
uv run --locked --env-file .env python apps/worker/main.py
```

Web 为 http://127.0.0.1:5173，Vite 将 /api 代理到 8000。同域代理不添加跨域白名单；端口冲突时修改已知配置，不终止未知服务。IdP 8080 仅预留，当前没有 IdP 服务。

```bash
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:8000/api/v1/ready
uv run --locked --env-file .env python apps/worker/main.py --enqueue local-smoke-001
uv run --locked --env-file .env python apps/worker/main.py --once
```

health 返回 200/ok；ready 验证数据库和迁移版本，成功 200/ready，数据库不可用或未迁移为 503/DATABASE_NOT_READY。每个响应有 X-Request-ID。Worker 完成 smoke 后 result 持久化为 smoke completed；相同 dedupe key 不重复创建。仅此命令行开发任务可用，无业务写 API、外部调用或通知。

## 验证

```bash
uv run --locked python infra/export_openapi.py
npm run api:types
npm run typecheck
npm run build
SILICON_TEST_PG_BIN="$(pg_config --bindir)" uv run --locked pytest -v
uv run --locked python infra/check_docs.py
git diff --check
```

测试强制 PostgreSQL 17.11；使用该程序建立临时独立集群、随机空闲端口和虚构 smoke job，不读取 DATABASE_URL 指向的库。测试覆盖空库迁移、角色权限、实际 HTTP 服务、停止/重启数据库后的 200/503/恢复、Worker 独立进程和重启持久化、并发领取、防重、过期租约/旧执行者隔离、重试/failed。结束后停止并清理测试自己创建的临时集群。

没有原生 17.11 的 CI/机器可先运行 `python3 infra/build_test_postgres.py --prefix /tmp/silicon-pg17`（需要编译器/make/bison/flex），再用该目录的 bin 作为 SILICON_TEST_PG_BIN；源码下载校验固定官方 SHA-256。已有目录不会覆盖。

OpenAPI JSON 和 schema.d.ts 均为生成物，不手改。TASK-000/verify.py 是历史基线验证脚本，固定当时任务状态；当前状态检查使用 infra/check_docs.py。实际证据和限制见 [TASK-001/result.md](docs/tasks/TASK-001/result.md)。

## 停止、清理和恢复

Web/API/Worker 分别 Ctrl-C，Worker 也响应 SIGTERM。本机常驻 PostgreSQL 保持运行，只有需要停止时执行 `brew services stop postgresql@17`；不要为单个项目清理而删除本机数据目录。可选容器使用 `docker compose --env-file .env -f infra/compose.yaml down`，保留卷；`down -v` 会删除该专属开发卷，仅确认数据可丢弃时手工执行。

构建产物只在 apps/web/dist，依赖环境在 node_modules/.venv/.tools；均被忽略，按需重装。两个原 Demo 的 dist 是源码，禁止删除。迁移运行器自动在临时目录排除 ._*，不清理仓库或参考仓库的磁盘元数据。测试库可重建；持久开发库降级须先备份，0001 降级会删除 jobs/outbox，不自动降级。
