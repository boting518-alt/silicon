# TASK-011 实施与复现说明

本任务遵循 [任务书](task.md) 和 [ADR-016](../../architecture/adr/ADR-016.md)。TASK-010 的历史结果和审查限制保持原样；本任务并不重新验收前序。

## 领域及页面

- 应收应付以签约销售合同 / 有效采购合同为统一额度来源；订单沿用原 ID。导入冻结付款节点只建立草稿，需要逐项确认。
- 草稿内容需修正时取消后重建。已确认金额、资金、发票不改写原内容；追加调整 / 核销逆向 / 退款逆向 / 作废记录。
- 客户收款、供应商付款及退款是人工登记。没有银行请求，不代表转账、税务开票或验真。
- 质保金留在原合同额度内；未释放不显示虚构到期或逾期。释放记录明确到期日，不增加金额。
- 发票只有内部档案编号引用；本期未新增文件上传和公开链接，因此不引入文件清理引用路径。
- 来源金额调整需明确商业依据，保留原合同金额。采购含税口径未确认时仍标注原商业行口径；不使用库存成本或默认税率。
- 资金工作台新增原设计 token 下的指标卡、列表、表单及历史记录。原 Demo 没有对应完整资金状态，这些为有意新增页面，不冒称原截图。
- 合同、订单的资金摘要独立请求；403 清除摘要，保留基础内容。窗口重新激活重新检查；企业上下文变化丢弃迟到成功响应。

## 准备与执行（从仓库根目录）

沿用根 README 的 Python 3.12 / Node 24.15.0 / npm 11 锁定安装步骤。本任务无依赖升级。PostgreSQL 17.11；Java 21；Keycloak 26.7.3。Keycloak 使用 `infra/fetch_keycloak.py` 下载及哈希验证；不打包安装目录。

```sh
export SILICON_TEST_PG_BIN="$PG17_HOME/bin"
export SILICON_TEST_KEYCLOAK_HOME="$KEYCLOAK_HOME"
.venv/bin/python -m pytest apps/api/tests/test_finance.py -q
.venv/bin/python -m pytest apps/api/tests -q
.venv/bin/python infra/export_openapi.py
npm run api:types
npm run typecheck
npm run build
node --test apps/web/tests/*.test.ts
.venv/bin/python infra/check_docs.py
git diff --check
```

数据库夹具从空临时目录初始化独立集群、随机端口，仅授权 `silicon_app` 非 owner / 非 superuser / 非 BYPASSRLS 运行应用查询。迁移用独立 migrator。测试退出关闭并删除该临时集群，不连接常驻数据库。OIDC 集成另外生成并信任测试 CA，不关闭主机名校验。

```sh
SILICON_BROWSER_FINANCE=1 SILICON_BROWSER_CONTRACTS=1 SILICON_BROWSER_CATALOG=1 \
  .venv/bin/python infra/browser_stack.py
```

浏览器栈从测试夹具创建隔离 PG、Keycloak、API、Vite 和文件目录，前置虚构销售合同/订单/设备、采购合同/订单通过原业务 API 建立；不预填资金事实。访问 `https://localhost:5173`，使用虚构 alice / `Fictional-alice-17!` 登录选择企业 A。虚构 carol / `Fictional-carol-17!` 为只读用户，无资金权限。企业 B 为空。停止本栈进程会清理其临时集群和进程。

须按 [浏览器基线准备](../../design/demo-baseline.md) 提供已信任 localhost 证书、私钥及固定字体到 `.tools`。本任务不修改系统信任，不把私钥纳入审查包。Reviewer 环境如无可信证书，需其环境所有者先准备；不可关闭 TLS 校验绕过。

组件测试页 `https://localhost:5173/tests/finance-component.html` 运行实际 React 与 HTTP 替身，只验证页面事件、重试与迟到响应，不能替代真实浏览器业务验收。

## 迁移及恢复

`0013_finance` 增加资金表、权限、RLS 和冻结触发器；不重建旧表或改写报价、合同、库存数据。运行 `infra/migrate.py upgrade head` / `current`，使用明确选定的 `MIGRATION_DATABASE_URL`。不得拿常驻数据库做测试。

空资金表可以降到 `0012_delivery`。有任意资金历史或命令记录时降级拒绝并事务回滚；不得清空表强制降级。部署恢复需使用已验证备份恢复或前向迁移，本任务不执行部署或生产恢复。

## 已发现并修正的实现问题

- 首条测试在不存在的资金接口得到 404，见 `evidence/plan-red.txt`。
- 第一轮冻结触发器把 BEFORE UPDATE 尚未重算的生成列纳入比较，错误拒绝确认；改为比较实际源列，见 `plan-trigger-failure.txt` 与 `plan-green.txt`。
- 金额上界现在显式拒绝绝对值达到 10^16；发票响应采用输出模型，不沿用禁止附加字段的输入模型。
- 扩展测试中事件监听起初只绑定夹具引擎而非实际 API 引擎，采购样例少填到期日。这两项是测试准备问题，未当作产品缺陷复现。原始失败日志保留。

原始 pytest 输出含行尾空格、类型检查含空白末行。为保留原始证据又通过差异检查，相应 `*.txt.raw.gz` 保留逐字节原输出；同名 `.txt` 仅清理行尾空白便于阅读，未改测试内容或结论。
