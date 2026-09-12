# TASK-013 R1/R2 增量修复

status: review_ready；仅本轮两项P2。基准706e032cce1d944d1b6566388789bba82308884d，原[独立报告](../../reviews/TASK-013-706e032-review.md)原样归档，不改结论。无用户未提交修改；历史结果和证据保留。

## R1：元数据同样执行来源权限

根因是未授权时只清值与明细，动态basis仍保留已发/待发样本数。统一metric出口现将未授权basis置为通用提示，reason继续使用通用权限说明。逐项检查：名称和单位是静态定义（集中度N来自公开筛选条件）；期间、截止日、阈值是请求条件；groups、value、贡献/注释/目标均已裁剪。不扩大角色权限。授权用户仍有准确样本解释。

真实PG/API覆盖0/1/2已发、2/1/0待发，先3 failed明确暴露动态文本，再3 passed。撤去delivery.read后overview不再返回数量说明，details返回403。组件新增200响应中的来源撤权：先打开授权说明，再焦点刷新并清空旧弹窗，重新打开只有通用说明。原焦点403、企业迟到成功响应、下钻快照变化回归保留。

## R2：期间流量与历史余额分开

根因是流量复用了余额confirmed()/as_of，并沿用全部资金历史的缺时点状态。现在期间收款/付款/两类退款只检查查询时已确认事实，以发生日归入[start,end)；逆向按自己的登记日归期。as_of只参与余额重建。当前confirmed状态和必填不可变发生日足够证明已知流量，不需要猜当年确认日；缺确认时间仍影响历史余额，不能因为无关计划缺确认时间遮蔽现金流。

固定2月期间：100收款、60付款、20客户退款、5供应商退款，净25。截止分别1/31、2/15、2/28，期间五项不变；未分配收款0/100/80、付款0/60/55。跨期原款及退款在1月、逆向在2月，则2月对应负贡献且与分页明细相加一致。补录历史发生日、缺计划/资金/退款确认元数据分别验证；未确认999草稿不纳入。旧测试的两条错误as_of现金流断言按固定期间修正，未改资金事实或迁移。

## 实际测试及失败保存

[验证清单](evidence/review-r1-r2/validation.json)记录准确命令。

- R1红：3 failed；绿：3 passed。
- R2红：固定期间首个as_of返回0而非100，1 failed；首次绿合并4 passed。
- 扩展分析：21 passed、3 failed，失败仅因新建未确认资金夹具漏必填notes；补齐夹具后新增审查测试8 passed。
- 完整非OIDC后端286 passed/13 warnings/373.90秒；含旧分析16项及身份、CRM、资金、交付、Worker、并发、迁移。真实OIDC另行执行以避免与浏览器Keycloak抢端口，1 passed/27.84秒。不会把拆分命令声称为一次全套运行。
- 实际React+HTTP替身8 passed；Node19 passed；类型检查、构建、OpenAPI/客户端重复生成逐字节一致通过。原测试及证据没有被新结果覆盖。

## 真实浏览器复现及结果

从仓库根使用既有锁定依赖和PG17.11/Java21.0.6/Keycloak26.7.3，设置 `SILICON_TEST_PG_BIN`、`SILICON_TEST_KEYCLOAK_HOME`。准备已有合法字体 `.tools/visual/PingFang.ttc` 及可信localhost证书/私钥 `.tools/tls/`，不打包私钥、不改信任、不忽略TLS。

运行：`SILICON_BROWSER_ANALYTICS_REVIEW=1 SILICON_BROWSER_CONTRACTS=1 .venv/bin/python infra/browser_stack.py`。它自建并清理隔离PG/IdP/API/文件目录；只能用于虚构夹具，不是生产认证入口。不要同时运行真实OIDC测试。

1. 浏览 https://localhost:5173，真实IdP登录 alice / Fictional-alice-17!，选企业A。
2. 固定期间2026-09-01至2026-09-13（不含），依次选择余额截止8/31、9/5、9/12。真实页面实收均80.00；前两个历史应收为0，9/12应收110.00。打开收款说明，明确截止日不截断流量。夹具是9/1发生、当前测试时确认；符合查询时已知口径。
3. 授权用户打开完工至首发说明，保留“经营样本1个；未发0个”。
4. 切企业B后80.00/110.00消失；退出并完成Keycloak确认，受保护数据清空。
5. 登录 carol / Fictional-carol-17!（夹具无delivery.read及finance.read），企业A同期间，打开样本说明，只有通用权限提示，没有经营样本或待发数量。两视口1440×900、390×844保存截图；移动端innerWidth/innerHeight实测390/844。
6. React测试另在/tests/analytics-component.html运行8项，明确为HTTP替身，不冒充数据库或上述浏览器流程。

实际浏览器和截图均来自最终修复实现，未改变产品布局。图片是工具输出JPEG，实际像素会缩放；详见[截图清单](evidence/review-r1-r2/screenshots.json)。旧截图与证据保持原样。关闭测试页面并恢复viewport，SIGTERM触发BROWSER_STACK_CLEANED，只清理本轮栈。

## 边界

无新迁移、无依赖升级、无角色默认授权扩大、无原始资金或发布快照变更。余额缺确认时间继续采用原保守历史不足规则，本轮只修正期间现金流。原标准财务周转率缺资料、地区为当前资料等产品限制仍在。未重跑不相关旧模块的单独浏览器流程或全部旧React夹具；后端核心回归已完整执行，前端实现未变。远程CI未核实；不部署、不开始TASK014、不自行accepted。

审查包用 `infra/package_task013_review.py --review-base 706e032cce1d944d1b6566388789bba82308884d --implementation <修复提交> --destination <新目录>/silicon-task013-review.zip` 导出最终HEAD完整源码，同时提供原验收基线和本轮基线差异，校验旧报告和旧TASK013证据字节不变、result前缀保留。
