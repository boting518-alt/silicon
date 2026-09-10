# TASK-004 结果

status: review_ready

## 提交与范围

- 用户已复核 base：`a6b640e6dd7f5ac1ecff40fa7f43cc5afe241d47`，main。
- 独立交接：`34d7cbce9014543c3600fce7b0ef55554c3b221b`。TASK-003 accepted，原样纳入增量审查，TASK-004 executing，补齐任务书。
- 实现及实际测试证据 head：`400fb00c02dba02a5beb6b745c2aab064aa63fe3`。本报告的 head 专指被测试的实现树；随后仅提交本报告、README、状态和清单，不把报告自身的提交号循环写入自身。最终文档提交号以 Git HEAD 和交付消息为准。
- 完整变更文件见 [清单](evidence/changed-files.txt)。原两个 TASK-003 报告及更早审查 SHA-256 均通过校验，历史结论与失败日志保留。起始只有未跟踪的增量报告，无已跟踪用户修改；未回退任何提交。

## 实现

新增 0005_catalog，十张租户目录表及运行角色 RLS/复合外键。SKU 制造商、销售品牌与有限结构化硬件规格分表；覆盖九类硬件、编号唯一、版本和启停。不建设供应商采购模块，不含内部成本。

包件/BOM 草稿、发布、修订及有来源的规则版本已贯通。发布冻结 SKU/规格/技术展开/规则/结果，旧父子记录数据库禁止修改；包含件不自动收费，技术替换不改价。图校验拒绝自引用、循环和无效数量，限制展开规模。已含与未含电源分别由真实测试和浏览器虚构样例验证。

价格表采用 NUMERIC(18,2)/Decimal、十进制字符串、CNY、税口径、范围、来源和左闭右开期间。未配置、零价、过期及未来价分别处理；已发布同口径期间重叠在并发锁内拒绝，新修订不能改写历史。不换算税额，无统一 13% 假设或隐式舍入。

所有接口沿用真实会话、membership、权限、预期企业/context、CSRF、幂等、expected_version 与审计。管理员维护，成员/只读角色可查。身份会话锁先于企业目录读共享/写排他事务锁；目录所有生产读写遵守相同顺序，多表聚合不混版本，切企业不会误投写入。选择企业级串行写是首期明确取舍，见 [ADR-009](../../architecture/adr/ADR-009.md)。

新增三类真实页面，复用硅屿 token/侧栏/面板和企业失效机制；旧响应代次保护覆盖目录所有命令。浏览器发现并修复 UTC 日期转换和编辑事件问题，最终桌面双列/手机单列表单已经复测。

## 实际验证

以下均在仓库根执行。数据库与 IdP 使用仓库夹具创建的独立临时实例，不连接、写入或停止常驻 PostgreSQL。

| 检查 | 命令 | 实际结果 |
|---|---|---|
| 完整后端，含真实 IdP | `SILICON_TEST_PG_BIN=/opt/homebrew/opt/postgresql@17/bin SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3" .venv/bin/python -m pytest apps/api/tests -q` | **66 passed，0 skipped，2 warnings，38.79s** |
| 目录真实 PG/API | 上述完整套件中的 `apps/api/tests/test_catalog.py` | 13 项，覆盖 CRUD、唯一、RLS/权限/跨租户 FK、包件/规则/版本、价格与边界、并发、幂等、CSRF/旧上下文及审计 |
| 聚合一致性 | `test_real_aggregate_read_waits_for_complete_write` 三种参数 | SKU 规格、BOM 子行、价格条目：事件同步读父后阻塞写，真实 PG blocking pid 验证等待，旧/新聚合完整 |
| 迁移/回归 | 完整套件 | 空库至 0005；0002/0003/0004 升级，其中 0004 原客户/联系人/身份/会话/租户任务保留。OIDC、会话、租户切换、CRM、Worker 领取/租约/重试/持久化/授权均回归 |
| 前端竞态/日期 | `node --test apps/web/tests/*.test.ts` | **14 passed，0 failed**；传输替身明确延迟成功 200，运行真实请求包装器，不以超时冒充 |
| 类型与构建 | `npm run typecheck`、`npm run build` | passed；Vite 8.2.2 构建成功 |
| API 契约 | `.venv/bin/python infra/export_openapi.py`、`npm run api:types` | passed；重复生成 SHA-256 完全一致 |
| Compose 配置 | `docker compose --env-file .env.example -f infra/compose.yaml config --quiet` | exit 0；仅配置验证 |
| 文档/历史报告 | `.venv/bin/python infra/check_docs.py` | passed；当前任务状态、相对路径、本地链接及原审查哈希 |
| 差异格式 | `git diff --cached --check`，交付后 `git diff --check a6b640e6dd7f5ac1ecff40fa7f43cc5afe241d47 HEAD` | passed；新文本证据仅规范化尾随空白，不改结果 |

命令及生成物哈希见 [验证记录](evidence/validation.json)，最终后端日志见 [full-tests-delivery.txt](evidence/full-tests-delivery.txt)。两条警告是现有 Starlette httpx/AnyIO 测试依赖弃用提示，未升级依赖。第一次套件失败源于升级夹具缺少 FORCE RLS 所需租户 GUC，已修正夹具并完整复跑；初期测试集合缩进/类型默认值问题的日志同样保留，不当作最终通过结果。

## 浏览器与截图

实际真实 IdP 登录 → A 创建 SKU → 含/不含电源包件 → BOM 发布/修订 → 有效价格/拒绝重叠/未来修订 → 刷新原版本保持，均完成。双标签切企业清除旧草稿，B 只读且无 A 数据，返回 A 不迁移草稿；会话失效、退出后保护、错误和键盘交互已检查。两个独立浏览器栈均正常清理。

详细步骤、日期修复差异及可复现命令见 [浏览器报告](browser-acceptance.md)。最终固定虚构夹具的三页面各 1440×900、390×844，共六张截图及哈希见 [截图清单](evidence/screenshot-manifest.json)。所有最终截图已经实际查看；初轮过程图仍保留，未更新原 Demo 基线冒充无差异。新维护状态原 Demo 没有，明确为沿用硅屿风格的新增页面。

## 限制与待独立审查

- `not_run`：远程 CI。当前无 remote；只报告本地命令。恢复条件为明确授权远程仓库/CI 并实际运行。
- `not_run`：容器运行实测。本次未启动 Docker 栈；恢复条件为专用容器环境实际迁移和运行检查。Compose 静态通过不替代容器实测。
- 示例规则仅有限平台检查，UNKNOWN 始终保留未覆盖范围；发布表示冻结目录内容，允许不完整包件的 BLOCK/UNKNOWN，不代表兼容认证或报价可发布。所有型号、价格和来源都是虚构数据。
- 首期目录写按企业串行，列表 UI 明示最多载入 100 条；SKU API 支持分页。大规模目录、完整配置器和供应商型号数据库不在本次范围。
- 发布价格不能缩短旧期间；未来修订必须不重叠。当前不实现税额/汇率、折扣、抵扣、利润或商业总价计算。
- 保留 production 拒绝启动；身份功能完成不等于生产运维就绪。未改证书信任、TLS 校验、原 Demo 或参考仓库元数据，未部署或创建远程。

TASK-004 保持 review_ready，等待独立审查；不自行 accepted，不开始 TASK-005。


## R1/R2 独立审查修复（2026-09-10）

status: review_ready。修复 base：`1d627b1225430919efb1ba80ac400460f0b9db83`；修复实现及回归证据 head：`04066fb5908b43146a45a16fdcc6ee4d83128130`。随后仅提交本节和增量文件清单，包中 final HEAD 明确记录收尾提交，不循环写入自身。上文 66 项通过等首次结果保持历史含义。

原 [审查报告](../../reviews/TASK-004-1d627b1-review.md) 从用户提供文件逐字节保存，SHA-256 `bd5f932eb7144d799f1b56e4307c8c7ea528b67b11e5bcdfb8987fea6b509531`，不修改 changes_requested 结论。判断 R1/R2 合理：真实 PG/API 首先复现 R1 列表 422 和 R2 价格修订 422，不将 Reviewer 的仓库替身探针冒充数据库证据。

- R1：允许 SKU 类别修改；已有 package 草稿类别不符时仍返回完整数据和 PACKAGE_REQUIRES_HOST/BLOCK，保存中间修复状态可行，发布重新校验并拒绝。没有丢弃单条记录或吞掉错误；三类目录加载请求均可用。
- R2：BOM/价格表复制历史成草稿与发布校验分离；停用主体/直接部件/价格 SKU 不阻止修订或草稿保存，停用项明确标示。发布在同一授权/目录锁事务重新校验，未修复项 422 DISABLED_SKU，包括停用前已经保存的价格草稿。修订链、幂等、expected_version、FK/RLS、防环和数量约束保留；不重新启用旧 SKU，不修改旧发布快照或条目。
- 价格响应增加只读 checks，前端展示草稿阻断原因。已发布价格 checks 为空，不表示当前销售授权；原历史价格查询语义未扩展。有限平台兼容 BLOCK/UNKNOWN 与停用/主体类别发布门槛明确区分，详见 ADR-009 新增节。

实际验证（命令环境为既有独立 PG 17.11、Keycloak 26.7.3、Java 21.0.6，不操作常驻数据库）：

| 检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest apps/api/tests/test_catalog.py -q`，前缀 `SILICON_TEST_PG_BIN=/opt/homebrew/opt/postgresql@17/bin` | 17 passed；新增 4 项覆盖类别修改、停用主体、停用部件、价格修订/移除/发布再检查，旧版完整响应保持 |
| `.venv/bin/python -m pytest apps/api/tests -q`，同 PG 前缀并设置 `SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3"` | 70 passed、0 skipped、4 warnings，43.71s；真实 OIDC、身份、CRM、Worker、空库/升级回归 |
| `node --test apps/web/tests/*.test.ts` | 14 passed，无失败/跳过 |
| `npm run typecheck`、`npm run build` | passed |
| `.venv/bin/python infra/export_openapi.py`、`npm run api:types` | passed；重复生成哈希一致 |
| `infra/check_docs.py`、Compose config、`git diff --check` | passed；新增原审查哈希校验 |
| 真实 HTTPS 浏览器定向回归 | passed；类别变化后三页面可加载，草稿发布阻断及修复；停用电源后修订移除、价格修订替换、刷新旧版保持；实际退出和栈清理完成 |

原始红/绿测试、完整回归、实际浏览器 DOM 和两张截图在 [新增证据目录](evidence/r1-r2/)，命令/哈希见 [validation.json](evidence/r1-r2/validation.json)，交互步骤见 [browser-notes.md](evidence/r1-r2/browser-notes.md)，修复文件见 [清单](evidence/r1-r2/changed-files.txt)。4 条 warning 为原 Starlette/AnyIO 弃用及既有并发 CRM 测试中的 Pydantic 元数据提示，未升级依赖。

本次无数据库迁移或旧快照重写，无视觉模板/CSS 改造。截图为定向 1280×720 操作证据，旧六张两视口基线保留，未重跑整套两视口视觉验收。远程 CI、容器运行、生产部署仍 not_run；没有改变证书信任、关闭 TLS、修改原 Demo、创建远程或开始 TASK-005。修复等待当前 Reviewer 增量复核，不自行 accepted。
