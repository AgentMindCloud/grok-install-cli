# grok-install

**The `npm install` for Grok agents.** Declare your agent in a single
`grok-install.yaml`, then install, run, and deploy it with one command.

[![CI](https://github.com/agentmindcloud/grok-install-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/agentmindcloud/grok-install-cli/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-3776ab.svg)](https://www.python.org/)
[![Works with xai-sdk](https://img.shields.io/badge/works%20with-xai--sdk-3f3f46.svg)](https://github.com/xai-org/xai-sdk)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)

---

## 60-second install

```bash
pip install grok-install
export XAI_API_KEY=...
grok-install init my-agent
grok-install run my-agent
```

That's it. Three commands from nothing to a live Grok agent answering prompts
at your terminal.

## Why this exists

Without `grok-install`, shipping a Grok agent means hand-rolling `xai-sdk`
boilerplate, wiring tools by hand, writing approval gates, and gluing a deploy
pipeline together. With `grok-install`, your agent is a YAML file:

```yaml
# grok-install.yaml
spec_version: "2.12"
name: hello-agent
llm:
  model: grok-2-latest
  api_key_env: XAI_API_KEY
runtime:
  type: cli
safety:
  safety_profile: balanced
agents:
  default:
    description: A friendly agent that can read files and search the web.
    tools:
      - read_file
      - web_search
```

The CLI handles the rest.

## Commands

| Command | What it does |
|---|---|
| `grok-install init` | Scaffold a new agent project. |
| `grok-install validate [path]` | Validate YAML against the spec. |
| `grok-install scan [path]` | Pre-install safety scan (green / yellow / red). |
| `grok-install run [path]` | Run the agent locally against Grok. |
| `grok-install test [path]` | Dry-run with mock tools (no network). |
| `grok-install deploy [path] --target vercel\|railway\|docker\|replit` | Generate deploy config. |
| `grok-install install <github-url>` | Clone + scan + run a remote agent repo. |
| `grok-install publish` | Print metadata for awesome-grok-agents submission. |

## Works with the official xAI SDK

Install the SDK extra when you need real model calls:

```bash
pip install 'grok-install[xai]'
```

`grok-install` never re-implements the SDK — it wraps it. Upgrade
`xai-sdk` on your own cadence without touching your agent config.

## Safety by default

Every project gets a pre-install scan that fails loudly on:

- Hard-coded API keys in YAML
- Writing tools without a rate limit
- `require_human_approval` missing for `post_thread`, `reply_to_mention`,
  `post_image`, `create_pr`, `comment_on_issue`, and `run_command`
- Reference to tools on the hard-block list (`mass_dm`, `bypass_rate_limit`,
  `image_gen_real_people`, ...)

At runtime every tool call passes through `RuntimeSafetyGate`, which blocks on
a CLI prompt until the user approves. There is no "skip the gate" flag.

See [SECURITY.md](./SECURITY.md) for the full threat model.

## Comparison vs hand-rolled SDK code

| | `xai-sdk` by hand | `grok-install` |
|---|---|---|
| Lines to get running | ~80 | 12 (YAML) |
| Built-in safety gate | ✗ | ✓ |
| Tool registry | ✗ | 20+ built-ins |
| Multi-agent swarm | DIY | `multi_agent_swarm: true` |
| Memory | DIY | SQLite, session + long_term |
| Deploy configs | DIY | `--target vercel\|railway\|docker\|replit` |

## Examples

- [`examples/hello-agent`](./examples/hello-agent) — a minimal working agent.
- [`examples/reply-bot`](./examples/reply-bot) — an X mention-reply bot with a
  human-in-the-loop approval gate.

## Spec

`grok-install` implements **grok-install.yaml v2.12**. See the top-level
`GrokInstallConfig` Pydantic model (`src/grok_install/core/models.py`) for the
authoritative schema.

## License

Apache 2.0 — see [LICENSE](./LICENSE).
