"""Thin model client. Dry-run mode returns caller-supplied stubs so the whole
chain (orchestrator, gate, reviewer, status board) can be exercised offline.

Providers (note grok ≠ groq):
    anthropic  Anthropic Messages SDK — api.anthropic.com (default;
               ANTHROPIC_BASE_URL redirects to a local server)
    grok       xAI's Anthropic-compatible endpoint (https://api.x.ai), same SDK
    groq       GroqCloud's OpenAI-compatible endpoint (https://api.groq.com/openai/v1)
    openai     api.openai.com/v1 (GPT-5 series uses max_completion_tokens)
    gemini     Google's OpenAI-compatible endpoint
               (https://generativelanguage.googleapis.com/v1beta/openai)

The OpenAI-style providers are called with httpx (ships with the anthropic SDK).

The API key is resolved from the constructor / `configure()` (dashboard settings)
first, then the provider's environment variables. It lives in process memory only
and is never written to disk."""
from __future__ import annotations

import json
import os
from typing import Callable

from .. import config

class LLMConfigError(RuntimeError):
    """The backend cannot be used as configured (no API key, a key or model it refuses).
    A user-fixable setup problem, not a bug — the CLI prints it as one line, not a traceback."""


class LLMResponseError(RuntimeError):
    """The backend answered, but with nothing usable (no choices, empty completion).
    Named so a caller can tell it from a transport failure."""


PROVIDERS = {
    "anthropic": {"label": "Anthropic (cloud, or local via ANTHROPIC_BASE_URL)",
                  "default_model": "claude-sonnet-5", "api": "anthropic",
                  "key_env": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")},
    "grok": {"label": "Grok (xAI)",
             "default_model": "grok-4.6", "api": "anthropic",
             "key_env": ("XAI_API_KEY", "GROK_API_KEY")},
    "groq": {"label": "Groq (GroqCloud — fast open models)",
             "default_model": "openai/gpt-oss-120b", "api": "openai-chat",
             "key_env": ("GROQ_API_KEY",)},
    "openai": {"label": "OpenAI",
               "default_model": "gpt-5.6", "api": "openai-chat",
               "max_tokens_param": "max_completion_tokens",
               "key_env": ("OPENAI_API_KEY",)},
    "gemini": {"label": "Gemini (Google)",
               "default_model": "gemini-3.1-pro", "api": "openai-chat",
               "key_env": ("GEMINI_API_KEY", "GOOGLE_API_KEY")},
}


class LLM:
    def __init__(self, model: str | None = None, dry_run: bool | None = None, max_tokens: int | None = None,
                 provider: str | None = None, api_key: str | None = None):
        self.provider = provider or config.PROVIDER
        if self.provider not in PROVIDERS:
            raise ValueError(f"unknown provider '{self.provider}' (choose from: {', '.join(PROVIDERS)})")
        # FUSA_MODEL applies to the configured provider; asking for another one gets its own
        # default, never a model id the other provider has never heard of.
        self.model = model or (config.MODEL if self.provider == config.PROVIDER
                               else PROVIDERS[self.provider]["default_model"])
        self.dry_run = config.DRY_RUN if dry_run is None else dry_run
        self.max_tokens = max_tokens or config.MAX_TOKENS
        self.api_key = api_key
        self._client = None

    def configure(self, *, provider: str | None = None, model: str | None = None,
                  api_key: str | None = None) -> None:
        """Runtime backend switch (dashboard settings). Drops the cached client."""
        if provider is not None:
            if provider not in PROVIDERS:
                raise ValueError(f"unknown provider '{provider}' (choose from: {', '.join(PROVIDERS)})")
            if provider != self.provider and model is None:
                self.model = PROVIDERS[provider]["default_model"]
            self.provider = provider
        if model:
            self.model = model
        if api_key:
            self.api_key = api_key
        self._client = None

    def resolved_key(self) -> str | None:
        """Explicitly configured key first, then the provider's env variables."""
        if self.api_key:
            return self.api_key
        return next((os.environ[v] for v in PROVIDERS[self.provider]["key_env"] if os.environ.get(v)), None)

    def _require_key(self) -> str:
        key = self.resolved_key()
        if not key:
            envs = " (or ".join(PROVIDERS[self.provider]["key_env"]) + (")" if len(PROVIDERS[self.provider]["key_env"]) > 1 else "")
            raise LLMConfigError(f"provider '{self.provider}' needs an API key — set {envs}, "
                                 "or enter it under ⚙ LLM in the dashboard")
        return key

    def _as_config_error(self, exc: Exception) -> LLMConfigError | None:
        """A key or model the provider refuses is a setup problem, not a crash. 429/5xx are
        transient and keep their own exception so a caller can tell the two apart."""
        status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
        if status not in (400, 401, 403, 404):
            return None
        body = getattr(getattr(exc, "response", None), "text", "") or str(exc)
        return LLMConfigError(f"provider '{self.provider}' refused the request ({status}) for model "
                              f"'{self.model}': {body.strip()[:300]}")

    def complete(self, system: str, user: str, *, stub: Callable[[], str] | None = None) -> str:
        if self.dry_run:
            if stub is None:
                raise RuntimeError("dry-run requested but no stub supplied")
            return stub()
        try:
            text = self._call(system, user)
        except (LLMConfigError, LLMResponseError):
            raise
        except Exception as exc:
            friendly = self._as_config_error(exc)
            if friendly is None:
                raise
            raise friendly from exc
        if not text.strip():                  # a reply of only reasoning/thinking blocks
            raise LLMResponseError(f"provider '{self.provider}' returned an empty completion for "
                                   f"model '{self.model}' — check the model id and max tokens")
        return text

    def _call(self, system: str, user: str) -> str:
        if PROVIDERS[self.provider]["api"] == "openai-chat":
            return self._complete_openai_chat(system, user)
        if self._client is None:
            import anthropic  # imported lazily so dry-run needs no key
            kwargs: dict = {}
            if self.provider == "grok":
                kwargs = {"base_url": config.GROK_BASE_URL, "api_key": self._require_key()}
            elif self.api_key:
                kwargs["api_key"] = self.api_key
            self._client = anthropic.Anthropic(**kwargs)
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")

    def _complete_openai_chat(self, system: str, user: str) -> str:
        """OpenAI-compatible chat completions (Groq, OpenAI, Gemini).
        httpx comes with the anthropic SDK."""
        key = self._require_key()
        spec = PROVIDERS[self.provider]
        base = {"groq": config.GROQ_BASE_URL, "openai": config.OPENAI_BASE_URL,
                "gemini": config.GEMINI_BASE_URL}[self.provider]
        import httpx
        r = httpx.post(
            base.rstrip("/") + "/chat/completions",
            headers={"authorization": f"Bearer {key}"},
            json={"model": self.model,
                  spec.get("max_tokens_param", "max_tokens"): self.max_tokens,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}]},
            timeout=300.0,
        )
        r.raise_for_status()
        try:
            body = r.json()
        except ValueError:
            raise LLMResponseError(f"provider '{self.provider}' returned a non-JSON body: {r.text[:300]}")
        choices = body.get("choices") or []
        if not choices:                       # content filter, quota notice, or an error body with 200
            raise LLMResponseError(f"provider '{self.provider}' returned no choices: "
                                   f"{json.dumps(body)[:300]}")
        return (choices[0].get("message", {}).get("content") or "").strip()
