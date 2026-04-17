"""YAML → Pydantic parser.
Supports the primary ``grok-install.yaml`` plus a ``.grok/`` directory of
overlay files that merge into the root config (last-write-wins per top-level
key). Parse errors include the source file and, where possible, the YAML line
number that caused validation to fail.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml
from pydantic import ValidationError
from grok_install.core.models import GrokInstallConfig


@dataclass(frozen=True)
class ParseError(Exception):
    """Raised when a YAML file fails to parse or validate."""
    path: Path
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.path}: {self.message}"


# ----------------------------------------------------------------------
# Custom constructor to inject __line__ on every mapping for nice errors
# ----------------------------------------------------------------------
def _construct_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[str, Any]:
    """Add __line__ key to every dict so we can show YAML line numbers in errors."""
    mapping = loader.construct_mapping(node, deep=True)
    mapping["__line__"] = node.start_mark.line + 1
    return mapping


# Register once at import time (safe + clean)
yaml.SafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _strip_line_markers(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: _strip_line_markers(v)
            for k, v in value.items()
            if k != "__line__"
        }
    if isinstance(value, list):
        return [_strip_line_markers(v) for v in value]
    return value


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, dict)
        ):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ParseError(path, f"cannot read file: {e}") from e

    try:
        # safe_load() + our custom constructor on SafeLoader = fully safe + line numbers
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as e:
        raise ParseError(path, f"invalid YAML: {e}") from e

    if not isinstance(data, dict):
        raise ParseError(path, "top-level YAML must be a mapping")
    return data


def _resolve_paths(target: Path) -> tuple[Path, list[Path]]:
    """Locate grok-install.yaml + any .grok/*.yaml overlays."""
    if target.is_file():
        primary = target
        root = target.parent
    else:
        root = target
        primary_candidates = [
            root / "grok-install.yaml",
            root / "grok-install.yml",
        ]
        primary = next((p for p in primary_candidates if p.is_file()), None)
        if primary is None:
            raise ParseError(root, "no grok-install.yaml found")

    overlays: list[Path] = []
    overlay_dir = root / ".grok"
    if overlay_dir.is_dir():
        overlays = sorted(
            p
            for p in overlay_dir.iterdir()
            if p.suffix in {".yaml", ".yml"} and p.is_file()
        )
    return primary, overlays


def load_config(target: str | Path) -> GrokInstallConfig:
    """Load & validate a config from a directory or a file path."""
    return parse_config(*_load_raw(Path(target)))


def _load_raw(target: Path) -> tuple[dict[str, Any], Path]:
    primary, overlays = _resolve_paths(target)
    merged = _read_yaml(primary)
    for overlay in overlays:
        merged = _deep_merge(merged, _read_yaml(overlay))
    return merged, primary


def parse_config(data: dict[str, Any], source: Path | None = None) -> GrokInstallConfig:
    """Validate a pre-loaded dict against the Pydantic spec."""
    cleaned = _strip_line_markers(data)
    try:
        return GrokInstallConfig.model_validate(cleaned)
    except ValidationError as e:
        lines = _format_validation_errors(e, data)
        header = str(source) if source else "config"
        raise ParseError(
            source or Path(header),
            "invalid grok-install config:\n " + "\n ".join(lines),
        ) from e


def _format_validation_errors(
    err: ValidationError, data: dict[str, Any]
) -> list[str]:
    out: list[str] = []
    for e in err.errors():
        loc = ".".join(str(x) for x in e["loc"])
        line = _lookup_line(data, e["loc"])
        suffix = f" (line {line})" if line else ""
        out.append(f"{loc}: {e['msg']}{suffix}")
    return out


def _lookup_line(data: Any, loc: tuple[Any, ...]) -> int | None:
    current: Any = data
    last_line: int | None = None
    for key in loc:
        if isinstance(current, dict):
            if "__line__" in current:
                last_line = current["__line__"]
            if key in current:
                current = current[key]
            else:
                break
        elif isinstance(current, list) and isinstance(key, int):
            if 0 <= key < len(current):
                current = current[key]
            else:
                break
        else:
            break
    if isinstance(current, dict) and "__line__" in current:
        last_line = current["__line__"]
    return last_line
