# TASK-001 独立审查

- 日期：2026-09-09
- 实际审查 HEAD：`8b7cf4a4a0dc1748e5142afb6b45876708febb1b`
- 交接/实现基线：`1e3b6c5fc7c40d9fc831de8e897d4c23f12cb1c6`
- 实现提交：`ad64b4ca6e9229fa4d05729e07b2bd08f36d89b1`
- 结论：**changes_requested**
- 发现：2 项 P2；未发现 P0/P1。现有 10 项测试复跑通过，但补充真实 PG 检查确认了现有测试未覆盖的 Worker 领取阻塞。

## 范围与状态

开始时 HEAD 与指定最终提交一致，工作树干净。提交关系为 `1e3b6c5 → ad64b4c → 8b7cf4a`，没有后续提交。完整检查 `1e3b6c5..8b7cf4a` 的 51 个变更文件；逐文件确认当前字节与待审查 commit 一致。

另检查 `ad64b4c..8b7cf4a`：只有 result.md 的内容提交记录/交接文字，以及 verification.txt 的最终证据追加，没有实现变动。result.md 的 head_commit 指向实现提交，不能与本报告审查的最终 HEAD 混淆。

已读取适用 AGENTS、TASK-001/task.md、result.md、架构/API 约束、ADR-005、dependencies.md、验证 JSON/文本、CI、Compose、启动说明，以及 API、迁移、Worker、测试、Web 和生成契约。按 Standards 与 Spec 两轴分别只读审查，主 Reviewer 独立复跑下述检查。未重复原 Demo 审查。

## Standards：发现

### R1 · P2 · 清理耗尽租约的普通 UPDATE 阻塞其他任务领取

**位置：** `apps/api/src/silicon/shared/jobs.py:24–28`；相关测试 `apps/api/tests/test_platform.py:78–83`。

`claim()` 先以普通 UPDATE 清理所有已过期且耗尽尝试次数的 running 任务，之后才执行带 SKIP LOCKED 的候选领取。清理 UPDATE 会等待这些行上的锁，使后面的 SKIP LOCKED 根本无法执行，影响原本未锁定的 queued 任务。

**实际复现：** 在独立 PG 17.11 临时集群（端口 62467）建立 A、B 两个 smoke job。A 先领取，再在测试事务中设为 `attempts=max_attempts`、`lease_until=now()-interval '1 second'`；B 保持 queued。连接一通过 `SELECT ... FOR UPDATE` 锁住 A；另一线程调用原实现 `claim(engine)`。

实际输出：

```text
CLAIM_WHILE_EXHAUSTED_LOCKED QueryCanceled elapsed 3.0
OTHER_JOB_STATUS queued
CLAIM_AFTER_UNLOCK succeeded
```

该 3 秒来自实际引擎 statement_timeout；测试没有模拟数据库锁。释放 A 后，同一领取逻辑立即成功领取 B。

**影响：** 一条待清理任务被锁定即可阻塞所有先执行该清理步骤的领取者。常驻 Worker 会记录 database_unavailable 并重试，单次 Worker 则失败退出；即使有其他可用任务也无法继续。当前没有业务数据，因此定为 P2 可用性问题，不推断交易损坏。

**测试缺口：** 现有 SKIP LOCKED 测试只锁 queued 行，未进入前置清理 UPDATE；10 项通过不能覆盖此分支。

**建议修复：** 清理也通过 `FOR UPDATE SKIP LOCKED` 选择待更新行，再更新这些已取得锁的行；避免在正常领取前执行可能全局等待的批量更新。增加真实 PG 回归：耗尽/过期行被其他事务锁住时，仍能在锁释放前领取另一 queued 行；之后再验证耗尽行最终进入 failed。

## Spec：发现

### R2 · P2 · 可选 Compose 启动路线缺少明确迁移步骤

**位置：** `README.md:46–52`；对照 `README.md:38–41`、`infra/bootstrap.sh:3–5`、`infra/bootstrap.sql:2–9`。

README 将容器数据库与本机服务描述为“二选一”。本机路线包含 `infra/migrate.py upgrade head/current`；容器路线只给出 `docker compose ... up -d --wait db`，随后进入启动 Web/API/Worker。Compose 初始化脚本只创建角色和权限，没有调用 Alembic；容器 healthcheck 也只检查 pg_isready。

**复现与证据层级：** 按 README 选择全新 Compose 卷，跳过本机 createdb/bootstrap 路线，仅执行容器分支后启动应用。依据初始化脚本的实际内容，此时没有 alembic_version/jobs，ready 会返回 503，Worker 无法处理 job。本次未启动容器，故不是 Docker 现场复现；这是命令路径与脚本的静态确定性检查。另行实测缺少版本表时 ready 503，支持上述 API 后果。

**影响：** 干净环境的读者必须自行从另一条路线推导缺失步骤，不能完整按可选路线重建可用骨架。文中“不能把容器已启动视作迁移成功”的提醒没有提供实际执行迁移的步骤。

**建议修复：** 在容器 up 后显式加入使用 `.env` 的 `infra/migrate.py upgrade head` 与 `current`，或者把迁移抽为两条 DB 初始化路线完成后的公共必做步骤。不要要求容器用户再次执行本机 createdb/bootstrap；同时说明若调整数据库端口应同步连接配置。

## 其余重点检查结果

- **工具与锁文件：** README 第 15～21 行明确创建 `.tools` venv、安装 uv 0.12.11、加入 PATH；没有把 `.tools/bin/uv` 当成天然存在的私人工具。Node/Python/npm/uv 版本有说明，npm/uv 锁文件与安装结果一致。锁文件、runtime 和 CI 未发现 `/Users/`、`/Volumes/`、Homebrew 绝对路径依赖。测试程序位置由 SILICON_TEST_PG_BIN 显式传入。
- **health/ready：** engine 延迟建立连接，health 不查询数据库；ready 读取 alembic_version 并与当前版本比较，连接异常、版本不符及版本表缺失返回稳定 503。真实停库测试和补充缺表测试通过。HTTP 错误结构及 request ID 有实测，未泄露 DSN、SQL 或内部堆栈。当前版本常量是 0001_platform；未来新增迁移时需同步 readiness 契约，不将未来扩展需求计作当前缺陷。
- **角色与迁移范围：** bootstrap 明确运行角色 NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOBYPASSRLS，迁移角色拥有数据库/schema/平台表；运行角色只有所需 DML 与版本读取权。实际运行角色建表被拒绝。0000 为空起点，0001 仅 jobs/outbox_events 及其约束索引；没有业务表。完整身份、租户和 RLS 未实现且明确属于 TASK-002。
- **迁移临时副本：** copytree 仅排除 `._*` 和 `__pycache__`，原 alembic.ini 仍被加载，仅重定向 script_location；当前 env.py、versions、模板及已安装 silicon 导入均保留。运行命令白名单不允许在临时目录生成 revision；异常没有被吞掉。含 null byte 的附属文件下 history/upgrade 正常，无效目标返回退出 1。没有发现当前有效迁移被过滤后冒充成功的证据；不保证任意未来迁移自定义外部依赖天然可用。
- **Worker 其余行为：** 实测并发同 key 入队唯一、同任务并发领取单胜者、普通已锁候选跳过、过期重领 token 更新、旧 Worker 心跳/完成/失败拒绝、重试延迟/耗尽 failed、独立进程与 DB 重启后的 completed 持久化。测试使用真实事务和进程，未仅模拟返回值。长任务持续心跳、任意业务 payload、外部副作用幂等和 outbox 投递器均未提供；ADR-005 对 smoke 边界的限制明确，不误认其为生产业务执行器。
- **前端与契约：** 只含硅屿 token 最小壳和真实 ready 连接检查，失败进入错误状态，没有回退假数据或业务页面。OpenAPI 与类型重新生成后逐字节匹配提交；仅有 health/ready 路由，未越界提供业务写接口。
- **CI/Compose：** CI 固定工具版本、按锁文件安装、校验生成契约漂移并执行构建/真实 PG 测试；PG 源码构建脚本有固定版本/hash 和失败传播。Compose 文件配置校验实际通过，使用同一 bootstrap，但存在 R2 的说明缺口。远程 CI 和容器启动的 not_run 记录真实明确。

## Reviewer 实际验证

为避免构建或生成命令改动工作树，使用 `git archive 8b7cf4a...` 导出全部已跟踪文件到 `/tmp/silicon-review-001-t_pqsy76`，在该干净源码副本新装依赖、生成文件并测试。该路径只是本次证据位置，不是项目依赖。临时副本里的独立复现脚本未加入目标仓库，也未修复或替换实现。

环境实际版本：macOS arm64、Node 24.15.0、npm 11.12.1、Python 3.12.7、uv 0.12.11、Homebrew PostgreSQL 17.11。uv 使用现有已核对版本的工具可执行文件，安装到全新的测试 `.venv`；未声称从零安装操作系统工具链。PG 仅使用现有 17.11 的程序文件，每次通过 initdb/pg_ctl 创建测试自己的临时集群、动态回环端口和独立 socket 目录；没有读取 `.env` 或连接常驻数据库。

| 实际命令/检查 | 结果 |
|---|---|
| `npm ci --ignore-scripts`（干净副本） | 退出 0，安装 56 packages |
| `UV_CACHE_DIR=/tmp/silicon-review-001-uv-cache <已核对的uv> sync --locked` | 网络执行许可后退出 0，安装 28 packages，silicon 从干净副本构建；锁文件未改变 |
| `npm run typecheck` | 通过，tsc 无错误 |
| `npm run build` | 通过，Vite 16 模块，生成临时副本的 apps/web/dist |
| `.venv/bin/python infra/export_openapi.py`、`npm run api:types` | 通过；openapi.json、schema.d.ts 与待审查提交逐字节一致 |
| `SILICON_TEST_PG_BIN=/opt/homebrew/Cellar/postgresql@17/17.11/bin .venv/bin/python -m pytest -v` | 在允许临时回环监听的执行环境退出 0：**10 passed, 2 warnings in 3.82s** |
| `.venv/bin/python infra/check_docs.py` | 退出 0，当前任务/相对路径/原报告 hash/41 本地链接通过；未检查外部链接 |
| `docker compose --env-file .env.example -f infra/compose.yaml config -q` | 退出 0，仅配置检查 |
| `git diff 1e3b6c5 8b7cf4a --check` | 退出 0 |
| 补充真实 PG 脚本（`reviewer_probe.py`，仅在临时副本） | 成功观察并记录 R1 的 QueryCanceled/queued/释放后成功；临时集群已清理 |
| 同一补充脚本：迁移附属文件/失败目标/缺表 readiness | `history` 0、`upgrade head` 0、`upgrade reviewer_missing_revision` 1；缺 alembic_version 表时 health 200、ready 503；附属探针文件已移除 |

初次尝试的失败也予以保留：默认 uv 缓存目录被沙箱拒绝（退出 2），改临时缓存后受沙箱 DNS 限制下载失败（退出 1）；授权网络执行后成功。pytest 初次在沙箱内无法 bind 回环端口，结果是 1 passed/9 setup errors；允许临时端口后才得到上表 10 passed。它们属于审查执行环境限制，不冒充首次通过，也不是自动审批拒绝或项目缺陷。

两条测试警告来自 Starlette TestClient 的 httpx 弃用与 anyio BlockingPortal 别名弃用；未屏蔽，未将其视为当前功能失败。

## 未验证事项与验收影响

- **远程 CI：not_run。** 无远程执行记录；本次只核查定义并运行本地对应的安装、生成、构建、真实 PG 测试。未独立复跑 Linux 下的 PG 源码下载编译路线，因此不认证整个 GitHub runner 流程已通过。
- **Compose 容器启动：not_run。** 本次采用任务允许的独立原生 PG 路线，未启动 Docker daemon 或占用 5432。TASK-001 具体验收要求真实 PG/API/Worker 与 Web 构建，没有强制容器实测；ADR-005 明确 Compose 为可选。因此容器未启动本身不构成必需验收缺失，但所交付可选路线的 R2 仍应修正。config 通过不等于容器运行通过。
- **本机 PostgreSQL 升级/恢复：未独立验证。** 只读取交付报告中的历史说明；没有停止、升级、降级或写入常驻 PG，没有读取无关原库、备份或私有恢复材料。临时测试成功不能证明整个升级/恢复过程正确。
- **依赖注册表时效/漏洞审计：未独立重做全部官方发行核验或 npm audit。** 已读取依赖说明，实际按锁安装、构建和测试验证本组合；执行者历史 audit 0 不转写为 Reviewer 的独立安全认证。
- **原 Demo、浏览器/视觉、业务 E2E、OIDC、生产数据：not_run。** 不属于本次骨架复核边界，不据此要求越界实施；本报告不认证生产业务可用性。

## 结论与交付边界

**changes_requested**：修复 R1 并加入对应真实并发回归，补齐 R2 的两路线公共迁移步骤，再进行增量复核。Standards 1 项（最高 P2），Spec 1 项（最高 P2）。

目标仓库仅新增本报告，原实现与证据未被修改；未提交、部署、创建远程、标记 accepted 或自动开始 TASK-002。
