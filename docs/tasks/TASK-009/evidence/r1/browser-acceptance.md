# TASK-009 R1 真实浏览器增量

结果：passed（本地执行者验证，不代表独立复核）。基准c08079e，旧证据不覆盖。

## 复现环境

从仓库根，使用锁文件准备Node24.15.0/npm11.12.1、Python3.12.7，设置 `SILICON_TEST_PG_BIN="$PG17_HOME/bin"`、`SILICON_TEST_KEYCLOAK_HOME="$KEYCLOAK_HOME"`。实际PG17.11、Keycloak26.7.3、Java21.0.6。准备步骤与固定哈希脚本沿用原 [浏览器记录](../../browser-acceptance.md)。既有可信localhost证书与字体为外部依赖，不打包私钥，不修改系统信任，不跳过TLS检查。

```bash
SILICON_BROWSER_ASSEMBLY=1 SILICON_BROWSER_INVENTORY=1 SILICON_BROWSER_CONTRACTS=1 SILICON_BROWSER_CATALOG=1 .venv/bin/python infra/browser_stack.py
```

打开 https://localhost:5173，真实IdP登录虚构alice / Fictional-alice-17!，选择企业A。独立栈只预置虚构订单和期初材料；全部装配与更正经页面点击完成。前端时钟固定2026-09-08，业务UTC实时。

## 实际步骤与证据

1. SO-CON-001、FINISHED、虚构用户甲创建工单b9a76a3a；确认需求，预留并领主体1件和内存2件，在制90元。
2. FIN-001首次完工到“虚构原料/A”，保存browser-original-device.txt。设备984d2050-84fb-47ba-87d4-5b6039d2a96e，实物95468174-9c35-40eb-a9aa-b821f6ce34bf。
3. 库存基础资料新增“虚构成品/更正库位”，回原工单填写更正原因，逆向原完工e23a4453。browser-reversed.txt显示在制90元、旧完工为历史、受控更正按钮。
4. 点击“更正原完工”，SN自动恢复FIN-001；选择新库位，确认框明确显示来源与历史保留。双击确认执行后只增加一次有效完工38cd2157，browser-corrected.txt：3件已领、WIP0、成品1，90=0+90。
5. 刷新页面再查设备，同一档案与实物ID，旧安装关闭、新安装有效；全部完工记录区分历史与当前，见browser-device-refreshed.txt。
6. 会话按测试期限失效，重新通过IdP登录。库存清单刷新仅FIN-001一件，位于“虚构成品/更正库位”，单位成本90，见browser-stock-refreshed.txt。未绕过会话或TLS检查。
7. 桌面1440×900截图device-desktop.jpg、history-desktop.jpg；移动实际innerWidth390/innerHeight844截图history-mobile.jpg。沿用原侧栏、配色和卡片；唯一有意变化是完工历史和更正引导。手机表格维持局部横向滚动，历史编号换行。
8. /tests/assembly-component.html复跑2项passed（真实React+HTTP替身）：创建响应丢失重试和跨企业迟到响应；component-regression.txt，不冒称真实PG。

结束只向本轮栈进程发SIGTERM，等待BROWSER_STACK_CLEANED；临时PG/IdP/文件目录自行清理，不操作常驻数据库。

not_run：其他浏览器引擎、真实采购新收货到装配全流程浏览器、远程CI、部署；旧TASK008文件下载限制及Reviewer未重跑的历史事实不改写。本轮采购阻止历史设备重复入库由真实PG/API测试覆盖。
