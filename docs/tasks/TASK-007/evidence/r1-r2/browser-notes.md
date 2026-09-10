# TASK-007 R1/R2/C1 定向浏览器验证

状态：passed（以下实际操作范围）；不是独立验收。证据对应本轮最终产品源码，随后仅有文档提交。原历史截图和结论未改写。

## 环境与复现

在仓库根完成 `uv sync --locked`、`npm ci --ignore-scripts`，Java21在PATH；按原 `../../browser-acceptance.md` 准备经校验的PG17/Keycloak26.7.3、合法字体和浏览器认可的localhost证书。使用环境变量指定本机工具位置，禁止指向常驻数据库。不修改系统信任或关闭TLS校验。先结束完整后端测试，再启动：

```bash
export SILICON_TEST_PG_BIN="$PG17_HOME/bin"
export SILICON_TEST_KEYCLOAK_HOME="$KEYCLOAK_HOME"
SILICON_BROWSER_CONTRACT_REPAIR=1 SILICON_BROWSER_CONTRACTS=1 SILICON_BROWSER_PUBLICATION=1 SILICON_BROWSER_CATALOG=1 SILICON_BROWSER_CATALOG_SEED=1 SILICON_BROWSER_QUOTES=1 .venv/bin/python infra/browser_stack.py
```

该显式测试种子预置一份未签合同资料和付款约定，不预置附件或签约。准备阶段使用测试客户端/身份夹具完成报价审批来源，不冒称浏览器执行审批。浏览器经真实IdP以 alice / Fictional-alice-17! 登录，选择虚构企业A，进入合同管理。以上仅为虚构开发身份。

```bash
# 包内 fixtures 可直接使用；如需重新生成，指定尚不存在的目录：
.venv/bin/python infra/create_contract_review_files.py "$REVIEW_OUTPUT/new-contract-fixtures"
```

1. 打开 DEMO-CON-007，上传 invalid.pdf：真实界面显示类型拒绝（browser-invalid-pdf.txt）。
2. 上传 proof-a.pdf 并显式关联，合同v1→v2；上传 unused-b.pdf，保留待关联。勾选线下签约确认并登记，真实API产生签约及关联订单。
3. 签后 proof-a.pdf 删除禁用，unused-b.pdf 关联禁用、删除可用且有解释。两视口实际截图见 screenshots.json。
4. 首次点击删除时测试会话恰好过期，页面要求重新登录，未把该次记为成功（browser-deleted-pending.txt）。通过真实IdP SSO重新登录并重新选择A后再次打开合同，删除B成功（browser-deleted-pending-success.txt）。重新载入后B消失，冻结合同仍v2、A保留（browser-reloaded.txt），关联订单仍可查询（browser-order.txt）。数据库清理24h、字节和快照精确不变另由真实PG测试证明，不能仅凭截图推断。
5. 签后上传 invalid.jpg：真实接口拒绝，桌面和移动错误截图保留。未重新执行浏览器下载落盘校验，PDF/JPEG/PNG字节精确往返由本轮PG/API测试覆盖。
6. 打开 /tests/contracts-component.html、/tests/publication-component.html、/tests/quote-component.html：6+5+3通过。它们运行实际React组件但HTTP为明确替身，不是实际PG/OIDC证据。组件包含旧pending按钮/删除生命周期、版本冲突、丢失成功响应重放、跨企业迟到响应及TASK005修复回归。

视口经DOM读取为1440×900与390×844；IAB原始JPEG导出1425×891与375×812，未重采样。移动document.scrollWidth=375，无横向溢出。桌面/移动截图已逐张目视核对，保留原绿灰token、侧栏、圆角表单；本轮有意变化仅pending说明和允许删除按钮、真实文件类型错误。C1最终控件样式已在截图中覆盖，不替换原Demo基线，不宣称像素自动对比通过。

测试结束发送SIGTERM给本次独立栈，由其finally清理临时集群/IdP/文件；原开发证书信任保留。其他浏览器、AV、生产存储及容器实测为not_run。本轮没有部署或TASK008工作。
