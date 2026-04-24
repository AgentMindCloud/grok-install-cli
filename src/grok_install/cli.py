"""Typer CLI for grok-install."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from grok_install import __version__
from grok_install.core.parser import ParseError, load_config
from grok_install.core.validator import validate_config
from grok_install.deploy.base import get_generator, write_artifacts
from grok_install.integrations.github import fetch_repo, parse_github_url
from grok_install.runtime.agent import AgentRunner
from grok_install.runtime.client import GrokClient
from grok_install.runtime.memory import MemoryStore
from grok_install.runtime.tools import ToolExecutor, ToolRegistry
from grok_install.safety.scanner import RuntimeSafetyGate, SafetyReport, scan_config

app = typer.Typer(
    name="grok-install",
    help="Install, run, and deploy Grok agents from a grok-install.yaml.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"grok-install {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: Optional[bool] = typer.Option(
        None, "--version", callback=_version_callback, is_eager=True
    ),
) -> None:
    """Root options."""


# --- init -------------------------------------------------------------------


_INIT_TEMPLATE = """\
spec_version: "2.12"
name: {name}
version: 0.1.0
summary: A Grok agent that says hello.
license: Apache-2.0

llm:
  provider: xai
  model: grok-2-latest
  api_key_env: XAI_API_KEY
  temperature: 0.7

intelligence:
  function_calling: true
  parallel_tool_calls: true
  multi_agent_swarm: false

runtime:
  type: cli
  permissions:
    - fs.read
    - net.read

safety:
  pre_install_scan: true
  minimum_keys_only: true
  safety_profile: balanced
  require_human_approval:
    - post_thread
    - reply_to_mention
    - post_image

agents:
  default:
    description: A friendly agent that can read files and search the web.
    tools:
      - read_file
      - web_search
    memory: session
"""


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Project directory to scaffold."),
    name: str = typer.Option("my-grok-agent", "--name", help="Agent slug."),
) -> None:
    """Scaffold a new agent project."""

    path.mkdir(parents=True, exist_ok=True)
    target = path / "grok-install.yaml"
    if target.exists():
        console.print(f"[yellow]!{target} already exists — not overwriting.[/]")
        raise typer.Exit(code=1)
    target.write_text(_INIT_TEMPLATE.format(name=name), encoding="utf-8")
    (path / ".grok").mkdir(exist_ok=True)
    (path / ".env.example").write_text("XAI_API_KEY=\n", encoding="utf-8")
    console.print(
        Panel(
            f"Scaffolded [cyan]{name}[/] in [bold]{path}[/]\n\n"
            "Next steps:\n"
            f"  export XAI_API_KEY=...\n"
            f"  grok-install run {path}\n",
            title="grok-install init",
            border_style="green",
        )
    )


# --- validate ---------------------------------------------------------------


@app.command()
def validate(
    path: Path = typer.Argument(Path("."), help="Config file or project directory."),
    json_output: bool = typer.Option(
        False, "--json", help="Emit a machine-parseable JSON report on stdout."
    ),
) -> None:
    """Validate a config against the grok-install spec."""

    if json_output:
        try:
            config = load_config(path)
        except ParseError as e:
            typer.echo(json.dumps(_parse_error_payload(e), indent=2))
            raise typer.Exit(code=2) from e
        report = validate_config(config)
        typer.echo(json.dumps(_validation_payload(report), indent=2))
        raise typer.Exit(code=0 if report.ok else 1)

    config = _load_or_exit(path)
    report = validate_config(config)
    _render_validation(report)
    raise typer.Exit(code=0 if report.ok else 1)


# --- scan -------------------------------------------------------------------


@app.command()
def scan(
    path: Path = typer.Argument(Path("."), help="Config file or project directory."),
    json_output: bool = typer.Option(
        False, "--json", help="Emit a machine-parseable JSON report on stdout."
    ),
) -> None:
    """Run the pre-install safety scan."""

    if json_output:
        try:
            config = load_config(path)
        except ParseError as e:
            typer.echo(json.dumps(_parse_error_payload(e), indent=2))
            raise typer.Exit(code=2) from e
        primary = _primary_file(path)
        raw = primary.read_text(encoding="utf-8") if primary else None
        report = scan_config(config, raw_text=raw)
        typer.echo(json.dumps(_scan_payload(report), indent=2))
        raise typer.Exit(code=report.exit_code)

    config = _load_or_exit(path)
    primary = _primary_file(path)
    raw = primary.read_text(encoding="utf-8") if primary else None
    report = scan_config(config, raw_text=raw)
    _render_scan(report)
    raise typer.Exit(code=report.exit_code)


# --- run --------------------------------------------------------------------


@app.command()
def run(
    path: Path = typer.Argument(Path("."), help="Config file or project directory."),
    prompt: str = typer.Option(
        "Hello!", "--prompt", "-p", help="Initial user message."
    ),
    agent: Optional[str] = typer.Option(
        None, "--agent", help="Named agent to start with."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Do not call the model; echo tool calls instead."
    ),
) -> None:
    """Run an agent locally against the configured Grok model."""

    config = _load_or_exit(path)
    agent_name = agent or next(iter(config.agents))
    console.print(f"[dim]Running agent[/] [bold]{agent_name}[/] from [cyan]{path}[/]")
    gate = RuntimeSafetyGate.from_config(config, callback=_cli_approval)
    registry = ToolRegistry.from_config(config)
    executor = ToolExecutor(registry=registry, gate=gate)

    if dry_run:
        console.print("[yellow]dry-run: using mock transport[/]")
        from grok_install.runtime.client import GrokClient as _GC

        class _Mock:
            def chat_completion(self, **_: object) -> dict:
                return {
                    "choices": [
                        {"message": {"content": "(dry-run) hello!", "tool_calls": []}}
                    ]
                }

        client = _GC(config.llm, transport=_Mock())
    else:
        try:
            client = GrokClient.from_config(config.llm)
        except RuntimeError as e:
            console.print(f"[red]{e}[/]")
            raise typer.Exit(code=2) from e

    memory = MemoryStore(":memory:")
    runner = AgentRunner(
        config, agent_name, client=client, executor=executor, memory=memory
    )
    result = runner.run(prompt)
    console.print(
        Panel(result.output or "(no output)", title=f"{agent_name}", border_style="cyan")
    )
    if result.tool_calls:
        console.print(f"[dim]{len(result.tool_calls)} tool call(s) executed.[/]")


# --- test -------------------------------------------------------------------


@app.command("test")
def test_cmd(
    path: Path = typer.Argument(Path("."), help="Config file or project directory."),
) -> None:
    """Dry-run an agent with mock tools (no network)."""

    run(path=path, prompt="hello (test)", agent=None, dry_run=True)  # type: ignore[arg-type]


# --- deploy -----------------------------------------------------------------


@app.command()
def deploy(
    path: Path = typer.Argument(Path("."), help="Project directory."),
    target: str = typer.Option(..., "--target", "-t", help="vercel|railway|docker|replit"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files."),
) -> None:
    """Generate deploy-target config files."""

    config = _load_or_exit(path)
    try:
        generator = get_generator(target)
    except KeyError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(code=2) from e
    artifacts = generator.artifacts(config)
    result = write_artifacts(
        target,
        artifacts,
        _project_root(path),
        instructions=generator.instructions(config),
        force=force,
    )
    for p in result.written:
        console.print(f"[green]wrote[/]   {p}")
    for p in result.skipped:
        console.print(f"[yellow]skipped[/] {p} (exists; pass --force)")
    console.print(Panel(result.instructions, title="next steps", border_style="cyan"))


# --- install ----------------------------------------------------------------


@app.command()
def install(
    url: str = typer.Argument(..., help="GitHub URL to clone."),
    dest: Path = typer.Option(Path.cwd(), "--dest", help="Clone destination."),
    run_after: bool = typer.Option(False, "--run", help="Run the agent after install."),
) -> None:
    """Clone, validate, and optionally run a remote grok-install project."""

    target = parse_github_url(url)
    console.print(f"[dim]Cloning[/] {target.slug}...")
    cloned = fetch_repo(url, dest)
    console.print(f"[green]ok[/] cloned to {cloned}")
    config = _load_or_exit(cloned)
    report = scan_config(config)
    _render_scan(report)
    if not report.ok:
        console.print("[red]scan failed — refusing to run[/]")
        raise typer.Exit(code=1)
    if run_after:
        run(path=cloned, prompt="Hello!", agent=None, dry_run=False)  # type: ignore[arg-type]


# --- publish ----------------------------------------------------------------


@app.command()
def publish(
    path: Path = typer.Argument(Path("."), help="Config file or project directory."),
) -> None:
    """Print the metadata that would be submitted to awesome-grok-agents."""

    config = _load_or_exit(path)
    payload = {
        "name": config.name,
        "version": config.version,
        "summary": config.summary,
        "authors": config.authors,
        "license": config.license,
        "safety_profile": config.safety.safety_profile,
        "tools": [t.name for t in config.tools] or sorted(
            {t for a in config.agents.values() for t in a.tools}
        ),
    }
    console.print(json.dumps(payload, indent=2))
    console.print(
        "[dim]Submit this JSON to https://github.com/agentmindcloud/awesome-grok-agents[/]"
    )


# --- helpers ----------------------------------------------------------------


def _load_or_exit(path: Path):
    try:
        return load_config(path)
    except ParseError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(code=2) from e


def _primary_file(path: Path) -> Path | None:
    if path.is_file():
        return path
    for name in (
        "grok-install.yaml",
        "grok-install.yml",
        "grok-swarm.yaml",
        "grok-swarm.yml",
        "grok-voice.yaml",
        "grok-voice.yml",
    ):
        candidate = path / name
        if candidate.is_file():
            return candidate
    return None


# JSON output payloads are schema-stable: the shape of these dicts is public
# API — consumers rely on the top-level keys and the "kind" discriminator.

_JSON_SCHEMA_VERSION = "1"


def _parse_error_payload(err: ParseError) -> dict:
    return {
        "kind": "parse-error",
        "schema_version": _JSON_SCHEMA_VERSION,
        "ok": False,
        "path": str(err.path),
        "message": err.message,
    }


def _validation_payload(report) -> dict:
    return {
        "kind": "validation",
        "schema_version": _JSON_SCHEMA_VERSION,
        "ok": report.ok,
        "issues": [
            {
                "level": i.level,
                "code": i.code,
                "message": i.message,
                "path": i.path,
            }
            for i in report.issues
        ],
    }


def _scan_payload(report: SafetyReport) -> dict:
    return {
        "kind": "scan",
        "schema_version": _JSON_SCHEMA_VERSION,
        "ok": report.ok,
        "findings": [
            {
                "severity": f.severity,
                "code": f.code,
                "message": f.message,
                "path": f.path,
            }
            for f in report.findings
        ],
    }


def _project_root(path: Path) -> Path:
    return path if path.is_dir() else path.parent


def _render_validation(report) -> None:
    if not report.issues:
        console.print("[green]✓[/] config is valid")
        return
    table = Table(title="validation")
    table.add_column("level")
    table.add_column("code")
    table.add_column("path")
    table.add_column("message")
    for i in report.issues:
        colour = {"error": "red", "warn": "yellow", "info": "cyan"}[i.level]
        table.add_row(
            f"[{colour}]{i.level}[/]", i.code, i.path, i.message
        )
    console.print(table)


def _render_scan(report: SafetyReport) -> None:
    table = Table(title="safety scan")
    table.add_column("severity")
    table.add_column("code")
    table.add_column("path")
    table.add_column("message")
    for f in report.findings:
        colour = {"green": "green", "yellow": "yellow", "red": "red"}[f.severity]
        table.add_row(
            f"[{colour}]{f.severity}[/]", f.code, f.path, f.message
        )
    console.print(table)


def _cli_approval(name: str, arguments: dict) -> bool:
    console.print(
        Panel(
            f"Agent wants to call [bold]{name}[/]\nArguments: {json.dumps(arguments, indent=2)}",
            title="approval required",
            border_style="yellow",
        )
    )
    if not sys.stdin.isatty():
        console.print("[dim]stdin is not a tty — denying for safety[/]")
        return False
    answer = input("Approve? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


if __name__ == "__main__":
    app()
