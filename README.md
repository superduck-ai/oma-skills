# OMA skills

面向 Open Managed Agents 部署的官方 Claude API / Claude Managed Agents 技能发行版。项目独立维护在 `superduck-ai/oma-skills`。

技能名称仍为 **`claude-api`**。官方描述、CMA 工具名称与 schema、onboarding、quickstart、任务 URL 分支、语言示例、`ant` CLI 和官方 SDK 均保留。OMA 只补充目标地址、凭证来源、部署模型目录及管理链接差异。

## 安装

通过标准 Agent Skills 安装器选择唯一技能：

```sh
npx skills add superduck-ai/oma-skills --skill claude-api
```

Claude Code 也可使用与官方仓库相同的 marketplace 结构：

```text
/plugin marketplace add superduck-ai/oma-skills
/plugin install claude-api@superduck-agent-skills
```

也可以直接把完整的 `skills/claude-api/` 目录放入宿主的技能目录。它是自包含的，不需要另装一个 `oma` 技能。它与官方版本占用相同的技能名称；在同一安装范围选择一个发行来源。

## 使用

显式选择 `claude-api`，说明目标为 OMA，再使用官方子命令。例如在支持 `$skill` 的宿主中：

```text
使用 $claude-api，为我的 OMA 部署执行 managed-agents-onboard。
```

官方的 `managed-agents-onboard`、quickstart 名称及任务 URL 参数保持原义。具体 slash 命令前缀由宿主决定。

在官方流程需要鉴权时，通过项目或宿主配置提供 `ANTHROPIC_BASE_URL` 和 `ANTHROPIC_API_KEY`。继续使用官方 `ant` 和 Anthropic SDK。本项目不定义默认 OMA 域名、新 CLI、SDK 包装器或额外环境变量协议。

由于保留了官方描述中的 provider 筛选规则，OMA 迁移请求应显式调用本技能。加载后，OMA 部署区块优先处理这类请求的连接和模型选择；其他请求继续遵循官方逻辑。

## 上游与本地改动

上游为 [anthropics/skills](https://github.com/anthropics/skills) 的 `skills/claude-api`，固定提交及文件摘要写入 [upstream.lock.json](upstream.lock.json)。

`skills/claude-api/` 由维护工具生成：

- 官方 `SKILL.md` 的 frontmatter 保持原样，仅在首个标题后插入有边界标记的 OMA 部署说明。
- 其余官方文件保持原始字节及 Git 可执行位。
- 新增 `oma/deployment.md`，来源为 `overlays/deployment.md`。

没有复制或改写另一套 CMA 流程，也没有把实例故障改成通用 API 限制。维护方式见 [上游同步](docs/upstream.md)，验证范围见 [验证说明](docs/validation.md)。

## 开发检查

```sh
python3 -m unittest discover -s tests -v
python3 scripts/upstream.py check
python3 scripts/upstream.py check --online
```

离线检查验证发行目录与记录的原始内容和部署区块一致；在线检查另外从官方固定提交取回来源并重新比较。检查失败不会自动重写文件。

本项目采用 Apache-2.0，保留上游许可证和来源说明，见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。
