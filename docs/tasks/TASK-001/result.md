# TASK-001 工程骨架交付

```yaml
task_id: TASK-001
status: review_ready
accepted_baseline: 88e3044ac8749a9c003fe2ecc78a6de0c9abf1d6
base_commit: 1e3b6c5fc7c40d9fc831de8e897d4c23f12cb1c6
head_commit: recorded_in_followup_evidence_commit
migration_impact: new platform tables only; no business migration
next_task: TASK-002 (planned, not authorized)
```

## 交接

产品/架构负责人明确确认 TASK-000 accepted，并分配 TASK-001。核对 HEAD 与 88e3044 完全相同；初始只有两份未跟踪 Review，无已跟踪用户修改。两份报告原样纳入 Git，SHA-256 后续检查一致；原 changes_requested 与增量 passed 结论未改。任务交接单独提交为 1e3b6c5fc7c40d9fc831de8e897d4c23f12cb1c6，之后才实现骨架。TASK-000 task/result/backlog 已记录用户验收依据，AGENTS Current scope 与 runtime.current_task 切换到 TASK-001。

## 实现

- React 19.2.8 / TypeScript 5.9.3 / Vite 8.2.2 最小壳，复用 packages/ui/tokens.css 的硅屿颜色、字体、边框与圆角；只有真实连接检查，没有假数据、完整侧栏或业务页面。
- FastAPI 工厂入口：health 200 不依赖数据库；ready 查询实际迁移版本，数据库停止或迁移缺失返回 503 和稳定错误字段，不暴露 SQL、DSN 或内部异常。每个响应有请求 ID。
- PostgreSQL 17.11 / SQLAlchemy / Alembic：0000 空基线，0001 仅 jobs/outbox_events；运行角色与迁移角色分开，运行角色非 owner/非超级用户、无 BYPASSRLS，不能建表。
- 独立 Worker 复用 silicon 包。只有开发 smoke 入队与处理；真实事务领取、幂等入队、租约 token、过期重领、心跳、重试退避、failed 和完成持久化。没有业务/租户任务，也不处理任意输入、调用外部服务或发通知。outbox 仅基础表，无投递器。
- npm/uv 精确版本与传递锁文件；生成 OpenAPI JSON 和 TypeScript 类型；本机运行/可选 Compose、环境示例、CI 和 README。
- ADR-005 解释有界 smoke、开发环境限制和迁移临时副本；dependencies.md 记录官方版本核验、兼容选择与 IdP 后置边界。

完整变更路径由 `git diff --name-only <base_commit> <head_commit>` 获取。主要目录为 apps/web、apps/api、apps/worker、packages/ui、packages/api-client、infra、.github，以及根依赖/配置文件和相关任务文档。没有修改原 Demo、部署配置、远程或业务模块。

## 实际验证

运行环境：macOS arm64；Node 24.15.0、npm 11.12.1、Python 3.12.7、uv 0.12.11。本次最终数据库测试使用本机 Homebrew PostgreSQL 17.11 的可执行程序，每次新建独立临时集群，不连接常驻库。具体逐命令退出码见 verification.json，实际输出见 verification.txt（机器仓库路径已替换为 `<repo>`）。

| 命令 / 检查 | 实际结果 |
|---|---|
| `.tools/bin/uv sync --locked` | passed，退出 0，严格按 Python 锁文件安装 |
| `npm ci --ignore-scripts` | passed，退出 0，从 npm 锁文件重装 |
| `uv run --locked python infra/export_openapi.py` 与 `npm run api:types` | passed，退出 0，生成 API 契约及对应类型 |
| `npm run typecheck` / `npm run build` | passed，分别退出 0；Vite 16 模块构建 |
| `SILICON_TEST_PG_BIN="$(pg_config --bindir)" uv run --locked pytest -v` | passed，10 tests，2 条上游弃用警告 |
| `uv run --locked python infra/check_docs.py` | passed；任务状态/相对目录/审查报告 hash/本地链接一致 |
| `docker compose --env-file .env.example -f infra/compose.yaml config -q` | passed，仅配置校验，退出 0 |
| `npm audit --json` | passed，0 已报告漏洞；不是全面安全认证 |
| `git diff --check` | passed，退出 0；提交前再查暂存差异 |

10 项测试实际覆盖：

1. 空 PostgreSQL 创建后的同一 bootstrap.sql 与全部迁移；迁移版本、运行角色和建表拒绝。
2. health/ready 正常响应和 request ID。
3. 未完成迁移时 ready 503、health 200。
4. 并发同 key 入队只创建一个 job；Worker 独立进程完成后重启不重复处理，结果和完成时间仍在。
5. 并发领取同 job 只有一个胜者。
6. 已锁行不会阻塞领取另一任务（SKIP LOCKED）。
7. 过期任务重领及新租约 token；旧 Worker 无法心跳、完成或失败覆盖新执行者。
8. 崩溃耗尽次数进入 failed；未知类型按退避重试直至 failed。
9. 实际 Uvicorn HTTP 服务，在真正停止 PG 后 health 200/ready 503、错误不泄露连接信息；恢复 PG 后 ready 200；常驻 Worker 完成任务，Worker/数据库再次重启后仍 completed 且 attempts=1。
10. 生产环境模式拒绝启动，避免将无身份骨架当生产系统。

## 执行中问题与修复

- 官方元数据中 TypeScript 当前主版本为 7，而 OpenAPI 工具 peer 为 ^5.x：选择并实测 5.9.3，不盲用 latest。
- npm 初装报告间接 js-yaml 漏洞：override 固定 4.3.2，重装、类型生成、构建和审计均通过。
- 原生 Alembic 扫描外置卷的 ._*.py 报 null bytes：增加 infra/migrate.py 在临时副本排除附属文件后调用 Alembic，实际迁移通过；未删除源码或参考仓库元数据。
- 第一次 OpenAPI 导出因沙箱不允许写 uv 缓存失败，导致当次缺少类型文件；在允许的依赖执行环境完成导出后重新运行通过，没有用空类型替代。
- 本机 PG 17 输出含 Homebrew 后缀，最初版本检查过严；修正为准确识别 17.11 后，使用本机版本重跑全部测试通过。
- Starlette TestClient 对 httpx 的弃用提示及其 anyio BlockingPortal 别名弃用提示共 2 条保留；没有隐藏警告。真实 HTTP/进程测试不只依赖 TestClient。

## 用户追加：本机 PostgreSQL 14 升级到 17

执行期间用户明确要求以后统一用本机 17，已完成 Homebrew PostgreSQL 17.11 安装、pg_upgrade --check、复制式迁移、默认命令链接切换、17 服务启动及迁移后 analyze/连接验证。14 原安装与原数据目录保留且停止；另有冷备份、逻辑备份和私有恢复说明存于用户本机目录，不纳入 Git。原库只有默认 postgres 数据库，没有用户表；未迁移业务数据。继承原显式配置及本地认证，17 仅监听回环 5432。

初始 Homebrew 缓存先提供 17.10；刷新官方索引后升级为 17.11，再迁移/验证。因此最终本机、开发版本要求和测试版本均为 17.11。测试始终使用独立临时集群，未停止或写入升级后的常驻库。启动服务后首次 analyze 早于服务就绪而失败，待就绪后复跑成功；没有把首次失败计为通过。

## 限制与待复核

- 远程 CI：not_run。当前没有 remote，只有 CI 定义与本地等价命令证据；没有宣称 GitHub Actions 已通过。
- Docker Compose 容器启动：not_run，Docker daemon 未运行。恢复条件是启动 Docker 并选择空闲的配置端口，再执行 README 的 up --wait 与迁移；不以 config 检查代替容器实测。
- Keycloak 26.7.3 仅官方候选版本记录，未安装/启动/验证 OIDC；完整身份/租户/RLS 属 TASK-002。
- 视觉截图、浏览器点击/E2E 与完整业务页面：not_run，属于 TASK-003 及后续。Web 只建 token 壳，不声称已迁移 Demo。
- 无业务金额、合同、库存、收付款、附件存储或业务 Agent。长任务持续心跳、外部幂等/投递等未来能力未实现，禁止将 smoke 用作真实业务执行器。
- 迁移 downgrade 会删除新增平台表，未自动对持久数据执行。回退代码不能替代数据库备份。

## 审查交接

TASK-001 状态仅为 review_ready，等待独立 Reviewer，执行者不标 accepted。TASK-002 保持 planned，未自动开始。先提交可复核实现与证据，再在单独证据提交记录实际内容 head_commit，避免文件包含自身 SHA；最终交付 SHA 在 `git rev-parse HEAD` 与回复中给出。Reviewer 检查 base..head_commit 的实现及随后仅报告证据的差异。
