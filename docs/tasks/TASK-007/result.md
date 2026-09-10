# TASK-007 实施结果

status: review_ready

本次为执行者交付，非独立验收，不开始TASK-008。TASK-006由负责人明确accepted，增量报告原样归档，保留此前changes_requested和旧验证限制。

## 提交基线与范围

实施前/已验收基线：`59f55c813aba62ec8f18dc5d5e7cc649b277aeca`。交接提交见本报告末尾提交登记，最终固定HEAD以审查包REVIEW_MANIFEST.md及git archive来源为准，不用工作树替代提交。

[原任务与新授权比较](handoff.md)：功能范围一致，新授权覆盖原“只准备”；详细原验收项未删除。[任务书](task.md)、[ADR-012](../../architecture/adr/ADR-012.md)、[真实浏览器记录](browser-acceptance.md)。

## 已实现

- 在TASK-006同一合同id上增加可编辑资料，原报价及来源合同快照不改。甲乙方、代表、项目负责人/关键人、内部membership引用和历史姓名分开。资料版本历史追加保存。
- 固定金额付款节点NUMERIC(18,2)、精确字符串，草稿可未配平、签约必须配平。签约日期加日历天；交付/验收未发生时待触发，不生成应收、收款、发票。
- 线下签约事实确认绑定版本/hash/幂等，在同一现有报价租户锁内冻结合同及一份待履行订单。编辑、附件删除、来源撤回与签约顺序明确；运行角色不能修改冻结事实。已签本轮不提供变更/解除。
- 私有PDF/JPEG/PNG上传、待关联/关联/删除、鉴权下载、服务端大小/type/hash；默认10MiB。签约后补充独立记录，不重写原冻结附件集。上传失败孤儿不可见，24小时以上、租户受控且跳过在途文件的清理工具，默认dry-run。
- 合同与订单侧栏、表单、只读配置/价格/品牌、付款约定、来源及历史，沿用既有硅屿样式。上下文切换清除页面，过期成功响应不能写回；API错误不假成功。
- 0008迁移、OpenAPI/生成类型、运行配置与虚构测试工具。没有更新业务依赖或原Demo。

## 实际验证

命令从仓库根运行，`PG17_HOME`/`KEYCLOAK_HOME`由复现者指定。环境：PG17.11、Java21.0.6、Keycloak26.7.3、Python3.12.7、Node24.15.0/npm11.12.1；锁文件未升级。

| 验证 | 命令/入口 | 实际结果 |
|---|---|---|
| 完整后端 | `SILICON_TEST_PG_BIN="$PG17_HOME/bin" SILICON_TEST_KEYCLOAK_HOME="$KEYCLOAK_HOME" .venv/bin/python -m pytest apps/api/tests -q` | **154 passed / 9 warnings /94.82s**，backend-final-green.txt |
| 新合同PG/API | 同完整套件test_contracts.py | 30项，包含CRUD/签约/防重/并发/权限/文件/旧数据与快照保持 |
| 迁移 | 完整套件repository-owned PG fixture及test_upgrade_from_task006_preserves_source_data | 空库→0008；创建旧业务数据、新表为空时降新模块到0007再升0008，原身份/CRM/报价/来源合同保持，不冒称从旧二进制启动验证 |
| 身份/报价/Worker | 完整后端 | 真实OIDC、运行角色RLS、原报价审批/发布/修订及TASK005核心回归包含在154中 |
| Node前端 | `node --experimental-strip-types --test apps/web/tests/*.test.*` | 19 passed |
| 实际React+HTTP替身 | `/tests/contracts-component.html`、publication/quote组件页 | 5+5+3 passed，单独统计，非真实PG |
| 类型/构建 | `npm run typecheck`、`npm run build` | passed |
| 接口一致性 | `.venv/bin/python infra/export_openapi.py`、`npm run api:types` | 再生成字节一致 |
| 文档/差异 | `.venv/bin/python infra/check_docs.py`、`git diff --check` | 交付前通过，见证据登记 |
| 浏览器 | [完整操作与复现](browser-acceptance.md) | 真实登录→合同→付款→上传关联→签约→订单→刷新；admin/viewer、A/B、来源撤回、重复签约与下载落盘摘要一致 |

[机器可读验证](evidence/validation.json)和原始输出都保留。9条警告为既有Starlette/AnyIO弃用和Pydantic alias警告，不称零警告。需要去除终端尾部空白的文本同时保留 `.raw.gz` 原始字节，不覆盖历史任务证据。

红绿及诊断：workspace-red 404→workspace-green1通过；已签补充材料拒绝的supplement-red→green。lifecycle初次503定位到触发器OLD字段分支错误后修正，保留diagnostic。workspace夹具TRUNCATE遗漏新表是准备错误，不算需求缺陷红测。expanded29通过、backend-first153通过；新增后续主数据快照用例后backend-final一次152通过/1失败/1错误：新增CRM请求漏幂等头，以及与浏览器并行IdP的8080冲突。补头并结束浏览器栈后最终154通过，未隐藏失败或修改产品认证语义。

## 浏览器与视觉证据

7张原始JPEG及hash见 [截图清单](evidence/screenshots.json)。视口1440×900/390×844，IAB导出1425×891/375×812，未重采样；移动document375无横向溢出。新增合同/订单内容不冒称原Demo既有页面状态，未更新历史基线来掩盖差异。

重复签约为同源测试页真实Cookie/真实API两次POST，同signed_id，订单前后1。来源失效浏览器验证撤回后新草稿禁用；真实PG对齐全资料的直接POST拒绝另测。下载工具事件超时，但真实文件已落盘，621bytes与SHA-256一致，见browser-download-hash。组件响应丢失/迟到成功是明确HTTP替身，不伪称浏览器随机网络故障。

## 限制和未执行

- 零金额签约政策未配置，明确阻断；正金额闭环完成。不假定真实税率/运费/收费政策；开发政策/虚构标记继承。
- 不支持已签变更/解除/电子签章、采购库存、实际收付款或履约核销，均为任务边界；未开始TASK008。
- AV未配置；类型/结构检查不保证无恶意软件。私有本地存储是开发适配器，生产存储、备份运维、系统时区及正式政策未验收，生产模式仍拒绝启动。
- Docker容器实测、其他浏览器/字体平台、自动像素阈值比较、正式业务验收为not_run；本轮用原生隔离栈，未改证书信任。远程CI未核实。
- 列表沿现有模块最多100条；更大规模分页/运维优化不冒称已完成。

独立PG/IdP/文件目录均由夹具清理，浏览器标签关闭、视口恢复；证书及原Demo保留。审查包包含完整固定提交源码、基线差异、历史报告与证据，不包含依赖、数据库、密钥或活动会话。
