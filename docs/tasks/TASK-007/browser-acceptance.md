# TASK-007 浏览器验收与复现

2026-09-10～11，执行者实测，非独立验收。使用真实 Keycloak/OIDC、浏览器 Cookie、独立 PostgreSQL 和虚构数据。保留原开发证书信任，未忽略 TLS 错误。

## 准备

从仓库根按 README 安装锁定依赖。需要 PostgreSQL 17.11 程序目录、Java 21.0.6、Keycloak 26.7.3（`infra/fetch_keycloak.py` 固定下载摘要）。设置 `SILICON_TEST_PG_BIN` 和 `SILICON_TEST_KEYCLOAK_HOME`，Java 在 PATH。沿用 [可信证书与固定字体准备](../TASK-005/browser-acceptance.md)；证书/私钥不入包，新机器需要自己授权浏览器信任，不能绕过校验。字体文件 hash 由脚本检查，不能声称替代字体视觉一致。

```bash
export SILICON_TEST_PG_BIN="${PG17_HOME}/bin"
export SILICON_TEST_KEYCLOAK_HOME="${KEYCLOAK_HOME}"
SILICON_BROWSER_CONTRACTS=1 SILICON_BROWSER_PUBLICATION=1 SILICON_BROWSER_CATALOG=1 SILICON_BROWSER_CATALOG_SEED=1 SILICON_BROWSER_QUOTES=1 .venv/bin/python infra/browser_stack.py
```

不要同时运行另一个 Keycloak 集成栈（本次第二个实例曾因 8080 被占用启动失败）。浏览器用 https://localhost:5173，IdP HTTPS 8443，API8000；PG 随机端口。脚本从空库迁移0008，用虚构种子建立A/B企业和开发报价政策，文件根在独立临时目录。Ctrl-C/SIGTERM只清理本栈PG/IdP/文件，打印BROWSER_STACK_CLEANED，不调用常驻createdb/bootstrap。

测试身份：alice / Fictional-alice-17!（A管理员、B只读），bob / Fictional-bob-17!（A管理员），carol / Fictional-carol-17!（A只读）。都是仓库明确的虚构测试凭据，不是生产身份。前台时钟/字体/动画使用既有视觉基线配置，服务端时间真实。

生成无业务效力的测试文件：

```bash
.venv/bin/python infra/create_contract_test_file.py /tmp/silicon-fictional-proof.pdf
```

## 实际产品流程

1. alice真实登录选A，在报价工作室打开虚构 TASK-006 发布验收v1，填写未来有效期提交；退出含IdP Logout，bob登录逐项说明四项UNKNOWN，批准并人工确认发布Q-000001。没有跳过双人审批。转合同草稿后从新侧栏“合同管理”打开。
2. 填写DEMO-CON-007、虚构甲乙方地址/代表、客户项目负责人/关键联系人，销售选alice、售后选bob。签约日期2026-01-01、交付说明明确未实际发货。一笔付款约定49660.01 CNY，与冻结报价配平。保存v1后其余校验通过，仅PROOF_REQUIRED阻断。日期控件通过真实键盘触发change，未操作React内部状态。
3. 选择仓库621bytes测试PDF（正文声明不是合同或签名）并上传。待关联状态仍禁止签约；关联后v2，勾选确认才可签约。见 browser-upload-pending、browser-sign-preview、browser-signed；上传不自动签约。
4. 实际点击登记签约并生成订单。合同进入只读，原附件不能删除；同一销售订单SO-DEMO-CON-007，49660.01 CNY，待履行，付款节点不是已收款。进入订单显示冻结设备/品牌、included电源不重复收费、付款约定；刷新重新进入仍保持。见 browser-order、browser-order-refreshed。
5. 用同源测试页 `/tests/contracts-replay.html` 的实际按钮，在真实登录Cookie下向真实API两次提交同一个签约命令；返回同一signed_id，订单数量前后均1。不是HTTP替身；测试入口不在应用构建入口中。见 browser-real-replay。
6. 从订单按钮返回报价历史，bob创建独立修订并提交；alice独立批准发布Q-000001-R2、转新合同草稿，再撤回该来源。新合同详情显示SOURCE_NOT_ACTIVE且签约按钮禁用，旧已签合同/订单保留。见 browser-source-blocked、source-blocked-desktop。该浏览器步骤验证失效提示与禁用，真实PG另覆盖资料齐全时直接POST仍拒绝。
7. alice切B后列表为空，没有A详情。退出后受保护内容移除。见 browser-tenant-b、browser-logout。短测试会话自然过期也清除页面；重新OIDC登录后保存内容仍在。
8. carol真实登录A：可读合同与订单，保存/上传禁用，联系方式空串，允许的原附件可下载。见 browser-viewer、browser-viewer-download。管理员下载也实际落到下载目录，621bytes及SHA-256与上传完全相同（browser-download-hash）。工具下载事件超时，但文件落盘及字节摘要已核实，没有把提示冒称落盘。

## 组件与截图

实际React组件HTTP替身单独计数：contracts-component5项，publication-component5项，quote-component3项；日志在evidence。覆盖编辑/不配平、冲突保留草稿、上传失败、签约响应丢失重试、企业迟到成功响应；原TASK005 R2/C1继续通过。Node19项另列。不能将这些计为PG或OIDC测试。

[截图清单](evidence/screenshots.json)含7张原始JPEG。实际视口1440×900及390×844，浏览器导出1425×891/375×812，不重采样。移动document宽375、innerWidth390，无横向溢出。沿用硅屿侧栏、绿色token、字体、留白和卡片；新增合同资料/只读状态/订单列表属于本任务有意新增，不冒称原Demo已有。参照 [原设计基线](../../design/demo-baseline.md) 和TASK003已存截图，未覆盖历史基线。未进行像素自动阈值比较或其他浏览器平台验证。

测试栈和临时标签已关闭，视口恢复；可信证书和字体保留。未执行真实商务签约、生产政策、AV扫描、容器运行及其他浏览器，不部署。数据库全回归在本栈停止后串行运行，结果见result。
