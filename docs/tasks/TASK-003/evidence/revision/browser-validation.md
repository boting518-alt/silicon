# R1 双标签浏览器复测

2026-09-10，本机 Codex In-app Browser，两个同源标签。由 `infra/browser_stack.py` 启动独立 PG 17.11、真实 Keycloak 26.7.3、API 和前端；仅虚构用户 alice / 虚构企业 A、B。沿用已信任的开发 HTTPS 证书，本轮未修改证书信任、系统设置或 TLS 校验。没有浏览器安全警告绕过。

## 实际步骤与观察

1. 标签一打开 https://localhost:5173，点击企业身份登录，经过真实 Keycloak 登录页、回调，选择 A；显示 7 家固定客户。
2. 标签一新增客户，填写编号 `R1-CREATE`、名称“不得落入企业 B 的草稿”。保持表单打开，标签二进入同一地址，选择 B。
3. 标签一表单、列表和详情被清空，企业选择恢复“请选择企业”，显示“企业上下文已变化，旧表单已失效。请重新选择企业；不会自动保存或迁移旧草稿。”旧保存按钮随表单移除。B 为空。见 [AX](create-invalidated-ax.txt)、[截图](create-invalidated.jpg)。
4. 标签一明确重新选择 A，打开原客户 CUS-001（澄川大学）并编辑，名称改为“不得跨企业保存的编辑”；标签二再次选择 B。标签一再次关闭旧编辑表单、提示重新选择。见 [截图](edit-invalidated.jpg)。
5. 标签一重新选择 A、打开原客户，仍为“澄川大学”、版本 1。关闭后打开新建，名称为空，旧草稿没有转移。
6. 明确选择 A 后重新创建 `R1-VALID` / “明确重新选择后创建”，保存成功为版本 1，刷新后仍能查询。见 [AX](explicit-selection-saved-ax.txt)。进一步编辑为“明确企业 A 的正常编辑”，保存成功显示版本 2。
7. 标签二选择 B，搜索 `R1-`，结果为 0；上述未提交草稿和有效 A 客户均没有落入 B。见 [AX](enterprise-b-empty-ax.txt)、[截图](enterprise-b-empty.jpg)。
8. 标签二退出，刷新两个标签都显示登录入口，受保护客户内容不可见。见 [标签二 AX](logout-ax.txt)、[标签一 AX](logout-tab-a-ax.txt)。

验收后关闭本次两个测试标签、结束本次 browser_stack；收到 `BROWSER_STACK_CLEANED`，进程退出码 0。未操作常驻 PG。

## 证据边界和复现

以上为真实 Cookie、登录跳转与点击，不是 httpx 登录替代。通知到达后旧表单已关闭，浏览器中没有再强行发送旧保存；通知丢失时的 HTTP 409、A/B 均无误写由 `test_crm_context.py` 的真实 PG/生产 API 回归独立覆盖，认证会话注入是明确的夹具。

延迟成功响应竞态由 `node --test apps/web/tests/context-race.test.ts` 确定性门控 HTTP 200 返回，调用未修改的生产 CrmRequests，覆盖列表、详情、新建、编辑；这是传输替身测试，不能称为浏览器网络拦截实测。焦点/可见性恢复检查已实现，本轮未单独屏蔽两个通知渠道后做浏览器故障注入；服务端保护不依赖该检查。

截图原始尺寸均为 1280×720，使用当时浏览器视口，没有覆盖或更新历史 1440×900 / 390×844 基线。已逐图查看：保留原侧栏、配色、排版和面板；本轮有意新增的是上下文失效提示及要求重新选择企业的状态。B 空列表截图处于页面下滚位置，企业 B 的选择值见对应完整 AX。不把本轮截图冒称新的完整视觉基线。

复现先设置 SILICON_TEST_PG_BIN 和 SILICON_TEST_KEYCLOAK_HOME，再运行 `.venv/bin/python infra/browser_stack.py`，等到 BROWSER_STACK_READY 后按上述步骤操作。需要此前可信的开发证书；证书不可用时停止浏览器验证，不忽略 TLS 错误。结束该栈后再运行真实 OIDC pytest，以免现有 Keycloak 开发 HTTP 8080 监听冲突。
