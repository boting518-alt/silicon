# TASK-005 报价视觉继承与有意变化

状态：captured / review_ready，执行者检查可用性，最终视觉认可由独立 Reviewer 决定。

来源：报价 Demo `65e465092f0afc5519ed1a60214697fbf6a2f2a5`，工作空间 `09e204ec99a74a821f35d6799b9e6e00c0c8393d`。本轮再次核对提交 blob 与参考副本字节，4+8 文件一致，记录于 [demo-source.json](../tasks/TASK-005/evidence/demo-source.json)；未改 Demo、未清理参考磁盘元数据。

| 内容 | 原始基线 | 本轮 |
|---|---|---|
| 桌面报价 | [1440×900](../tasks/TASK-003/evidence/screenshots/original-quote-1440.jpg) | [当前草稿](../tasks/TASK-005/evidence/quote-desktop-1440.jpg)、[金额来源](../tasks/TASK-005/evidence/quote-desktop-summary-1440.jpg) |
| 手机报价 | [390×844](../tasks/TASK-003/evidence/screenshots/original-quote-390.jpg) | [关联入口](../tasks/TASK-005/evidence/quote-mobile-390.jpg)、[SVG 展开](../tasks/TASK-005/evidence/quote-mobile-svg-390.jpg)、[总额](../tasks/TASK-005/evidence/quote-mobile-summary-390.jpg)、[检查范围](../tasks/TASK-005/evidence/quote-mobile-checks-390.jpg) |
| 异常联动 | 原 Demo 无对应真实状态 | [PSU 警告](../tasks/TASK-005/evidence/quote-desktop-warning-1440.jpg) |

保留原 box/draw 等距 SVG 几何、面色、部件布局与展开位移，改写为 React 事件绑定；保留浅灰绿背景、绿色服务器卡、白配置/金额卡、标题与眉题、留白/圆角。SVG 不携带 Demo 商品价格/优惠/PDF逻辑。不是新后台模板，也不是重画服务器样式。

有意变化：

- 报价三栏进入已有 215px 业务侧栏壳，顶部增加客户、项目、名称和已保存草稿选择，原 Atlas G4/4U 改为“服务器结构”，不伪造真实型号。
- 配置来源为已发布 BOM 与当前 SKU；原必选/扩展 tabs 改为可见字段序列，原 +/- 改为原生数量输入；included 独立勾选，根基价与替换费用说明明确。此是最小操作壳，不是完整配置器。
- 原人民币整数展示改为精确两位 CNY、每行来源/版本/期间；增加已保存金额、当前试算、优惠上限、缺价和 UNKNOWN 的说明，因此卡片更长，桌面底部与手机需滚动。
- 未选部件仍以虚线/淡色显示位置；必选缺失与停用/规则异常有状态名称和橙色。PASS 绿、UNKNOWN 灰、WARN/BLOCK 暖色，颜色不是唯一提示。
- 原独立报价 Demo 无真实身份、客户选择、版本冲突或企业隔离，新增状态不冒称原始基线。工作空间侧栏和认证入口沿用 TASK-003/004。
- 手机沿用单列，关联字段位于 SVG 前，导航沿用工作空间紧凑样式。实测页面宽度为 390，没有新增横向溢出。

原截图和本轮虚构配置不同，不主张像素一致。本轮例子为 CPU1/GPU2/内存4/系统盘1/包含电源2，v2整机2；实际价格由独立 PG 种子计算。固定 PingFang 字体、页面显示日期 2026.09.08、动画停用沿用既有插件；服务端计价时刻真实运行，未冻结认证时效。首轮移动总额截图早于 UNKNOWN 颜色调整但文字正确；最终 quote-mobile-checks-390.jpg 记录调整后的最终样式，旧截图没有被用作像素阈值基线。

[截图尺寸/校验清单](../tasks/TASK-005/evidence/screenshot-manifest.json) 与 [交互记录](../tasks/TASK-005/browser-acceptance.md) 一起供审查。其他字体/浏览器、真实供应商参数和正式销售状态未验证。
