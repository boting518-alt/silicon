# 独立审查

TASK-000 当前等待独立上下文审查，没有 passed 或 accepted 结论。

## 15. 独立 Reviewer 提示词与结果模板

Review 输入必须包含 base commit、head commit、任务书和可读仓库；不能仅把执行者一句“全部测试通过”转给 Reviewer。

```text
你是 SILICON 的独立 Reviewer。本次只审查指定 TASK，不实现新功能。
先读取任务书、AGENTS.md 和相关 ADR，然后检查 base..head 的实际 diff。
确认 head 与结果报告相同；仓库有后续改动时区分未审查内容。
复现与该任务风险直接相关的测试，检查未覆盖的边界和越权情况。
特别检查 UI 基线、金额/税/快照、库存/成本、租户、Agent 工具权限。
报告发现、文件位置、影响、复现方法和建议修复，不只总结做了什么。
结论只能是 passed、changes_requested 或 blocked。
没有源码/环境/关键测试证据时标记验证限制，不能无条件 passed。
不要自行修改截图基线、合并分支或部署。
输出 docs/reviews/<task-id>-<head-short>.md。
```

任务结果建议模板：

```yaml
task_id: TASK-000
status: review_ready
base_commit: <actual>
head_commit: <actual>
summary: <what and why>
changed_files: []
verification:
  - command: <actual command or inspection>
    result: passed | failed | not_run
    evidence: <report path or concise output>
acceptance:
  - criterion: <task criterion>
    evidence: <actual evidence>
known_limits: []
open_decisions: []
migration_impact: none
next_task: TASK-001
```

Review 严重性：P0 数据泄漏/不可恢复损坏；P1 金额、库存、权限或关键闭环错误；P2 有替代路径的功能问题；P3 文案/轻微样式。P0/P1 未修复不进入下一里程碑；不以“当前是 MVP”为由豁免核心交易正确性。

你发回本对话的最小材料：result.md、Review 报告、base/head commit、变更 diff 或可访问仓库、测试输出；UI 任务再加截图。若本对话无法访问代码，我会明确只做报告复核，不能替代代码审查。



本地首次提交为空审查基线；文档内容提交后另有结果证据提交。result.md 的 head_commit 固定被测内容提交，最终 delivery commit 用 git rev-parse HEAD 解析，避免把包含自身 SHA 的文件伪造成可实现的自引用。Reviewer 同时检查 base..head_commit 的内容 diff 与 head_commit..HEAD 的结果证据 diff。
