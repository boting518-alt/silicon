# R1/R2/C1 定向浏览器与组件验证

2026-09-10；状态 review_ready。以下是执行者实测，不是独立复核通过。没有改变原 Demo、视觉 token、TLS 信任或常驻 PostgreSQL。

## 组件红绿测试

使用新增 `apps/web/tests/quote-component.html` / `.jsx`，通过开发 HTTPS 服务打开 `/tests/quote-component.html`。它挂载真正的 React DOM、QuoteStudio 与生产 api/request 层，通过实际 label/input/select/button 事件推进；只在 HTTP 边界提供模拟响应，不替换 hooks 或组件处理函数，不是数据库/OIDC 验收。测试页面不属于 Vite 产品构建入口。

原实现运行结果见 component-red.txt：同内容新建未产生第二份、失败重试后新建未独立、重算没有计算中状态，3 项均 failed。修复后 component-green.txt 为 3 passed，覆盖：

1. 新建相同内容两次，ID/列表均独立；第二份编辑不影响第一份；打开第一份再新建也独立。
2. 模拟服务端创建成功但响应丢失，重试保留 key、仅一份；随后显式新建产生第二份。
3. 保存历史金额 → 未保存名称编辑 → 成功计价 → 延迟失败：计算中隐藏旧试算，失败清除成功提示并要求重算，历史标记明确，编辑保持 → 重试成功。

此套为可重复执行的真实 React 组件交互测试，另有原 Node 19 项自动化；不把 HTTP 替身称作真实后端。浏览器导航工具一次等待超过其短期限时，仅重新读取页面实际状态，未降低测试条件或改为成功假数据。

## 真实 IdP / PG 浏览器复现

从仓库根安装既有锁定依赖，准备 PG17.11、Java21.0.6、Keycloak26.7.3；设置 `SILICON_TEST_PG_BIN` 与 `SILICON_TEST_KEYCLOAK_HOME` 为自己的安装位置。沿用 [原浏览器准备](../../browser-acceptance.md) 中的可信 localhost 证书和固定合法字体，不能跳过证书校验。新设备信任需另获用户授权。

先结束真实 OIDC pytest，确认端口空闲。只启动本测试栈，不执行 createdb/bootstrap：

```bash
SILICON_BROWSER_QUOTE_REVIEW=1 SILICON_BROWSER_CATALOG=1 SILICON_BROWSER_CATALOG_SEED=1 SILICON_BROWSER_QUOTES=1 .venv/bin/python infra/browser_stack.py
```

脚本创建独立临时PG并迁移，独立Keycloak/H2，虚构客户/企业/目录；新开关只选择 `infra.quote_review_fixture:create_app`。factory要求 SILICON_ENV=test 且专用开关，默认 API/生产启动不使用它，无 HTTP 故障控制接口。只改变这次测试的响应交付，身份/权限/计价/事务均为真实后端。

登录 https://localhost:5173，虚构 alice / Fictional-alice-17!，选择 A（admin）→ 报价与利润。客户“澄川大学 · 人工智能学院”/项目“科研平台”，BOM“虚构回归 · 混合可选件”。该夹具包含必选匹配 CPU/内存、可选不匹配 CPU/内存、可选 included 电源×2及必选系统盘，全部为虚构型号和价格。

| 检查 | 实际操作与结果 | 证据 |
|---|---|---|
| R1 全选 | CPU/内存两类均 BLOCK，SVG 橙色；可选电源 N+1 PASS；小计26660.51，included电源不收费 | r1-selected-block.txt、r1-block-1440.jpg |
| R1 取消 | 取消两个不匹配可选件，重新计价CPU/内存PASS，价格22660.51；取消件不在商业行 | r1-excluded-pass.txt |
| R2 相同新建 | 名称“完全相同的虚构草稿”，保存；点新建，填完全相同客户/项目/BOM/排除项/数量/名称再保存。两个ID不同，列表两份 | r2-distinct-ids.json、r2-first/second.txt |
| R2 编辑 | 只将第二份改名“仅修改第二份”，成为v2；重新打开第一份仍原名v1 | r2-edited-second.txt、r2-first-unchanged.txt、r2-two-drafts-1440.jpg |
| R2 丢失响应 | 新建“响应丢失虚构草稿”，保存前用下面的create-loss命令；真实上游提交返回201，但夹具丢弃成功结果、改送503，页面显示错误；原页再点保存，重放同ID，库/列表总共三份，不是四份 | r2-lost-response.txt、r2-retry-success.txt、r2-retry-list.json、transport-events.jsonl |
| C1 重算 | 保留历史v1，名称改为“未保存编辑仍保留”；成功计价后用trial-failure命令再点重算。先显示计算中、没有旧试算；失败后提示待重算，保留历史标记和未保存名称；重试成功 | c1-calculating*.txt/jpg、c1-failure-desktop.txt、c1-retry-success.txt |
| C1 手机 | 390×844重复成功→故障→失败→重试。提示自动聚焦、金额区域只保留历史保存结果，当前显示待重算；重试恢复22660.51 | c1-failure-mobile.txt、c1-failure-390.jpg、c1-history-390.jpg、c1-mobile-retry-success.txt |
| 切企业 | 带未保存编辑切B，页面只读、旧名称/草稿清空 | tenant-b-empty.txt |

本地一次性传输故障（从仓库根、测试栈运行中执行）：

```bash
.venv/bin/python infra/quote_review_fixture.py --arm create-loss
.venv/bin/python infra/quote_review_fixture.py --arm trial-failure
```

每条在对应点击前单独执行，不连续同时设定。create-loss在真实授权/创建/提交完整完成后，将原成功响应替换为503，**不是伪造数据库成功或修改客户端 fetch**。trial-failure同样在真实试算后延迟最多7秒并交付503；可用 `--arm release` 提前结束等待。只消费一次，下一次请求走真实正常响应；不记录Cookie/令牌/折扣码。事件只含模式、上游状态及虚构草稿id/version。

browser-pg-crosscheck.json 是对该独立集群的只读核对：3条创建命令、3份草稿，其中两条创建request_hash相同但id不同；第二份v2、第一份v1；丢失响应记录id与重试结果一致。它补充实际浏览器交互，不冒称UI自身返回的日志。

结束前复制 `.tools/quote-review-events.jsonl` 作证据；Ctrl-C栈并等待 BROWSER_STACK_CLEANED。只在已结束测试栈且确认记录已复制后，删除本轮生成的 `.tools/quote-review-control.json` 与 `.tools/quote-review-events.jsonl`（脚本下次启动拒绝覆盖已有控制文件）。原始PG/IdP临时目录由栈清理，常驻PG/证书信任不变。本轮已完成上述清理。

## 视觉与限制

6张原始JPEG的尺寸/hash见 screenshots.json。与原 [TASK-005 视觉对照](../../../../design/task005-visual-comparison.md) 保持相同卡片/布局/SVG，只增加明确重算状态与历史标签；R1异常着色来自现有样式。未重拍或修改旧截图，不进行盲目像素基线更新。手机实际document宽度=viewport=390。

本轮为定向真实浏览器流程，不宣称重新执行全部旧功能/双标签浏览器竞态。原跨企业延迟成功响应/并发编辑在Node与完整PG回归通过。远程CI、Docker启动及其他浏览器/字体仍not_run；无生产部署。
