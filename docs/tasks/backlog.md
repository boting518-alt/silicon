# 任务登记

唯一当前任务：TASK-013，status: review_ready。TASK-000～TASK-012 已由产品/架构负责人确认 accepted；TASK-014 起均为 planned；后续条目只是规划，不授权实施。依赖任务需通过独立审查，P0/P1 修复后才可前进，最终 accepted 由业务验收人决定。

## 10. 分阶段交付计划

TASK-000～TASK-012 为 accepted；TASK-013 为 review_ready；TASK-014～016 均为 planned。TASK-000～003 足够启动；后续任务在前序稳定后细化，不让 Codex 一次生成所有系统。

| 任务 | 范围 | 前置 | 完成判据 |
|---|---|---|---|
| TASK-000 | 源码盘点、Demo 基线、文档落仓 | 无 | 确认两个来源 commit、文件与访问条件；保留 token；标记假业务规则；首期目录和任务就绪 |
| TASK-001 | 工程骨架、CI、本地运行 | 000 | Web/API/DB/Worker 启动；health/ready；真实 PG 迁移；CI 命令可重复执行 |
| TASK-002 | 身份、租户、权限、审计 | 001 | 两个租户测试越权；运行 DB 角色真实经过 RLS；成本字段、附件边界有测试 |
| TASK-003 | 原 UI 壳迁移 + 客户纵切 | 002 | 原侧栏和客户页风格保持；创建/编辑/刷新持久化；一个客户多个联系人/项目 |
| TASK-004 | SKU、准系统包件、BOM、价格表 | 003 | 包含电源和不含电源两类准系统；规则版本；有效价、未知价区分 |
| TASK-005 | 配置报价与折扣 | 004 | 原 SVG 与报价联动；后端权威计价；兼容失败/未知；折扣越权与并发防重测试 |
| TASK-006 | 报价发布、审批、合同草稿 | 005 | 发布快照不被改写；内容变更审批失效；报价转合同草稿保持一致 |
| TASK-007 | 合同签约、订单、付款节点、附件 | 006 | 甲乙方冻结；内部责任人历史；合同与开票/交付状态独立 |
| TASK-008 | 采购、到货、成本与库存移动 | 007 | 分批收货、待检隔离、SN/批次、期初导入；库存成本对账 |
| TASK-009 | 预留、装配与设备档案 | 008 | 并发预留不超卖；零件/WIP/成品不重复成本；部件安装历史 |
| TASK-010 | 测试、分批发货、验收、退货 | 009 | 禁止无货出库；一单多批；部分退货与逆向成本流水 |
| TASK-011 | 应收应付、发票登记、收付款核销 | 010 | 部分/多对多核销、预付款/退款/质保金；不把签约额显示为收入 |
| TASK-012 | 售后、备件、换件与 RMA | 011 | 旧件去向、新件来源、人工费用、供应商返厂记录齐全 |
| TASK-013 | 经营驾驶舱、地图和周转 | 012 | 图表与明细同源；截止日/期间/税口径清楚；缺数据不造周转率 |
| TASK-014 | Agent 执行器与只读经营助理 | 013 | 真实模型与 mock 分开；越权/注入/预算/超时测试；所有事实可追溯 |
| TASK-015 | 合同抽取与报价草稿 Agent | 014 | 字段证据、版本绑定审批、去重执行；错误结果不污染业务记录 |
| TASK-016 | 导入强化、套餐与用量、客户试运行 | 015 | 导入对账；服务端 entitlement；完整正向+逆向 E2E；备份恢复演练 |

TASK-008 开始提供基本期初导入，TASK-016 是工具化强化，不把首批数据导入拖到最后才考虑。

验收里程碑：

- M1（000–007）：可真实保存并发布报价、创建合同，客户能看到与原 Demo 一致的风格。
- M2（008–012）：一笔采购到交付回款，以及一次换件都能追踪。
- M3（013–016）：老板看真实经营指标，Agent 提供可核验帮助，可以进入付费试运行。

工期不根据“AI 写代码很快”直接承诺。先完成 000–003，记录真实每任务耗时和返工率，再估算后续；首版优先闭环，不以页面数量当完成度。



## 可执行任务书

- [TASK-000](TASK-000/task.md) / [结果](TASK-000/result.md)
- [TASK-001](TASK-001/task.md)
- [TASK-002](TASK-002/task.md)
- [TASK-003](TASK-003/task.md)

## TASK-001 交接依据

2026-09-09，产品/架构负责人依据 [首次审查](../reviews/TASK-000-91ac217-review.md) 与 [R1 增量复核](../reviews/TASK-000-88e3044-review.md) 明确接受 TASK-000 并分配 TASK-001。已核对 HEAD 为 88e3044ac8749a9c003fe2ecc78a6de0c9abf1d6，两份报告原样纳入 Git；未覆盖用户修改。

## TASK-001 交付

工程骨架已由产品/架构负责人确认 accepted；实际验证与限制见 [结果](TASK-001/result.md)。

## TASK-002 交接依据

2026-09-09，产品/架构负责人依据 [首次审查](../reviews/TASK-001-8b7cf4a-review.md) 和 [增量复核](../reviews/TASK-001-c50a951-review.md) 确认 TASK-001 accepted，明确分配 TASK-002。交接时 HEAD 为 c50a95126ec9de6c471c2425cde3dac5f9012993；只有未跟踪的增量报告，原样纳入 Git，无用户修改被覆盖。历史验证及两轮报告结论保持原样。

## TASK-002 交付

身份与隔离纵切进入 review_ready，实际命令与限制见 [结果](TASK-002/result.md)。保留生产启动拒绝；TASK-003 仍为 planned，未开始。

## TASK-003 交接

2026-09-10，产品/架构负责人依据 [TASK-002 独立审查](../reviews/TASK-002-9936743-review.md) 确认身份与隔离纵切 accepted，并明确分配 TASK-003。交接 HEAD 为 99367439f175c1b749395b40f7a0d4a0af068afb，main 分支，只有未跟踪审查报告；原样纳入 Git，无已跟踪用户修改。保留原测试结果及报告结论；浏览器完整验收、远程 CI、容器、远端即时撤销及生产运维限制继续适用。TASK-003 已明确授权浏览器测试，不能以协议测试替代。


## TASK-003 交付

原 UI 壳与客户管理纵切进入 review_ready；真实 OIDC/PG/API/Worker 共 45 项通过，实际浏览器交互与两视口截图已完成。有意视觉变化与 not_run 限制见 [结果](TASK-003/result.md)。保持等待独立复核，不标 accepted，不开始 TASK-004。

## TASK-004 交接

产品/架构负责人依据 [首次审查](../reviews/TASK-003-45453c7-review.md) 与 [增量复核](../reviews/TASK-003-a6b640e-review.md) 确认 TASK-003 accepted 并明确分配 TASK-004。main/HEAD 为 a6b640e6dd7f5ac1ecff40fa7f43cc5afe241d47；只有未跟踪的增量报告，原样纳入 Git，无已跟踪用户修改。历史结果、限制与结论不改写。[TASK-004 任务书](TASK-004/task.md) 补齐原规划，TASK-005 未授权。

## TASK-004 交付

目录、包件/BOM、版本化规则与价格进入 review_ready；本地完整后端 66 项、前端 14 项通过，真实浏览器及两视口截图已完成。详见 [结果](TASK-004/result.md)，其中保留远程 CI/容器 not_run 与有限规则范围。等待独立审查，不开始 TASK-005。

## TASK-005 验收交接

2026-09-10，产品负责人依据 [增量复核](../reviews/TASK-004-a8ce3e2-review.md) 明确 accepted TASK-004 并分配 TASK-005。HEAD a8ce3e2c13736a032958decf1e65fb482cd4ebf6 与被审查提交一致，main 工作树干净。保留首次报告和历史限制，未修改旧 result。原无 TASK-005 任务书，依据用户范围补齐 [任务书](TASK-005/task.md)。

## TASK-005 交付待审查（2026-09-10）

TASK-005 status: review_ready。配置报价草稿、服务端计价、开发单码优惠、原 SVG 联动与独立 PG/浏览器验证已交付；结果见 [result](TASK-005/result.md)。不自行 accepted，不启动 TASK-006。TASK-004 的两轮报告与历史结果不改写。

## TASK-005 独立审查修复

2026-09-10：按用户授权修复 [R1/R2/C1报告](../reviews/TASK-005-6d2a818-review.md)，新增实际PG与React组件回归及定向真实浏览器证据。状态保持review_ready，详见 [结果追加](TASK-005/result.md)；不自行accepted，不开始TASK-006。

## TASK-006 验收交接

2026-09-10，负责人依据 [TASK-005 增量复核](../reviews/TASK-005-da215ad-review.md) 明确 accepted TASK-005 并分配 [TASK-006](TASK-006/task.md)。main/HEAD da215ad9b22e5d831c0d7a319885ddf7ad3ec8ef 与审查基线一致；只有未跟踪的同报告，已与附件逐字节核对原样归档。旧 result、首次审查及证据不改写；Reviewer 未重跑 PG/OIDC/完整浏览器等限制保留。TASK-006 executing，不开始 TASK-007。

## TASK-006 交付待审查

审批、发布快照和来源合同草稿进入 review_ready，见 [结果](TASK-006/result.md)。独立PG/OIDC完整116项及补充3项、真实双人浏览器与两视口证据均如实记录；正式商务政策/远程CI等限制保留。不自行accepted，不开始TASK-007。

## TASK-007 验收交接

负责人明确确认 TASK-006 accepted，审查对应 59f55c813aba62ec8f18dc5d5e7cc649b277aeca，并授权 [TASK-007](TASK-007/task.md) executing。增量报告 TASK-006-59f55c8-review.md 尚未在仓库/Downloads/附件目录找到，待原样归档；不编造审查结论正文。旧报告及结果保持原样。见 [交接记录](TASK-007/handoff.md)。

## TASK-008 验收交接

负责人明确接受TASK-007并授权TASK-008。基线4802fcccb739fa89cada3be5179e21e0066121a0，main工作树干净。 [增量报告](../reviews/TASK-007-4802fcc-review.md)原样归档；首次报告、旧result及验证限制不变。Reviewer未重跑完整PG/IdP/浏览器、Store父进程监控受环境限制等事实保留。见 [任务书](TASK-008/task.md) 与 [交接](TASK-008/handoff.md)。

## TASK-009 验收交接

负责人明确接受TASK-008并授权TASK-009。核对main/HEAD为b56ed65f2a234a956f75102b1320f7658dddfd71，工作树干净，无后续提交。passed结论及审查HEAD依据本次用户声明；增量报告TASK-008-b56ed65-review.md尚未找到，不能声称已读取或归档。完整TASK-009任务书同样未找到，业务实现等待原件，不以摘要补造规则。首次报告、TASK-008 result及全部历史证据保持原样。见[交接与缺失记录](TASK-009/handoff.md)。

TASK-009完整任务书与TASK-008增量报告现已补齐，见[任务书](TASK-009/task.md)、[增量报告](../reviews/TASK-008-b56ed65-review.md)。缺失记录保留为历史，继续实施。

TASK-009实现及本地验证完成，进入review_ready；见[执行结果](TASK-009/result.md)。TASK-010及后续仍为planned，等待独立审查。

## TASK-010 验收交接

负责人依据[TASK-009增量审查](../reviews/TASK-009-17088be-review.md)确认 accepted，明确授权[TASK-010](TASK-010/task.md) executing。核对及限制见[交接](TASK-010/handoff.md)。历史记录保留。

TASK-010 实现及验证进入 review_ready，见[结果](TASK-010/result.md)。等待独立审查，不自行 accepted，不开始 TASK-011。

TASK-010 R1 按用户授权修复：保留基础设备权限，交付历史独立授权。原样归档[独立报告](../reviews/TASK-010-9da23ab-review.md)，实际回归与限制追加至[结果](TASK-010/result.md)。状态保持 review_ready，等待增量复核，不开始 TASK-011。

## TASK-011 验收交接

负责人依据[TASK-010增量报告](../reviews/TASK-010-b6ca2fe-review.md)确认accepted，并授权[TASK-011](TASK-011/task.md) executing。见[交接](TASK-011/handoff.md)；历史报告及验证限制保持不变。

TASK-011 实现与本地验证完成，进入 review_ready，见[结果](TASK-011/result.md)。完整后端 237 项、React 组件 4 项和 Node 19 项通过；真实资金浏览器闭环及两视口证据已保存。等待独立审查，不自行 accepted，不开始 TASK-012。

TASK-011 R1 按用户授权修复：原样归档[独立报告](../reviews/TASK-011-680c071-review.md)，新增负向调整完整更正、兼容迁移及真实PG/页面回归。追加证据见[结果](TASK-011/result.md)，状态保持review_ready，等待增量复核，不开始TASK-012。

负责人依据[TASK-011增量报告](../reviews/TASK-011-6d89a10-review.md)明确接受TASK-011，并授权[TASK-012](TASK-012/task.md)。见[交接](TASK-012/handoff.md)，历史验证限制保留。

## TASK-013 验收交接

负责人依据[TASK-012增量报告](../reviews/TASK-012-18966f4-review.md)确认accepted，并授权[TASK-013](TASK-013/task.md)。见[交接](TASK-013/handoff.md)；历史结果与Reviewer验证限制保留。

TASK-013 实现与本地验证完成，状态 review_ready，见[结果](TASK-013/result.md)。历史验收和限制保留，等待独立审查，不开始 TASK-014。
