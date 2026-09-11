# TASK-012 实施与复现

从仓库根目录运行；使用原锁定依赖，不升级。Python3.12.7、Node24.15.0/npm11.12.1、PostgreSQL17.11、Java21.0.6、Keycloak26.7.3。依赖安装见README；验证不使用常驻数据库的bootstrap路径。

```bash
uv sync --locked
npm ci --ignore-scripts
# PG17_HOME / JAVA_HOME 可指向 Reviewer 自己的已核验安装。
# 缺少 PG 时可用固定源代码构建：
.venv/bin/python infra/build_test_postgres.py --prefix "$PWD/.tools/review-pg17"
export PG17_HOME="$PWD/.tools/review-pg17"
export SILICON_TEST_PG_BIN="$PG17_HOME/bin"
.venv/bin/python infra/fetch_keycloak.py --destination .tools/keycloak
export SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3"
.venv/bin/python -m pytest apps/api/tests -q
npm run typecheck
npm run build
node --test apps/web/tests/*.test.ts
.venv/bin/python infra/export_openapi.py
npm run api:types
.venv/bin/python infra/check_docs.py
```

PG/Keycloak准备脚本验证锁定下载校验值。PG夹具在临时目录、随机端口创建bootstrap/migrator/app角色；实际应用角色无superuser/BYPASSRLS。结束时仅停止并移除夹具目录。真实OIDC夹具创建并信任自己的测试CA，开启主机名校验，不修改系统信任。

## 领域实现

service模块使用已有稳定设备、库存层/移动和安装历史，未建设平行实物账。customer代管层不计自有成本；领用仍计库存，安装才消费，未用退回待检；安装更正追加原成本逆向。原完工安装、报价和交付快照保留。原件修复保持SN；供应商换新建立新SN并关联原RMA行，后续处置需明确所有权/成本依据。手工兼容确认保留UNKNOWN与核验依据，不伪称厂商验证。

服务收费为独立customer_service/supplier_repair来源；资金计划显式创建/确认，现金及核销沿用TASK011。人工/其他费用与材料成本字段权限分开。详细锁序、来源防改、幂等重放及状态见 [ADR-017](../../architecture/adr/ADR-017.md)。

## 迁移

0015_service在0014上增加售后表、FORCE RLS和不可变约束，给既有安装增加稳定slot_id和可选service_work_id。资金source_id生成表达式兼容合同和服务来源，原记录未改写。空新增域可以降级到0014并还原库存状态/移动类型约束、表达式及权限；有售后事实时拒绝降级并保持事务回滚。实际旧库升级和阻止降级测试在test_service.py；不可将丢弃业务数据视为回滚手段。生产恢复需另行制定备份恢复流程，本任务未部署。

## 浏览器

需合法可用的固定字体 `.tools/visual/PingFang.ttc`（browser_stack验证哈希），以及已可信的localhost证书 `.tools/tls/localhost.crt` 和私钥。包内不含字体、私钥或安装包。缺失时在自己的开发环境准备；系统信任变更须另获授权，禁止关闭TLS或忽略证书错误。

```bash
SILICON_BROWSER_SERVICE=1 .venv/bin/python infra/browser_stack.py
```

打开 `https://localhost:5173`，虚构用户alice，密码Fictional-alice-17!。真实Keycloak登录选择企业A；B为管理员但无业务前置。前置通过已有API产生订单、3台完工设备、其中1台发货、供应商及虚构期初备件；没有售后、RMA、费用、资金或核销事实。选择实际下拉框中的已发货SN，不依赖随机UUID或固定设备排序。`infra/service_examples.py`可重复准备。

与本机实际操作一致的步骤见 [浏览器验收](browser-acceptance.md)。`/tests/service-component.html`为实际React加HTTP替身，单独记录。浏览器栈与完整OIDC测试串行，避免Keycloak默认端口冲突。Ctrl-C/SIGTERM清理栈所拥有进程、PG与临时文件；确认BROWSER_STACK_CLEANED。实际执行中曾仅重载临时API保留已创建事实，未修改数据库业务数据或证书信任。
