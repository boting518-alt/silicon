# TASK-002：身份与租户隔离

status: accepted
owner: 执行线程
reviewer: 独立上下文，待指定

## 目标与前置

TASK-001 通过独立复核，启动和测试已可复现。

必读：AGENTS.md、runtime/project.json、docs/design/demo-baseline.md、docs/architecture 下相关契约和 ADR、backlog 与前置任务 Review。

## 允许范围

identity、shared、迁移、Worker 租户上下文、开发 IdP、集成测试与文档；不扩展业务模块。

## 实施要求

接一个真实 OIDC IdP（本地 Keycloak），授权码登录、服务端 session、HttpOnly/Secure Cookie、CSRF；生产没有演示快捷登录。membership 验证后选择租户，分别检查角色、数据范围与字段权限。租户业务关系用复合外键；RLS 默认拒绝，事务设置上下文；运行角色非 owner、非 superuser、无 BYPASSRLS，迁移角色独立。审计涵盖登录/切租户/拒绝/受控修改；两个虚构租户用相同编号测试。提供最小受保护测试资源验证成本字段和附件元数据/下载授权边界，不提前开发附件完整产品。

## 验收与实际证据

未登录 401，无权限 403，跨租户详情统一 404；列表/搜索/导出/聚合不泄漏。连接复用切换租户无残留，无上下文拒绝；伪造 tenant_id 拒绝；成本字段按角色过滤；附件访问同样隔离。Worker 无租户或无授权拒绝并记审计。用实际运行角色执行直接 SQL RLS 测试及两租户同编号案例，验证 CSRF 拒绝与会话退出失效。未建模块用测试夹具覆盖边界，不声称全产品接口已测试。

执行者必须将每个检查拆为可运行的实际命令，记录环境版本、退出码、摘要、证据相对路径及 not_run 原因。不要在尚无实现时伪造测试命令已经通过。

## 不在范围

不自研生产密码体系，不使用超级用户测试冒充隔离完成，不引入真实人员或客户。

## 退出、失败与交付

交付 scoped commit、base/head、diff、docs/tasks/TASK-002/result.md，状态 review_ready。独立 Reviewer 在相同内容 commit 复现检查，输出 docs/reviews/TASK-002-<head-short>.md。失败记录复现与修复，不进入下一任务；执行者不自行 accepted。涉及迁移先在测试库验证，不能以代码回滚代替数据恢复；不部署、不外发。
