# 独立本地 SourceBundle 发布

## 数据路径

```text
local directory
  -> al-site preflight + deterministic tar.gz
  -> Site MCP JSON control: create multipart session
  -> direct exact-part PUT to short-lived TOS presigned URLs
  -> Site MCP JSON control: status / refresh / complete / abort
  -> Site Manager safe extract + canonicalize + secret scan
  -> platform-owned OCI source@sha256:...
  -> SaveSiteVersion(source_bundle + short-lived receipt)
  -> build -> scan -> preview -> deploy
```

本地文件不经过 MCP/APIG，也不进入 CRD、Secret 或 skill 状态文件。MCP 只转发不超过 1 MiB 的控制 JSON；分片通过精确、短期、只允许对应 object/upload/part 的 TOS URL 直传。请求不会向 TOS 发送 Site OAuth、conversation 或 trusted identity header。

中断续传状态保存在权限为 `0600` 的 `~/.al-site-mcp/uploads/<archive-sha256>.json`，只包含 caller-bound session token 和已完成分片 ETag，不包含 presigned URL。重试会与 TOS 的已上传 part 状态合并，并只刷新缺失 part 的 URL。最终 receipt 绑定当前 user/org/service caller，仅在同一进程中交给 `SaveSiteVersion`。

## 命令

只上传并保存版本：

```bash
python3 scripts/al_site.py save-local . --site-id SITE_ID
```

保存、等待版本 Ready、部署并等待部署 Ready：

```bash
python3 scripts/al_site.py deploy-local . --site-id SITE_ID
```

覆盖构建和运行配置：

```bash
python3 scripts/al_site.py deploy-local . \
  --site-id SITE_ID \
  --build '{"mode":"dockerfile","dockerfile":"Dockerfile","path_prefix_aware":true}' \
  --runtime '{"port":8080,"health_path":"/healthz"}'
```

`build.dockerfile` 始终相对于 `build.context`。项目结构为 `app/Dockerfile` 时，使用：

```json
{"mode":"dockerfile","context":"app","dockerfile":"Dockerfile","path_prefix_aware":true}
```

不要同时写 `context=app` 和 `dockerfile=app/Dockerfile`，否则实际解析路径会变成 `app/app/Dockerfile`。本地命令会在上传前验证解析后的 Dockerfile 确实存在。

Site workload 强制 `runAsNonRoot`。Dockerfile 最终阶段若显式设置用户，使用数字 UID/GID：

```dockerfile
USER 65532:65532
```

不要使用 `USER nonroot:nonroot` 等命名用户；kubelet 在启动镜像前不会读取镜像内的 `/etc/passwd` 来证明它不是 root。本地命令会提前拒绝显式的命名用户和 UID 0。若最终阶段没有显式 `USER` 或使用变量，客户端无法证明基础镜像的最终 OCI user，仍应由调用方确保它是数字非 root UID。

## 发布边界

- `.alignore` 可排除依赖缓存、测试产物和本地大文件。
- `.git`、`.env`、`.ssh`、`.aws`、`.kube`、`.docker/config.json`、`.npmrc`、`.pypirc` 等平台 denylist 永远不上传。
- 高置信 private key、AWS key、GitHub token、Slack token 会在客户端和服务端两次拒绝。
- symlink 必须保持在源目录内；socket、device、FIFO、hardlink archive 等特殊类型被拒绝。
- 客户端预检用于尽早阻止敏感文件离开本机；服务端规范化和扫描才是权威安全边界。
- 客户端同时预检 Dockerfile 相对路径和可确定的最终阶段用户；Sandbox export 与纯远端 Git 来源应在提交 `SaveSiteVersion` 前按同一规则检查源码。
- TOS 只承担短期传输 staging，不是 Site 的业务制品库；完成后唯一持久输入是平台 OCI SourceBundle digest。
- 同一内容在服务端得到内容寻址的 OCI digest。SiteVersion 只保存 digest 引用，不保存 archive。

## 与其他来源的关系

本地、Sandbox export 和 Git source 都收敛为同一种 OCI SourceBundle，后续 build/scan/preview/deploy 没有分叉。OCI image source 是唯一跳过 source build 的显式路径。
