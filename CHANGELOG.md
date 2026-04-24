# Changelog

All notable changes to `grok-install` are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-04-19

### Added
- `--json` flag on `grok-install validate` for schema-stable,
  machine-parseable reports on stdout. Exit code is non-zero when the
  config fails validation (1) or fails to parse (2).
- `--json` flag on `grok-install scan` with the same exit-code contract
  (0 when no red findings, 1 when red findings exist, 2 on parse error).
- JSON payloads carry a `schema_version` discriminator so downstream
  consumers can pin.
- Parser now recognizes `grok-swarm.yaml` and `grok-voice.yaml` as valid
  project-config filenames, matching grok-yaml-standards@2.0+.
- Optional top-level `swarm` and `voice` objects on the install spec
  (passthrough fields for swarm-orchestration and voice-runtime settings).
- `CHANGELOG.md`, `DISCLAIMER.md`, and `.github/FUNDING.yml`.

### Changed
- Package version bumped to 0.2.0.

## [0.1.0] - 2026-04-18

### Added
- Initial release: YAML-driven Grok agent CLI with `init`, `validate`,
  `scan`, `run`, `test`, `deploy`, `install`, and `publish` commands.
- Pre-install safety scanner and runtime `RuntimeSafetyGate`.
- Deploy-config generators for Vercel, Railway, Docker, and Replit.
- Built-in tool registry covering file ops, shell, X, GitHub, web, and
  memory operations.
