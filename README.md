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
| `grok-install init [path] --name <slug>` | Scaffold a new agent project. |
| `grok-install validate [path] [--json]` | Validate YAML against the spec. |
| `grok-install scan [path] [--json]` | Pre-install safety scan (green / yellow / red). |
| `grok-install run [path] [-p PROMPT] [--agent NAME] [--dry-run]` | Run the agent locally against Grok. |
| `grok-install test [path]` | Dry-run with mock tools (no network). |
| `grok-install deploy [path] --target vercel\|railway\|docker\|replit [--force]` | Generate deploy config. |
| `grok-install install <github-url> [--dest DIR] [--run]` | Clone + scan + optionally run a remote agent repo. |
| `grok-install publish [path]` | Print awesome-grok-agents JSON metadata on stdout. |
| `grok-install --version` | Print the installed version. |

Pass `--json` to `validate` or `scan` for a schema-stable, machine-parseable
report on stdout. Exit codes: `0` ok, `1` validation/scan failed, `2` parse
error. Payloads carry a `schema_version` discriminator so downstream tools can
pin.

## Project layout

`grok-install` recognises any of these filenames as the primary config:
`grok-install.yaml`, `grok-install.yml`, `grok-swarm.yaml`, `grok-swarm.yml`,
`grok-voice.yaml`, `grok-voice.yml`. A sibling `.grok/` directory of
`*.yaml`/`*.yml` overlays is deep-merged into the primary config (last-write
wins per top-level key) — handy for environment-specific tweaks without
forking the main file.

Top-level blocks supported on the install spec: `llm`, `intelligence`,
`runtime`, `safety`, `promotion`, `tools`, `agents`, `swarm`, `voice`,
`deploy_targets`, `env`. Runtime `type` is one of `cli`, `x-bot`, `webhook`,
`scheduled` (requires a cron `schedule`), or `http`.

## Multi-agent swarm

Set `intelligence.multi_agent_swarm: true` and declare each agent's `handoff:`
list. At runtime `SwarmOrchestrator` drives the hops with a cycle guard, and
an agent can transfer control by calling the built-in `handoff_to` tool.

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
| Tool registry | ✗ | 17 built-ins |
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
