# Changelog

All notable changes to `grok-install` land here. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 2.0.0 — 2026-04-18

### Added

- **Opt-in telemetry** (`grok_install.telemetry`). New CLI command group
  `grok-install telemetry enable | disable | status`. Telemetry is OFF by
  default; no network traffic happens without an explicit opt-in. Events
  carry only a coarse anonymous install id, CLI/Python versions, `sys.platform`,
  and timing/result fields — never paths, agent names, tool names, or any
  config contents. Set `GROKINSTALL_TELEMETRY=0` to force off system-wide.
- **Swarm safety scanner**. New pre-install checks for handoff cycles,
  fan-out, orphan agents, swarm-flag mismatch, oversized swarms, and
  privilege escalation across agent hand-offs.
- **Voice safety scanner**. New `voice:` block on `grok-install.yaml`
  (backwards-compatible — all fields default to off). New scanner rules for
  unbounded recording, voice + write combos in research profile, wake-word
  without approval gates, loose-profile recording storage, and dead audio
  permissions.
- New test fixtures: `tests/fixtures/voice.yaml`, `voice_bad.yaml`,
  `swarm_cycle.yaml`.

### Changed

- Package version bumped from `0.1.0` to `2.0.0`.
- Coverage floor raised from 80% to 90%.

### Security

- Scanner now catches cross-agent privilege escalation that was previously
  only enforced at runtime by `SwarmOrchestrator`.
- Telemetry has a hard allow-list of payload keys so that any future event
  accidentally carrying a path/name/tool is dropped before it leaves the
  process.

---

_GrokInstall is an independent community project. Not affiliated with xAI,
Grok, or X._
