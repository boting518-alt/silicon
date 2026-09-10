# TASK-005 配置报价与折扣草稿 — 执行结果

status: review_ready

日期：2026-09-10。完成当前任务纵切，等待独立 Reviewer；不自行 accepted，不开始 TASK-006。

## 提交与范围

- accepted base / 启动时 HEAD：`a8ce3e2c13736a032958decf1e65fb482cd4ebf6`，main，工作树干净。
- 独立验收交接：`b98662f74ca4fb418a06322e224a76ca0b8fa74d`。原样归档 TASK-004 增量报告；将 TASK-004 accepted、TASK-005 executing，创建原来不存在的任务书；没有改写 TASK-004/result.md 的历史状态或测试结果。
- 本文件随实现提交；准确实现 commit 在下方交付追记登记。最终审查包的 final HEAD 由包外 REVIEW_MANIFEST.md 固定，源码完全来自该 commit 的 git archive，避免在文件内记录自身尚未生成的提交号。

## 完成内容

0006_quotes 增加草稿、追加/排除部件、折扣政策与幂等命令表，复合租户 FK / FORCE RLS；项目 FK 延迟至事务提交，兼容 CRM 正常重建同 ID 项目，阻止移除仍被引用的项目。空库迁移及 0002/0003/0004/0005 升级均在真实 PG 回归中执行，0005 的原身份/客户/SKU/BOM/价格数据保持。

新 `/api/v1/quotes` 列表/详情/创建/更新，`/evaluate` 后端试算与 `/discount` 已配置码解析。服务端检查身份、membership、quote/CRM 权限、客户范围、项目归属、预期企业/context、CSRF、幂等键与 expected_version。没有客户端金额授权入口、快捷生产身份、发布、审批、合同或核销 API。

固定已发布 BOM 与当前 SKU 重新校验；included 不重复收费，排除包含件不扣根基价，替换按新部件价格另算。金额 Decimal/NUMERIC、CNY 精确字符串，单行→整机数量→单码优惠按 HALF_UP 到分，记录来源/版本/有效期。零价与未知/未来/过期价分开；无价或无效优惠可保存待补全草稿。保存结果与当前重算分别返回，价格变化触发 needs_reprice。单码开发百分比政策校验启停/企业/权限/期间/范围/税口径/最低额/上限，无次数配额、预占或核销。

锁顺序、开发规则、历史快照与可售有效性区别见 [ADR-010](../../architecture/adr/ADR-010.md)。会话/membership → 目录共享 → 报价共享读/排他写 → CRM 父共享；目录修改在报价聚合读取期间等待，不返回混合状态。真实销售/发布政策未配置，sale_ready 始终 false；金额可算不等于兼容或可发布。

前端沿用业务侧栏、硅屿 token 和原报价 SVG 几何/布局；真实客户/项目/BOM/SKU、部件勾选/数量、权威计价、折扣应用/移除、持久保存与重新打开。企业切换清空旧内容，原生产请求层拒绝五类延迟成功响应；编辑/窗口重新激活隐藏旧试算。SVG 点击/键盘定位，缺失/未选/停用/规则警告联动；UNKNOWN 中性颜色，明确非通过。

## 实际验证

环境：macOS；PG 17.11 Homebrew、Java 21.0.6+8（本机 Oracle JDK）、Keycloak 26.7.3、Python 3.12.7、uv 0.12.11、Node 24.15.0、npm 11.12.1。未升级依赖。版本输出见 [environment.json](evidence/environment.json)。

| 检查 | 准确命令（仓库根） | 实际结果 |
|---|---|---|
| 最终完整后端 | `SILICON_TEST_PG_BIN=/opt/homebrew/opt/postgresql@17/bin SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3" .venv/bin/python -m pytest apps/api/tests -q` | **87 passed，0 skipped，4 warnings，46.14s**；见 backend-verified.txt |
| 报价定向并发 | 同 PG 前缀，`.venv/bin/python -m pytest apps/api/tests/test_quotes.py -q -k aggregate` | 1 passed，15 deselected；明确 SQL 同步点及 pg_blocking_pids，不靠超时失败替代成功读取 |
| 前端自动化 | `node --test apps/web/tests/catalog-time.test.ts apps/web/tests/context-race.test.ts` | **19 passed**；5条 quote 列表/详情/试算/保存/优惠延迟成功响应，以及原上下文/时间用例 |
| 契约 | `.venv/bin/python infra/export_openapi.py`、`npm run api:types`，重复一次比较生成物字节 | 两次一致，SHA 见 contract-repeatability.txt |
| 前端检查 | `npm run typecheck`、`npm run build` | 均 exit 0 |
| 文档 | `.venv/bin/python infra/check_docs.py` | 交付前检查状态、历史报告 SHA 与所有相对链接；见 docs-final.txt |
| Compose | `/Applications/Docker.app/Contents/Resources/bin/docker compose --env-file .env.example -f infra/compose.yaml config --quiet` | exit 0，配置检查；未启动容器 |
| 改动格式 | `git diff --check`、暂存后 `git diff --cached --check` | 交付前执行并记录，无空白错误 |
| 浏览器 | 独立栈启动、CUA 真实 HTTPS 点击/输入/刷新与两视口截图 | 完整草稿链路实际完成，见下节 |

16 个新增报价 PG/API 用例覆盖 included/替换无抵扣、未知/零价/时效边界、Decimal/折扣上限/最低额/舍入、非法客户端金额、企业/权限、幂等与并发编辑、并发无配额试算、SKU停用/嵌套当前有效性、原必选类别、RLS和项目约束、目录写与聚合读取的一致性。原身份/OIDC、CRM、目录与 Worker 回归未跳过。报价认证夹具注入测试会话，数据库/计价/授权逻辑真实；另有真实 IdP 协议测试及真实浏览器登录，不将两者混称。

日志保留红绿历程：quote-red 为未实现的 404；quote-boundaries 暴露政策测试种子未设置 FORCE RLS 所需 user GUC，已修正夹具；quotes-final 的 1 失败为并发同步错误依赖线程名，改为实际 SQL 事件后通过 quote-concurrency 及最终完整回归。full-first 是补充两项测试前 85 passed 的历史结果。backend-final 是受限沙箱回环 bind 被拒绝，15 passed/72 setup errors；取得允许本地监听的执行环境后，backend-verified 完成 87 passed。没有删除失败日志或降低断言。新文本证据如需去除行尾空白/补终止换行，原始字节另存同名 .raw.txt.gz；内容和失败结果均保留。4 warnings 为既有 Starlette/AnyIO 弃用及并发 TestClient 的 Pydantic alias 警告，未通过无关升级消除。

## 浏览器与视觉证据

[浏览器操作/复现](browser-acceptance.md)、[视觉差异说明](../../design/task005-visual-comparison.md)、[截图清单](evidence/screenshot-manifest.json)、[验证汇总](evidence/validation.json)。7 张原始 JPEG 均为 1440×900 或 390×844，无像素修改。完成登录/企业A/客户项目/配置/SVG定位/试算/折扣拒绝与应用移除/保存v1/刷新重新打开/整机2保存v2/再次恢复；不含电源差异、企业B空与只读、自然会话失效、真实退出也已执行。一次机价 84300.51；5% 后80085.48；两台小计168601.02、优惠上限5000.00、结果163601.02。均为虚构价格，不是供应商报价。

浏览器使用既有获授权证书信任，本轮不更改系统或用户信任。独立栈创建并清理自身 PG/IdP；不连接、停止或写入常驻 PG。原 Demo 本轮再核对来源字节，视觉使用既有固定原图对照，不修改原图。未以 httpx 冒充 Cookie/跳转/点击验收。

## 限制与恢复条件

- 真实销售/税费/运费/完整兼容政策未配置；正式发布、审批、锁价/核销和合同未实现，不能将本草稿视为可销售最终报价。业务明确相应规则并分配后续任务后再实施。
- 单码百分比开发配置，无次数限制或折扣后台；试算与保存没有消耗/释放时点。真实配置必须由授权操作员明确建立，遵守 ADR 锁序，不用 Demo 政策替代。
- 最小 UI 客户/草稿选项最多100条，每类别一个追加型号；API/已有BOM可表达多行。完整检索与复杂多型号配置器未建设。应用不实时推送所有价格变化；显示观察时刻，焦点重入提示重算，保存强制重算。
- 本轮浏览器双标签保存竞态 not_run；自动化以确定性成功延迟测试生产请求层，真实PG另外验证上下文与并发，不冒充双标签浏览器。可按独立栈再打开两个标签重演。
- 远程 CI not_run（无远程）、容器启动 not_run（仅配置）、其他浏览器/字体/视口 not_run；未部署、不建远程。生产拒绝启动保护保持。
- 新机器重跑视觉需同 hash 合法字体与已获授权的可信开发 HTTPS；测试私钥、系统字体、环境/PG/Keycloak安装包不在审查包中。准备方法均为相对路径/环境变量。

## 交付追记

实现与验证 commit：`6963527074072f491db030b8a9970d3f2867f150`。测试对象为该实现树，后续仅补齐交付文档；最终受审 HEAD 由审查包 REVIEW_MANIFEST.md 与回复精确给出。完整变更清单见 [changed-files](evidence/changed-files.txt)，实现以来文档收尾单独在包内 changes/implementation-to-final.patch 列出。最终状态 review_ready，不自行作独立审查结论。

## 独立审查修复 R1 / R2 / C1（2026-09-10）

status: review_ready

修复前基准：`6d2a81846aa515e8c69f028d68f619d40b502292`。开始时 main/HEAD 与该基准相同，无后续提交及已跟踪修改；仅本次报告已未跟踪地放在 docs/reviews 中。将其原样纳入版本控制，SHA-256 `1a27276947e33b2044a46ed091cb7741b1b251c3687324cd5933a94e5e4ea788`，不修改 changes_requested 结论。当前仍为TASK-005修复，不开始TASK-006。上方首次执行历史/限制及旧证据保持不变。

### 修改与原因

- **R1**：模板 required 被错误用作实际选择过滤。仅报价兼容输入改为当前全部已选行，实际类别完整性统计全部选中类别，原模板必选类别另行保留。原返回技术行的 required、目录 checks 语义与已发布快照不改。排除件不计价、不检查；UNKNOWN仍表示资料不足。真实PG/API覆盖混合必选/可选CPU不匹配BLOCK、排除后PASS、内存BLOCK、可选电源WARN/PASS/排除BLOCK、可选CPU满足类别与原必选GPU不能消失，included不重复收费、BOM完整响应不变。
- **R2**：相同payload不等于同一次新建意图。“新建草稿”和成功打开已有草稿重置本地命令身份；失败重试不重置；保存签名包含创建/更新目标。服务端重放、IDEMPOTENCY_CONFLICT、expected_version不改。实际React DOM组件覆盖新建、重复内容、打开后新建、响应丢失重试和第二份编辑；真实浏览器/PG再次核对独立ID、三次意图只有三份。
- **C1**：重算开始清除当前试算，显示计算中；失败清除成功提示、显示失败/待重算。历史金额改为明确“历史保存结果”，不丢弃未保存配置。组件及真实浏览器都完成先成功→失败→重试成功；桌面/手机截图记录状态。没有修改金额规则、视觉风格、依赖、迁移、认证或TLS。

决策补充见 [ADR-010](../../architecture/adr/ADR-010.md)。可重复的实际React测试在 apps/web/tests/quote-component.html/.jsx；只模拟HTTP边界，不替换组件/hooks。另有独立测试栈 `infra/quote_review_fixture.py`，显式test factory在真实提交后丢弃成功响应并交付503；无产品控制接口、不绕过权限，用于实际浏览器故障回归。

### 本轮实际验证

| 检查/命令（仓库根） | 结果 | 新证据 |
|---|---|---|
| `SILICON_TEST_PG_BIN=/opt/homebrew/opt/postgresql@17/bin .venv/bin/python -m pytest apps/api/tests/test_quotes.py -q -k selected_optional_cpu` | 原实现1 failed（PASS错误，预期BLOCK）→修复后1 passed | r1-red / r1-green.txt |
| 实际React DOM组件测试页 `/tests/quote-component.html` | 原实现3 failed →修复后3 passed | component-red / component-green.txt |
| `SILICON_TEST_PG_BIN=/opt/homebrew/opt/postgresql@17/bin SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3" .venv/bin/python -m pytest apps/api/tests -q` | **92 passed、0 skipped、3 warnings，45.65s** | backend-full.txt |
| `node --test apps/web/tests/catalog-time.test.ts apps/web/tests/context-race.test.ts` | **19 passed**，保留并发/跨企业延迟成功响应 | frontend.txt |
| `npm run typecheck` / `npm run build` | exit 0 | typecheck / build.txt |
| `.venv/bin/python infra/export_openapi.py` / `npm run api:types` | exit 0，生成物与审查基准字节相同 | contract-check.txt |
| `.venv/bin/python infra/check_docs.py`、`git diff --check`（含暂存及最终范围） | 交付检查通过 | docs-check / diff-check.txt |
| 独立可信HTTPS浏览器定向操作 | R1/R2/C1实际完成，6张1440×900/390×844截图 | browser-notes.md、screenshots.json |

本轮新增5项PG参数化用例，覆盖上述R1和真实重复创建/重放/编辑隔离；完整回归包含原身份、真实OIDC、目录、CRM、Worker、空库及升级。PG/IdP全为独立临时实例，不读写/停止常驻数据库。3条warnings为原Starlette/AnyIO弃用及并发TestClient的Pydantic alias提示，未升级依赖消除。

首次新增PG夹具误用了禁止另计价的package类型，被422拒绝；修正为BOM后才取得真正R1红灯。r1-fixture-red.txt保留该准备错误，不把它冒称R1复现。所有本轮证据新增于 [r1-r2-c1](evidence/r1-r2-c1/)，不覆盖原记录；必要的文本行尾规范化保留同名raw.gz原始字节。

### 浏览器、剩余限制与交付

[本轮浏览器复现/限制](evidence/r1-r2-c1/browser-notes.md)、[验证汇总](evidence/r1-r2-c1/validation.json)。实际使用原可信证书、固定字体及相同硅屿壳；CPU/内存可选不匹配阻断且取消后移除，电源included不收费；两份相同草稿ID不同，第二份编辑不改第一份；真实提交成功但成功响应被测试传输丢弃后，重试仍只有一份。计算中、失败、历史金额与重试在两个视口均可辨认，未保存名称保留。

本轮没有重新跑全部旧浏览器路径或双标签浏览器保存竞态；原相关Node/PG回归通过，不能冒称双标签实际交互。远程CI、Docker运行及其他浏览器/字体not_run（无远程/非本轮要求）；未部署、未创建远程。原真实商务政策未配置、无次数预占核销和生产拒绝启动等限制继续适用。

修复实现commit与最终HEAD在交付追记和审查包固定清单登记。新审查包从最终commit完整导出，另含相对此次6d2a818基准的增量diff/changed-files/log；原完整审查包保留。最终review_ready，等待独立Reviewer复核，不自行accepted。
