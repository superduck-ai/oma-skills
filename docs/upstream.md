# 同步官方来源

官方 `skills/claude-api` 是工作流、工具与 SDK 指南的唯一来源。根目录 `upstream.lock.json` 记录固定提交、来源文件摘要和发行文件摘要。`overlays/` 维护 OMA 部署差异；维护脚本中的 `IDENTITY` 定义产品名称、发现描述和标题。

## 更新

选择已审阅的完整提交 SHA，再运行：

```sh
python3 scripts/upstream.py sync --commit <40-character-commit-sha>
python3 -m unittest discover -s tests -v
python3 scripts/upstream.py check --online
```

工具仅下载 `anthropics/skills` 的固定提交，提取 `skills/claude-api`。生成的 `skills/oma-api/` 安装目录包含完整上游资源、一个 OMA 说明区块和一份部署参考。不要直接编辑生成目录。

修改 `overlays/` 后，使用当前锁定的提交重新运行 `sync`。本地官方 tarball 可通过 `--archive /absolute/path/archive.tar.gz` 提供；发布前仍运行在线来源校验。工具拒绝覆盖不符合上一次生成摘要的手工修改。

审阅更新时检查官方新增或变更的命令、工具与描述，优先删除已经可以被上游代替的 OMA 内容。只有实际存在且无上游对应的 OMA 功能，才添加独立扩展及其权威合同。

## 发行不变量

- 只有一个可安装的 `SKILL.md`，技能身份为 `oma-api`。
- 入口 name、description、标题和 Markdown 调用示例使用 OMA 身份；其他 metadata 保留。
- 原始入口前缀存入锁文件。还原前缀、移除 OMA 区块并逆转命令名后，所有来源文件恢复为官方原始字节。
- SDK 目录、工具定义、许可证及相对路径完整保留。
- 部署参考与 `overlays/deployment.md` 一致。
- 固定提交使用完整 SHA，不自动追踪 `main`。

`.gitattributes` 保留发行目录原始字节，避免 checkout 的换行转换破坏来源验证。维护工具按 Git 的 `0644` / `0755` 语义保留可执行位。

## 设计选择

本项目采用单一 canonical 技能目录。另一个可行方案是同时安装官方技能与独立 OMA 连接技能，但它要求宿主协调两个技能。当前方案让一次安装包含全部官方引用，同时以 `oma-api` 作为用户可识别的产品名称。

本地身份替换和入口插入均由脚本确定性生成。它处理明确的 OMA 目标，不替换官方访谈、工具处理、事件循环或应用迁移实现。
