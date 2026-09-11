# TASK-009 浏览器验收与复现

status: review_ready；本地实际操作，不代表独立审查通过。

## 环境

Codex In-app Browser，真实 HTTPS localhost:5173、真实 Keycloak 26.7.3、独立 PostgreSQL 17.11 与应用运行角色。使用既有可信证书；本轮没有修改系统信任，没有关闭证书或主机名验证。虚构身份 alice / Fictional-alice-17!。仅独立测试环境使用。

从仓库根准备锁定依赖（npm ci --ignore-scripts、uv sync --locked）；设置 `SILICON_TEST_PG_BIN="$PG17_HOME/bin"` 与 `SILICON_TEST_KEYCLOAK_HOME="$KEYCLOAK_HOME"`。PG/Keycloak下载与校验见 infra/build_test_postgres.py、infra/fetch_keycloak.py；Java21由 JAVA_HOME/PATH 提供。

浏览器需要合法取得且通过脚本哈希核对的 `.tools/visual/PingFang.ttc`，以及 `.tools/tls` 中被该浏览器正常信任的 localhost 证书和私钥。包内不含字体、私钥和软件安装包；缺失时在审查者环境自行准备，修改信任须另外取得授权，不能忽略TLS错误。

```bash
SILICON_BROWSER_ASSEMBLY=1 SILICON_BROWSER_INVENTORY=1 SILICON_BROWSER_CONTRACTS=1 SILICON_BROWSER_CATALOG=1 .venv/bin/python infra/browser_stack.py
```

栈自行创建随机端口临时PG、测试角色、IdP、文件根，迁移到0010并生成虚构已签约订单和库存。装配工单/预留/领料/完工并未预置；全部通过浏览器完成。前端视觉时钟固定2026-09-08，业务到期以服务端真实UTC计算。测试结束给该栈进程SIGTERM或Ctrl-C，等待 BROWSER_STACK_CLEANED；不得操作常驻数据库。

## 实际执行

1. 真实OIDC登录，选择虚构企业A，进入装配工单。选择 SO-CON-001（三台额度）、FINISHED、虚构用户甲、计划日期和虚构备注。
2. 双击创建，列表仅出现一张工单4b792f02；确认需求。主体PUB-H一件，memory两件，含于包件项仅展示不另领。
3. 分别预留主体1件、memory2件，24小时由服务器计算；页面显示固定层和剩余数量。
4. 本次数量1，先领memory一件再领主体，WIP85.00。尝试完工 FICTIONAL-ASM-009 被 MATERIALS_INCOMPLETE 拒绝，金额/库存未假成功。
5. 再领memory一件，确认完工：已领3件、WIP0、成品1；对账90.00=0.00+90.00。设备状态待检/待测试，未发货、未验收、未收款。
6. 刷新页面，设备查询输入部件SN H1，找到同一成品；打开后展示原客户/合同/订单/报价、同一inventory_unit、两个安装来源和成本90.00。新增来源入口真实读取库存移动，显示期初导入及两个成本层，不伪造采购订单。
7. 初次企业切换时登录已到期，页面清空并要求重新登录（browser-enterprise-b.txt）。重新登录后确认A设备存在，再切B，清单清空无A数据（browser-enterprise-b-verified.txt）。
8. 桌面1440×900、移动390×844实际截图。一次设置视口作用于组件标签而未改变业务页，保留 source-viewport-attempt-desktop.jpg 明确为桌面；关闭组件标签后核对 innerWidth/innerHeight=390/844，保存 source-mobile-verified.jpg。不把尝试截图冒称移动端。

## 组件证据与发现的修复

`/tests/assembly-component.html` 使用真实React+HTTP替身，2项passed：一次创建提交后响应丢失仍使用原key，显式新建生成第二操作身份；企业A成功响应被确定性延迟至B后才返回，不污染页面。保存 assembly-component-final.txt，不能替代上述真实接口流程或PG并发。

真实浏览器发现StrictMode初始加载被effect cleanup代次递增提前作废，第二effect又被busy跳过，页面为空。移除该错误cleanup，保留ContextTicket、请求取消和load代次检查；组件初始挂载现使用StrictMode。真实页面随后完成全流程。服务端duration_hours避免固定视觉Date产生已过期预约；对应PG红绿证据单列。

## 视觉继承与限制

对照 docs/design/demo-baseline.md 的原业务工作空间配色、侧栏、圆角卡片、排版与留白；使用现有CSS，没有新模板或改写原Demo。装配/设备/来源面板为本任务新增状态，原Demo没有同状态截图，不冒称原始基线。手机表格保持局部横向滚动，来源文本换行；两视口截图已目视检查。未引入新的服务器SVG或3D。

not_run：其他浏览器引擎、真实供应商资料、生产部署、远程CI、装配来源为采购收货的完整浏览器新购入闭环（本次使用期初材料；既有采购PG回归覆盖收货，来源接口沿用原权限）。无需重复TASK-008文件下载验收，历史not_run保持原样。没有新增附件引用。
