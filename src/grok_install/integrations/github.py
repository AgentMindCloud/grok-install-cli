"""GitHub repo fetcher used by ``grok-install install <github-url>``."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_GITHUB_URL = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:|github:)"
    r"(?P<owner>[A-Za-z0-9][A-Za-z0-9._-]*)/"
    r"(?P<repo>[A-Za-z0-9][A-Za-z0-9._-]*?)(?:\.git)?/?$"
)


@dataclass(frozen=True)
class GitHubTarget:
    owner: str
    repo: str

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}.git"

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_github_url(url: str) -> GitHubTarget:
    m = _GITHUB_URL.match(url.strip())
    if not m:
        raise ValueError(f"not a GitHub URL: {url!r}")
    return GitHubTarget(owner=m["owner"], repo=m["repo"])


def fetch_repo(
    url: str,
    dest: str | Path,
    *,
    runner=subprocess.run,  # type: ignore[no-untyped-def]
) -> Path:
    """Clone the repo into ``dest``. Safe-by-default: ``--depth 1``."""

    target = parse_github_url(url)
    out = Path(dest)
    out.mkdir(parents=True, exist_ok=True)
    clone_path = out / target.repo
    if clone_path.exists():
        raise FileExistsError(f"{clone_path} already exists")
    runner(
        ["git", "clone", "--depth", "1", target.clone_url, str(clone_path)],
        check=True,
    )
    return clone_path
