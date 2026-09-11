# TASK-011 浏览器验收记录

执行者本地验证，不代替独立审查。真实业务流程使用独立 PostgreSQL 17.11、Keycloak 26.7.3、API 和浏览器认可的 localhost HTTPS。没有关闭 TLS 校验或修改系统信任。环境启动和清理输出见 [日志](evidence/browser-stack.txt)，准备方法见 [实施说明](implementation.md)。

## 实际浏览器流程

2026-09-11，Codex In-app Browser。使用 alice / 虚构企业 A；所有数据均为虚构测试资料。

1. 从应用点击企业登录，真实 IdP 输入虚构身份后回调，选择 A。
2. 销售来源 CON-001 原金额 300：建立首期款 100 和尾款 200 草稿，分别明确确认。确认前不计应收，确认后未结 300，实际收款仍为 0。
3. 登记预收 150，流水 BROWSER-RC-001；确认后一次分配首期 100、尾款 50。第二笔 150、BROWSER-RC-002 继续核销尾款。应收结清，实际收款 300。
4. 撤销第一笔对尾款的 50 分配。未结和可退资金同时恢复 50，现金流仍为 300。
5. 按虚构商业减价依据追加尾款 -50，不更改原金额 200；再关联原资金登记退款草稿 50，确认实际退款后销售净实收 250。见 [销售退款页面](evidence/browser-sales-refund.txt)。本浏览器采用显式商业减价；实际实收退货关联由真实 PG/API 的 1000 场景覆盖，二者不混称。
6. 采购来源 PC-2ac9bd5e 原约定 500：建立并确认首期应付 200，登记并确认预付 250，核销 200，登记供应商实际退回剩余预付 50。见 [采购退款页面](evidence/browser-purchase-refund.txt)。
7. 刷新整页并重新进入资金工作台：未结应收/应付均 0；实收 300、实付 250、客户退款 50、供应商退款 50；净现金流 50。见 [刷新页面](evidence/browser-refreshed.txt)。
8. 进项发票人工登记：含税 100、净额 90、税额 11 被 `FIN_TAX_SUM_INVALID` 拒绝，见 [错误](evidence/browser-input-rejected.txt)；改税额为 10 后保存并确认。没有假定税率或税务验真。见 [发票](evidence/browser-invoice.txt)。
9. 企业切 B，无资金权限，A 的列表、金额和旧表单清空，明确 FORBIDDEN；切回 A 原记录仍在。见 [企业 B](evidence/browser-enterprise-b.txt)。
10. 正常应用退出并在 IdP 确认 Logout；再以 carol 只读身份进入 A。原 [订单详情](evidence/browser-no-finance-order.txt)、[已签合同](evidence/browser-no-finance-contract.txt)、[设备 DEL-0](evidence/browser-no-finance-device.txt) 可用。资金摘要单独提示未授权；[资金入口](evidence/browser-no-finance-denied.txt) 拒绝，没有资金金额。

任务书示例 1000、质保金释放、并发争用、真实退货关联及发票红字/作废主要由 PostgreSQL/API 测试覆盖，本浏览器没有声称逐一点击所有组合。

## React 交互（HTTP 替身，单独列明）

[测试页](../../../apps/web/tests/finance-component.html) 实际渲染 Finance / FinanceSummary，StrictMode 开启。页面结果见 [原始输出](evidence/finance-components.txt)。4 项通过：

- 同内容显式新建生成不同创建身份；创建成功但响应丢失后同 key 重试只有一条；第二条确认响应丢失重试仍复用该确认 key，不改变第一条。
- 确定性延迟成功创建响应，切换企业 / 卸载后不污染新页面。
- 获准摘要先可见，模拟撤权 403 后窗口重新激活清除旧金额，基础内容保留。
- 大金额和负值的分配后余额预览使用整数分，精确减法，非法输入不当零。

这些替身结果不是数据库或浏览器业务闭环证据；上文真实流程没有替换 fetch。

## 视觉对照及有意变化

对照 [原始 Demo](../../design/task003-visual-comparison.md) 中客户桌面与窄屏图，检查本次最终截图。保留原白侧栏、浅灰绿背景、深绿首卡、眉题、PingFang 字体、圆角卡片、控件与留白。资金页面没有原 Demo 中对应的完整资金事实状态，故为新增设计，而非像素复刻声明。

新增 13 个真实金额指标、四类记录入口、核销/逆向/发票历史和独立摘要；移动端两列指标、单列记录与表单，保留正常纵向滚动。修正资金记录列表受到原导航移动偏移规则影响的问题，金额小字在移动端保持显示。中间图片保留为 `intermediate-*`，不当作最终效果。

- [桌面 1440×900](evidence/finance-desktop.jpg)
- [移动 390×844](evidence/finance-mobile.jpg)
- [移动发票详情](evidence/finance-mobile-invoice.jpg)
- [无权限订单摘要](evidence/finance-permission-order.jpg)

截图为浏览器原始 JPEG，未编辑像素；文件扩展名已按实际 MIME 改为 jpg。工具输出位图实际 1425×891 / 375×812，CSS 视口 1440×900 / 390×844；[视口读取](evidence/viewport.json) 和 [图片清单](evidence/screenshots.json) 分别记录。后置首次尺寸读取误落到另一选中测试标签，保留 `intermediate-viewport.json`；关闭夹具标签后重新核验业务标签尺寸，没有以错误的测量结果作为通过依据。

前端视觉时钟固定 2026-09-08T04:00:00Z，字体及动画由既有 browser_stack/Vite 基线机制固定；认证/资金发生有效性仍使用后端真实时间，不冻结安全时钟。

## 过程中发现与修正

- StrictMode 的 setup/cleanup 重放与加载互斥相遇，首轮结果被错误丢弃；修正为实际卸载/上下文隔离与请求代次共同保护，组件夹具也开启 StrictMode。
- 开发会话短期到期时真实请求被 401 拒绝，见 [历史现场](evidence/browser-session-expired.txt)。资金页面现在对 401 清空受保护数据并交给主身份入口处理；经正常 OIDC 重新登录继续，没有延长会话或绕过认证。
- 移动列表导航偏移已限定在资金样式内修正，没有修改原 Demo。

其他浏览器、真实银行/税务服务、生产政策与部署未运行；不在本任务外扩。
