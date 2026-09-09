# TASK-000 独立审查

- 审查日期：2026-09-09
- 实际审查 commit：`91ac21771230f4e784442592c0bc80c27f8f77b3`
- 结论：**changes_requested**
- 原因：发现 1 项 P2 文档顺序冲突。未发现 P0/P1；没有证据表明 Demo 源码损坏。结论限于 TASK-000 文档交付，不代表生产功能通过。

## 审查范围与仓库状态

已读取适用的根 `AGENTS.md`、TASK-000 任务书与 result.md，检查祖先目录说明（未发现额外 AGENTS），并审查产品、架构、领域模型、API、Agent、指标、四份 ADR、待定事项、Demo 基线与 manifest、运行手册、backlog、TASK-001～003、runtime 和验证脚本。Standards 与 Spec 两轴分别由独立只读子审查上下文核查，主 Reviewer 另行核验源码与交付证据。

开始时 `git rev-parse HEAD` 与指定 commit 完全一致，分支 main，remote 数量 0，`git status --short` 无输出。没有后续提交或未提交业务改动需排除。

目标不是首个提交：其父提交为 `63d75022600c5ced4226e9167fca4af903ae5b2c`，此前 `e98d435e10b663430d6a5f17734923ea8d0fb426` 是空审查基线。因此审查了 `e98d435..91ac217` 的全部 29 个交付文件，而非只审最后一次差异；另核对 `63d7502..91ac217` 确实仅更新 result.md 和 verification.txt。result.md 中 head_commit 是内容提交，末尾已解释证据提交的区别，不判为虚报 HEAD。

本次只新增本报告，不修改原交付、任务状态或 Demo，不提交、部署、创建远程或启动 TASK-001。

## Standards：发现

### R1 · P2 · README 的骨架启动前置形成循环

- 位置：[README.md 第 18 行](../../README.md#L18)；对照 [TASK-001/task.md](../tasks/TASK-001/task.md) 第 9、19、23、33 行，以及 AGENTS.md 第 54 行。
- 事实：README 写“**TASK-001 独立复核前不开发骨架**”。但 TASK-001 的目标正是开发骨架，必须有骨架交付才能复核；任务书的实际前置是“TASK-000 文档独立复核通过，并明确分配本任务”。
- 影响：执行者从入口阅读会得到相互冲突的开始条件，需要自行判断哪个任务编号写错，不满足 TASK-000“文档可支持执行者开始 TASK-001”的无歧义交接要求。README 第 12 行提供任务书优先的替代路径，因此为 P2，不提升为关键闭环或权限错误。
- 建议修复：将该句明确改为“TASK-000 独立复核通过并明确分配 TASK-001 前不开发骨架”，再检查入口、AGENTS、backlog 与任务书一致。本次未代为修改。
- 复现：直接对照上述两文件，无须启动服务或业务测试。

范围表述观察（不另计缺陷）：TASK-001 允许范围未列 docs，但实施要求明确允许 ADR/OD-012、交付条款明确要求 result.md；TASK-003 的客户端生成、报告也有明确条款授权。按全文可执行，建议今后统一范围列表，但不据此声称任务被阻断。

## Spec：检查结果

本轴未发现需另立修复项的规格缺失或越界。工程版本待 TASK-001 核验锁定、本地默认 Keycloak 在 TASK-002 接入 OIDC，属于有默认值的工程选择，不是必须猜测的业务决策。

- 产品与架构一致：首期经营工作台、模块化单体、Vite/React/TypeScript、FastAPI、PostgreSQL、独立 Worker、私有对象存储；生产与 Sites Demo 身份隔离。ADR-001～004 与正文没有发现实质冲突。
- 租户：data-model.md 第 29～43 行明确复合租户关系、membership、字段权限、非 owner/非 superuser/无 BYPASSRLS 的运行角色、独立迁移角色、事务上下文及无上下文拒绝。TASK-002 将其转为真实运行角色 SQL、连接复用、两租户同编号、Worker、附件与成本字段测试。
- 金额与快照：data-model.md 第 30～33、59～65 行明确 Decimal/NUMERIC、API 十进制字符串、后端权威计价、折扣尾差轨迹、报价发布/合同签约不可变版本，以及内容变更令审批失效。具体小数位、舍入模式与业务税政策尚未形成完整计价实现规范；必须在后续金额功能前固定，但 TASK-001 不创建这些业务模型，不据此要求本次实现。
- 库存与成本：data-model.md 第 69～85 行明确移动台账、锁定与并发预留、可用量排除项、SN 个别计价/批次 FIFO、零件→WIP→成品成本连续、逆向更正、部件安装历史；合同、物流、验收、发票、应收应付与资金核销独立。
- Agent：agent-policy.md 第 23～37 行及 ADR-004 明确白名单、预算、proposal/版本/hash、执行再授权、关键操作人类确认、提示注入隔离及 uncertain，研发助手授权没有被误用为线上业务权限。
- TASK-001～003 除 R1 入口错误外依赖顺序明确。001 有 health/ready 的 200/503、真实 PG 迁移与 job、重启持久化、锁文件与 CI；002 有隔离与会话边界；003 有客户独立关系、真实 CRUD、刷新持久化、冲突及固定双视口视觉验收。003 仅预留多合同关系，不提前要求实现 TASK-007。

## 实际验证与证据

以下为 Reviewer 实际检查，不是仅抄录执行者的 passed。

| 检查 | 实际结果 |
|---|---|
| `python3 docs/tasks/TASK-000/verify.py` | 退出 0：22 必需文档、44 本地 Markdown 链接、相对配置与任务状态、12 个 Demo 文件 hash/blob、6 个 JS 语法、10 个 HTML 本地引用、颜色及有限持久化入口检查通过 |
| `git diff e98d435..91ac217 --check` | 退出 0 |
| 独立 `git ls-tree` 与逐文件 `git show HEAD:<path>` 字节比较 | 生产 29 文件、报价 4 文件、工作空间 8 文件全部与实际 checkout 一致；manifest 列表覆盖两份 Demo 的完整已跟踪文件树 |
| 原始输入指南与归档字节比较 | 完全相同 |
| Sites `get_site`、`list_site_versions(limit=1)` 只读复核 | 报价 active/v1/`65e465092f0afc5519ed1a60214697fbf6a2f2a5`；工作空间 active/v4/`09e204ec99a74a821f35d6799b9e6e00c0c8393d`；两个 live URL 与基线一致。未更新或部署 |
| 原 Demo 静态源码核查 | HTML 脚本顺序及 12 个导航一致；客户由 contracts.map 派生、串联 deliverySteps 开票、1.13 税换算、20% 审批阈值、8000 费用及 1.8% 费用均能定位到原始源码；已正确标成演示限制 |
| CSS 与复用边界 | 两份根背景/文字/字体一致，主按钮分别 #214f3c 与 #254f3d，工作空间 215px 侧栏、13px 指标圆角及边框等与基线一致；响应式存在覆盖规则，未将静态默认值当全视口截图结果 |
| dist 处理 | 两份均为原生已跟踪 HTML/CSS/JS，无 package.json 构建要求；AGENTS、ADR-002、手册和 gitignore 均明确保留 dist，不存在误删建议 |
| runtime 与文件依赖 | 所有路径相对仓库根；两个同级参考 checkout 当前可读，未创建应用目录明确为 planned；历史绝对路径仅位于归档或禁止使用的示例，未成为运行依赖 |
| 凭据与范围静态检查 | 29 个已跟踪文件无 AppleDouble、业务实现或部署配置；私钥头、常见 OpenAI/GitHub token、长 Bearer 值、URL 内嵌凭据模式均无匹配。模式检查不等于全面秘密检测认证 |

外部文档链接也实际打开了全部 7 个唯一官方页面，均返回对应文档内容：[FastAPI](https://fastapi.tiangolo.com/project-generation/)、[PostgreSQL SELECT](https://www.postgresql.org/docs/current/sql-select.html)、[RLS](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)、[显式锁](https://www.postgresql.org/docs/current/explicit-locking.html)、[SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/versioning.html)、[Temporal](https://docs.temporal.io/evaluate/understanding-temporal)、[React](https://react.dev/learn/thinking-in-react)。本次未核定未来安装版本组合；动态 current 链接不能替代 TASK-001 版本锁定。

## 外置磁盘元数据检查

实际执行三仓库的 `git fsck --full`：生产仓库退出 0，但有 54 行 `bad sha1 file` 诊断；两个 Demo 退出均为 4，分别有 3/2 行 non-monotonic index / index not opened 诊断。所有诊断路径均指向 `._*` 附属文件，故不能简单写“fsck 全通过”。

随后对两份参考仓库真正的非 `._` pack index 分别运行 `git verify-pack -v <index>`，均退出 0；再结合 41 个当前已跟踪文件可读且与 Git blob 字节相同，未发现真实 pack 或当前源码损坏。当前审查、静态源码读取及 TASK-001 文档依赖未被阻断；但会要求 fsck 零错误的流程仍会受影响。

因此保留 OD-018 的健康文件系统重新获取/复核建议，尤其在 UI 迁移前执行；无需删除或修改原 Demo 来消除本次问题。没有把 AppleDouble 告警升级为无证据的源码损坏，也没有把有错误的完整健康检查记作通过。

## 未验证事项及其影响

- 浏览器、截图、E2E、静态 HTTP 服务均未运行。只能确认源码与来源，不能确认实际点击、刷新或视觉保真；原报告清楚标为 not_run / visual_baseline: pending，符合 TASK-000 范围。
- PostgreSQL、应用构建、Worker、迁移、业务金额/库存/权限测试未执行，当前没有生产骨架。本文确认的是约束及后续验收设计，不是实现正确性；不构成本次缺陷。
- Sites 已核对身份、保存版本及 live URL，未通过浏览器验证线上页面或匿名访问；有授权要求不等于失效链接。重新克隆、离线源码包恢复流程本次未演练，目前本地固定源码完整可读。
- 未验证地图素材许可、坐标系、未来模型能力与依赖兼容组合，已有明确后续门槛；在对应功能启用前必须完成。
- 不能追溯证明执行者当时的 DNS 失败、批准过程和提交前暂存检查确实发生；能独立确认的是当前内容、diff、来源与上述复跑结果。原报告未将未执行的浏览器/数据库项目写为通过。

## 结论与后续边界

**changes_requested**：先由执行者修正 R1，再对修订 commit 复核。所需修复是明确入口前置，不是补做 TASK-000 范围外业务测试。本审查不自动赋予 TASK-001 开工授权，也不将 TASK-000 标为 accepted。

两轴计数：Standards 1 项发现，最高 P2；Spec 0 项发现。Demo 与证据核查未新增缺陷，验证限制如上。
