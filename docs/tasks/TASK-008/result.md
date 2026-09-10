# TASK-008 执行结果

status: review_ready

采购、分批到货、SN/批次成本层、质检隔离、成对移动、整张逆向、成本/数量对账和基本期初导入已进入独立审查。TASK-007 的 accepted 来自负责人明确授权；本任务未自行 accepted，不开始 TASK-009。

## 基线与交接

- 已接受基线：4802fcccb739fa89cada3be5179e21e0066121a0，开始时 main 工作树干净。
- 独立交接提交：0992ffbf6da59ea7237d20aeac2d9c3cb6e7e9ab。
- [TASK-007增量报告](../../reviews/TASK-007-4802fcc-review.md)与用户附件逐字节相同，首次报告、历史结果/限制不变。Reviewer 未独立重跑完整数据库/浏览器、Store父进程监测受环境限制等事实仍是历史事实。
- 附件原文保存在 [task-source](task-source.md)，[任务书](task.md)增加当前状态，验收前置由[交接](handoff.md)更新；没有已有独立TASK008任务书被覆盖。
- 实现提交与收尾范围在本报告末尾登记；最终受审HEAD由审查包 REVIEW_MANIFEST.md 完整固定，避免提交内容自引用其哈希。源码从该HEAD完整git archive导出，差异从上述已接受基线计算。

## 实现与决策

新增0009_inventory（从0008_contracts升级），包含供应商、采购合同/商业行、订单/取消、收货、库位、追踪方式、物理件、FIFO层、移动/分录/余额、期初批次及行、私有来源文件、显式合同增量和命令记录。仓库首期以库位的warehouse名称分组，未建设独立仓库主数据管理。商品复用既有SKU，制造商/品牌快照来自目录。

服务端身份/预期企业上下文 → catalog共享锁 → inventory租户共享读/排他写锁，保证聚合一致、净剩余与余额串行判断；单租户写串行是已记录的吞吐取舍。所有表RLS/FORCE RLS与同租户外键，幂等重放重查当前权限和来源，成本字段在响应前裁剪。

合同生效冻结双方/商业行/来源资料；追加同价数量使用不可变增量记录，不改旧快照。订单必须来自合同并受额度约束；确认后冻结，未到部分明确取消。收货保存不入库，过账待检，部分合格/隔离按件或批次数量成对移动。

SN只裁剪外空白及Unicode NFC，保留大小写和标点；物理unit与成本层分开，完整逆向后的更正收货复用物理ID、保留旧成本层。批次同名也不合并不同成本层。已过账事实不可改删，整张逆向按依赖倒序；不冒充退货、报损或付款。

CNY、piece整数；金额Decimal/NUMERIC两位小数、API精确字符串，不计算税率或抵扣资格。unknown必须NULL，已知零有效；自有已知成本小计与未知数量分开。对账按层/库位/状态比较台账与数量投影，成本投影为余额×不可变单位成本，分别返回已知金额/未知数量，不自动修平。历史as_of读取不可变台账；投影比较明确是当前。

期初CSV有界解析、原字节保存在TASK007同一私有Store；hash规范化行序、外部行身份双重防重。预览不写库存，明确提交重新校验且整批原子。固定截止日，关闭普通入口后才开始后续收货；首笔业务之后禁止重开回填。采购PDF/JPEG/PNG沿用原文件解码/私有下载，不另建公开文件系统。

前端沿用奶白、深绿、圆角、侧栏与现有token。采购、订单、收货、质检/移动、搜索/对账、期初与基础资料均调用真实API；采购来源时间线由真实关联记录构成。过账/取消/冲销有业务确认；错误不假成功，迟到企业响应被丢弃。原Demo无修改。

详见 [ADR-013](../../architecture/adr/ADR-013.md)。没有依赖升级、外部通知或生产部署。

## 实际验证

环境：macOS，Python3.12.7、Node24.15.0/npm11.12.1、uv0.12.11、PostgreSQL17.11、Java21.0.6、Keycloak26.7.3；[原始版本输出](evidence/environment.json)。测试临时集群使用silicon_app运行角色，非owner/超级用户/BYPASSRLS；独立IdP与自建测试CA校验，所有常驻数据库未连接/停止/写入。

```bash
export SILICON_TEST_PG_BIN="$PG17_HOME/bin"
export SILICON_TEST_KEYCLOAK_HOME="$KEYCLOAK_HOME"
.venv/bin/python -m pytest apps/api/tests -q
node --test apps/web/tests/*.test.ts
npm run typecheck
npm run build
.venv/bin/python infra/export_openapi.py
npm run api:types
.venv/bin/python infra/check_docs.py
docker compose --env-file .env.example -f infra/compose.yaml config -q
git diff --check
```

- 最终完整后端：**184 passed，6 warnings，124.88s**，[backend-complete](evidence/backend-complete.txt)。含18项新库存测试及166项前序目录/报价折扣/发布修订/合同/身份/真实OIDC/Worker等回归。警告为现有Starlette弃用和Pydantic并发schema警告；没有隐藏失败。
- 空库0009及已有0008升级保存签约合同的实测包含于以上；旧schema由真实downgrade建立，保留先前业务记录，不称为运行了旧版应用可执行程序。
- Node：19 passed；typecheck、build通过；生成OpenAPI/TypeScript再次生成字节一致；Compose配置检查exit0，未启动容器。
- 实际React组件页、HTTP替身：2 passed（丢响应重试/旧企业成功响应延迟）。它不是数据库或真实采购浏览器证据。
- 真实浏览器：alice登录 → A → 期初失败再成功 → 建合同/订单 → 两批2+3收货 → 4合格/1隔离 → SN搜索/移库 → 对账 → 刷新 → B隔离 → carol无成本视图。参见[复现及详细限制](browser-acceptance.md)、[截图索引](evidence/screenshots.json)。桌面1440×900、移动390×844；原始导出1425×891/375×812。
- 文档状态、报告哈希、相对路径和链接检查通过；最终暂存差异检查与打包校验另由交付登记/审查包记录。

### 任务书验收场景对应

| 场景 | 真实PG/API证据（test_inventory.py） |
|---|---|
| 1 合同两订单、额度、两批/取消 | contract_orders_bound_to_frozen_quantity；two_orders_batches_cancellation_and_amendment |
| 2 五件4合格1隔离、所有权可用 | receipt_partial_inspection_and_conserved_cost；opening_preview_atomic_dedupe_and_customer_ownership |
| 3 SN防重/并发/大小写与更正身份 | same_serial_concurrent_different_orders_and_case_preservation；serial_correction_reuses_physical_identity |
| 4 并发收货防超收/无残留 | concurrent_receipts_reverse_replay_and_reconciliation |
| 5 并发批次移库防负库存/不丢成本 | batch_layers_unknown_zero_and_concurrent_transfer |
| 6 幂等、来源、撤权、企业上下文 | supplier_persisted_and_scoped；current_permission_context_cost_and_cross_tenant；并发收货/逆向重放 |
| 7 部分质检/移库守恒与成本来源 | receipt_partial_inspection_and_conserved_cost；batch_layers_unknown_zero_and_concurrent_transfer |
| 8 逆向、重复拒绝、依赖 | reverse_dependency_in_order_restores_cost_and_history；serial_correction_reuses_physical_identity |
| 9 冻结、供应商历史、运行角色RLS | unknown_cost_and_original_supplier_snapshot；rls_no_context_immutable_facts_and_projection_discrepancy |
| 10 未知/零/暂估、差异定位 | unknown_cost_and_original_supplier_snapshot；batch_layers_unknown_zero_and_concurrent_transfer；projection_discrepancy |
| 11 期初原子/hash/行序/截止 | opening_preview_atomic_dedupe_and_customer_ownership；opening_errors_closed_boundary_and_atomicity；closed_opening_rejects_new_preview_and_reverse_checks_version |
| 12 租户/权限/文件与导入 | current_permission_context_cost_and_cross_tenant；attachment_private_frozen_and_original_import_download；rls_no_context；原Worker授权回归 |
| 13 空库/升级/前序核心 | conftest空库；upgrade_task007_keeps_signed_contract；完整184项 |

不新增库存后台任务；即时库存命令全部同步事务，原Worker授权测试仍通过。以上按风险组合测试，不表示每个接口与每种恶意输入的穷举验证。

## 红绿与修复记录（原日志保留）

供应商/采购/期初端点的404红测随后变绿；receipt-red在采购冻结触发器字段分支处503，是当时实现错误，不能说它已验证收货业务拒绝。purchase-green名字不代表通过：旧触发器错误后purchase-fixed通过。并发red在对账端点缺失处失败，不能冒充已复现超收。

expanded-first真实暴露撤销成本权限后仍能重放含成本创建（200而非403），修复为重放前重查；expanded-green12通过。inventory-final中的对账探针失败是owner连接未设租户导致UPDATE0的夹具准备错误；补上下文和rowcount断言后通过，不当作产品缺陷。

final-boundary-red真实显示关闭期初仍接受新预览；已拒绝新预览且保留已过账同内容重放。cost-projection-red显示差异缺金额；补齐比较。backend-release是沙箱禁止监听端口（15通过、169环境setup错误），不是数据库产品结果；获准隔离运行后backend-release-green仍有3项失败，是成本JOIN键拼写错误且进程已加载旧代码；修正后重新启动完整backend-complete，184通过。保留所有中间日志，不把文件名green作为结论。

浏览器首次日期控件未同步React，保留未过账旧草稿；修复onInput后实际保存正确日期并完成两批。真实会话过期一次，重新登录后继续，不将失败计作成功。初始布局诊断图保留，最终恢复token留白和按钮宽度。

## 限制与复现

- not_run：Docker容器实际运行、远程CI核实、其他浏览器引擎、自动像素阈值比对、生产部署及真实业务验收。真实税费资格/费用分摊未配置，不推定统一税率。
- 浏览器完整闭环早于最终采购时间线/关闭预览按钮/成本对账细节收尾；最后这些变更通过类型/构建或真实PG，本轮未重复整套浏览器流程。截图不冒充新增细节的浏览器证明。
- 首期仅同价合同增量、整张错误逆向、整数piece、CNY；不实现预留、FIFO出库消耗、装配、发票/付款、采购退货或复杂期初迁移。
- 采购来源的可选销售订单/项目关联在API与数据库约束中支持；页面首期按通用备货操作，尚无来源选择控件。供应商更新接口具版本校验，页面本轮仅基础新增/查询。仓库以名称分组，不提供独立仓库更名流程。
- 初次无效CSV预览记录冻结保存；同内容重放仍返回旧预览，主数据修正后请修改/重新生成有区别的待导入文件再预览。已提交内容绝不重复入账。
- 本地文件类型验证不是AV或硬隔离沙箱。Store原历史限制继续保留；不宣称旧冻结文件被重新认证。未修改系统信任、原Demo、常驻数据库。
- 原始日志可能含历史本机路径，它们不是复现依赖。所有复现命令以仓库根及环境变量运行；审查包不含PG/Java/Keycloak安装包、字体、TLS私钥、真实数据或依赖目录。

浏览器夹具退出记录BROWSER_STACK_CLEANED；新CSV生成脚本只写虚构文件，不连接DB。独立审查包由 `infra/package_task008_review.py --implementation "$IMPLEMENTATION_COMMIT" --destination "$REVIEW_ZIP"` 从干净已提交HEAD生成并解压校验。完整源码、二进制差异、日志/截图、任务/ADR/报告及SHA256SUMS均包含；旧历史证据保持。
