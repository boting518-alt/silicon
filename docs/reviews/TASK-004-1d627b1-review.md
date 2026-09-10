# TASK-004 独立审查

日期：2026-09-10。Reviewer：本对话助手，直接读取源码与运行可用测试。

结论：**changes_requested**。发现两项 P2。未确认 P0/P1；这不代表未复跑的数据库、浏览器及生产路径全部安全。TASK-004 保持 review_ready，不开始 TASK-005。

## 来源与核验范围

- 审查包：silicon-task004-review.zip。
- 已验收基线：a6b640e6dd7f5ac1ecff40fa7f43cc5afe241d47。
- 交接：34d7cbce9014543c3600fce7b0ef55554c3b221b。
- 实现：400fb00c02dba02a5beb6b745c2aab064aa63fe3。
- 最终快照：1d627b1225430919efb1ba80ac400460f0b9db83。

提交身份依据包内 manifest、提交日志和 patch；本包不含 .git，没有独立访问原仓库远程，因此不把包内身份声明说成已对远程 Git 验证。独立运行 SHA256SUMS，271 个条目全通过；安装、生成和检查后再次全通过，原已打包文件未改变。

读取根 AGENTS、TASK-004 task/result、ADR-009、目录完整 models/routes/service、0005 迁移、前端 Catalog、请求上下文组件、相关身份事务代码、目录测试及差异清单；核对实现后收尾文件范围，查看最终六张截图。审查重点是目录发布/修订、SKU 生命周期、金额/价格区间、事务边界、权限复用、UI 和测试覆盖。没有声称逐行审查全部历史模块或全部原始日志。

## R1 · P2：修改 SKU 类别使已有包件草稿不可读，并连带阻断目录 UI 加载

位置：`apps/api/src/silicon/catalog/service.py` 69–90、131–134、162–169；`apps/api/src/silicon/catalog/routes.py` 的 GET /boms；`apps/web/src/Catalog.tsx` 33–38。

`save_sku` 允许更改 category，没有检查该 SKU 是否仍被准系统包件当作主体。草稿 `bom()` 每次读取都调用 `bom_snapshot(validate=False)`，但主体必须为 host 的检查不受 validate 开关控制。于是一个原本合法的草稿，可能因另一条成功的 SKU 修改变成 GET 422。

正常业务步骤：

1. 创建 host 类型 H，建立以 H 为主体的 package 草稿。
2. 使用当前 expected_version 将 H.category 改为 cpu；当前代码允许保存。
3. 读取该草稿，或它处于本页结果时读取 GET /catalog/boms，抛出 `422 PACKAGE_REQUIRES_HOST`。
4. 三类目录页面初始化都 Promise.all 请求 SKU/BOM/价格/规则；任一 BOM 读取失败阻止 install 全部数据。刷新后连商品页面也无法正常装载列表，用户难以通过 UI 把类别改回。SKU 单独 API 仍可用，不是数据丢失。

**实际证据级别：** 已用未修改的生产 `bom_snapshot` 做服务函数探针，只替换 SKU repository 读取，传入 category=cpu 的现存 package 主体，实际输出 `422 PACKAGE_REQUIRES_HOST`。写入允许、列表传播及前端连带失败依据完整调用路径静态检查；本次未执行真实 PG/HTTP 或浏览器重现这一缺陷。

建议：选择并明确 SKU 类别变更政策。可在持有现有目录写锁时拒绝会破坏现有引用的类别变更，提供稳定冲突错误；或允许草稿失效但保证读取仍返回可修复内容与 BLOCK。无论哪种，单条草稿问题不应让无关目录页面全部不可用。不能只吞掉异常并静默丢弃该记录。

回归要求：真实 PG/API 创建 H→建立草稿→修改类别→检查结果。若拒绝，确认修改整体回滚；若允许，确认列表、详情和修复操作可用。浏览器刷新三类目录页面不得被单个坏草稿阻断。

## R2 · P2：SKU 停用后，已有发布版本无法创建修订草稿

位置：`apps/api/src/silicon/catalog/service.py` 195–201、172–174、133/147，以及 237–242 的 revise_price、210–213。

`revise_bom` 直接把旧版本原内容交给 `save_bom(validate=True)`；`revise_price` 同样把旧条目交给 `save_price`。两条保存路径立即拒绝停用 SKU。修订 API 仅接受 expected_version，用户不能在创建修订时提交替换后的行。因此，一旦旧 BOM 的主体/直接部件或价格表某 SKU 停用，用户连可编辑的修订草稿都拿不到。

典型场景：旧电源停售，操作员停用旧 SKU，希望修订已发布包件换成新电源；或价格表有一项停售，要在下一修订删除它。当前只能临时重新启用旧 SKU，或建立与旧 family 无关的新记录，无法正常保持修订链。

**实际证据级别：** 服务函数探针调用真实 `revise_bom` 与 `revise_price`，仅替换已发布对象与当前 SKU 的 repository 读取：旧快照 enabled=true、当前 SKU enabled=false；分别输出 `422 DISABLED_SKU`，在新草稿插入前失败。BOM 探针使用停用主体；直接部件同样由 147 行拒绝，属于静态路径确认。没有将这些探针称为真实 PG/HTTP 复现。

建议：分离“复制历史内容成为待修复草稿”和“发布/启用时的业务有效性检查”。允许旧版生成含失效引用且明确标识的修订草稿，用户在草稿中替换/移除后再发布；或者提供原子复制并替换的修订命令。保留旧版、family、revision、租户/FK、防环及幂等约束。不得以修改历史快照或自动重新启用 SKU 绕过。

同时明确价格发布时的停用政策：当前 save_price 会拒绝停用 SKU，而 publish_price 不重新检查；不要修好 revise 后留下不清楚的发布语义。这是本修复的规则一致性关注点，不另立第三项缺陷。

回归要求：发布含部件 P 的 BOM/含 P 与另一有效 SKU 的价格表→停用 P→创建修订→替换/移除 P→保存并发布→旧版不变。旧修订在未解决失效项时按明示政策处理，不能显示虚假有效状态。

## 定向探针说明

探针保存在审查环境独立目录，未修改生产文件。使用 unittest.mock.patch 替换 service.sku/row/bom/price_book 的仓库读取，真实执行 bom_snapshot、revise_bom、revise_price 和其下游校验。不是数据库替代测试，也不验证事务或 RLS。

实际输出：

```text
R1 existing package after host category edit: 422 PACKAGE_REQUIRES_HOST
R2 revise published BOM after subject retired: 422 DISABLED_SKU
R2 revise price book after priced SKU retired: 422 DISABLED_SKU
Service-function probes only: repository reads substituted; not PostgreSQL or HTTP reproduction.
```

最小 R1 可复现代码（在锁定依赖环境中运行）：

```python
from uuid import uuid4
from unittest.mock import patch
from silicon.catalog import service
from silicon.catalog.models import Sku, BomInput
from silicon.identity.access import Denied
host = Sku(id=uuid4(), number='H', name='H', category='cpu',
           manufacturer='M', brand='B', brand_kind='own', version=2)
body = BomInput(name='existing package', kind='package',
                subject_sku_id=host.id, lines=[])
with patch.object(service, 'sku', return_value=host):
    try:
        service.bom_snapshot(None, body)
    except Denied as exc:
        print(exc.status, exc.code)
```

上述构造代表成功类别修改后的数据形态；验证完整写入和读取序列仍需新增真实 PG/API 回归。

## 独立实际执行

环境：Linux x86_64，Node 24.19.0、npm 11.9.0；uv 下载并使用 Python 3.12.7，Python 依赖按 uv.lock 安装。Node/npm 与原机略有差异，未冒称原机完全同版本。

| 检查 | 实际结果 |
|---|---|
| `sha256sum -c SHA256SUMS` | 前后两次 271 条通过，原文件未改 |
| `uv sync --locked` | 成功，Python 3.12.7，33 包安装，锁文件不变 |
| `npm ci --ignore-scripts` | 成功 |
| `node --test apps/web/tests/*.test.ts` | 14 passed，0 failed，0 skipped |
| `.venv/bin/python -m pytest apps/api/tests/test_oidc_validation.py -q` | 14 passed；JWT 校验替身测试，不是真实 IdP |
| `npm run typecheck`、`npm run build` | 成功，Vite 8.2.2、20 modules |
| export_openapi.py、npm run api:types | 成功，重新 SHA 校验确认生成文件与包中完全相同 |
| infra/check_docs.py | 成功，148 个本地链接及状态/历史报告等检查 |
| 生产服务函数定向探针 | 得到上述三个预期缺陷错误；仓库读取使用替身 |
| PG 17.11 下载/构建脚本 | 下载/配置开始，configure 因 `bison not found` 失败；未完成安装、未启动 PG |

没有将执行者的 66 passed 转写为我实际复跑通过。

## 其余审查与边界

- 目录读共享/写排他 advisory lock、身份/上下文检查、幂等及保存结果同事务的设计在已读路径中一致；本次没有独立 PG 并发证据，因此不宣称已认证其锁和 RLS 正确性。
- 发布 BOM 保存有类型快照，嵌套发布包件使用已冻结子快照；金额使用 Decimal/NUMERIC，重叠价格比较为同范围/币种/税口径和左闭右开时间段，存在企业级写串行保护。相关正向测试已阅读，但未复跑数据库部分。
- BLOCK/UNKNOWN 允许目录发布在 ADR-009 和 UI 中明确区分为内容冻结，不是兼容认证或正式报价发布；不凭此单独判缺陷。TASK-005 必须另设报价有效性门槛。
- 列表最多 100 项在 UI/ADR 中有说明，作为已声明首期限制；不是完整大目录分页体验。
- 实际打开并查看 final-sku-1440/390、final-bom-1440/390、final-price-1440/390 共六张 JPEG。可见范围保留浅灰底、深绿操作、细边框与桌面双列/手机单列表单；未见需另列的明显视觉问题。部分图处于滚动位置，不能证明整页所有控件或交互均合格。
- **真实 PG 全套、真实 Keycloak 集成：not_run。** 当前缺 PG 17.11，构建缺 bison；系统 Java 是 17 而非所需 21。没有为追求 passed 跳过 fixture 或换成 SQLite。恢复需完成隔离工具链准备后复跑。
- **真实浏览器交互：not_run。** 当前没有原授权字体和浏览器信任条件；没有修改系统信任或忽略 TLS。历史浏览器记录与截图仅作为证据阅读，不代表本次实时复现。
- 远程 CI、Compose、原 Demo 重演、生产部署均未执行；无用户常驻数据库访问。

## 修复交接

请执行者仅修复 R1/R2、增加真实 PG/API 和必要浏览器回归，保留本报告及历史证据；记录修复 base/head，状态保持 review_ready。修复后将更新的源码审查包和新增日志上传到本对话，由本 Reviewer 增量复核。不开始 TASK-005，不以“本地已有全部测试通过”代替新增场景验证。
