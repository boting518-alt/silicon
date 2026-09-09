# TASK-001：工程骨架

status: executing
owner: 执行线程
reviewer: 独立上下文，待指定

## 目标与前置

TASK-000 文档独立复核通过，并明确分配本任务。

必读：AGENTS.md、runtime/project.json、docs/design/demo-baseline.md、docs/architecture 下相关契约和 ADR、backlog 与前置任务 Review。

## 允许范围

apps/web、apps/api、apps/worker、packages/api-client、infra、CI、测试、README、runtime/project.json；只建立 UI 空壳，无业务页面。

## 实施要求

锁定 Web/Python/PG/IdP 工具版本与 lockfile；核验官方维护状态和兼容组合。无既有包管理器，暂定 npm+uv，实际决定写 ADR 或落实 OD-012。实现 Web、API、Worker 入口；/api/v1/health 只测进程、/api/v1/ready 实测数据库并在不可用时返回 503；独立 Worker 使用真实 PG job。创建迁移链、jobs/outbox 最小设施（不创建业务模型）；开发环境配置、CI 和 README 完整启动/停止/清理步骤。端口暂定 Web 5173、API 8000、PG 5432、开发 IdP 8080；冲突时显式配置，不扫描并占用未知服务。服务端环境示例至少区分应用/迁移数据库连接和环境名；不得提交密钥。

## 验收与实际证据

空 PostgreSQL 执行迁移成功；ready 正常 200、数据库停止后 503 且不泄露连接信息；Worker 领取虚构 job 并持久化 completed，重启后仍可查询；Web typecheck/build 成功。CI 从干净 checkout 使用锁文件复现上述命令。

执行者必须将每个检查拆为可运行的实际命令，记录环境版本、退出码、摘要、证据相对路径及 not_run 原因。不要在尚无实现时伪造测试命令已经通过。

## 不在范围

不接入真实模型、OIDC 业务流程、生产客户或完整模块；Worker 测试无外部副作用。

## 退出、失败与交付

交付 scoped commit、base/head、diff、docs/tasks/TASK-001/result.md，状态 review_ready。独立 Reviewer 在相同内容 commit 复现检查，输出 docs/reviews/TASK-001-<head-short>.md。失败记录复现与修复，不进入下一任务；执行者不自行 accepted。涉及迁移先在测试库验证，不能以代码回滚代替数据恢复；不部署、不外发。
