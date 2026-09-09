# TASK-002 身份与隔离纵切交付

```yaml
task_id: TASK-002
status: review_ready
accepted_baseline: c50a95126ec9de6c471c2425cde3dac5f9012993
base_commit: 088fd4f3418f408f5d1356e62c5ca6768eb4a5cf
head_commit: a2e76b3b423eb1c0e4a196c1fd95954b05b09ea3
head_scope: implementation_and_test_evidence
next_task: TASK-003 (planned, not authorized)
```

## 交接与范围

产品/架构负责人依据 [首次审查](../../reviews/TASK-001-8b7cf4a-review.md) 和 [增量复核](../../reviews/TASK-001-c50a951-review.md) 确认 TASK-001 accepted。开始时 HEAD 与 c50a951 基线一致，main 分支；只有未跟踪的增量报告，没有已跟踪用户修改。报告原样纳入版本控制。单独交接提交为 088fd4f3418f408f5d1356e62c5ca6768eb4a5cf；之后才实现 TASK-002。runtime、AGENTS Current scope、backlog 与任务状态已同步。

## 实现

- Keycloak 26.7.3 真实 OIDC 授权码适配器，PKCE S256、一次性 state 与浏览器绑定、nonce、固定 issuer/RS256/JWKS、aud/azp/sub/iat/exp 校验。随机服务端 session 只保存 token hash，Secure/HttpOnly/__Host Cookie、独立 CSRF token + Origin 检查，旋转、退出、过期和用户禁用失效。
- 全局用户/企业/membership/角色/权限，会话中的企业选择须有效 membership；新 OIDC 用户不自动获权。共享身份/租户上下文服务，操作权限、own/all 数据范围、字段读取过滤与字段写入拒绝。真实前端最小入口提供登录、读取状态、切企业与退出，保留硅屿 token；未迁移业务页面。
- 0002_identity 迁移：全局身份控制面和强制 RLS 审计；会话/任务复合 membership 外键；事务级 tenant/user GUC 与默认拒绝函数。窄 SECURITY DEFINER 锁定 membership 函数，运行角色无需更新 membership 权限。测试中的成本/附件资源表与 HTTP 探针只存在于 test_identity.py，不是生产接口或业务迁移。
- 原全局 smoke 调度不变；租户 identity.check 使用授权入口、租户/actor/kind 幂等域，执行前重查 membership，拒绝缺上下文或撤权任务。审计与完成原子且受租约 token/有效期约束，保留原重试、旧 Worker 拒绝及有界 SKIP LOCKED 清理。
- 审计 actor/tenant/action/object/outcome/request_id，不接受敏感正文、令牌或任意 metadata；拒绝在回滚后保留。README、开发 TLS/IdP 下载和虚构身份配置脚本、环境示例、OpenAPI 类型与 CI 同步。
- 保留 production 模式拒绝，理由及边界见 [ADR-006](../../architecture/adr/ADR-006.md)。原 Demo、常驻 PostgreSQL、远程仓库与部署均未修改；未开始 TASK-003。

## 验证环境与命令

macOS arm64；Node 24.15.0、npm 11.12.1、Python 3.12.7、uv 0.12.11、PostgreSQL 17.11 Homebrew 程序、Java 21.0.6、Keycloak 26.7.3。应用新依赖 PyJWT 2.13.0、cryptography 50.0.1 等见 [版本记录](../../architecture/dependencies.md)。比较交接 commit 与当前 uv.lock，所有已有依赖版本均未变化。

命令从仓库根执行。PG 程序目录仅作为测试输入，fixture 创建新的 /tmp/silicon-test-* 数据目录、动态回环端口及 socket；新旧迁移测试都在这个临时集群内。真实 IdP 复制分发包到临时目录、使用自己的 H2 数据与动态 HTTPS 端口；API 也是独立进程。finally 停止本次创建的进程/数据库，测试没有读取 .env 或连接、停止、写入常驻 PG。

```bash
SILICON_TEST_PG_BIN="$(pg_config --bindir)" SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3" .venv/bin/python -m pytest -v --tb=short
.venv/bin/python infra/export_openapi.py
npm run api:types
npm run typecheck
npm run build
.venv/bin/python infra/check_docs.py
docker compose --env-file .env.example -f infra/compose.yaml config -q
git diff --check
```

| 实际检查 | 结果与证据 |
|---|---|
| 全套 pytest（真实临时 PG + Keycloak + HTTPS API + Worker） | 退出 0，**37 passed, 2 warnings in 33.67s**；[完整输出](evidence/pytest.txt) |
| 新增开发配置脚本测试：`.venv/bin/python -m pytest apps/api/tests/test_identity.py::test_dev_provisioning_is_idempotent_and_does_not_authenticate -v --tb=short`，同一 SILICON_TEST_PG_BIN 设置 | 退出 0，**1 passed, 2 warnings in 2.04s**；[补充输出](evidence/provisioning.txt)。该测试在全套运行后新增并单独执行，未声称一次性 38 项全跑 |
| OpenAPI 导出与 TypeScript 生成 | 退出 0，生产路由仅七项身份/健康接口，无测试探针 |
| `npm run typecheck` / `npm run build` | 均退出 0，Vite 16 模块构建 |
| `infra/check_docs.py` | 退出 0，任务状态/相对路径/历史报告 hash/本地文档链接通过 |
| Compose `config -q` | 退出 0，仅配置验证 |
| `git diff --check` | 退出 0 |
| 交接前后 uv.lock 版本映射比较 | 所有已有依赖版本不变，只增加必要认证依赖 |

构建/文档命令的退出码与原始输出见 [checks.txt](evidence/checks.txt) 和 [checks.json](evidence/checks.json)。较早完整运行 **33 passed** 保留于 [pytest-initial.txt](evidence/pytest-initial.txt)。两个 warning 均为原有 Starlette/httpx 和 anyio 弃用提示，未屏蔽或为此升级依赖。没有将本地通过转写为远程 CI 通过。

## 证据覆盖与限制

- 真实 IdP：浏览器协议的真实 HTML 表单登录 → Keycloak 授权码 → API 服务端换码/JWKS 验签 → 安全 Cookie → 会话读取；异浏览器拒绝、回调重放拒绝、无 CSRF 退出拒绝、本地撤销、Keycloak 退出确认及重新登录必须再次输入凭据、会话过期、旧 Cookie 拒绝。此项通过独立 HTTPS 进程/httpx 完成，不是 mock。
- 明确替身：test_oidc_validation.py 用 HTTP 替身提供真实加密 JWT，测试过期/错误签名/算法/issuer/aud/azp/nonce/声明缺失；test_identity.py 的 session_insert 是认证替身，用于隔离权限边界，不作为真实登录证据。
- 真实 PG：运行角色非 owner/non-super/non-BYPASSRLS；FORCE RLS 默认无上下文零行、写拒绝；两租户相同编号/对象 ID、跨租户复合外键；同一物理连接 A/B/A 复用与异常回滚清理；membership 撤销、多企业切换及伪造选择拒绝；列表/搜索/导出/聚合/详情、字段读写和附件元数据/下载边界；Worker 授权、撤销、缺上下文、旧租约和审计原子性；空库迁移与 TASK-001 队列数据升级保留；原 PG/API/Worker 回归。
- 远程 CI：not_run，无远程仓库/runner 结果。CI 已增加固定 Keycloak 与 Java 配置；本地 Oracle Java 通过不等同于远程 Temurin/Linux 已通过。
- Compose 容器启动：not_run，未启动 Docker，仅配置检查；数据库与 IdP 功能通过独立原生实例验证。
- 浏览器视觉/完整前端端到端：not_run。Vite HTTPS 实际启动，但内置浏览器访问被 ERR_CERT_AUTHORITY_INVALID 拦截；未绕过自签名证书警告或修改系统信任。恢复条件：用户为开发浏览器信任该本地证书后补跑视觉/前端点击流程。真实 OIDC 协议集成已独立执行，不能当成视觉截图。
- 无完整文件业务、对象存储、角色管理界面、业务权限矩阵或远程 IdP back-channel 撤销。IdP 端提前撤销的本地会话最迟在原 ID token exp 失效；本任务提供本地退出和用户禁用立即拒绝。未宣称生产安全、运维或业务可用性通过。

## 调试与历史证据

初轮 17 项运行中，5 项 setup 因 PG FOR SHARE 还需 UPDATE 权限失败，1 项原保护文案断言失败；改用固定 search_path、受限执行权限的只读锁函数，并更新断言保护目的，随后 17 passed。没有扩大运行角色修改 membership 的权限。

真实 IdP 首轮 HTTP 表单失败提示 restart cookie missing；改为 HTTPS 并在 API 显式验证测试 CA。随后登录/回调通过，退出表单因相对 action 被测试客户端当绝对 URL 失败；测试改用当前响应 URL 解析相对表单，真实集成 1 passed。后续全套 33 passed 的输出保留为初轮完整证据；新增边界断言后的最终结果另记。以上失败未隐藏或冒充首次通过。

状态为 review_ready，等待独立审查与产品/架构负责人验收；执行者不自行 accepted。

## 提交与最终校验

实现与测试证据已提交，head_commit 指向该实现提交；随后单独提交本报告的精确提交号和文档证据格式修正，最终交付 HEAD 另在交付消息列出，不能将两个提交混同。2026-09-10 完成交付记录。

完整变更文件见 [changed-files.txt](evidence/changed-files.txt)。暂存阶段检查曾发现 checks.txt 文件尾多余空行；已移除并重新检查全部相对交接基线的增量。此修正不改变命令原始输出或测试结论。两轮 TASK-001 及 TASK-000 历史报告的内容 hash 均保持不变。
