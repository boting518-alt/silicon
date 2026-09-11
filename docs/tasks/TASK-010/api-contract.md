# TASK-010 API 契约索引

权威schema为 packages/api-client/openapi.json 与生成 schema.d.ts，前端直接引用生成类型。

统一 `/api/v1/delivery`，GET 需要 delivery.read；写命令需要CSRF、X-Expected-Tenant、X-Session-Context、Idempotency-Key，认证和membership由服务端决定。

| 路径 | 权限/命令 |
|---|---|
| GET devices、devices/{id} | 测试资格、库存版本、完工及履约历史 |
| POST devices/{id}/tests | delivery.test；expected_version + completion_id + items + performed_at |
| GET orders | 既有订单明细汇总：累计、净交付、退回、净验收、剩余 |
| GET shipments、shipments/{id} | 冻结收货快照、实际设备行、验收链与退回 |
| POST shipments | delivery.ship；订单、设备ID列表、收货快照；草稿不占库 |
| POST shipments/{id}/confirm、cancel | delivery.ship；expected_version + confirmed |
| POST shipments/{id}/accept | delivery.accept；expected_version + line_ids + 时间及确认信息 |
| POST shipments/{id}/return | delivery.return；expected_version + line_ids + 实收时间、原因、待检库位 |
| POST shipments/{id}/correct-acceptance、reverse | delivery.correct；显式更正，不删原事实 |
| GET reconciliation | 数量、原成本层出入库引用及库存投影差异 |

每行代表一台稳定设备，不接受前端金额或任意数量。未知/无资格/重复/版本冲突返回稳定4xx；不自动重试改投其他企业。多表读写共享既有库存领域事务锁。所有金额返回精确字符串，无inventory.cost移除cost字段，包括幂等重放。动作执行人服务端记录，报告字段为人工登记编号而非可点击外部文件URL。
