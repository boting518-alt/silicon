# TASK-011 执行结果

status: review_ready

本轮完成应收应付、资金登记、核销、退款、质保金和发票登记的经营子台账。等待独立 Reviewer，不自行 accepted，不开始 TASK-012。没有外部转账、税务开票或部署。

## 提交来源

- 已验收基线：`b6ca2feab718614d407897e1d0b3762633ba1fe3`。
- 单独验收交接：`d136c1b80f78d41df174446174a8b0fb444a2cb6`。
- 实施前领域决策：`0a65225e9668784915e3c5bd8f3c2dc255590ef1`。
- 实现提交及收尾信息在下方提交登记追加；最终 HEAD 由审查包 `REVIEW_MANIFEST.md` 与 `PACKAGE_CHECKS.json` 精确记录，源码从该提交导出，避免文档自引用提交号。
- 原 [TASK-010 增量报告](../../reviews/TASK-010-b6ca2fe-review.md) 原样归档；旧结果、首次报告及历史验证限制不改写。

## 实现与不变量

- 沿既有合同、订单、客户、供应商建立显式确认的应收应付；冻结付款节点导入只生成草稿。金额上限、节点去重、来源调整与商业依据均由后端校验。
- 收付款区分草稿与确认，预收预付和未分配金额独立展示。多对多核销、部分核销和逆向在同一事务内完成；退款以原资金为来源并限制可退余额。实际销售退货可以关联商业应收减少，不使用库存成本计算退款。
- 质保金包含在原额度中，明确释放和到期，不自动虚构逾期。发票登记支持来源分摊、金额/税额校验、红字及作废；不改变现金余额。
- 金额使用 Decimal / NUMERIC，API 为十进制字符串，拒绝浮点输入、过大金额与多于两位小数。未知金额不当零，无默认真实税率。
- 资金权限独立于库存成本。合同/订单金融摘要独立授权，403 清除资金但保留基础业务页面；成本不可见不会自动阻止有独立授权的资金功能。
- 延续预期企业/会话校验、RLS、来源可见性和撤权后重放保护。内部命令包含操作与来源作用域；发票来源集合参与作用域，不串用不同来源同键。
- [ADR-016](../../architecture/adr/ADR-016.md) 记录共享/排他资金锁及既有锁序，完整读取在共享锁内完成。真实并发测试明确同步点并观察写方等待，避免混合聚合。
- 新增 `0013_finance`，旧报价、合同、库存及设备事实不被重写。空资金表可降级；非空历史/命令拒绝降级，不能靠删除事实恢复。
- 草稿修正采用取消重建；确认后的事实用追加逆向/调整。前端延续原 token、侧栏和卡片，资金页面属于明确新增设计。

完整模型、事务与恢复限制见 [实施说明](implementation.md)、[数据模型](../../architecture/data-model.md) 和 [API 约定](../../architecture/api-conventions.md)。

## 实际验证

| 检查 | 实际结果 | 原始证据 |
| --- | --- | --- |
| 完整后端，隔离 PG/真实 OIDC 集成 | 237 passed，14 warnings，242.17 秒 | [最终日志](evidence/backend-final.txt) |
| 资金定向真实 PG/API | 14 passed，3 warnings，29.48 秒；最终全套含最后补充断言 | [定向日志](evidence/finance-final.txt) |
| 前端 Node | 19 passed | [日志](evidence/frontend-node.txt) |
| 实际 React 组件，HTTP 替身 | 4 passed | [组件证据](evidence/finance-components.txt) |
| 类型检查 / 构建 | passed | [类型](evidence/frontend-typecheck.txt)、[构建](evidence/frontend-build-final.txt) |
| OpenAPI / 客户端再次生成一致性 | 两份生成文件 SHA-256 均未变化 | [生成日志](evidence/contract-generation.txt) |
| 文档 / 差异空白检查 | passed | [文档](evidence/docs-final.txt)、[差异](evidence/diff-check.txt) |
| 真实浏览器业务闭环及两视口 | passed，边界见下 | [验收记录](browser-acceptance.md) |

定向测试覆盖额度并发、同一资金/计划争用、失败原子回滚、重复外部凭证、响应丢失重放、多来源同键隔离、退款和逆向、发票红字/作废、真实销售退货、1000 元含质保金示例、源数据不可变、权限撤销、企业错配、非 owner 应用角色 RLS、多表一致读取，以及空库/前序数据升级和受限降级。定向 14 项包含在完整 237 项内，不重复计数。警告原样保留，未通过屏蔽消除。

红绿与中间失败保留：初始接口不存在的 [404 红测](evidence/plan-red.txt)、[触发器失败](evidence/plan-trigger-failure.txt)、[首项绿测](evidence/plan-green.txt)、[第一轮扩展结果](evidence/finance-first.txt)、[夹具修正过程](evidence/finance-expanded.txt)。后者测试监听引擎/缺少日期的错误明确属于准备错误，不冒称业务缺陷复现。

React 覆盖 StrictMode 初始请求、显式新建相同内容的独立身份、创建及确认响应丢失后的同键重放、迟到成功响应不污染新上下文、资金摘要撤权清空、整数分计算。不是仅验证请求头转发，也不替代真实数据库证据。

## 浏览器与视觉

使用独立 PostgreSQL / Keycloak / API / 文件目录、虚构 alice 和 carol，可信 HTTPS；未更改系统信任或放松 TLS。实际完成：两笔应收 → 两笔收款 → 多节点部分核销 → 逆向 → 商业调整 → 客户退款；应付 → 预付 → 核销 → 供应商退款；刷新后金额持久化；发票税额错误拒绝后正确登记；企业切换和无资金权限用户的基础合同/订单/设备查询。

保留 [桌面](evidence/finance-desktop.jpg)、[移动资金](evidence/finance-mobile.jpg)、[移动发票](evidence/finance-mobile-invoice.jpg)、[基础订单权限](evidence/finance-permission-order.jpg)；CSS 视口 1440×900、390×844，工具截图像素尺寸另列于 [截图校验清单](evidence/screenshots.json) 和 [视口实测](evidence/viewport.json)。已与 TASK-003 原 Demo 基线对照，新增资金卡片有意变化及中间移动布局修正见验收记录。

过程中的会话过期被真实拒绝，未延长会话逃避；重新登录继续验证。保留 [过期证据](evidence/browser-session-expired.txt)。隔离栈停止并输出 `BROWSER_STACK_CLEANED`，不停止或写入常驻 PostgreSQL。

## 限制与复现

- 远程 CI **未核实**；本地通过不代表独立审查通过。
- Docker、其他浏览器引擎、生产和真实银行/税务集成为 **not_run**，不在本轮环境或范围。
- 发票红字/作废与 1000 元质保金示例完成真实 PG/API；未另做浏览器全路径，不能声称每个后端分支都有浏览器证据。
- 本期发票证据为档案编号登记，不是新增上传、税务验真或正式发票生成；草稿修复取消重建。
- 资金写路径使用租户级串行锁；未做大规模吞吐量测试。不等同于生产上线就绪。
- 复现需安装锁定依赖、PG17、Java21、Keycloak26.7.3；浏览器另外需要合法固定字体和可信 localhost 证书。包不含私钥、字体安装或数据库目录。准确环境见 [environment.json](evidence/environment.json)，准备、创建与清理见 [实施说明](implementation.md)。

全部准确命令、结果和 not_run 见 [validation.json](evidence/validation.json)。变更路径见 [changed-files.txt](changed-files.txt)。审查包由 `infra/package_task011_review.py` 从最终提交完整导出，并验证文件哈希、增量补丁重放及历史证据不变。
