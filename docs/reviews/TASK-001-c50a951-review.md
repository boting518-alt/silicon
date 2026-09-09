# TASK-001 R1/R2 增量复核

- 日期：2026-09-09
- 实际修复 commit：`c50a95126ec9de6c471c2425cde3dac5f9012993`
- 对照 commit：`8b7cf4a4a0dc1748e5142afb6b45876708febb1b`
- 原报告：[TASK-001-8b7cf4a-review.md](TASK-001-8b7cf4a-review.md)
- 结论：**passed**

## 范围与状态

HEAD 与指定修复 commit 一致，直接父提交为上述对照 commit，初始工作树干净，无后续修改需排除。已读取适用 AGENTS、任务书、原发现、修复结果与独立验证证据，检查全部增量。

本次提交包含六个文件：README、jobs.py、新增两项回归所在 test_platform.py、原报告纳入 Git、result.md 修复附录及 verification-r1-r2.txt。依赖、前端、数据库迁移、连接/超时设置、Worker 入口和原有测试夹具没有改变。

## R1：已解决

位置：`apps/api/src/silicon/shared/jobs.py:23–34`。

清理改为 MATERIALIZED CTE，先通过 `FOR UPDATE SKIP LOCKED LIMIT 100` 取得符合耗尽/过期条件的行锁，再在同一事务更新这些行。被其他事务锁住的耗尽任务不进入该批 UPDATE，后续 queued 任务领取可以继续；没有通过吞异常、放宽超时或删除清理逻辑掩盖问题。

实际复跑新增测试 `test_locked_exhausted_lease_does_not_block_queued_job`（test_platform.py 第 86～117 行）通过：A 处于耗尽且过期状态并被独立连接持锁，另一个线程在两秒内领取 B；断言发生在 A 的持锁事务退出前，且 A 仍为 running。释放锁后再次调用 claim，A 转为 failed/LEASE_EXHAUSTED，租约字段清空。这验证了原报告描述的真实锁竞争行为，不是只检查 SQL 文本或模拟返回值。

`test_exhausted_lease_cleanup_is_bounded`（第 120～132 行）也通过：101 条耗尽记录第一次只清理 100 条，下一次完成剩余一条。原有并发幂等入队、单胜者领取、普通锁跳过、租约 token/旧 Worker 拒绝、重试与 failed、独立进程和数据库重启持久化测试均通过。

未发现本次清理修改引入新的正确性问题。批量上限限制更新行数，不等同于对任意规模队列的查询耗时保证；本次不作大规模性能认证。

## R2：已解决

位置：`README.md:26–68`。

本机和 Compose 初始化路线现在明确二选一，其后共有“**两条路线都必须执行迁移**”章节，提供 `upgrade head`、`current` 两条命令，并要求确认 `0001_platform (head)` 后才启动 API/Worker。

文档还明确：Compose 新卷已执行角色 bootstrap，不重复本机 createdb/bootstrap；根目录 .env 两条 URL 必须指向同一选定数据库并分别使用运行/迁移角色；主机端口改变时同步 URL，原生初始化也显式指定端口；启动终端清除已导出的 URL，避免覆盖 .env。数据库 pg_isready、迁移完成、API ready 三个阶段不再混同。

已对照未变动的 Compose/bootstrap/migrate 配置与原审查上下文，没有发现新的步骤冲突。该结论是启动说明完整性的复核，不声称实际启动了 Docker。

## Reviewer 实际验证

从修复 commit 用 git archive 导出干净临时副本到 `/tmp/silicon-rereview-001-er9ffzim`。复用现有 Python 依赖环境，没有安装或更新依赖；通过显式 PYTHONPATH 指向临时副本，另行断言 silicon.shared.jobs 实际从该副本导入，避免误跑旧可编辑安装。原仓库实现未被改动。

实际执行：

```bash
# 工作目录：上述临时源码副本
PYTHONPATH=/tmp/silicon-rereview-001-er9ffzim/apps/api/src \
SILICON_TEST_PG_BIN=/opt/homebrew/opt/postgresql@17/bin \
/Volumes/Lenovo3/workspace/SILICON/silicon-workspace/.venv/bin/python -m pytest -v
```

结果：**退出 0，12 passed, 2 warnings in 3.65s**。包含新增两项及原有十项相关 PG/API/Worker 测试。两条警告仍为 Starlette/httpx 与 anyio BlockingPortal 弃用，未屏蔽。

已先检查未变动的 database fixture：使用 PostgreSQL 17.11 程序新建 `/tmp/silicon-test-*` 集群、动态回环端口和独立 socket 目录；所有测试连接被覆盖为该集群，结束通过 finally 停止并清理。测试在允许临时回环监听的执行环境完成，没有连接、停止或写入常驻 PostgreSQL。

其他实际检查：

| 检查 | 结果 |
|---|---|
| `git diff 8b7cf4a c50a951 --check` | 退出 0 |
| 临时副本运行 `infra/check_docs.py` | 退出 0，任务状态、相对路径、历史报告 hash、43 本地链接通过 |
| 提交关系与初始工作树 | 修复为直接子提交，HEAD 匹配，工作树干净 |
| 原报告保留 | 本次写报告前后 SHA-256 均为 `57ad643e89edab14558aed19a7e499c1396781ab0b46060bda59bbb2e06e1dce`，未修改 |

修复证据记录的“旧实现先跑新增测试得到两项失败”本次仅阅读，没有独立重跑旧实现；不将其记作 Reviewer 本次执行结果。以上通过结论来自本次真实修复版本测试。

## 未验证事项与结论边界

按增量范围未重复原 Demo、前端构建、外部依赖核验，也未启动 Compose 或远程 CI；本次差异不涉及这些实现。原报告对此类未验证项目的限制继续适用，不影响 R1/R2 关闭。未检查本机 PG 升级或备份恢复。

**passed**：R1、R2 均关闭，新增发现 0。保留原报告的历史 changes_requested 结论，以本报告记录修复后的增量通过。

仅新增本报告，不修改实现或任务状态，不提交、不标记 accepted、不开始 TASK-002。
