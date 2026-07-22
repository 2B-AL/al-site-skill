# 独立本地 Git 发布

## 支持边界

Site MCP 的原生 source 类型只有：

- `source_bundle`：由公共 Gateway 上传本地目录后得到的平台 OCI digest 与短期 receipt，独立于 Sandbox。
- `sandbox_handoff`：显式消费 `al-sandbox handoff` 返回的一次性 SourceBundle export grant；Site MCP 不持有长期 Sandbox endpoint/token。
- `git`：由 Site source importer 拉取固定 commit，独立于 Sandbox。
- `oci`：校验并部署固定 image digest，独立于 Sandbox。

`deploy-local-git` 使用 Git 方式；适合必须以远端 commit 为审计事实来源的发布。一般本地开发可直接使用 `deploy-local`，其大文件走独立二进制上传端点而不是 MCP JSON。

## 前置条件

- 项目是 Git 工作区。
- tracked 和 untracked 文件均无改动。
- HEAD 是固定 commit，并位于有名字的本地分支。
- 远端对应分支 ref 与本地 HEAD 完全一致。
- Site 构建网络能访问 repository。
- 私有仓库通过 `--credential-env` 提供 importer 支持的短期凭据。

## 命令

只保存版本：

```bash
python3 scripts/al_site.py save-local-git . --site-id SITE_ID
```

保存、等待 Ready、部署并等待 Ready：

```bash
python3 scripts/al_site.py deploy-local-git . --site-id SITE_ID
```

传 build/runtime override：

```bash
python3 scripts/al_site.py deploy-local-git . \
  --site-id SITE_ID \
  --build '{"mode":"dockerfile","dockerfile":"Dockerfile","path_prefix_aware":true}' \
  --runtime '{"port":8080,"health_path":"/healthz"}'
```

`--build` 和 `--runtime` 也支持 `@file.json`。

## 为什么 Git 模式拒绝脏工作区

Git 模式声明远端 commit 是输入事实，因此必须 fail closed：先 commit/push，再发布准确 SHA。需要发布工作区当前内容时应改用 `save-local`；它通过独立流式端点上传并由服务端生成同一种不可变 OCI SourceBundle，不会把文件塞进 1 MiB MCP JSON。
