# TASK-001 依赖与兼容组合

核验日期：2026-09-09。先查官方文档与注册表版本/engines/peerDependencies/requires-python，再精确锁定并实测；不使用 latest 作为安装或部署策略。

| 层 | 实际固定版本 | 验证 |
|---|---|---|
| Node / npm | 24.15.0 / 11.12.1 | npm ci、typecheck、build |
| React / react-dom | 19.2.8 / 19.2.8 | 同补丁版本，构建通过 |
| Vite / plugin-react | 8.2.2 / 6.1.1 | Node 要求 ^20.19 或 >=22.12；插件 peer Vite ^8，匹配 |
| TypeScript | 5.9.3 | openapi-typescript 7.13.0 的 peer 要求 ^5.x，故未选择注册表当前 7.0.2 |
| React 类型 | @types/react 19.2.18 / @types/react-dom 19.2.7 | 类型检查通过 |
| OpenAPI 生成 | openapi-typescript 7.13.0 | 生成 JSON 对应类型、确定性检查 |
| 间接依赖 override | js-yaml 4.3.2 | 初装审计发现上游依赖 4.3.1 漏洞；固定修复版本后 npm audit 0 漏洞 |
| Python / uv | 3.12.7 / 0.12.11 | uv lock、sync --locked、真实测试；Python 3.12 为当前已测小版本 |
| FastAPI / Pydantic | 0.141.1 / 2.13.5 | 要求 Python >=3.10 / >=3.9，组合 API 测试通过 |
| SQLAlchemy / Alembic | 2.0.52 / 1.19.2 | psycopg 同步引擎、真实 PG 迁移 |
| psycopg + binary / Uvicorn | 3.3.5 / 0.52.4 | PostgreSQL 连接、HTTP 独立进程 |
| pytest / httpx | 9.1.1 / 0.28.1 | 10 测试通过；Starlette 与 anyio 相关两条弃用警告保留，不伪称无警告 |
| 构建 backend | hatchling 1.32.0 | 可编辑安装通过 |
| PostgreSQL | 17.11 | 官方支持期至 2029-11-08；本机 Homebrew 与官方源码构建版均实测 |
| 开发 IdP 候选 | Keycloak 26.7.3 | 官网当前发行版，仅记录候选；未安装/启动，端口 8080 预留，兼容实测交 TASK-002 |

Python 完整传递版本见 uv.lock（包括 Starlette 1.6.0），JS 完整版本及完整性见 package-lock.json。版本更新必须重新解析锁文件并执行相关检查；当前 Python/Node 补丁为本机实际可用版本，不宣称它们是该系列最新补丁。Vite 8.2 受常规补丁维护，React 19.2 属当前文档分支；FastAPI、Pydantic、SQLAlchemy、Alembic、psycopg 等本次官方注册表均有兼容的稳定发行版本，但不据此承诺长期支持期限。

## 官方依据

- [Vite 支持版本](https://vite.dev/releases)、[运行环境要求](https://vite.dev/guide/)。
- [React 版本](https://react.dev/versions)。
- [FastAPI 发布说明](https://fastapi.tiangolo.com/release-notes/)。
- [PostgreSQL 版本政策](https://www.postgresql.org/support/versioning/)。
- [uv 锁定与同步](https://docs.astral.sh/uv/concepts/projects/sync/)。
- [Keycloak 下载](https://www.keycloak.org/downloads)。
- [js-yaml 漏洞公告](https://github.com/advisories/GHSA-2883-xcg3-v3hh)。

精确发行元数据读取自 registry.npmjs.org 与 pypi.org 官方包注册表，兼容结论最终以本仓库实际测试为证。

## TASK-002 验证组合

未升级 TASK-001 的 React/Vite/TypeScript/FastAPI/SQLAlchemy/Alembic/psycopg 等版本。
新增 PyJWT[crypto] **2.13.0**，httpx **0.28.1** 从已有测试依赖同时列为运行依赖；锁定新增传递依赖 cryptography **50.0.1**、cffi **2.1.1**、pycparser **3.0**。安装后用真实 Keycloak 26.7.3 授权码 + HTTPS + RS256/JWKS 路径验证该组合，非只凭版本号判断兼容。

官方来源：[PyJWT 2.13.0 文档](https://pyjwt.readthedocs.io/en/stable/)、[Keycloak 26.7.3 发行](https://www.keycloak.org/2026/08/keycloak-2673-released)、[Keycloak TLS](https://www.keycloak.org/server/enabletls)。下载官方 GitHub 26.7.3 tar.gz 的实际 SHA-256 为 `77657f30b7e90d70f727712ce1c967f430fd6a5e9f458d32d8c6df0635345f47`，下载脚本固定此摘要并拒绝覆盖已有 IdP。不是 latest 策略。

本机实际 Java **21.0.6**；CI 声明 Temurin **21.0.6+7**（Java 21 同一补丁线），但远程 CI 未运行，不能把本机 Oracle Java 通过等同于远程 Temurin runner 已通过。生产模式继续拒绝启动，发行版本兼容实测不是生产安全/运维认证。
