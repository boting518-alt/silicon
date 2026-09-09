# Demo 源码与视觉基线

source_status: available
visual_baseline: captured_TASK-003
browser_testing: TASK-003 已执行，见 [视觉对照](task003-visual-comparison.md)；以下盘点段落保留 TASK-000 当时的静态验证范围。

## 来源与本次核验

2026-09-09 使用同账号 Sites get_site、list_site_versions 获取项目和版本，再通过官方短期凭据克隆独立参考仓库。仅执行读取，未 push、保存版本、修改访问或部署。Sites 访问需授权，不假定公开 URL 匿名可用。

| Demo | 页面 | 项目身份 | 保存版本/源码 HEAD | 相对参考目录 |
|---|---|---|---|---|
| 配置报价 | https://silicon-server-studio.huiquan003.chatgpt.site | appgprj_6a9e678b54f48191af4637dae884188f | v1 / 65e465092f0afc5519ed1a60214697fbf6a2f2a5 | ../silicon-quote-reference |
| 业务工作空间 | https://silicon-contract-studio.huiquan003.chatgpt.site | appgprj_6a9f6c67e8dc8191a7dd9c3aca8604c1 | v4 / 09e204ec99a74a821f35d6799b9e6e00c0c8393d | ../silicon-workspace-reference |

两个源码 HEAD、Sites 最新保存版本 provenance 与指南完全一致，未发现更新差异；hosting.json 各自 project_id 正确且 static.directory=dist。克隆为 detached HEAD，生产仓库未包含其源码、远程或部署身份。[文件 hash 清单](source-manifest.json)记录 4+8 个已跟踪文件，每个文件与对应 Git blob 字节相同，已跟踪工作树干净。OS 生成的 ._* 不是源码，Git pack 附属文件有告警，见待定事项 OD-018。

## 页面、文件与交互清单

| 来源/文件 | 本次静态读取证据 | 保留与迁移边界 |
|---|---|---|
| 报价 dist/index.html | 单页，引用 style.css 和 app.js | 页头、三栏工作区、报价对话框 |
| 报价 dist/style.css | .workspace 三栏，.visual 圆角 18px，.quote 桌面 sticky；1150/720px 响应断点 | 保留 CSS 几何及窄屏堆叠意图 |
| 报价 dist/app.js:1–12 | catalog、页面 state、折扣初始化、subtotal/power/issues | 目录/价格/规则改为 API，不复用 Number 为权威计价 |
| 报价 dist/app.js:13–19 | renderComponents/renderQuote/draw、SVG 部件、数量/型号选择、展开、必选/可选标签 | ServerDiagram、QuoteSummary；SVG 部件选择联动，不引入 WebGL |
| 工作空间 dist/index.html | 12 个 data-view；脚本顺序 app→land→analytics→operations→business | 保留侧栏/页头与各页面意图；迁移时显式模块依赖 |
| 工作空间 dist/app.js | contracts/devices、renderList/renderDetail、asset/modal | 合同详情、设备档案和弹窗；以后逐页接 API |
| 工作空间 dist/analytics.js:10,21 | customers=contracts.map；包装 legacyRender；筛选、客户列表/详情、地图 | 客户独立模型，保留搜索/筛选/详情交互 |
| 工作空间 dist/operations.js:2,42 | 固定演示日和 taxDemo；包装 opsLegacyRender；采购、库存、预留/释放、收付款模拟 | 台账和事务后端化，纯页面模拟不可成为正式成功 |
| 工作空间 dist/business.js:4,13,19 | deliverySteps、proposalCalc、包装 bizBaseRender；报价/审批/交付/售后/续保扩容 | 费用来源、版本审批、换件历史与库存同事务 |
| 工作空间 dist/land.js | 静态地图数据 | 只作为视觉参考，坐标系/素材许可生产化前核实 |
| 工作空间 dist/style.css | .sidebar 固定宽 215px，.metrics 四列，面板细边框 | WorkspaceShell、PageHeading、MetricCard、ActionCard |
| 两套 .openai/hosting.json | 独立身份与 dist 静态托管 | 不复制到生产工程 |

工作空间导航：desk（业务驾驶舱）、deal（报价与利润）、fulfillment（交付）、support（售后）、growth（续保扩容）、overview（经营总览）、customers（客户）、contracts（合同）、devices（设备）、purchasing（采购）、inventory（库存）、turnover（周转）。这些是已读取导航和函数，不代表本次点选测试通过。

## CSS token 基线

| 语义 token 建议 | 源值 | 证据 |
|---|---|---|
| --color-background | #f5f7f8 | 两份 style.css :root |
| --color-text | #202e2d | 两份 :root |
| --color-primary-workspace | #254f3d | 工作空间 .primary |
| --color-primary-quote | #214f3c | 报价 .primary；是相对指南补充的实际差异 |
| --color-feature-surface | #244d3e | 工作空间 style.css |
| --color-selected / --color-soft-surface | #eaf3ed / #edf3ef | 工作空间选中区域 / 报价 .visual |
| --color-border | #e0e7e2 | 工作空间 .metric |
| --font-family | Inter, PingFang SC, Microsoft YaHei, sans-serif | 两份 :root；字体降级需固定 |
| --radius-button / --radius-card / --radius-panel | 8px / 13px / 18px | 按钮、工作空间指标、报价面板；并非所有元素唯一圆角 |

以上为源码读取结果，未做对比度或截图验收。保留留白、浅色面板、深绿强调和中英小标题，同时在迁移时验证焦点、弹窗与窄屏可读性。

## 演示数据和假业务规则

- 全局数组/页面变量与后续脚本包装 render。静态检索未发现 fetch、XMLHttpRequest、localStorage 或 IndexedDB 持久化入口；刷新恢复样例是源码推断，尚未浏览器复测。
- 报价 SILICON95、GPU 插槽和功耗×1.2 仅为示例；主机示例不含电源，生产须逐 SKU 记录 included components。
- operations.js:2 的 1.13 不是统一税率；business.js:13 的成本、8000 费用、20% 阈值和 :16 的 1.8% 直接费用只能作为虚构测试样例。
- analytics.js:10 的一合同一客户不满足生产关系；business.js:4 的串联开票不满足独立单据状态。
- 两套报价逻辑必须最终统一到后端服务；未知成本/兼容不能当零/通过。原页面的审批、开票、收付款和服务操作是模拟。

## UI 迁移前依赖

1. 保持两份固定 commit 参考源码可读；换机器按照运行手册重新获取，不依赖本机绝对路径。不可用时改标 demo_source_pending，仅阻塞 UI 迁移。
2. TASK-002 审查通过，客户契约/权限已明确；原 DOM 与 React 不同时管理同一子树。
3. TASK-003 开始时获得浏览器测试授权；固定 1440×900、390×844，时钟、字体与虚构数据，关闭随机动画；先取原 Demo 截图，再取迁移对照。
4. 明确未接入页面标识、加载/失败/空状态、键盘和弹窗行为；截图差异须人工解释确认，不能默认整体接受新基线。
5. 在健康文件系统核验参考仓库 pack 告警；地图数据的来源、版本、许可及坐标系在地图生产化前补齐。

未重绘 UI、未使用默认模板、未做浏览器视觉验收。获取和启动方法见 [运行手册](../runbooks/demo-sources.md)。


## TASK-003 增量

2026-09-10 按 OD-018 独立克隆并核验全部 12 个 blob/文件 hash、项目身份和完整 fsck，原参考仓库未修改。原工作空间客户列表/详情与报价首页已取得两视口截图；迁移范围及差异见 [视觉对照](task003-visual-comparison.md)。TASK-000 的 not_run 为历史结论，不改写为当时已通过。地图许可仍待其生产化前核实。
