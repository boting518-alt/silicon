# TASK-003 视觉基线与有意变化

状态：captured，等待独立视觉复核。执行者已逐图检查，不自行确认最终 UI 验收通过。

## 固定输入

原工作空间 `09e204ec99a74a821f35d6799b9e6e00c0c8393d`（8 文件）；原报价 `65e465092f0afc5519ed1a60214697fbf6a2f2a5`（4 文件）。迁移前先从原只读副本取得客户列表/详情截图，报价只作来源盘点、不迁移。OD-018 采用新的无硬链接完整克隆，在健康临时目录 fsck 与逐 blob/hash 核验，原库及磁盘元数据不变。原始核验见 [首次](../tasks/TASK-003/evidence/demo-source-check.json) 和 [最终重核验](../tasks/TASK-003/evidence/demo-source-final-check.json)。

时钟固定为 2026-09-08T04:00:00Z；中文日期显示 2026.09.08。字体固定 PingFang.ttc，SHA-256 `6bccdb1a967b2ae7e856927eb559591b2ce05656b0d4ad2764b9c9429f12c0b7`，由本机合法字体文件提供，不提交字体。所有动画、过渡和文本光标关闭；原 Demo Math.random 固定种子 7，产品没有依赖 Math.random 的视觉输出。视口为 1440×900、390×844。字体文件不存在时失败，不回退不同字体。

原工作空间使用源码内 2026 年 7 位虚构成交客户，源数据/HTML 不修改。迁移端使用 `infra/browser_stack.py` 明确的独立客户夹具：对应 7 个名称/地区，每户 2 联系人/1 项目，建档时间固定并按编号排序；A 7 户、B 空。它是测试夹具，不把原合同数组用于产品客户身份。后端当前时钟和认证时效不冻结，产品显示时钟只由开发视觉插件控制。

所有截图为浏览器原始 JPEG；没有拼图、缩放或修改像素。实际尺寸与 hash 见 [截图清单](../tasks/TASK-003/evidence/screenshot-manifest.json)。早期截图视口设置落在非目标标签、以及将 JPEG 标为 png 的采集问题已纠正；没有既有像素快照断言被批量更新或绕过。

## 同视口对照

| 状态 | 原始基线 | 迁移后 |
|---|---|---|
| 桌面客户列表 | [1440×900](../tasks/TASK-003/evidence/screenshots/original-customers-1440.jpg) | [1440×900](../tasks/TASK-003/evidence/screenshots/migrated-customers-1440.jpg) |
| 手机客户列表 | [390×844](../tasks/TASK-003/evidence/screenshots/original-customers-390.jpg) | [390×844](../tasks/TASK-003/evidence/screenshots/migrated-customers-390.jpg) |
| 桌面客户详情 | [1440×900](../tasks/TASK-003/evidence/screenshots/original-detail-1440.jpg) | [1440×900](../tasks/TASK-003/evidence/screenshots/migrated-detail-1440.jpg) |
| 手机客户详情 | [390×844](../tasks/TASK-003/evidence/screenshots/original-detail-390.jpg) | [390×844](../tasks/TASK-003/evidence/screenshots/migrated-detail-390.jpg) |
| 报价首页（仅盘点） | [1440×900](../tasks/TASK-003/evidence/screenshots/original-quote-1440.jpg) / [390×844](../tasks/TASK-003/evidence/screenshots/original-quote-390.jpg) | 未迁移，没有伪造对应页面 |

## 差异逐项说明

| 元素 | 保留内容 | 有意变化/待复核判断 |
|---|---|---|
| 桌面壳 | 215px 白侧栏、77px 页头、浅灰绿背景、原标识字符、12 导航顺序、原标题和英文眉题、主区留白 | 非客户导航禁用并增加“未启用”；原虚构身份换成已登录用户，页头增加企业选择/退出 |
| 四指标卡 | 原四列/手机两列、深绿首卡、边框圆角与字号层级 | 合同签约额/设备数换成真实客户/联系人/项目/地区计数；不展示未实现财务与设备数据 |
| 筛选与表格 | 原浅色搜索、细分隔线、客户强调色、档案入口 | 去除基于合同的日期/销售/行业下拉；提供名称/编号/城市/联系人搜索与稳定分页。新增客户按钮；金额/设备列替换联系人/项目，建档者与内部责任分工分开 |
| 固定数据 | 相同七个客户名称及地区用于几何对照 | 原客户编号含跳号，迁移夹具 CUS-001～007；原客户经理/售后人员不冒充真实 membership，改为虚构用户甲；当前阶段统一稳定合作，其他状态在编辑及自动测试覆盖 |
| 详情 | 原生 dialog、760px 最大宽度/94% 手机宽度、90vh、绿色 hero、模糊遮罩、关闭按钮 | 原合同派生摘要与仅会话跟进表单换为持久客户聚合，增加联系人/项目/地点/内部责任与角色历史。正文增加内边距、底部操作保持可达；内容更长可滚动 |
| 窄屏导航 | 原同一壳和按钮风格 | 原图导航逐行且会撑宽；本次修复为视口内紧凑换行，保留顺序，给企业操作与客户内容留空间。此为有意适配变化，非宣称像素相同 |
| 窄屏表格 | 横向表格容器 | 增加可聚焦 region 和明确无障碍名称，键盘可横向滚动；页面宽度保持 390 |
| 新建/编辑/错误 | 使用原输入、圆角与深绿操作风格 | 原 Demo 无独立新建客户、多联系人/项目聚合编辑、版本冲突、权限/登录状态。以下均为新设计，不能冒称原始基线 |

新增状态证据：[新建表单](../tasks/TASK-003/evidence/screenshots/migrated-create-390.jpg)、[重复编号](../tasks/TASK-003/evidence/screenshots/browser-duplicate-error-390.jpg)、[版本冲突](../tasks/TASK-003/evidence/screenshots/browser-version-conflict-390.jpg)、[持久编辑](../tasks/TASK-003/evidence/screenshots/browser-persisted-edit-1440.jpg)、[空企业](../tasks/TASK-003/evidence/screenshots/browser-tenant-b-390.jpg)、[真实 IdP 登录](../tasks/TASK-003/evidence/screenshots/browser-keycloak-login-390.jpg)、[退出保护](../tasks/TASK-003/evidence/screenshots/browser-logged-out-390.jpg)。

本次没有截图自动像素阈值“全部通过”的结论。原数据语义与新 CRM 不同，上述变化必须独立复核；字体平台差异、其他浏览器、其他视口尚未验证。复现服务、信任前提和操作记录见 [浏览器验收](../tasks/TASK-003/browser-acceptance.md)。地图素材许可仍是未来地图生产化前的依赖，未纳入本次产品。
