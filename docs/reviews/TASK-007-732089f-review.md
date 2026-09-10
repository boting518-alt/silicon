# TASK-007 独立审查报告

结论：**changes_requested**。发现 2 项 P2，均在附件范围。修复后进行增量复核；当前不确认 TASK-007 accepted，不开始 TASK-008。

## 审查对象与边界

- 输入：silicon-task007-review.zip、result(20260910-164025).md。
- 基线：59f55c813aba62ec8f18dc5d5e7cc649b277aeca。
- 实现：1f19d3dc3c8dd967218e1083b95b0e4f75d4a61a。
- 样式提交：2fb0e796267711c36a6ba42ae19724cabb6c2127。
- 最终 HEAD：732089f2e812920c2e20b863cf9749b4dd6dad3e。

提交标识与干净工作树来自包内清单；本次未验证 Git 对象库、远程分支或 CI。独立审查了任务书、合同模型/服务/路由、文件适配器与清理、迁移、页面、相关测试和证据。未修改实现。

## R1 / P2：签约前未关联附件在签约后无法删除或回收

定位：apps/api/src/silicon/contracts/service.py，associate 第 112–120 行，尤其第 115 行；另见 sign 第 130–137 行、infra/clean_contract_files.py 及 Contracts.tsx 附件按钮。

复现流程：

1. 完善合同，上传并关联有效证明 A。
2. 再上传文件 B，但保持 pending；上传时合同未签，因此 supplemental=false。
3. 签约。签约只冻结 linked 文件，所以 B 不属于 signed_files 或原签约附件快照。
4. 删除 B 被 associate 的“已签且非 supplemental”条件直接拒绝，返回 409 CONTRACT_ALREADY_SIGNED；前端也禁用了该删除按钮。
5. 孤儿清理永久跳过 pending/linked 引用，因此等待超过 24 小时也不能回收 B。

影响：正常两阶段上传流程遗留无法处理的待关联记录和文件。它既不能被关联、下载或删除，也不属于不可变签约证据；与 ADR 所述“pending 遗留由授权用户显式删除”不一致。

独立验证：执行真实 associate 函数，将数据库访问边界替换为“已签合同 + 非补充 pending 文件”的固定返回；remove=True 得到 409，未执行 UPDATE。签约排除 pending、清理跳过 pending 的路径经源码核对。没有将此探针冒称真实 PG/API 复现。

修复要求：

- 根据是否被已签版本实际引用决定删除保护，允许当前有权限用户删除未被引用的 pending 文件。
- 不改变已冻结文件的内容、元数据、引用或已签快照；不把 B 静默改成原冻结附件。
- 若不支持签约后关联这类旧 pending，可继续阻断关联，并指引删除后以补充材料重新上传。
- 同步前端删除条件与后端生命周期规则；删除不应修改已签工作资料版本。
- 保持业务锁、当前权限、幂等、审计及物理回收边界。

必要回归：真实 PG/API 完成上述流程，删除 B 后清理只回收 B；A 下载/hash、签约内容及订单保持不变。覆盖重复删除命令重放、越权删除以及删除与签约竞争。组件验证旧 pending 的可删除状态。

## R2 / P2：仅凭头尾标记接受无法解析的签约证明

定位：apps/api/src/silicon/contracts/storage.py，validate 第 17–20、33 行；测试夹具见 apps/api/tests/test_contracts.py 的 PDF 常量。

独立执行 Store.validate，以下非文档内容均被接受：

```python
pdf = b'%PDF-1.4\nthis is plain text, no PDF objects or pages\n%%EOF'
jpg = b'\xff\xd8\xff' + b'not a JPEG image, plain text' + b'\xff\xd9'
store.validate('invalid-proof.pdf', pdf)  # application/pdf
store.validate('invalid-proof.jpg', jpg) # image/jpeg
```

对该 PDF 独立运行 pdfinfo，返回非零，报告无法读取 trailer/xref。它没有 PDF 页或对象；JPEG 同样没有可解码图像结构。

上传随后写为 pending，attach 和 sign 只复核文件存在性、长度/hash。由此，从源码可确认错误格式可以成为 linked proof 并满足证明材料存在条件。本次没有独立执行这条完整 HTTP 签约链。

影响：损坏文件或伪造格式被显示为“已就绪”，可作为不可变签约证据保存，用户下载后无法正常打开。现有测试主要检查 HTML、后缀不符、超限和明显动作关键字，未覆盖带正确头尾但内容无效的文件；测试中使用的简化 PDF 也不足以证明真实文档结构有效。

本项是任务书要求的文件内容类型/就绪校验问题，不要求此任务新增病毒扫描，不宣称已经发现任意代码执行或主动内容攻击。

修复要求：

- 在明确资源上限下进行可靠的 PDF 结构/页面可读性与 JPEG/PNG 解码或等价结构验证；不能只再增加几条魔数检查。
- 解析失败返回明确 4xx，不创建可关联附件；保留大小、扩展名、hash、私有存储与下载鉴权限制。
- 更新测试为真正有效的最小 PDF/JPEG/PNG，并添加正确头尾但损坏、截断、缺图像数据的反例。
- 如需解析依赖，选择范围最小的方案、固定版本并说明资源限制；不得把格式验证宣称为恶意软件扫描。
- 对已存在但未冻结的文件明确验证策略；不得改写旧签约文件来修复测试。

必要回归：真实上传 API 拒绝上述反例；合法三种格式仍可上传、关联、下载；失败不产生可见半完成文件。验证清理及 R1 路径，并保持签约和订单防重回归。

## 验证结果

本次独立执行：

| 检查 | 结果 |
| --- | --- |
| SHA256SUMS | 694 项通过 |
| npm run build，含 tsc --noEmit | 通过 |
| node --test apps/web/tests/*.test.* | 19 passed |
| infra/check_docs.py | 通过，含 228 个本地链接 |
| OpenAPI 导出及客户端生成 | 通过；两份契约文件再生成逐字节一致 |
| R1 服务层探针 | 复现错误拒绝删除 |
| R2 Store.validate 探针 | 复现两种无效格式被接受 |
| 无效 PDF 的 pdfinfo 检查 | 非零退出，结构不可解析 |
| 提交截图人工查看 | 查看签约确认桌面图和订单移动图，延续原样式方向 |

构建复用了当前环境既有依赖安装，未重新执行干净安装。

提交方证据：后端 154 passed / 9 warnings，其中新合同 30 项；实际 React+HTTP 替身合同 5、发布 5、报价 3 项；另有真实登录、签约、订单、下载、租户/角色及来源失效浏览器记录。上述结果归属于执行者，本 Reviewer 未在当前环境重跑完整 PostgreSQL/IdP、React DOM 或真实浏览器测试；当前环境缺少适用的 PG/IdP 运行条件。

测试成功并不覆盖本报告新增的两条附件反例。迁移证据采用生成旧业务数据、降至 0007 再升 0008 的方式，交付已准确披露；本次不将其描述为旧版本程序启动验证。

## C1：最终样式提交的截图证据尚未覆盖（非阻断备注）

交付明确说明截图早于 2fb0e796 样式细化提交，最终构建已通过。现有截图不能证明最终 HEAD 的控件视觉效果。请在上述修复的定向浏览器验收中补充最终版本桌面/移动截图，保留旧图和提交对应说明，无需重复全套历史截图。

## 后续交接

将本报告原样新增到 docs/reviews/TASK-007-732089f-review.md。只修复 R1/R2 并补齐定向证据；历史 result、失败日志与报告保留，用追加记录描述修复。

交付新实现/最终 HEAD、差异、真实回归结果和更新审查包，状态维持 review_ready。TASK-008 继续等待 TASK-007 的增量复核与明确验收。
