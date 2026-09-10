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

提交与审查包生成后在此追加固定实现提交；最终 HEAD、完整提交日志/changed-files 与源码一致性/SHA256 校验由审查包清单给出，不自行做独立审查结论。
