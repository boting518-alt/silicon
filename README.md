# 硅屿 SILICON

面向设备销售、组装、交付与售后团队的经营工作台。TASK-000 已由产品/架构负责人确认 `accepted`；当前 TASK-001 工程骨架为 `executing`。

## 阅读入口

1. [工程约束](AGENTS.md)、[相对路径配置](runtime/project.json)。
2. [产品边界](docs/product/scope.md)、[架构](docs/architecture/architecture.md)、[领域模型](docs/architecture/data-model.md)。
3. [Demo 基线](docs/design/demo-baseline.md)、[架构决策](docs/architecture/adr/ADR-001.md)、[待定事项](docs/architecture/open-decisions.md)。
4. [任务状态](docs/tasks/backlog.md)、[TASK-000 结果](docs/tasks/TASK-000/result.md)、[独立审查流程](docs/reviews/README.md)。

源指南原样归档在 docs/reference；其中旧会话路径仅为历史信息。当前执行规则以 AGENTS、任务书和对应 ADR 为准，冲突须记录，不能静默覆盖。

## 当前仓库

在只含输入指南的目录内新建独立 silicon-workspace；main 为本地初始分支，无 remote。不存在沿用的框架、包管理器或用户未提交代码。两份 Demo 作为同级独立参考 checkout 保持原身份。

TASK-000 已复核并 accepted，TASK-001 已明确分配，现开始工程骨架。具体版本、锁文件和运行命令由 TASK-001 验证后记录。参考 Demo 的静态启动方法见运行手册。

## 文档索引

- [API 契约](docs/architecture/api-conventions.md)
- [Agent 权限](docs/architecture/agent-policy.md)
- [指标定义](docs/architecture/metrics.md)
- [导入与运维目标](docs/runbooks/operations.md)
- [Demo 获取及本地启动](docs/runbooks/demo-sources.md)
- [TASK-001](docs/tasks/TASK-001/task.md)、[TASK-002](docs/tasks/TASK-002/task.md)、[TASK-003](docs/tasks/TASK-003/task.md)

技术组合为 React/TypeScript/Vite + FastAPI 模块化单体 + PostgreSQL + 独立 Worker + 私有对象存储。生产不继承 Sites Demo 的部署身份或托管配置。
