"""A rate limit is transient, not a crash and not a setup problem.

One `run-all` fires roughly thirty model calls back to back, so a per-minute limit on a
shared endpoint is the expected path rather than an edge case. The client has to ride one
out, and when it cannot, it has to say what the provider actually said — a daily cap and a
momentary burst need different reactions from the person reading the log.
"""
from __future__ import annotations

import httpx
import pytest

from fusa.agents.llm import LLM, LLMConfigError, LLMRateLimitError

URL = "https://api.groq.com/openai/v1/chat/completions"
RATE_BODY = {"error": {
    "message": "Rate limit reached for model `openai/gpt-oss-120b` in organization org_x on "
               "tokens per minute (TPM): Limit 8000, Used 7800, Requested 6200. "
               "Please try again in 8.52s.",
    "type": "tokens", "code": "rate_limit_exceeded"}}
OK_BODY = {"choices": [{"message": {"content": "the work product"}}]}


def responder(monkeypatch, *responses):
    """Serve `responses` in order; record the sleeps the client asks for."""
    calls, slept = [], []
    queue = list(responses)

    def fake_post(u, headers=None, json=None, timeout=None):
        calls.append(u)
        status, body, hdrs = queue.pop(0) if len(queue) > 1 else queue[0]
        # a str body is a provider that answered with something other than JSON
        payload = {"content": body} if isinstance(body, str) else {"json": body}
        return httpx.Response(status, headers=hdrs or {},
                              request=httpx.Request("POST", u), **payload)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    return calls, slept


def groq(**kw) -> LLM:
    return LLM(provider="groq", dry_run=False, api_key="test-key", **kw)


def test_a_rate_limited_call_is_retried_and_then_succeeds(monkeypatch):
    calls, _ = responder(monkeypatch, (429, RATE_BODY, {"retry-after": "1"}), (200, OK_BODY, None))
    assert groq().complete("sys", "user") == "the work product"
    assert len(calls) == 2                      # it rode the limit out instead of dying


def test_the_client_waits_as_long_as_the_provider_asks(monkeypatch):
    _, slept = responder(monkeypatch, (429, RATE_BODY, {"retry-after": "9"}), (200, OK_BODY, None))
    groq().complete("sys", "user")
    assert slept == [9.0]                       # honoured, not a guess of our own


def test_without_a_retry_after_header_the_wait_still_backs_off(monkeypatch):
    _, slept = responder(monkeypatch, (429, RATE_BODY, None), (429, RATE_BODY, None),
                         (200, OK_BODY, None))
    groq().complete("sys", "user")
    assert len(slept) == 2 and slept[1] > slept[0]


def test_a_server_error_is_retried_too(monkeypatch):
    calls, _ = responder(monkeypatch, (503, {"error": "upstream"}, None), (200, OK_BODY, None))
    assert groq().complete("sys", "user") == "the work product"
    assert len(calls) == 2


def test_an_exhausted_limit_reports_what_the_provider_actually_said(monkeypatch):
    """The failure a person reads must name the limit, not link to an MDN page."""
    calls, _ = responder(monkeypatch, (429, RATE_BODY, {"retry-after": "1"}))
    with pytest.raises(LLMRateLimitError) as e:
        groq().complete("sys", "user")
    assert len(calls) > 1                       # it did try again before giving up
    assert "tokens per minute (TPM)" in str(e.value) and "Limit 8000" in str(e.value)
    assert "groq" in str(e.value)


def test_a_wait_longer_than_the_cap_fails_at_once(monkeypatch):
    """An hour-long Retry-After is a daily cap: no amount of waiting inside this run helps."""
    calls, slept = responder(monkeypatch, (429, RATE_BODY, {"retry-after": "3600"}))
    with pytest.raises(LLMRateLimitError) as e:
        groq().complete("sys", "user")
    assert len(calls) == 1 and slept == []      # never blocks the run for an hour
    assert "3600" in str(e.value)


def test_a_refused_key_is_never_retried(monkeypatch):
    calls, _ = responder(monkeypatch, (401, {"error": {"message": "Invalid API Key"}}, None))
    with pytest.raises(LLMConfigError):
        groq().complete("sys", "user")
    assert len(calls) == 1                      # a setup problem cannot be waited out


def test_each_retry_is_announced_so_the_run_log_shows_the_wait(monkeypatch):
    responder(monkeypatch, (429, RATE_BODY, {"retry-after": "2"}), (200, OK_BODY, None))
    said: list[str] = []
    llm = groq()
    llm.on_retry = said.append
    llm.complete("sys", "user")
    assert said and "429" in said[0] and "2" in said[0]


def test_the_cli_reports_a_rate_limit_as_one_line_not_a_traceback(workspace, monkeypatch, capsys):
    """The whole point of the fix is a readable failure — a traceback here would undo it."""
    import importlib

    import fusa.cli
    import fusa.config
    responder(monkeypatch, (429, RATE_BODY, {"retry-after": "1"}))
    monkeypatch.setenv("FUSA_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("FUSA_DRY_RUN", "0")            # the workspace fixture stubs the model out
    importlib.reload(fusa.config)
    code = fusa.cli.main(["run", "sys-hara"])
    err = capsys.readouterr().err
    assert code == 3                                   # transient: distinct from a setup problem (2)
    assert "tokens per minute (TPM)" in err and "Traceback" not in err


def test_a_wait_of_exactly_the_cap_is_still_waited_out(monkeypatch):
    """MAX_RETRY_WAIT is the longest wait this run will sit through, not the first it refuses."""
    from fusa.agents.llm import MAX_RETRY_WAIT
    _, slept = responder(monkeypatch, (429, RATE_BODY, {"retry-after": str(int(MAX_RETRY_WAIT))}),
                         (200, OK_BODY, None))
    assert groq().complete("sys", "user") == "the work product"
    assert slept == [MAX_RETRY_WAIT]


def test_a_limit_that_outlasts_every_retry_says_how_many_attempts_it_made(monkeypatch):
    """'still limited after 4 attempts' and 'asked for longer than we will wait' call for
    different reactions, and the count is the reader's evidence that we did try."""
    from fusa.agents.llm import MAX_RETRIES, MAX_RETRY_WAIT
    _, slept = responder(monkeypatch, (429, RATE_BODY, {"retry-after": str(int(MAX_RETRY_WAIT))}))
    with pytest.raises(LLMRateLimitError) as e:
        groq().complete("sys", "user")
    assert slept == [MAX_RETRY_WAIT] * MAX_RETRIES
    assert f"still limited after {MAX_RETRIES + 1} attempts" in str(e.value)


def test_an_error_body_that_is_not_json_is_still_quoted_back(monkeypatch):
    """A gateway's HTML page is the only explanation there is; dropping it leaves the log
    saying nothing about why the run stopped."""
    responder(monkeypatch, (429, "<html>too many requests</html>", {"retry-after": "3600"}))
    with pytest.raises(LLMRateLimitError) as e:
        groq().complete("sys", "user")
    assert "too many requests" in str(e.value)
