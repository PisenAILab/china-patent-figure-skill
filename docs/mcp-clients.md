# MCP 客户端接入

本页是各类 AI 客户端接入「中国专利附图 Skill」的写法。工作台启动后（`pfk start`），MCP 与 REST 共用同一个 token。

MCP 端点是 `POST http://127.0.0.1:8790/mcp`，请求头 `Authorization: Bearer <token>`；token 由 `pfk start` 打印，也存在 `~/.config/patent-workbench/config.json`（`api_token`）。工具：列出工程、读零件、起名、候选分图、出图（异步）、导出附图包、画流程图——和浏览器用的是同一套服务。Agent 只写 plan，位置都由程序算。

| 客户端 | 配置在哪 | 写法 | 我们实跑过 |
| --- | --- | --- | :---: |
| **Claude Code** | 项目里的 `.mcp.json`，或 Skill | 见下 | ✅ Skill + MCP |
| **Claude Desktop** | `claude_desktop_config.json`（经 `mcp-remote`） | 见下 | — |
| **Cursor** | `.cursor/mcp.json` | 见下 | — |
| **Codex** | `~/.codex/config.toml` + [`AGENTS.md`](../AGENTS.md) | 见下 | ✅ AGENTS.md 路由 |
| **Windsurf** | `~/.codeium/windsurf/mcp_config.json` | 见下 | — |
| **Trae** | IDE 的 MCP 设置 → 手动配置（JSON） | 见下 | — |
| **CodeBuddy** | `~/.codebuddy/.mcp.json` 或项目 `.mcp.json`；`codebuddy mcp add` | 见下 | — |
| **Qwen Code** | `~/.qwen/settings.json`；`qwen mcp add` | 见下 | — |
| **Kimi Code CLI** | `~/.kimi-code/mcp.json`；TUI 里 `/mcp-config` | 见下 | — |
| **OpenClaw** | `~/.openclaw/openclaw.json` 的 `mcp.servers` | 见下 | — |

未标 ✅ 的写法按各家官方文档（2026-10-19 查阅）整理，我们还没有端到端跑过；文档里查不到的点标「待核」。写错了请提 issue。

<details>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add --transport http china-patent-figure http://127.0.0.1:8790/mcp --header "Authorization: Bearer <token>"
```

或 `.mcp.json`：

```json
{ "mcpServers": { "china-patent-figure": { "type": "http", "url": "http://127.0.0.1:8790/mcp",
  "headers": { "Authorization": "Bearer <token>" } } } }
```

Skill：把本仓库放到 `~/.claude/skills/china-patent-figure-skill/`，入口是 [`SKILL.md`](../SKILL.md)。
</details>

<details>
<summary><b>Claude Desktop</b></summary>

Claude Desktop 只启动 stdio 服务器，用 `mcp-remote` 桥到 HTTP 端点：

```json
{ "mcpServers": { "china-patent-figure": { "command": "npx",
  "args": ["-y", "mcp-remote", "http://127.0.0.1:8790/mcp",
           "--header", "Authorization: Bearer <token>"] } } }
```
</details>

<details>
<summary><b>Cursor</b></summary>

```json
{ "mcpServers": { "china-patent-figure": { "url": "http://127.0.0.1:8790/mcp",
  "headers": { "Authorization": "Bearer <token>" } } } }
```
</details>

<details>
<summary><b>Codex</b></summary>

```toml
[mcp_servers.china-patent-figure]
url = "http://127.0.0.1:8790/mcp"
bearer_token_env_var = "PFK_TOKEN"   # export PFK_TOKEN=<token>
```

Codex 与其他运行时的路由：[`AGENTS.md`](../AGENTS.md)。
</details>

<details>
<summary><b>Windsurf</b></summary>

```json
{ "mcpServers": { "china-patent-figure": { "serverUrl": "http://127.0.0.1:8790/mcp",
  "headers": { "Authorization": "Bearer <token>" } } } }
```
</details>

<details>
<summary><b>Trae</b></summary>

Trae 的 MCP 设置里选「手动配置」，HTTP 类型用 `url`，可带 `headers`（[官方文档](https://docs.trae.cn/ide/add-mcp-servers)）：

```json
{ "mcpServers": { "china-patent-figure": { "url": "http://127.0.0.1:8790/mcp",
  "headers": { "Authorization": "Bearer <token>" } } } }
```

待核：文档只说「HTTP 类型」，未区分 SSE 与 Streamable HTTP；中国专利附图 Skill 的 `/mcp` 是 Streamable HTTP。
</details>

<details>
<summary><b>CodeBuddy</b></summary>

用户级 `~/.codebuddy/.mcp.json`（或项目根 `.mcp.json`），`type` 为 `http`（[官方文档](https://www.codebuddy.ai/docs/cli/mcp)）：

```json
{ "mcpServers": { "china-patent-figure": { "type": "http", "url": "http://127.0.0.1:8790/mcp",
  "headers": { "Authorization": "Bearer <token>" } } } }
```

或命令行：`codebuddy mcp add --scope user --transport http china-patent-figure http://127.0.0.1:8790/mcp`（请求头待核：文档的 `add` 示例未给 `--header`，可改用 `codebuddy mcp add-json` 写入上面的 JSON）。
</details>

<details>
<summary><b>Qwen Code</b></summary>

`~/.qwen/settings.json`（Streamable HTTP 用 `httpUrl`，SSE 才用 `url`；[官方文档](https://qwenlm.github.io/qwen-code-docs/en/users/features/mcp/)）：

```json
{ "mcpServers": { "china-patent-figure": { "httpUrl": "http://127.0.0.1:8790/mcp",
  "headers": { "Authorization": "Bearer <token>" } } } }
```

或 `qwen mcp add --transport http china-patent-figure http://127.0.0.1:8790/mcp --header "Authorization: Bearer <token>"`。
</details>

<details>
<summary><b>Kimi Code CLI</b></summary>

`~/.kimi-code/mcp.json`（旧版 Kimi CLI 已归档，请用 Kimi Code CLI；[官方文档](https://moonshotai.github.io/kimi-code/en/customization/mcp)）：

```json
{ "mcpServers": { "china-patent-figure": { "url": "http://127.0.0.1:8790/mcp",
  "headers": { "Authorization": "Bearer <token>" } } } }
```

也可在 TUI 里用 `/mcp-config` 交互添加。待核：文档示例没有带 `headers` 的 HTTP 条目，`headers` 只在字段表里说明为「附加到每个请求的静态请求头」。
</details>

<details>
<summary><b>OpenClaw</b></summary>

`~/.openclaw/openclaw.json` 的 `mcp.servers`，远程服务器显式写 `transport`（[官方文档](https://docs.openclaw.ai/gateway/config-extensions)）：

```json
{ "mcp": { "servers": { "china-patent-figure": {
  "url": "http://127.0.0.1:8790/mcp", "transport": "streamable-http",
  "headers": { "Authorization": "Bearer <token>" } } } } }
```

待核：文档提到 `openclaw mcp set` 可写入同样的配置，本机 2026.3.8 版的 `openclaw --help` 未列出 `mcp` 子命令，以 `openclaw config schema` 的实际输出为准。
</details>

REST：`/v1/*`，交互文档 `http://127.0.0.1:8790/docs`，契约 [`docs/openapi.yaml`](openapi.yaml)。命令行：`pfk <工具>`（`analyze`、`render`、`annotate`、`qa`、`export`、`check`、`flowchart`、`suggest`…），退出码 `0` 通过、`1` 失败、`2` 用法错误。
