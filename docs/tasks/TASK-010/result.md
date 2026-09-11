status: review_ready

# TASK-010 执行结果

## 交接与来源

已验收基线 `17088be77dd1472ce11287f7b6ae88cfcb0bf721`。交接提交 `c6d5bc3a2d4e1a2569ed18f3e6816f45503610d6`：TASK-009 按用户确认 accepted，原样归档 passed 增量报告（与附件逐字节一致）；TASK-010 executing。初始 main 无后续提交，只有该未跟踪报告，无用户实现修改。旧 result、changes_requested 报告及历史验证限制保留。

## 实现与边界

新增0012交付迁移与 delivery 模块，使用原 sales_orders 单配置订单行、asm_devices/asm_completions 和 inv_layers/entries/movements，不另建库存账或设备实物。测试逐项追加，最新失败覆盖资格；完工和库存版本绑定，退货/移库/更正后重测。发货草稿不占库存，确认事务校验资格/关联/剩余/预留，原成本出库；部分验收不再结转；实收退货恢复原成本层pending及待履约数量。支持无下游整批误操作冲销、追加验收更正；已过账履约保护装配来源。

沿用身份/租户/CSRF/预期企业、成本裁剪、命令幂等与同序事务锁。原设备查询增加履约历史，交付页面使用原token/卡片/表单，真实失败不降级假数据。设计与恢复限制见 [ADR-015](../../architecture/adr/ADR-015.md)。

当前支持的设备来源为已有装配完工（含第三方品牌产品），无档案采购整机不自动放行；未建设新的第三方独立成品建档。测试/验收报告为人工档案登记编号，不提供公开URL或假装已有文件上传。现有付款节点不改写为收款。未实现财务、硬件采集Agent、物流、签章、生产部署或TASK-011。

## 验证记录

准确命令及最终结果见 [验证清单](evidence/validation.json)。

- 首条真实PG/API测试 testing-red 因新入口不存在404失败，testing-green第一次迁移引用误写users而非identity_users，修正后testing-green-2通过1项。
- returns-red完整准备三台后在未实现的验收入口404失败；returns-green通过2项，覆盖两批、部分验收、原成本退货、重测重发、持久身份及180元成本连续性。
- concurrency首次误把未消耗的100元原材料排除在全库存期望之外；修正期待总库存180而不是80。history-concurrency最初试图逆向有其他工单后续领料依赖的共享层，改为先更正再准备第二台，未放宽装配依赖规则。
- domain-final为交付5项加既有更正6项，11 passed /3 warnings；随后补充最新失败、移库失效、错误行/未发验收及对账。
- backend-first：8 failed /212 passed /1 error，版本断言未更新、迁移命令配置路径/对账键夹具错误及真实IdP启动失败。backend-final：6 failed /216 passed，临时迁移库清理超时导致同名库级联失败，另有新增移库夹具漏填reason。独立upgrade-diagnosis：5 passed；第三次backend-complete：5 failed /217 passed，仍发现清理超时，已读临时PG日志证实DROP触发检查点3.176秒而应用连接仅3秒，pg_stat_activity无残留连接。撤回WITH(FORCE)，只对临时升级库删除设置30秒维护超时，业务和并发超时不变；诊断原始片段见cleanup-diagnosis.txt。
- 实际React组件+HTTP替身2通过；Node19通过；类型、构建及OpenAPI再生成字节一致通过。组件替身不替代真实PG或浏览器。
- 真实浏览器已完成要求闭环及桌面/移动、企业B隔离、退出保护，见 [浏览器记录](browser-acceptance.md)。最终净交付3、退回1、累计4、待履约0、净成本180。保存早期与最终截图并区分中间状态。

最终完整后端：**222 passed /10 warnings /201.73秒**，无失败/跳过，见evidence/backend-verified.txt。包含新增6项交付回归和全部前序216项；真实OIDC成功。不是累计历史运行次数。最终前端构建见build-final-device.txt，Node19、组件2项、类型及契约一致性通过。

## 限制

远程CI未核实；Docker/其他浏览器/生产环境 not_run，未要求部署且本次未运行。人工登记不是硬件认证，未集成实际报告采集/物流/财务。新增设备档案履约摘要在核心浏览器闭环之后修改，类型/构建验证，未再独立点击该摘要；交付页面同源完整历史已经真实点击验证。原TASK-009 Reviewer未独立重跑PG/IdP/浏览器等限制仍为历史事实，本轮不是独立验收。

迁移空库及0011升级验证保留身份、订单、完工、实物和原成本；交付表非空时降级拒绝，不能删除历史来降级。普通恢复走既有备份恢复规程，本轮没有重建业务数据库。测试栈结束记录BROWSER_STACK_CLEANED。

实现提交与最终HEAD在提交登记及审查包中固定，审查包从干净commit导出全部tracked源码与相对基线差异；不包含依赖、私钥、数据库、环境秘密或AppleDouble。不自行accepted，不开始TASK-011。

## 提交登记

实现与证据提交：`663725a3887c2cb15222182d661d9f9642a5aa0f`。交接提交：`c6d5bc3a2d4e1a2569ed18f3e6816f45503610d6`。随后收尾提交仅固定本登记和文件/提交索引；最终HEAD由审查包REVIEW_MANIFEST.md精确记录，避免自引用提交号。状态review_ready，等待独立审查。

打包：`.venv/bin/python infra/package_task010_review.py --implementation 663725a3887c2cb15222182d661d9f9642a5aa0f --destination "$REVIEW_ZIP"`。完整源码、基线差异、逐文件Git blob比对、补丁重放、历史保留及解压SHA256SUMS均由脚本验证。GitHub推送和远程SHA在最终交付消息核实，CI未核实。

## R1 增量修复（2026-09-11）

本轮审查基准与修复起点：`9da23ab4aef6fdc766a68379a694c65bef3f8f4b`，main 工作树干净、无后续提交；未reset或覆盖用户修改。用户已明确授权仅修复R1。原样归档[独立审查报告](../../reviews/TASK-010-9da23ab-review.md)，SHA256固定于文档检查；旧报告、原测试结果、历史限制及发布快照保留。状态继续 **review_ready**，不自行accepted、不开始TASK-011。

原因：设备及装配页面强制使用要求delivery.read的设备聚合接口，导致保留device.read但无delivery.read的用户失去基础列表、搜索、详情与装配初始加载。

修复：基础列表/搜索/详情回到原 `/assembly/devices`，详情重新向后端校验读取权限；交付历史按delivery.read独立加载，独立状态与错误提示。刷新、搜索、重开/关闭先清空旧交付信息，403保留基础数据并明确提示，其他失败显示真实错误；代次/企业上下文保护拒绝关闭或切企业后迟到的成功响应。基础列表不再猜测交付状态。未更改后端生产权限、默认角色、迁移、写命令或接口契约；delivery-only的既有设备投影范围、成本另行授权和关联ID不授予对象访问，在[ADR-015](../../architecture/adr/ADR-015.md)明确。不通过扩大授权或假数据掩盖错误。

### 实测

- 修复前实际React测试：基础设备列表断言失败，工单数据也未加载。保存 [红灯观察](evidence/r1/component-red.txt)。这是真实浏览器运行的React+HTTP替身，不冒充PG复现。
- 新React权限回归3 passed：无交付权的基础设备与工单交互；授权历史→实际组件403→历史清除、基础保留；确定性延迟成功历史响应在关闭详情及切企业后不得重新进入页面。原装配2、交付2也通过（创建丢响应幂等与跨企业迟到成功响应）。
- 定向真实PG/API：7 passed /3 warnings /17.34秒。覆盖独立细粒度权限、列表/搜索/详情、无交付权创建装配草稿、交付撤权、delivery-only范围、跨租户404、成本裁剪及原交付并发/成本/迁移核心回归。新增权限测试使用真实非owner应用角色，只有OIDC登录准备使用测试替身。最初6 passed/1 failed因viewer测试夹具漏配assembly.read；只补充该测试角色权限并finally恢复，不修改生产角色策略，不算产品红灯。
- 完整后端：**223 passed /13 warnings /205.51秒**，包括真实OIDC、会话、RLS、迁移、Worker及所有前序报价/目录/客户/库存/装配/交付回归。无失败或跳过；警告为既有依赖弃用/字段属性诊断，没有升级依赖。
- Node19 passed；类型检查、构建、OpenAPI与客户端再生成字节一致、文档及diff检查通过。见[准确命令及结果](evidence/r1/validation.json)。
- 真实浏览器：真实IdP登录A→保存DEL-0测试→设备基础详情及测试历史→临时集群撤交付权→重开得到403且清旧历史→装配列表和对账→按SN搜索→移动端刷新恢复→恢复原权限查历史→企业B隔离→真实退出。桌面1440×900、移动390×844证据及可重复夹具步骤见[浏览器记录](evidence/r1/browser-acceptance.md)、[截图清单](evidence/r1/screenshots.json)。测试栈已清理，无常驻库/证书信任/原Demo改动。

### 限制与增量交付

本轮只重复查询权限相关浏览器流程，没有重跑全部发货/验收/退货浏览器闭环（旧证据保留，真实PG核心全量已重跑）。真实浏览器成本身份为admin，成本隐藏及delivery-only边界由真实PG/API验证。非阻断“确认发货时间展示”建议只记入ADR，未扩大实现。Docker、其他浏览器、远程CI和生产环境 not_run/未核实；不宣称独立复核已通过。

权限浏览器辅助脚本首次由迁移角色读取data_directory被正确拒绝，随后改为在连接前核对临时PG进程标记及端口，不提升数据库角色权限；原输出保留。截图索引制作时排除AppleDouble读取项，未删除磁盘元数据。历史局限不改写。

本轮独立修复提交与后续登记提交见下方提交登记；最终HEAD由增量审查包清单固定，避免自引用。使用 `infra/package_task010_repair.py --implementation <修复提交> --destination "$REVIEW_ZIP"`，从最终干净commit导出完整源码、相对本轮审查基准的binary diff/文件清单/日志、全部历史与新增证据，验证逐文件Git blob、补丁重放、旧证据不变、秘密排除及解压SHA256SUMS。旧审查包不覆盖。
