# 经营指标字典 v1（TASK-013）

编码前固定。共同口径：Asia/Shanghai自然日；期间[start,end)，截止日含当日；截至查询时已知事实重建。金额CNY Decimal字符串、不自动含税换算，不称营收或利润。每项返回value/unit/status/reason/basis/date与可下钻标识。空的完整集合=0；未知值=null。未授权=unauthorized（没有贡献、排行或链接）；不适用筛选=not_applicable；资料不足=unavailable/partial。

共同粒度约束：每条贡献有稳定source_id；聚合、地区与排行及分页下钻来自同一贡献集合。后续请求带snapshot摘要；变化则拒绝并刷新。下钻排序date/label/value加id，25默认、100上限。默认长期订单90天、库存180天、近期应付7天，均是用户筛选阈值，不是预测。

| ID / 名称 / 单位 | 来源、粒度、键 | 公式 / 日期 / 状态与逆向 | 权限 / 范围 / 下钻对账 / 缺项 |
|---|---|---|---|
| contracts / 本期签约额 / CNY | signed_contracts.id；content.commercial.config.customer_id | 每签约冻结commercial.calculation.total一次；fields.signed_on或登记日；退货不冲减签约 | contract.read；当前CRM owner；合同贡献求和=卡片=地区；税按冻结商业金额，资料缺失partial |
| contract_count / 签约合同数 / 份 | 同上 | 期间签约事实去重计数 | 同上，合同下钻 |
| dispatched / 发出 / 台 | del_lines.id→movement_id→inv_movements | 期间原出库+1；误操作逆向在逆向日期-1；不是按草稿日期 | delivery.read；订单→冻结customer→当前owner；发货贡献 |
| returned / 实际退回 / 台 | del_returns.id→movement_id | 期间实际实收+1；申请不计 | 同上，原发货下钻 |
| net_delivery / 净交付 / 台 | 上述两类贡献 | dispatched-returned；一台重发另有出库行 | 同上，允许跨期净流量负数，非截止日在外数量 |
| receipts,payments / 实收、实付 / CNY | fin_cash.id | 已确认资金occurred_at金额；误冲销在reversal.created_at反向，不按当前布尔值过滤历史 | finance.read；receivable当前客户owner，payable可见供应商；资金贡献；税不适用 |
| customer_refunds,supplier_refunds / 付出、收到退款 / CNY | fin_refunds.id→cash_id | 确认退款occurred_at，逆向日反向；核销不产生现金流 | 同上；退款贡献；无确认事实历史partial |
| net_cash / 净现金流 / CNY | 四类资金贡献 | receipts-payments-customer_refunds+supplier_refunds | finance.read；同源贡献符号加总；不称利润 |
| receivables,payables / 截止日未结 / CNY | fin_plans.id；调整/更正/核销/逆向/释放按plan_id预聚合 | 确认额+截至日前adjustment+correction-有效allocation；确认时点须可靠；未释放不伪造到期 | finance.read；来源可见性同原子台账；每计划一行，对账remaining；缺确认时间历史unavailable |
| overdue_receivables,due_payables / 逾期应收、近期应付 / CNY | 同计划 | due_date<as_of逾期；近期as_of至as_of+7含末日；只有已释放有到期日 | 同上；阈值明示；未释放另分组 |
| advance_receipts,advance_payments,unallocated_receipts,unallocated_payments / 未分配资金 / CNY | cash.id→allocation/refund/reversals | 截止日已确认资金-有效退款-有效核销；purpose区分advance与unallocated | finance.read；各自下钻不与债权抵销 |
| business_customers / 有签约业务客户 / 家 | 期间合同客户ID | distinct customer | contract.read；客户贡献 |
| new_customers / 新增成交客户 / 家 | 客户首份签约日期 | 首次签约属于期间；不是建档日期 | 同上；此前所有可见签约建立首日 |
| concentration / 前N客户签约集中度 / % | 同期间合同按customer汇总 | 前N签约/期间签约×100；默认5，可配置；分母0=null | contract.read；客户排行与总额对账；缺金额不可计算 |
| customer_distribution / 当前客户地区分布 / 家 | crm_customers.id、province | 当前可见客户数，不伪造历史省份 | crm.read；当前owner；34省+海外+未知=总数 |
| signed_regions,delivery_regions / 地区签约与净交付 / CNY、台 | 合同/发货贡献关联当前CRM地区 | 与上述总览相同；标题明确当前客户地区 | 各自源权限；未知/海外保留；非实际历史收货地点 |
| product_rank,brand_rank,manager_rank / 销售结构 | signed.content商业host、fields.sales | 签约额按冻结配置的主机/销售品牌/销售负责人各分组一次；不按技术行重复金额 | contract.read；缺字段单列未知，不猜名称 |
| inventory_known_cost / 自有库存已知成本 / CNY | inv_entries按layer/location/state合并；layer成本 | effective_on<=as_of的移动有符号数量×原unit_cost；含WIP/成品/service_issued；客户所有排除 | inventory.read+inventory.cost；all范围；按层库位状态下钻，与台账同口径；未知数量另计partial |
| inventory_unknown / 自有未知成本数量 / 件 | 同上 | 自有且unit_cost为空的正余额合计，不能当0成本 | 同上；层下钻 |
| inventory_quantity / 库存/保管结构数量 / 件 | 同上 | 按ownership/state/stage分组；原料、WIP、成品、售后暂存、客户、supplier分别表达 | inventory.read；all范围；不含金额字段时仍可显示数量 |
| inventory_age / 库龄 / 件 | layer.source_movement.effective_on | as_of-原层入库日；0–30/31–60/61–90/91–180/181+；移库不重置，成品起点=完工 | inventory.read；原入库缺失=未知；分档与余额合计一致；最新销售退回日另给本次在库时长 |
| completion_to_ship / 完工至首次发货 / 天 | asm_completions→del_lines→movement | 已发样本日期差均值/样本数；排除已逆向完工；同时列未发数量 | delivery.read；源owner；样本0=null；未来日期或缺失排除并说明 |
| overdue_orders / 长期待履约订单 / 台 | sales_orders.id→signed→del_lines/returns/reversals | 截止日订单quantity-净已发；签约距截止日超过阈值 | delivery.read；owner；订单明细，不将装配完工当交付 |
| held_devices / 客户设备待归还 / 台 | svc_receipts.id→svc_returns.receipt_id | 截止日前接收且未归还；performed_at | service.read；设备订单客户owner；工单明细；非自有库存 |
| rma_outside,rma_overdue / 在外及逾期返修件 / 件 | svc_rma_lines→old_parts.layer→inv_entries supplier | 截止日supplier余额；expected_on<截止日逾期；分批返回逐笔减 | service.read；工单owner；RMA下钻；不使用当前completed覆盖历史 |
| rma_held / 返回后仍隔离 / 件 | returns→inspections(hold)→dispositions | 截止日前hold且未最终处置；每返回数量，不按RMA单数 | service.read；原工单owner；工单下钻；保持TASK012修复语义 |
| DIO,DSO,DPO,CCC / 标准周转 | 会计收入/赊销赊购及完整平均余额未具备 | v1均null/unavailable，列具体缺少的来源/平均余额与历史覆盖 | 对应资金/库存权限；无权限不透露业务值；不以当前余额当期间平均 |

## 下钻和范围

每条明细只返回label、日期、数量/获授权金额、分组与受控业务目标，不返回联系人/详细地址。业务目标存在不代表授权，原详情仍独立鉴权。金额明细依对应源权限，库存金额额外成本权限。客户/地区过滤应用于能关联客户的合同/交付/应收/售后；应付与自有库存明确not_applicable。产品/品牌/负责人为签约分组维度，非跨全部模块筛选。

## 历史不足

确认时间表仅保存时间元数据；回填来源为成功finance.<kind>.confirm审计，不用创建日期猜测。缺确认时点的旧确认计划在历史截止日返回不足，不显示今天余额。所有数据不足/样本不足在UI独立显示，空集合零与未知null不同。
