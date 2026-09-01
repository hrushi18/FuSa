"""Thin model client. Dry-run mode returns caller-supplied stubs so the whole
chain (orchestrator, gate, reviewer, status board) can be exercised offline."""
from __future__ import annotations

from typing import Callable

from .. import config


class LLM:
    def __init__(self, model: str | None = None, dry_run: bool | None = None, max_tokens: int | None = None):
        self.model = model or config.MODEL
        self.dry_run = config.DRY_RUN if dry_run is None else dry_run
        self.max_tokens = max_tokens or config.MAX_TOKENS
        self._client = None

    def complete(self, system: str, user: str, *, stub: Callable[[], str] | None = None) -> str:
        if self.dry_run:
            if stub is None:
                raise RuntimeError("dry-run requested but no stub supplied")
            return stub()
        if self._client is None:
            import anthropic  # imported lazily so dry-run needs no key
            self._client = anthropic.Anthropic()
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
