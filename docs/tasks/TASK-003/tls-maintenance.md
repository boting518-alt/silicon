# TLS 测试维护

2026-09-10，按用户明确要求进行独立维护，不改变产品认证语义。

仓库 real_oidc 夹具在生成测试证书后建立 ssl.create_default_context(cafile=cert)，断言 CERT_REQUIRED 和 check_hostname；将该上下文显式传给启动等待、主客户端、异浏览器和旧 Cookie 客户端。证书加载失败直接抛错，无关闭验证回退，无 Reviewer 临时适配器或路径依赖。夹具停止自己的进程后移除测试私钥、证书及 Keycloak 副本，保留诊断日志；不改变系统信任。

实际命令：

```bash
SILICON_TEST_PG_BIN="$(pg_config --bindir)" SILICON_TEST_KEYCLOAK_HOME="$PWD/.tools/keycloak/keycloak-26.7.3" .venv/bin/python -m pytest apps/api/tests/test_oidc_integration.py apps/api/tests/test_oidc_validation.py apps/api/tests/test_identity.py -v --tb=short
```

退出 0：26 passed，2 项已有弃用 warning，31.63 秒，无 skip。包含真实 Keycloak/HTTPS 登录回调退出、认证负向、真实 PG 权限与配置脚本测试。原始输出见 [tls-maintenance.txt](evidence/tls-maintenance.txt)。这不是浏览器点击或系统证书信任的验收。TASK-002 的原测试记录与独立审查报告未修改。
