"""`.env` key loading — a real environment variable always wins."""
import os

from fusa import config


def test_loads_keys_and_ignores_comments(tmp_path, monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("FUSA_PROVIDER", raising=False)
    (tmp_path / ".env").write_text(
        "# a comment\n\nFUSA_PROVIDER=grok\nexport XAI_API_KEY = 'xai-from-file'\nnot a pair\n")
    try:
        assert set(config.load_dotenv(tmp_path / ".env")) == {"FUSA_PROVIDER", "XAI_API_KEY"}
        assert os.environ["XAI_API_KEY"] == "xai-from-file"     # quotes and `export ` stripped
        assert os.environ["FUSA_PROVIDER"] == "grok"
    finally:
        for k in ("XAI_API_KEY", "FUSA_PROVIDER"):
            os.environ.pop(k, None)


def test_real_environment_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-from-shell")
    (tmp_path / ".env").write_text("XAI_API_KEY=xai-from-file\n")
    assert config.load_dotenv(tmp_path / ".env") == []
    assert os.environ["XAI_API_KEY"] == "xai-from-shell"


def test_missing_file_is_not_an_error(tmp_path):
    assert config.load_dotenv(tmp_path / "nope.env") == []


def test_a_refused_key_is_a_config_error_not_a_crash(monkeypatch):
    """A key the provider rejects reads like the missing-key case, not a stack trace."""
    import httpx
    from fusa.agents.llm import LLM, LLMConfigError

    class Refused(httpx.Response):
        pass

    def fake_post(url, headers=None, json=None, timeout=None):
        return httpx.Response(401, text='{"error":"Incorrect API key provided."}',
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    llm = LLM(provider="groq", dry_run=False, api_key="gsk_wrong")
    try:
        llm.complete("s", "u")
        raise AssertionError("expected LLMConfigError")
    except LLMConfigError as e:
        assert "refused the request (401)" in str(e) and "Incorrect API key" in str(e)


def test_transient_failures_are_not_swallowed_as_config_errors(monkeypatch):
    import httpx
    from fusa.agents.llm import LLM, LLMConfigError

    def fake_post(url, headers=None, json=None, timeout=None):
        return httpx.Response(503, text="upstream busy", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    llm = LLM(provider="groq", dry_run=False, api_key="gsk_ok")
    try:
        llm.complete("s", "u")
        raise AssertionError("expected an error")
    except LLMConfigError:
        raise AssertionError("503 is transient, not a setup problem")
    except httpx.HTTPStatusError:
        pass


def test_example_file_documents_every_provider_key():
    """config.ROOT moves with FUSA_ROOT, so locate the shipped file from the package."""
    from pathlib import Path
    import fusa
    from fusa.agents.llm import PROVIDERS
    text = (Path(fusa.__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    for p in PROVIDERS.values():
        assert p["key_env"][0] in text
