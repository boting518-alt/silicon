# TASK-000

status: review_ready

## 11. TASK-000：可直接执行的首个任务书

**名称：保留硅屿 Demo 的工程启动与架构落仓**

目标：将本指南变成目标仓库的权威项目文档，完成现有 Demo 盘点，为真实功能开发建立可审查基线。本任务不实现完整业务、不改写旧 Demo、不部署新站。

输入：本指南、两个 Demo 源码或同账号可访问的 Sites 项目、用户指定的目标仓库。若尚无目标仓库，创建独立本地目录 `silicon-workspace`；先检查是否存在，禁止覆盖。若位于已有仓库，先执行 `git status` 并保留用户修改。

允许写入：目标仓库的 README、AGENTS.md、docs、runtime/project.json、必要的 gitignore。原 Demo 源码只读。已有 AGENTS.md 只合并适用内容，不覆盖既有高优先级约束。

步骤：

1. 确认工作目录、Git remote、默认分支、工作树状态、现有 AGENTS.md；记录来源而不打印凭据。
2. 读取两个 Demo；检查当前 commit 是否与指南一致，若更新则记录差异，不能回退覆盖新版本。
3. 生成 `docs/design/demo-baseline.md`：来源、页面/文件清单、主要 CSS token、交互、假数据/内存状态、复用与重构边界。浏览器不可用时明确 `visual_baseline: pending`，不得用文字检查代替截图。
4. 生成 `docs/product/scope.md`、`docs/architecture/architecture.md`、`data-model.md`、`api-conventions.md`、`agent-policy.md`、`metrics.md`；记录 ADR-001 模块化单体、ADR-002 保留视觉渐进迁移、ADR-003 台账与快照、ADR-004 受控 Agent。
5. 生成 `docs/tasks/backlog.md`、TASK-001～003 的独立任务书及本任务完成报告。任务文件 ID 必须与 backlog 一致。
6. 生成相对路径配置 `runtime/project.json`。不要把当前会话 `/workspace/...` 或个人电脑 `/Volumes/...` 路径变成项目依赖。
7. 检查文档之间是否有数据库、框架、术语、审批边界和目录冲突；把未确认事项记录为 open decision，并给默认假设。
8. 若可运行两份原生 Demo，记录启动方法；任务 000 不要求主动浏览器测试。视觉回归在任务 003 执行，届时明确授权测试并固定视口与数据。
9. 在目标仓库创建一个 scoped commit，回报 HEAD；若环境不允许 Git 提交则交付 diff 和原因，不谎称已提交。不创建新远程或部署。

验收：文档可支持执行者开始 TASK-001；已明确 Demo 基线及获取办法；生产架构与 Demo 托管不混淆；没有引入业务代码、密钥、真实客户数据或未经请求的部署。

若来源源码不可访问：仍完成上述架构文档和工程任务书，把源码依赖列为 `demo_source_pending`；只在开始 UI 迁移前要求补齐源码。不能凭印象重画 UI 并声称复用了原 Demo。
