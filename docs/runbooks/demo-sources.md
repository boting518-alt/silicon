# 原 Demo 获取与本地启动

路径从生产仓库根解析，配置见 runtime/project.json。参考 checkout 当前在同级 silicon-quote-reference 与 silicon-workspace-reference，两者与生产仓库完全独立。

## 再次获取

通过 Sites get_site 核对 demo-baseline 中准确 project_id，list_site_versions 取得版本及源码 commit。使用官方 source credential，以每命令 HTTP Authorization header 认证克隆；不要把凭据写入 URL、配置、文件或日志。已有参考目录先检查身份、分支、工作树和 HEAD，不覆盖、不回退。新机器若无 Sites 权限，接收同 commit 源码 checkout/源码包并核验 hosting.json、完整文件和 hash；不能把网页文本当源码。访问失败标记 demo_source_pending，记录失败与恢复条件，继续非 UI 工作。

首次受沙箱网络限制解析失败，经允许的网络执行环境重试后两次克隆成功。本次只读远端，未 push 或部署。外置卷创建 ._*.idx 时 Git 可能报 non-monotonic index；本次逐文件 Git blob 比较均通过。不要删除或改动参考源码来“修复”；推荐健康本地文件系统新目录重新克隆后复核。

## 静态启动（本次 not_run）

没有 package.json、依赖安装或构建步骤；dist 是原生源码目录。从生产仓库根分别在两个终端启动：

```bash
python3 -m http.server 4171 --bind 127.0.0.1 --directory ../silicon-quote-reference/dist
python3 -m http.server 4172 --bind 127.0.0.1 --directory ../silicon-workspace-reference/dist
```

访问本地 4171 / 4172 端口；Ctrl-C 停止。若端口占用，人工指定其他端口并记入结果，不终止未知进程。以上是依据文件结构给出的启动方法，不是本次实际运行证据。TASK-003 明确浏览器授权后再建立固定视口截图；静态预览不涉及 Sites 发布。
