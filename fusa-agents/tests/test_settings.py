"""LLM provider settings: Grok (xAI) backend + dashboard settings endpoints."""
import pytest
from fastapi.testclient import TestClient

from fusa.agents.llm import LLM, PROVIDERS


@pytest.fixture
def client(workspace, monkeypatch):
    for var in ("XAI_API_KEY", "GROK_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY",
                "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    from fusa.ui.server import create_app
    app = create_app(root=workspace, dry_run=True)
    with TestClient(app) as c:
        yield c


def test_settings_lists_providers_and_defaults(client):
    s = client.get("/api/settings").json()
    assert s["provider"] == "anthropic"
    assert set(s["providers"]) == {"anthropic", "grok", "groq", "openai", "gemini"}
    assert s["providers"]["grok"]["key_env"] == ["XAI_API_KEY", "GROK_API_KEY"]
    assert s["providers"]["groq"]["key_env"] == ["GROQ_API_KEY"]
    assert s["providers"]["openai"]["key_env"] == ["OPENAI_API_KEY"]
    assert s["providers"]["gemini"]["key_env"] == ["GEMINI_API_KEY", "GOOGLE_API_KEY"]
    assert s["api_key_set"] is False


@pytest.mark.parametrize("provider,default_model", [
    ("groq", "openai/gpt-oss-120b"), ("openai", "gpt-5.6"), ("gemini", "gemini-3.1-pro")])
def test_switch_provider_uses_its_default_model(client, provider, default_model):
    s = client.post("/api/settings", json={"provider": provider, "api_key": "demo-key"}).json()
    assert s["provider"] == provider and s["model"] == default_model and s["api_key_set"] is True


def test_switch_to_grok_with_key_never_echoes_it(client):
    r = client.post("/api/settings", json={"provider": "grok", "model": "grok-4.6", "api_key": "xai-secret-123"})
    assert r.status_code == 200
    s = r.json()
    assert s["provider"] == "grok" and s["model"] == "grok-4.6" and s["api_key_set"] is True
    assert "xai-secret-123" not in r.text
    meta = client.get("/api/meta").json()
    assert meta["provider"] == "grok" and meta["model"] == "grok-4.6"


def test_unknown_provider_rejected(client):
    r = client.post("/api/settings", json={"provider": "no-such-provider"})
    assert r.status_code == 400
    assert "unknown provider" in r.json()["detail"]


def test_settings_rejected_while_busy(client):
    runner = client.app.state.runner
    assert runner.lock.acquire(blocking=False)
    try:
        assert client.post("/api/settings", json={"provider": "grok"}).status_code == 409
    finally:
        runner.lock.release()


def test_settings_test_in_dry_run(client):
    r = client.post("/api/settings/test").json()
    assert r["ok"] is True and "dry-run" in r["note"]


def test_grok_without_key_fails_fast(monkeypatch):
    for var in ("XAI_API_KEY", "GROK_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    llm = LLM(provider="grok", dry_run=False)
    with pytest.raises(RuntimeError, match="API key"):
        llm.complete("s", "u")


def test_grok_key_resolves_from_environment(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-env-key")
    assert LLM(provider="grok", dry_run=True).resolved_key() == "xai-env-key"


@pytest.mark.parametrize("provider,key_var", [
    ("groq", "GROQ_API_KEY"), ("openai", "OPENAI_API_KEY"), ("gemini", "GEMINI_API_KEY")])
def test_openai_style_provider_without_key_fails_fast(monkeypatch, provider, key_var):
    for env in PROVIDERS[provider]["key_env"]:
        monkeypatch.delenv(env, raising=False)
    llm = LLM(provider=provider, dry_run=False)
    with pytest.raises(RuntimeError, match=key_var):
        llm.complete("s", "u")


@pytest.mark.parametrize("provider,model,url,tokens_param", [
    ("groq", "openai/gpt-oss-120b", "https://api.groq.com/openai/v1/chat/completions", "max_tokens"),
    ("openai", "gpt-5.6", "https://api.openai.com/v1/chat/completions", "max_completion_tokens"),
    ("gemini", "gemini-3.1-pro",
     "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "max_tokens"),
])
def test_openai_style_provider_calls_its_endpoint(monkeypatch, provider, model, url, tokens_param):
    seen = {}

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "  hello  "}}]}

    def fake_post(u, headers=None, json=None, timeout=None):
        seen.update(url=u, headers=headers, payload=json)
        return FakeResponse()

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)
    llm = LLM(provider=provider, model=model, dry_run=False, api_key="test-key", max_tokens=123)
    assert llm.complete("sys prompt", "user prompt") == "hello"
    assert seen["url"] == url
    assert seen["headers"]["authorization"] == "Bearer test-key"
    assert seen["payload"]["model"] == model and seen["payload"][tokens_param] == 123
    assert seen["payload"]["messages"][0] == {"role": "system", "content": "sys prompt"}


def test_provider_switch_falls_back_to_provider_default_model():
    llm = LLM(dry_run=True)
    llm.configure(provider="grok", api_key="xai-x")
    assert llm.model == PROVIDERS["grok"]["default_model"]
    llm.configure(provider="anthropic")
    assert llm.model == PROVIDERS["anthropic"]["default_model"]
    llm.configure(model="grok-4-fast")            # explicit model always wins
    assert llm.model == "grok-4-fast"


GROK_HARA = """---
id: HARA
title: Hazard Analysis and Risk Assessment (assumed, SEooC)
agent: sys-hara
clauses: 26262-3:6
status: draft
---

## HZ-1 — Loss of pressure signal
- function: pressure sensing
- asil: D

### AOU-001
- text: the host evaluates the status word every cycle
"""


def test_grok_runs_sys_hara_through_the_gate(workspace, monkeypatch):
    """Full grok path minus the network: base_url, key, response parsing, id pass, gate."""
    import anthropic
    from fusa.models import Status
    from fusa.orchestrator import Orchestrator

    seen = {}

    class Block:
        type, text = "text", GROK_HARA

    class FakeClient:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.messages = self

        def create(self, **kwargs):
            seen["model"] = kwargs["model"]
            if "independent functional-safety reviewer" in kwargs["system"]:
                return type("R", (), {"content": [type("B", (), {"type": "text",
                    "text": '{"verdict": "approved", "findings": []}'})()]})()
            return type("R", (), {"content": [Block()]})()

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
    orch = Orchestrator(root=workspace, dry_run=False)
    orch.llm.configure(provider="grok")

    assert orch.run("sys-hara", log=lambda *a: None) == Status.REVIEWED
    assert seen["base_url"] == "https://api.x.ai" and seen["api_key"] == "xai-test-key"
    assert seen["model"] == "grok-4.6"

    rec = orch.reg.process.get("HARA")
    assert rec.gate.passed and not rec.gate.errors        # the AOU/HZ-1 output no longer fails
    content = (workspace / "_generated" / "HARA" / "HARA.md").read_text()
    assert "### HZ-001" in content and "#### AOU-001" in content


def test_unknown_provider_raises_in_constructor():
    with pytest.raises(ValueError, match="unknown provider"):
        LLM(provider="no-such-provider", dry_run=True)
