# API、状态与事务契约

状态：TASK-000 建议基线，等待独立复核；不代表功能已实现。

来源：[启动指南](../reference/SILICON_Codex_Architecture_and_Kickoff.md)。以下保留对应原文规则；本次具体决策见 [ADR](adr/ADR-001.md)。

金额为十进制字符串；无授权字段不得进入响应。401 表示未登录，403 表示已登录但缺操作权限；跨租户对象使用统一不泄漏存在性的 404。错误响应包含稳定 code、message、request_id。分页默认 page_size=25、上限 100，排序必须稳定并带 id 决胜；这些为 TASK-003 默认建议，API 实现前固定到 OpenAPI。

## 7. 状态、API 与事务契约

示例状态机：

- 报价版本：draft → validated → pending_approval（必要时）→ approved → issued → accepted / expired / withdrawn。未触发审批时由系统规则记录 approved 依据，而不是伪造人工审批。
- 合同：draft → internal_approved → signed → active → closed；amendment 独立版本，termination 有生效日期与结算处理。
- 装配：planned → materials_reserved → in_progress → testing → completed；失败进入 rework。
- 售后：open → triaged → in_progress → resolved → closed；需要时 reopened。RMA 用独立子流程，不强迫客户工单等待返厂完成才关闭。

领域命令 API，而不是给前端任意 PATCH status：

| API | 核心要求 |
|---|---|
| `POST /api/v1/quotes/preview` | 输入 SKU、数量、上下文；后端返回价格、税、规则和成本可见字段 |
| `POST /api/v1/quotes` | 保存草稿，审计来源；不预留库存 |
| `POST /api/v1/quotes/{id}/issue` | 检查版本、权限、规则、审批、折扣额度；创建不可变快照 |
| `POST /api/v1/contracts/from-quote` | 指向已发布 quote_version；生成合同草稿，不自动标记签约 |
| `POST /api/v1/stock-reservations` | 按订单行和仓库申请；数据库事务竞争安全 |
| `POST /api/v1/assemblies/{id}/complete` | 领料与完工成本结转、一物一位、测试条件检查 |
| `POST /api/v1/shipments/{id}/post` | 预留消费、出库、设备归属与事件同事务 |
| `POST /api/v1/cash-transactions/{id}/allocate` | 检查剩余资金和目标余额；核销不可重复 |
| `POST /api/v1/service-tickets/{id}/replace-component` | 旧件拆卸、新件出库和安装、费用与证据同事务 |
| `GET /api/v1/insights/overview` | 期间、as_of、维度、口径版本；支持下钻来源 |
| `POST /api/v1/agent-runs` | 异步返回 run_id；强制当前身份、租户、预算和允许工具 |

所有会产生副作用的命令要求 `Idempotency-Key`。唯一域为租户、操作者、操作类型与 key；保存请求 hash 和结果，命令与幂等结果同事务提交。同 key 同内容返回原结果，同 key 不同内容返回 409。版本字段必须与后端条件更新一起检查；仅用 ORM 版本号不能取代跨请求的 expected_version 校验。[SQLAlchemy 版本控制](https://docs.sqlalchemy.org/en/20/orm/versioning.html)

业务事务写 outbox 后提交，异步消费者才执行附件生成、通知候选或报表刷新。不要在数据库事务内等待 LLM 或外部邮件。外部系统不支持幂等、请求超时但可能已经发送时，转 uncertain 待核对，不能盲目重发。

## TASK-011 经营资金

`/api/v1/finance` 独立使用 `finance.read` 及相应命令权限，沿用预期企业 / 会话上下文和 CSRF。原合同、订单、设备查询不要求财务权限；其摘要单独访问资金来源接口。

- `sources` / `sources/{direction}/{id}` / `parties`：既有身份和商业来源，不返回库存成本或无关联系方式。
- `plans`、`cash`、`refunds`、`invoices`：列表 / 详情 / 新草稿；`confirm` 明确确认，`cancel` 只取消草稿。
- `plans/import` 导入冻结合同节点；`plans/{id}/adjust` 追加有依据金额；`release` 登记满足条件和到期日。
- `cash/{id}/allocate` 一次原子提交多行目标及各自版本；`allocations/{id}/reverse` 的 expected_version 是原资金当前版本。
- `refunds/{id}/confirm` 同时提交退款与原资金版本；确认前按原来源重新计算可退额。
- `reverse` 为不可变事实的受控逆向；不删除事实，不代表外部退款或作废税务票。
- `source-adjustments` 保存商业依据和当前来源版本；`summary` / `reconciliation` 为当前经营口径及明细守恒，不是法定收入或利润。

所有写入保留幂等键，同一次响应丢失重试复用；显式新建意图使用新键。金额为最多两位小数的精确字符串；不接受 JSON 浮点数、非有限值或 CNY 以外币种。拒绝使用 `FIN_*` 稳定代码；409 表示版本、额度或业务约束冲突，422 表示输入/方向/金额关系错误，403 权限不足，404 对象不可见。
