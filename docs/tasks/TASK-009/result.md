# TASK-009 执行记录

status: review_ready

已验收基线：b56ed65f2a234a956f75102b1320f7658dddfd71。前次缺失资料交接8a3cac4690272b40ec82ec1c0b0ee1467c499ce8；完整原件交接01e2c27（完整提交由最终交付登记固定）。main，开始仅用户新增增量报告未跟踪，原样归档，无用户改动被覆盖。

原件见original-task.md；task.md只增加status、移除附件前言并替换报告sandbox链接，业务要求未删减。TASK-008 result、两轮审查及原测试证据不变。Reviewer未独立重跑完整PG/IdP/浏览器、下载落盘校验not_run等限制不改写。

## 实现方向与边界

ADR-014记录身份→目录→报价→库存锁序；冻结订单映射included不重复领料；单台工单计划额度；固定SN/FIFO层预留；现有Worker授权到期；领料转wip，完工仅领料成本转待检成品；设备引用同一实物、安装历史及逆向保留。无新附件类型，无依赖升级、不启用测试发货或真实付款。

## 验证进行中

原始日志在evidence。mapping-red为沙箱禁止临时端口setup错误，不是产品失败；mapping-red-isolated真实404，新入口落地后mapping-green通过。reserve-red为未实现ready，reserve-green并发2项通过。issue-green因成品SKU转换遗漏manufacturer_id而失败，修复后issue-fixed3通过；移库测试原目标为受保护在制库位，改为普通库位专门检验预留。boundaries中的到期探针漏设user上下文，未更新RLS行，不算到期产品缺陷；补齐上下文后expanded11通过。backend-first的8失败/1错误源于最新迁移版本仍写0009（含ready影响OIDC启动）；正在修复重跑。typecheck中一次新增对账JSX闭合错误已修复，后续类型检查/构建通过。

当前尚未交付，不宣称TASK-009通过；后续追加准确最终测试和浏览器结果，完成后review_ready，不开始TASK-010。


## 最终交付（2026-09-11）

TASK-009进入review_ready，不自行accepted，不开始TASK-010。以上进行中记录保留为历史；下列最终验证替代当时的“正在修复/尚未交付”描述。

- 已验收基线：`b56ed65f2a234a956f75102b1320f7658dddfd71`。
- 缺失资料交接：`8a3cac4690272b40ec82ec1c0b0ee1467c499ce8`。
- 完整任务书/增量报告原样归档交接：`01e2c2759bb29d728ccd38f45db0597d689f0ceb`，亦为实现前HEAD。
- 实现commit将在随后的提交登记中记录；最终HEAD由审查包REVIEW_MANIFEST.md固定，避免提交自引用。所有源码从该HEAD导出。

### 实现

新增0010迁移、assembly领域/API、单台工单及设备页面；订单冻结配置映射、included不重复领料、台数额度、SN/FIFO固定来源、部分预留/释放、UTC到期Worker、实际领料→在制→待测试成品、设备同一实物引用、安装历史、整次逆向及后续依赖保护、数量/成本对账。复用现有库存移动和成本层，未另建台账。草稿可修复缺失追踪信息后再确认；签约订单和发布报价不变。

前后端继续使用既有身份/RLS/预期企业会话、权限重查、幂等与expected_version；后台执行重新授权。多表详情保持共享领域锁，写路径同序排他。成本字段按inventory.cost裁剪；来源移动下钻不显示采购金额。未新增附件类型、未升级依赖、未修改原Demo/系统信任/常驻数据库。

### 实际验证

准确命令、环境、日志与not_run见 [validation.json](evidence/validation.json)。完整后端209 passed / 10 warnings /169.69秒，含真实OIDC、空库迁移、前序报价发布/修订、合同、采购库存和文件保护回归；后续到期重预留小修另跑相关全集，59 passed / 5 warnings /46.42秒，含18项装配场景，结果见最终日志。弃用及Pydantic既有警告未通过升级依赖隐藏。

新增真实PG/API覆盖并发SN争抢、FIFO部分消费、主动释放与领料竞争、同时完工防重、幂等重放、安装唯一、跨企业和撤权、成本隐藏、未知成本/待检/隔离/代管阻断、逆向及旧入口保护、0009升级保留来源订单库存、确定性详情读取等待完整提交、服务器时长与Worker撤权。测试身份夹具替代OIDC，仅认证集成用真实IdP；不混称全部测试均走真实登录。

前端Node19项通过；实际React+HTTP替身2项通过；类型检查、构建、OpenAPI/生成类型一致性通过。实际浏览器完成订单→工单→预留→分批领料→完工→设备与来源→刷新、企业切换；缺一件内存的完工明确拒绝，双击创建仅一单。85元不完整在制经补领5元后，90=0+90，成品仍待测试。详见 [浏览器记录](browser-acceptance.md) 与 [截图索引](evidence/screenshots.json)。

### 失败与修复的补充历史

- backend-first迁移头断言修复后backend-fixed为206通过，后来新增测试后backend-final为209通过。
- duration-red真实422；实现服务端duration_hours后duration-regression为36通过，避免固定视觉时钟令预留过期。
- 浏览器StrictMode初始加载代次取消问题修复，最终组件StrictMode挂载通过；用户未保存数据不跨企业搬运。
- 末轮追溯面板TypeScript检查发现异步闭包receipt可能未定义，捕获orderId后build-final与typecheck-verified通过。
- node-final使用文件系统glob误纳入AppleDouble，属测试入口准备问题；node-tracked-final限定已跟踪测试后19通过，没有清理磁盘元数据。
- expiry-replace-red为真实VERSION_CONFLICT：清理到期行的内部版本递增发生在调用方版本校验前；调整为锁内先验证，再清理和重读需求，不放宽并发保护。红绿日志保留。
- 日志若含尾空格，以raw.gz保留原始字节、文本副本只规范尾空白；证据索引记录sha，不篡改结果。

### 限制

只记录实际领料成本，不含人工、费用分摊或税费政策推定；成品状态待测试，不启用发货/验收/收付款。预留一年上限是开发输入边界，不声称真实企业政策。无新附件业务；历史TASK008文件验收限制保留。手机宽表局部横向滚动；新增装配状态没有原Demo一模一样截图，不冒称旧基线。其他浏览器、采购收货至装配完整浏览器新购入流程、远程CI、生产部署均not_run，详情见浏览器记录。独立Reviewer尚未复核本任务。

审查包提供最终完整源码、基线/交接/实现差异、全部已有审查报告、原始红绿日志、截图、相对路径复现、SHA256SUMS和解压检查；不包含依赖、数据库、证书私钥或真实业务数据。Git正常快进推送与远程SHA核对由最终交付输出记录，推送不等于审查通过。

文档首次收尾检查早于validation.json生成而失败，补齐证据索引后重跑；不作为业务缺陷。

## 提交登记

实现提交：`1ed29e2c32030e3b1190fa2f68b06f7b2cb8bcd3`。该提交含最终到期重预留修复及59项定向回归；此前完整后端209项结果如上保留。收尾提交只固定登记和差异索引；最终HEAD见审查包REVIEW_MANIFEST.md。
