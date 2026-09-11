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
