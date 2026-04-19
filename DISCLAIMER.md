# Disclaimer

`grok-install` is an **unofficial**, community-maintained CLI for declaring,
validating, running, and deploying Grok agents from a single YAML file.

- This project is not affiliated with, endorsed by, or sponsored by
  xAI Corp, X Corp, or Anthropic.
- "Grok" and "xAI" are trademarks of their respective owners. References to
  these names describe interoperability only.
- `grok-install` wraps — but does not re-implement — the official
  [`xai-sdk`](https://github.com/xai-org/xai-sdk). Upgrade the SDK on your
  own cadence.
- The pre-install safety scanner and `RuntimeSafetyGate` are best-effort
  defensive tools. They reduce common mistakes (hard-coded secrets, missing
  approval gates, blocked tool references) but do **not** replace:
    - A hardened sandbox host for `shell.exec` / `run_command`.
    - Independent security review of your agent's tool definitions and
      system prompts.
    - Rate-limiting and abuse detection on any third-party service the
      agent posts to.
- The CLI emits deploy-target artifacts (Dockerfiles, Vercel configs, etc.).
  You are responsible for reviewing those artifacts before shipping them to
  production.
- No warranty is provided. See [LICENSE](./LICENSE) (Apache 2.0) for the
  full disclaimer of warranties and liability.

If you discover a security issue, follow the responsible-disclosure
instructions in [SECURITY.md](./SECURITY.md).
