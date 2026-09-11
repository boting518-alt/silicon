# TASK-011 R1 浏览器与组件证据

真实浏览器使用现有可信 HTTPS、独立 PG17.11 / Keycloak26.7.3 / API，虚构 alice 选择企业 A；未修改证书信任，不关闭校验。启动命令同原实施说明的 SILICON_BROWSER_FINANCE=1、SILICON_BROWSER_CONTRACTS=1、SILICON_BROWSER_CATALOG=1，另外指定 SILICON_TEST_PG_BIN 与 SILICON_TEST_KEYCLOAK_HOME。本次未预填资金事实。

实际操作：来源 CON-001（原额度300）→ 建立 R1 误减恢复验证计划300并确认 → 误减-200，显示有效100 → 填写原因及 R1-CORRECTION 依据，点击原调整旁“撤销误减额” → 有效300，原调整仍为-200，关联更正为+200 → 刷新页面重新打开，金额及关系保持。没有修改来源额度。1000→800→1000 的应收/应付场景分别由真实 PG/API 测试覆盖，未冒称本次浏览器使用1000合同。

证据：[误减](browser-reduced.txt)、[更正](browser-corrected.txt)、[刷新](browser-refreshed.txt)。已更正后不再提供重复更正按钮。页面说明恢复不撤销退款或实物退货，后者在真实 PG/API 回归有实际退货、退款后更正覆盖。

[桌面](desktop.jpg) CSS视口1440×900，[移动](mobile.jpg) CSS视口390×844；截图工具输出像素1425×891和375×812。截图定位到原金额及历史更正区域。保持原卡片、字体、侧栏与配色，只新增原调整编号、更正关系和明确入口。初次全页截图发生工具拼接重复，保留 intermediate-*-full.jpg 作为非验收中间产物；最终使用原生视口截图，未修图消除问题。

实际 React + HTTP 替身页 `/tests/finance-component.html` 5项通过，见 [组件结果](components.txt)：新增误减入口、原因/依据、响应丢失后同键重试一次、原历史保留及按钮退出；原新建幂等、上下文迟到成功拒绝、撤权清空和精确金额测试保留。该测试与上方真实 IdP/PG 浏览器操作明确分开。

独立浏览器栈已 SIGTERM 关闭，见 browser-stack.txt 的 BROWSER_STACK_CLEANED；仅清理本轮进程及临时集群。完整后台回归首次与浏览器 IdP 并行启动导致默认8080端口占用；对应 backend.txt 与 oidc-startup-conflict.txt 保留，随后串行复跑，结果以 validation.json 为准。其他浏览器、容器及生产操作未运行。

日志如包含终端行尾空白，同名 `.raw.gz` 保留逐字节原输出；可读 `.txt` 仅整理行尾空白。旧证据目录中的原日志不变。
