# Security policy

## Reporting a vulnerability

Email `security@agentmind.cloud` with a reproducer and the commit hash you
tested. We triage within 72 hours and publish a CVE if the issue is exploitable.
Please do not open a public issue for suspected vulnerabilities.

## Threat model

`grok-install` takes untrusted YAML from the user and the internet and turns it
into LLM tool calls. The interesting boundaries are:

| Boundary | Enforced by |
|---|---|
| YAML → Pydantic | `core/models.py` — strict `extra="forbid"`, field validators |
| YAML → runtime tools | `core/registry.py` built-in list + `ToolRegistry.from_config` |
| Tool call → side effect | `safety/scanner.py` `RuntimeSafetyGate` |
| Network secrets | `safety/scanner.py` scans raw YAML for `xai-`, `sk-`, `ghp_` |

## Hard-blocked tool names

These names fail the pre-install scan and are refused at runtime even if the
user declares their own schema for them:

```
image_gen_real_people, mass_dm, scrape_private_profile,
bypass_rate_limit, delete_account, sudo_run, exfiltrate_credentials
```

## Approval gate

Every tool listed in `safety.require_human_approval` must pass through the
`RuntimeSafetyGate`. In the default CLI, that means an interactive prompt;
non-tty contexts deny automatically. There is no "auto-approve everything"
mode in the CLI itself — the library exposes `auto_approve=True` only for
tests and for callers who wrap the CLI with their own approval logic.

## Sandboxing `run_command`

`run_command` is declared in the built-in registry so agents can call it, but
**the sandbox is the host's responsibility**. The scanner emits a yellow finding
if `shell.exec` is granted without the `strict` safety profile. In Docker and
Vercel deploys we run as a non-root user by default.
