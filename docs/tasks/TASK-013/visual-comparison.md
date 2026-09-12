# TASK-013 有意视觉变化

沿用[原Demo基线](../../design/demo-baseline.md)、[TASK003迁移对照](../../design/task003-visual-comparison.md)和既有页面：硅屿深绿/淡绿、灰白背景、字体、圆角卡片、留白、侧栏及移动端折行导航不变。没有编辑原Demo或重新套模板。

新增集中筛选器、签约金额深绿主卡、独立经营/资金/异常区域、指标口径弹窗和可回到原业务的贡献明细。签约、实收、净交付分开，不称收入或利润。移动端筛选两列、卡片自适应、弹窗内表格可滚动，不横向堆叠整屏卡片。

原Demo不存在这些真实账龄、权限和历史状态，属于本轮新设计，不能声称逐像素原始基线。省级方格示意和真实地区表使用同一数据；并非行政边界地图，也不是客户精确位置。地图来源见[地区说明](../../analytics/regions-source.md)。既有tokens和字体被复用，未更新历史截图来消除差异。

overview-final-1440、overview-390、report-full-1440、mobile-verified-390为本轮页面；region-drill、original-contract、receivable-age、historical-stock-age、ccc-explanation与nonfinance系列展示交互状态。initial-date-input及最初overview为过程证据，最终输入样式见overview-final。完整截图清单记录实际尺寸和SHA256。

截图实际编码为JPEG，已按原字节改正扩展名，没有重新压缩或改图。部分中间截图名含390但实际为桌面，清单按实际像素标注；最终移动全页是mobile-verified-390.jpg，浏览器实测innerWidth390/innerHeight844。

全页截图是浏览器工具拼接产物，部分长图存在重复片段；不据此声称逐像素无差异。视口布局以overview、drill、nonfinance单视口截图与对应真实DOM为准，地图交互数值另外由实际点击记录核验。
