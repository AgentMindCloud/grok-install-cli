"""X (Twitter) posting helper.

Every write goes through a ``RuntimeSafetyGate`` — nothing is posted without
explicit approval. Actual HTTP calls are stubbed so this file works with no
credentials; users plug in their transport when wiring it to their app.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from grok_install.safety.scanner import RuntimeSafetyGate


class _HTTPClient(Protocol):
    def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]) -> Any: ...


@dataclass
class XPoster:
    """Thin facade over the X v2 API."""

    bearer_token: str
    gate: RuntimeSafetyGate
    http: _HTTPClient | None = None
    base_url: str = "https://api.x.com/2"

    def post_thread(self, posts: list[str]) -> list[str]:
        if not posts:
            raise ValueError("posts cannot be empty")
        self.gate.check("post_thread", {"posts": posts})
        ids: list[str] = []
        reply_to: str | None = None
        for body in posts:
            tid = self._create_post(body, reply_to=reply_to)
            ids.append(tid)
            reply_to = tid
        return ids

    def reply_to_mention(self, mention_id: str, body: str) -> str:
        self.gate.check("reply_to_mention", {"mention_id": mention_id, "body": body})
        return self._create_post(body, reply_to=mention_id)

    def _create_post(self, body: str, *, reply_to: str | None) -> str:
        payload: dict[str, Any] = {"text": body}
        if reply_to:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to}
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        if self.http is None:
            return f"dryrun-{hash(body) & 0xFFFF:x}"
        response = self.http.post(
            f"{self.base_url}/tweets", json=payload, headers=headers
        )
        if hasattr(response, "json"):
            data = response.json()
        else:
            data = response
        return str(data.get("data", {}).get("id", ""))
