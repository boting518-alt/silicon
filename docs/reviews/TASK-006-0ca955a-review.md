# TASK-006 独立审查报告

- 结论：**changes_requested**。
- 发现：2 项 P2。
- 日期：2026-09-10。
- 最终受审 HEAD：`0ca955af10115b1fb7369885c348465672b22dc9`。
- 实现提交：`262eea882dac44c28198db3cf0625cd118273b46`。
- 基线：`da215ad9b22e5d831c0d7a319885ddf7ad3ec8ef`。
- 输入：silicon-task006-review.zip、result(9).md、本轮任务书及已有基线。

## R1 · P2：已发布草稿可以再次提交，绕过独立修订流程

位置：`apps/api/src/silicon/publication/service.py` 的 submit、issue；`apps/web/src/Publication.tsx` 的 DraftSubmission。

quote.save 已检查草稿是否发布并抛出 PUBLISHED_DRAFT_REQUIRES_REVISION，但 publication.submit 仅检查 expected_version，随后冻结新候选并更新 approval_candidate_id，没有检查该草稿是否已有发布版本。前端原草稿的提交入口也没有依据已发布状态阻止再次提交。

复现步骤：

1. 草稿 D 提交、由另一授权人员批准，发布为 Q-000001。
2. 保持 D 的草稿 version 不变，使用新的幂等键或新的 valid_until 再提交 D。
3. submit 产生新候选 C2，并重新绑定草稿候选指针。
4. 另一授权人员可批准 C2。issue 对 C2 找不到既有发布记录，fresh 也没有“同草稿已发布”门槛。
5. 对初始草稿 source_version_id=None，编号分支会创建新的根编号，而不是沿 Q-000001 生成独立修订草稿与 R2。

Reviewer 定向服务探针确认 submit 会在未查询草稿既有发布记录的情况下插入候选。后续批准/发布及新根编号行为通过实际代码路径核对；本环境未运行完整 PG/HTTP 重演，不将该证据表述为端到端实测。

影响：可以改变有效期或采用最新重算内容重新发布同一草稿，绕开任务书要求的独立修订来源链。旧发布正文虽然未被改写，但业务版本历史不再遵循规定的修订流程。

修复要求：

- 在同一报价事务锁下，拒绝对已有发布版本的草稿发起新的提交审批，返回明确修订要求。
- 在发布消费入口补足对应不变量，防御历史/并发产生的不同候选；不能只隐藏前端按钮。
- 同一次已成功命令的幂等重放应返回原结果，不当作新提交；区分重试和新的业务意图。
- 前端已发布草稿明确引导到“创建修订草稿”。
- 增加真实 PG/API 与组件回归：发布后新 key 再提交、改变有效期再提交、发布与重新提交竞争；同 key 重放不重复；通过独立修订建立 R2 后正常发布；旧版本保持不变。

## R2 · P2：内部修订幂等作用域遗漏来源版本，可复用并改写另一来源的草稿

位置：`apps/api/src/silicon/publication/service.py` 的 revise；关联 `silicon/quotes/service.py` 的 save。

外层幂等 operation 正确包含源版本：quote.revise:<version_id>。但 revise 调用 q.save 时使用 `revision:` + key，并统一落入内部 quote.create 作用域，没有纳入 source version id。外层本应独立的两个命令在内层发生碰撞。

复现步骤：

1. 准备两个有权访问的发布版本 V1/V2，config 完全相同；可以来自两份独立报价。
2. 同一用户分别向 `/versions/V1/revise` 和 `/versions/V2/revise` 使用同一个 Idempotency-Key K，expected_version 均有效。
3. 第一次内部保存键是 revision:K，生成修订草稿 D，来源设为 V1。
4. 第二次内部 quote.create 命中相同 key/hash，返回 D。
5. revise 无条件更新 D.source_version_id=V2，两个来源共用一个草稿，第一次修订的来源被改写。

Reviewer 探针执行实际 publication.revise 和实际 q.save，以内存仓储边界替代数据库，确认两次调用返回同一草稿 id，最后来源更新为 V2。若配置不同，同样的作用域错误会触发不应出现的 IDEMPOTENCY_CONFLICT。该探针不是 PG/HTTP 实测。

影响：来源追溯被污染。外层已经把 key 按操作及资源隔离，不能要求客户端以全局永不重复的 key 来掩盖内层作用域缺陷。

修复要求：

- 内部幂等身份纳入外层完整操作/来源版本，采用有界编码或摘要，保持输入长度约束；或统一使用一次明确的修订创建命令。
- 来源关联与新草稿创建原子完成；不能在重放命中其他草稿后无条件改写来源。
- 增加真实 PG/API 回归：相同 key 用于 V1/V2，内容相同和不同都应分别创建正确来源的独立草稿；重试各自命令返回各自草稿，来源不变。
- 保留权限重查、跨企业隔离、旧审批不继承及不同来源后续发布编号测试。

## 独立检查结果

- SHA256SUMS：554 项通过，生成接口后再次检查。
- 检查生命周期服务、路由、模型、0007 迁移、旧草稿保存门槛、审批/合同页面、ADR-011 及相关测试。
- `npm run typecheck`：通过。
- `npm run build`：通过；24 modules，index-DiWuu6uQ.js。
- `node --test apps/web/tests/*.test.ts`：19 passed、0 failed。
- `infra/check_docs.py`：通过，207 个本地链接。
- OpenAPI 重新导出、客户端重新生成：与受审生成物 SHA-256 一致。
- 执行上述服务定向探针，加载实际 review006/source 模块；仓储、授权/计价依赖部分替换，证据边界已分别说明。
- 查看发布桌面及撤回来源合同移动端截图，开发政策和来源风险提示明确。本次没有单独列出视觉阻断项。

没有修改受审实现、旧报告或原 Demo。复用上一轮锁定依赖安装环境，构建及接口再生仅用于验证。

## 执行者证据与限制

交付报告记录完整后端 116 passed，另有随后补充的 3 passed；不能合并宣称一次119项完整运行。实际 React DOM 新4项、原3项和两身份浏览器流程属于执行者证据，本轮未独立重跑。

本环境没有可用 PostgreSQL17.11 / Java21 / Keycloak 测试栈；此前 PostgreSQL 构建受缺少 bison/flex 限制。本轮未重跑真实 PG/API/Worker/OIDC、React DOM 浏览器测试页、双标签操作、远程 CI、容器运行或生产部署。不能据源码检查宣称所有并发/权限路径均已实测通过。

截图清单如实记录实际导出1425×891、375×812等尺寸，与目标视口尺寸不同；此为已披露验证限制，不将其说成目标像素截图已验收。

包不含 .git；提交身份依据 manifest/差异和交付记录，未访问用户本机或GitHub核验。包内“无remote”仅为当时交付记录，本轮没有核实此前已授权的远程推送状态。

## 交接要求

保持 TASK-006 未验收。修复 R1/R2，追加定向红绿测试、相关回归及结果；保留本报告与历史证据，提交增量审查包后再复核。TASK-007/008任务书可保持 planned，本次不授权开始其实现。
