"""Built-in tool registry.

YAML files usually list tools by name (``read_file``, ``post_thread``). When a
listed name matches an entry here we auto-expand it to a full xAI-SDK-compatible
schema. Unknown names must be declared in full under the ``tools:`` block.
"""

from __future__ import annotations

from typing import Any

from grok_install.core.models import RateLimit, ToolParameterSchema, ToolSchema

_BUILTINS: dict[str, ToolSchema] = {}


def _register(**kwargs: Any) -> None:
    tool = ToolSchema(**kwargs)
    _BUILTINS[tool.name] = tool


def _obj(properties: dict[str, dict[str, Any]], required: list[str]) -> ToolParameterSchema:
    return ToolParameterSchema(
        type="object", properties=properties, required=required
    )


# --- File ops ---------------------------------------------------------------

_register(
    name="read_file",
    description="Read the contents of a file from the sandboxed workspace.",
    parameters=_obj(
        {"path": {"type": "string", "description": "Relative path from workspace root."}},
        ["path"],
    ),
    permission="fs.read",
)
_register(
    name="write_file",
    description="Write text to a file inside the sandboxed workspace. Overwrites existing files.",
    parameters=_obj(
        {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        ["path", "content"],
    ),
    permission="fs.write",
)
_register(
    name="list_directory",
    description="List files in a directory.",
    parameters=_obj(
        {"path": {"type": "string", "description": "Directory path."}},
        ["path"],
    ),
    permission="fs.read",
)
_register(
    name="search_code",
    description="Search for a regex pattern across the workspace.",
    parameters=_obj(
        {
            "pattern": {"type": "string"},
            "path": {"type": "string", "description": "Optional subdirectory to limit the search."},
        },
        ["pattern"],
    ),
    permission="fs.read",
)

# --- Shell ------------------------------------------------------------------

_register(
    name="run_command",
    description=(
        "Run a shell command inside a sandboxed subprocess. "
        "The host MUST enforce the sandbox; this schema only describes the interface."
    ),
    parameters=_obj(
        {
            "command": {"type": "string"},
            "timeout_seconds": {"type": "integer", "description": "Default 30."},
        },
        ["command"],
    ),
    permission="shell.exec",
)

# --- X ops ------------------------------------------------------------------

_register(
    name="post_thread",
    description="Post a thread to X. Always requires human approval.",
    parameters=_obj(
        {
            "posts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ordered list of post bodies; first is the root.",
            }
        },
        ["posts"],
    ),
    permission="x.write",
    rate_limit=RateLimit(per="hour", max=4),
)
_register(
    name="reply_to_mention",
    description="Reply to an @-mention. Requires human approval.",
    parameters=_obj(
        {
            "mention_id": {"type": "string"},
            "body": {"type": "string"},
        },
        ["mention_id", "body"],
    ),
    permission="x.write",
    rate_limit=RateLimit(per="hour", max=20),
)
_register(
    name="search_x",
    description="Search X for posts matching a query.",
    parameters=_obj(
        {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
        },
        ["query"],
    ),
    permission="x.read",
)
_register(
    name="analyze_engagement",
    description="Summarise engagement metrics for a post.",
    parameters=_obj(
        {"post_id": {"type": "string"}},
        ["post_id"],
    ),
    permission="x.read",
)
_register(
    name="post_image",
    description="Attach an image to a post. Requires human approval.",
    parameters=_obj(
        {
            "image_url": {"type": "string"},
            "alt_text": {"type": "string"},
            "body": {"type": "string"},
        },
        ["image_url", "alt_text", "body"],
    ),
    permission="x.write",
    rate_limit=RateLimit(per="day", max=8),
)

# --- GitHub -----------------------------------------------------------------

_register(
    name="fetch_repo",
    description="Clone a public GitHub repo into the workspace.",
    parameters=_obj(
        {"url": {"type": "string"}},
        ["url"],
    ),
    permission="github.read",
)
_register(
    name="create_pr",
    description="Open a pull request. Requires human approval.",
    parameters=_obj(
        {
            "repo": {"type": "string"},
            "base": {"type": "string"},
            "head": {"type": "string"},
            "title": {"type": "string"},
            "body": {"type": "string"},
        },
        ["repo", "base", "head", "title", "body"],
    ),
    permission="github.write",
)
_register(
    name="comment_on_issue",
    description="Comment on a GitHub issue or PR.",
    parameters=_obj(
        {
            "repo": {"type": "string"},
            "issue_number": {"type": "integer"},
            "body": {"type": "string"},
        },
        ["repo", "issue_number", "body"],
    ),
    permission="github.write",
)

# --- Web --------------------------------------------------------------------

_register(
    name="web_search",
    description="Run a web search and return titles + snippets.",
    parameters=_obj(
        {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
        },
        ["query"],
    ),
    permission="net.read",
)
_register(
    name="fetch_url",
    description="Fetch a URL and return its text body.",
    parameters=_obj(
        {"url": {"type": "string"}},
        ["url"],
    ),
    permission="net.read",
)

# --- Memory -----------------------------------------------------------------

_register(
    name="save_memory",
    description="Persist a key/value memory for this agent.",
    parameters=_obj(
        {
            "key": {"type": "string"},
            "value": {"type": "string"},
            "scope": {"type": "string", "enum": ["session", "long_term"]},
        },
        ["key", "value"],
    ),
    permission="memory.write",
)
_register(
    name="recall_memory",
    description="Recall a previously stored memory by key.",
    parameters=_obj(
        {
            "key": {"type": "string"},
            "scope": {"type": "string", "enum": ["session", "long_term"]},
        },
        ["key"],
    ),
    permission="memory.read",
)


BLOCKED_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "image_gen_real_people",
        "mass_dm",
        "scrape_private_profile",
        "bypass_rate_limit",
        "delete_account",
        "sudo_run",
    }
)


def is_builtin_tool(name: str) -> bool:
    return name in _BUILTINS


def get_builtin_tool(name: str) -> ToolSchema | None:
    return _BUILTINS.get(name)


def iter_builtins() -> list[ToolSchema]:
    return list(_BUILTINS.values())
