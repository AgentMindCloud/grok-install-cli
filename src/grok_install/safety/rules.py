"""Hard-coded safety rules.

Anything here is policy — not something the YAML can override. The scanner
walks every config against these lists before we touch the network.
"""

from __future__ import annotations

import re
from typing import Final

BLOCKED_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "image_gen_real_people",
        "mass_dm",
        "scrape_private_profile",
        "bypass_rate_limit",
        "delete_account",
        "sudo_run",
        "exfiltrate_credentials",
    }
)

HIGH_RISK_PERMISSIONS: Final[frozenset[str]] = frozenset(
    {
        "shell.exec",
        "x.write",
        "github.write",
        "net.write",
        "fs.write",
    }
)

SENSITIVE_ENV_PREFIXES: Final[tuple[str, ...]] = (
    "sk-",
    "xai-",
    "ghp_",
    "gho_",
    "ghs_",
    "ghu_",
    "bearer ",
    "aws_",
    "aws-secret",
)

_PATTERN_SECRET_IN_VALUE = re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"]?[\w-]{10,}")
_PATTERN_HARDCODED_XAI = re.compile(r"xai-[A-Za-z0-9]{20,}")
_PATTERN_HARDCODED_OPENAI = re.compile(r"sk-[A-Za-z0-9]{20,}")
_PATTERN_HARDCODED_GITHUB = re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")

BLOCKED_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "hardcoded-secret-generic": _PATTERN_SECRET_IN_VALUE,
    "hardcoded-xai-key": _PATTERN_HARDCODED_XAI,
    "hardcoded-openai-key": _PATTERN_HARDCODED_OPENAI,
    "hardcoded-github-token": _PATTERN_HARDCODED_GITHUB,
}

REQUIRE_APPROVAL_DEFAULT: Final[frozenset[str]] = frozenset(
    {
        "post_thread",
        "reply_to_mention",
        "post_image",
        "create_pr",
        "comment_on_issue",
        "run_command",
    }
)

# --- swarm rules ------------------------------------------------------------

SWARM_MAX_AGENT_COUNT: Final[int] = 16
SWARM_MAX_HANDOFF_FANOUT: Final[int] = 5

SWARM_WRITE_PERMISSIONS: Final[frozenset[str]] = frozenset(
    {
        "x.write",
        "github.write",
        "net.write",
        "fs.write",
        "shell.exec",
    }
)

# --- voice rules ------------------------------------------------------------

VOICE_MAX_RECORDING_SECONDS_WARN: Final[int] = 300

VOICE_PERMISSIONS: Final[frozenset[str]] = frozenset(
    {
        "audio.read",
        "audio.write",
        "audio.record",
    }
)
