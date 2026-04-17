# Contributing to grok-install

Thanks for your interest! The goal is a small, auditable, no-surprise CLI.

## Setup

```bash
git clone https://github.com/agentmindcloud/grok-install-cli
cd grok-install-cli
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev,xai]'
```

## Running tests

```bash
pytest --cov=grok_install --cov-report=term-missing
```

We target 80%+ line coverage; CI fails below that.

## Lint + type-check

```bash
ruff check .
ruff format --check .
```

## Adding a built-in tool

1. Declare it in `src/grok_install/core/registry.py` with a full JSON-schema
   parameters block and the narrowest permission that works.
2. If the tool has side effects, add its name to `REQUIRE_APPROVAL_DEFAULT` in
   `src/grok_install/safety/rules.py`.
3. Add a test under `tests/test_runtime.py` that exercises the new schema.

## Adding a deploy target

Create a module under `src/grok_install/deploy/` that:

1. Defines a class with a `target: str` attribute, an `artifacts()` method that
   returns `list[DeployArtifact]`, and an `instructions()` method.
2. Is registered in `get_generator()` in `deploy/base.py`.
3. Has a parametrised test in `tests/test_deploy.py`.

## Pull requests

- Keep PRs small and single-purpose.
- Every new code path needs a test.
- Do not introduce new hard-blocked tool names without a short rationale in the
  PR description.

Thanks!
