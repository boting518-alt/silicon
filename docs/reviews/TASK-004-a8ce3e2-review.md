# TASK-004 增量独立复核

- 结论：**passed**。
- 复核日期：2026-09-10。
- 被审查 HEAD：`a8ce3e2c13736a032958decf1e65fb482cd4ebf6`。
- 修复实现：`04066fb5908b43146a45a16fdcc6ee4d83128130`。
- 上次审查基准：`1d627b1225430919efb1ba80ac400460f0b9db83`。
- 输入：silicon-task004-review(1).zip、result(5).md、上次审查源码与报告。
- 范围：R1/R2 修复及其直接影响；不是一次新的全系统或生产上线认证。提交身份依据交付包清单，当前环境没有原仓库 .git 或远程可供验证。

## 问题关闭

| 项目 | 结论 | 复核依据 |
| --- | --- | --- |
| R1：SKU 类别变更导致 package 草稿和目录页面读取失败 | 已解决 | bom_snapshot 默认返回带 PACKAGE_REQUIRES_HOST/BLOCK 的草稿；仅 validate=True 时拒绝类别不符。save_bom 允许保存修复中间状态，publish_bom 保留重新校验。新增测试覆盖四类列表读取、保存、拒绝发布和替换主体后发布。 |
| R2：停用 SKU 阻断历史版本创建修订 | 已解决 | BOM/价格草稿保存仍检查引用存在性，但不再因停用而拒绝复制。修订沿用 family；发布继续校验主体、直接部件或价格行当前状态。新增测试覆盖主体/部件停用、价格停用、幂等重放、修复发布和历史内容不变。 |
| R2 延伸：草稿保存后 SKU 才停用 | 已解决 | publish_price 在目录写事务路径中重新读取价格草稿 checks，遇到停用 SKU 拒绝发布；测试覆盖停用前已保存的草稿。 |

价格响应新增只读 checks，前端显示明确修复提示，OpenAPI 与生成类型同步。ADR-009 明确草稿可修复与发布有效性的区别；没有迁移、旧快照重写或自动重新启用 SKU。未发现本次修复引入的新阻断项。

## Reviewer 独立执行

- 审查包 SHA256SUMS：301 项通过。
- 对比前后源码，检查服务、模型、前端、回归测试、ADR 和文档检查脚本的变化；旧报告受到原哈希保护。
- `npm run typecheck`：通过。
- `npm run build`：通过；产物 index-BajV_SFH.js 与提交证据一致。
- `node --test apps/web/tests/*.test.ts`：14 passed、0 failed。
- `infra/check_docs.py`：通过，当前最终包检查 153 个本地链接。交付证据中的 148 是此前运行记录；最终包新增文档后本次检查通过，不构成阻断。
- 重新导出 OpenAPI、生成 TypeScript 类型：前后 SHA-256 完全一致。
- 使用实际新 service 模块执行定向函数探针：类别不符及停用状态返回草稿 BLOCK、草稿允许保存、发布拒绝类别不符/停用项、拒绝价格发布时没有调用更新。仓储读取/写入用 mock 替代，因此这部分不证明 PostgreSQL、HTTP 或事务行为。
- 查看两张新增 1280×720 截图及浏览器操作记录：提示与历史版本展示符合本次改动，未发现新的明显视觉问题。未重新执行浏览器。

复用上一轮锁定依赖环境及 node_modules；本次测试明确加载 review004fix/source 的代码。接口重新生成没有改变受审文件内容。构建只产生本地验证产物，不修改实现或原 Demo。

## 执行者证据与验证边界

已检查新增测试代码、validation.json、catalog-green.txt、full-regression.txt、browser-notes.md 及相关操作证据。执行者报告目录测试 17 passed，全后端 70 passed、0 skipped、4 warnings；这些属于提交的执行证据，不计为 Reviewer 独立重跑结果。

当前环境缺少可运行的 PostgreSQL 17 和 Java 21/Keycloak 测试栈；PostgreSQL 源码构建也受缺少 bison/flex 限制，因此本次未重跑真实数据库/API/Worker/Keycloak 回归。未执行远程 CI、容器运行或生产部署。两张增量截图不替代完整桌面/移动端视觉基线重验。

嵌套包件内部仍使用已发布技术快照；直接引用主体校验当前启用状态。这符合本次 ADR。已发布价格的 checks 为空仅表示没有草稿修复项，不代表当前可售。后续报价功能应按其任务书实现交易时有效性判断，不将本次通过等同于完整兼容认证或销售授权。

## 交接结论

本轮 R1/R2 已关闭，TASK-004 可完成验收交接。将本报告新增到 `docs/reviews/TASK-004-a8ce3e2-review.md`，保留原报告，并同步任务状态及交接引用。随后可按已发布 TASK-005 任务书推进；本次复核未开始 TASK-005，也未在用户仓库代改状态。
