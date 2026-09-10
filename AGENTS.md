# SILICON Engineering Instructions

## Mission
把硅屿两套 Demo 演进为可用的设备销售与服务经营工作台。
保留原视觉和交互意图；按 docs/tasks 中当前任务推进。

## Read order
1. 本文件及当前目录适用的更高优先级说明。
2. runtime/project.json 和当前任务书。
3. 任务相关的产品、架构、ADR、API 与设计基线。
4. docs/tasks/backlog.md 中最近任务状态和相关 Review。

## Working rules
- 先确认仓库、分支、工作树和 task_id；不覆写用户未提交改动。
- 每次只执行当前明确分配的任务；不以便利为理由跨任务大重构。
- 日常可逆实现、测试、修复和文档更新继续自主完成。
- 稳定保存 task_id、当前 commit、已完成内容、阻塞与下一步。
- 架构或业务不变量变化须写 ADR，并说明与原任务的关系。
- 原 Demo 的 dist 是已跟踪源码；不得当缓存删除。
- 不修改原 Demo 项目身份，不把它部署成生产系统。

## Invariants
- 金额与兼容校验以后端为准，所有金额用 Decimal/NUMERIC。
- 发布报价和签约合同是不可变快照，变更建立新版本。
- 所有业务查询/命令/文件/后台任务/Agent 都检查租户和权限。
- 库存通过受控移动台账修改；已过账记录用逆向记录更正。
- 幂等键、expected_version 和事务并发校验不可只放在前端。
- LLM 不直接改库；权限、计价和状态流转由确定性服务控制。
- 不伪造成功、测试、审批、外部发送或模型调用。

## UI
- 继承 docs/design/demo-baseline.md 和现有 token。
- 不引入新的后台模板替换现有设计。
- API 失败显示错误，不自动回退假数据。
- 关键改动保留相关视觉和端到端证据。

## Verification
- 从业务风险选择测试；PG 语义测试使用真实 PostgreSQL。
- 修改钱、库存、权限和 Agent 执行时必须覆盖边界/并发/逆向场景。
- 检查当前任务相关测试、迁移和构建；不用无关大规模测试掩盖缺失的关键验证。
- 测试未执行写 not_run 和原因，不能写 passed。

## Delivery
- 输出变更原因、文件、测试命令与结果、风险、commit。
- 生成 docs/tasks/<task-id>/result.md，进入 review_ready。
- 不自行将自己的任务标为 accepted。
- 不强推、不自动合并主分支、不上传密钥或真实数据。
- 上线、外部发送或不可逆数据操作遵守当前用户授权和发布流程；
  未授权时先交付可审查的变更和恢复方案。


## Current scope
- 当前只执行已明确分配的 TASK-007；状态以 docs/tasks/backlog.md 为准。
- TASK-000～TASK-006 已由产品/架构负责人确认 accepted；TASK-007 已明确分配，完成后进入 review_ready，不自动开始 TASK-008。
- runtime/project.json 所有路径相对仓库根解析；参考 checkout 是独立只读仓库，不入生产提交。
- 归档指南中的旧会话绝对路径是历史资料，禁止用作运行依赖。
