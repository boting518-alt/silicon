# R1/R2 浏览器回归

2026-09-10，真实内置浏览器、独立 PG/Keycloak，已有可信 localhost HTTPS；没有修改证书信任或忽略 TLS。沿用原虚构目录种子、字体与显示时钟。启动命令（仓库根）：

```bash
SILICON_BROWSER_CATALOG=1 SILICON_BROWSER_CATALOG_SEED=1 \
SILICON_TEST_PG_BIN="$SILICON_REVIEW_PG_BIN" \
SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3" \
.venv/bin/python infra/browser_stack.py
```

SILICON_REVIEW_PG_BIN 指向 Reviewer 自己的 PostgreSQL 17.11 bin。本机执行时 SILICON_TEST_PG_BIN 为 /opt/homebrew/opt/postgresql@17/bin。Keycloak 26.7.3 / Java 21.0.6，alice 为虚构测试身份。首次在栈就绪前打开页面得到 ERR_CONNECTION_REFUSED；等待 BROWSER_STACK_READY 后新标签正常登录，不是 TLS 绕过。结束真实退出，Ctrl-C 后 BROWSER_STACK_CLEANED，测试进程退出 0。

## R1 实际操作

1. 原已含电源包件创建 revision 2 草稿。
2. 在商品页将 DEMO-HOST 从 host 改为 cpu，保存成功，商品列表仍加载（r1-sku-loaded.txt）。
3. 刷新页面，进入价格维护与包件列表，均正常加载（r1-price-loaded.txt）。打开 revision 2 显示主体类别 BLOCK；发布被明确拒绝，仍可编辑（r1-bom-readable-blocked.txt）。
4. 用表单将主体替换为 DEMO-BARE，改名 R1 修复主体，保存并发布成功（r1-repaired-published.txt）。没有把单条草稿丢弃。

## R2 实际操作

1. 在商品页停用 DEMO-PSU；从 R1 修复主体已发布版创建下一修订成功，直接发布被拒绝（r2-bom-revision-blocked.txt）。
2. 编辑并移除旧电源，改名 R2 移除停用电源，保存发布成功（r2-bom-repaired.txt）。无电源的有限平台 BLOCK 保留；这与停用 SKU 的发布门槛不同。
3. 查看原始已含电源 revision 1，仍有两只虚构电源和原主体（r2-bom-old-unchanged.txt），旧快照不变。
4. 停用 DEMO-HOST，原价格表创建 revision 2 草稿成功，显示停用行 BLOCK；点击发布得到明确错误（r2-price-revision-blocked.txt、r2-price-blocked.jpg）。
5. 编辑将定价 SKU 替换为 DEMO-BARE，保存并发布成功（r2-price-repaired.txt）。刷新后原 revision 1 仍是 DEMO-HOST / 10000.50 / 原期间（r2-price-old-after-refresh.txt、r2-price-old.jpg）。旧 SKU 未自动启用。

两张截图为本次浏览器原始 1280×720 JPEG，均已查看，不覆盖旧 1440×900/390×844 基线。本次是定向功能回归，没有重新宣称全套两视口视觉验收；布局/CSS 未改，只增加停用项提示。价格“移除一项并保留另一项”及停用 BOM 主体的分支由新增真实 PG/API 测试验证；浏览器执行的是 BOM 移除部件、价格替换 SKU。

新增文本证据仅规范化行尾空白。旧截图、日志、审查报告保留原样。浏览器证据是实际点击/刷新，不是 API 测试替代。
