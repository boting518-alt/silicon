# TASK-006 执行结果

status: review_ready

## 固定来源与交接

- 任务基准/已审查HEAD：`da215ad9b22e5d831c0d7a319885ddf7ad3ec8ef`。
- 独立交接：`919f75aa537082d19a05865bb4e5e85893548ab5`。
- 开始时 main，无已跟踪用户修改；仅未跟踪增量报告，逐字节与Downloads附件相同，原样归档。
- 用户依据 [TASK-005增量报告](../../reviews/TASK-005-da215ad-review.md) 明确accepted。首次changes_requested报告、旧result和旧证据未改写。Reviewer当时未重跑真实PG/OIDC/浏览器等限制保留。
- 附件落为 [任务书](task.md)，只增加来源说明和状态。未开始TASK-007，无remote/部署。

## 实现与设计

[ADR-011](../../architecture/adr/ADR-011.md) 记录阶段性收敛：继续原Decimal计价器、全部人工审批、无自批、未知成本/费用不填零、版本化开发/正式发布政策、BLOCK不可豁免、WARN/UNKNOWN逐项说明与依据。无额度预占/核销；有限额政策明确拒绝。开发标记冻结并继承合同，正式政策没有自动种入企业，生产拒绝启动保护保持。

0007_publication增加候选、不可变决定、发布内容与独立生命周期、事件、来源合同和幂等记录，所有表RLS及复合租户FK。运行角色不能UPDATE/DELETE冻结内容。发布重新校验当前草稿版本/候选指针/内容hash/有效期/价格/折扣/政策及提交人审批人实时权限。hash规范UTC排除观察时钟；重新提交有效期也使旧审批失效。

统一锁序：会话/当前身份→其他参与者身份共享→catalog共享→quote共享读/排他写→CRM父共享。与旧草稿编辑串行，未新建计价器。幂等保存结果id，重放重新授权；同候选只能发布一次，同发布版本最多一个合同。发布后修改必须独立修订（Q-000001-R2等），撤回/过期与正文分开，合同保留并标源风险。

UI沿用硅屿壳，增加工作室提交入口、审批/风险详情、人工发布确认、版本历史/修订/撤回及侧栏合同草稿。旧异步代次/上下文、TASK-005 R1/R2/C1保留。内部审批说明只对审批权限返回，普通发布/合同没有原始折扣码或内部审批正文。合同乙方法人、付款节点、附件和签约明确待补齐；不假定登录人是责任人。

## 实际验证

命令均从仓库根运行；本机具体PG路径仅记录实测，不作为异机运行依赖。

| 检查 | 命令 | 结果/证据 |
|---|---|---|
| 缺政策红绿 | `SILICON_TEST_PG_BIN=/opt/homebrew/opt/postgresql@17/bin .venv/bin/python -m pytest apps/api/tests/test_publication.py -q` | 首个用例404失败→迁移/服务后1通过；submission-red/green.txt |
| 完整后端 | `SILICON_TEST_PG_BIN=/opt/homebrew/opt/postgresql@17/bin SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3" .venv/bin/python -m pytest apps/api/tests -q` | **116 passed，0 skipped，3 warnings，60.69s**；backend-final.txt |
| 后续补充PG | 同PG变量，`.venv/bin/python -m pytest apps/api/tests/test_publication.py -q -k 'new_price_boundary or current_price_version_boundary or member_submit'` | **3 passed，23 deselected，2 warnings**；publication-supplement.txt。未冒称它们包含于上行116 |
| 前端Node | `node --test apps/web/tests/*.test.ts` | **19 passed**；frontend.txt |
| 实际React DOM | 开发HTTPS `/tests/publication-component.html`、`/tests/quote-component.html` | 新4通过/原3通过，HTTP替身；component-final / quote-component-regression.txt |
| 类型与构建 | `npm run typecheck`、`npm run build` | exit0，typecheck-final/build-final.txt |
| 契约 | `.venv/bin/python infra/export_openapi.py`、`npm run api:types` | 重复生成字节一致，contract-check.txt |
| 文档与差异 | `.venv/bin/python infra/check_docs.py`、`git diff --check` | 交付时实际输出见docs-check/diff-check.txt |
| 真实浏览器 | [浏览器命令及完整步骤](browser-acceptance.md) | 两身份、双标签旧审批被拒、v2重审发布、重复转合同、未来价格修订后历史不变、刷新、撤回警示、企业B隔离；7张截图 |

本任务新增26项PG参数化用例；完整116包含其中23项，另3项为随后增加的补充。空库迁移和0006升级保留原客户、联系人、草稿和目录/身份/Worker数据。已有0001至0005升级回归继续通过。所有PG实例独立临时创建/清理，真实OIDC明确执行，没有用mock替代。3条完整回归warnings为原Starlette/AnyIO弃用及并发Pydantic alias提示，未升级依赖消除。

首次沙箱端口限制记录submission-sandbox.txt，经工具批准后在独立PG执行真正红灯。主链路初次失败发现UTC与数据库+08:00字符串导致无意义hash不同，修正UTC规范化并保留lifecycle-first-red.txt；正常时钟流逝和PG往返已回归。没把准备失败或未执行算通过。

## 证据、限制与复现

[验证汇总](evidence/validation.json)、[截图清单](evidence/screenshots.json)、[浏览器PG核对](evidence/browser-pg-crosscheck.json)、[浏览器说明](browser-acceptance.md)。新证据独立目录，不覆盖TASK-005。文本行尾规范化前原始字节保留raw.txt.gz。

- 本轮浏览器新增的是未来不重叠价格版本，未改系统时间或旧价；当前价跨界使用真实PG加显式时钟测试覆盖。发布正文与合同JSON逐字相同，原hash不变。
- 最终修订编号分支由真实PG验证；浏览器验证修订草稿建立。最后失效按钮更新由真实React测试验证；核心双标签服务端拒绝为真实浏览器已执行。
- 客户/候选/版本列表首期最多100条；未建设全量搜索/通用审批编排。成员身份共享锁粒度为当前租户全成员，先确保授权与锁序；高规模优化后续另评估。
- 正式发布政策、可靠成本与真实商务责任仍需企业配置，本轮只验证显式开发政策；无税额换算/运服费/额度预占核销/外发/签约/生产运维。
- 远程CI not_run（无remote）、容器运行 not_run（原生独立栈）、其他浏览器/字体 not_run。原所有浏览器场景未全量重跑，相关PG/组件回归单独如实列出。
- 临时PG/IdP已清理，证书信任/常驻数据库/原Demo不变。依赖与lock未升级。状态review_ready，等待独立审查。

实现commit在交付追记登记；最终受审HEAD固定于包内REVIEW_MANIFEST.md和交付回复（避免提交自引用）。审查包从最终Git commit全量导出，包含基准到HEAD binary diff、日志/文件清单和收尾差异、原报告/任务书/ADR/证据/SHA256SUMS。

### 截图导出补记

页面在 1440×900、390×844 视口验证；IAB 的 screenshot 和原始 getScreenshot 两个接口均缩小导出为 1425×891、375×812（滚动条区域）。没有重采样伪装尺寸。补拍第二独立栈的提交页面仍有相同限制；final-login 是设置视口前的 1280×720。实际尺寸与哈希见 screenshots.json，不能称为指定像素的未缩放截图。第二栈只补拍提交，不替代第一栈完整两人审批流程；两栈均已清理。
