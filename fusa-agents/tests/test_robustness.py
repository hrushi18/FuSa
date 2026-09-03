"""Bugs found by feeding the chain what real models and real users actually produce.

Each test below reproduced a crash: a JSONDecodeError, a pydantic ValidationError, or a
KeyError that ended the run with a traceback.
"""
import json

import httpx
import pytest

from fusa.tools import modeljson

HARA = "---\nid: HARA\nagent: sys-hara\n---\n\n### HZ-001\n- asil: D\n- text: x\n"


# ---- reading a verdict out of model output ----------------------------------

@pytest.mark.parametrize("raw,verdict", [
    ('{"verdict":"approved","findings":[]}', "approved"),
    ('Here is my review:\n```json\n{"verdict":"approved","findings":[]}\n```\nHope that helps.', "approved"),
    ('<thinking>checking clauses</thinking>\n{"verdict": "approved", "findings": []}', "approved"),
    ('{"verdict": "APPROVED", "findings": []}', "approved"),
    ('{"verdict": "Approve", "findings": []}', "approved"),
    ('{"verdict":"rework","findings":[]}', "rework"),
    ('{"verdict":"unclear","findings":[]}', "rework"),          # unreadable is never approval
])
def test_verdict_is_read_through_prose_fences_and_casing(raw, verdict):
    data = modeljson.extract_object(raw)
    assert modeljson.coerce_verdict(data, "HARA", "rev")["verdict"] == verdict


@pytest.mark.parametrize("raw", ["", "   ", "The document looks fine.", "```\nnot json\n```", None])
def test_unreadable_replies_yield_no_object(raw):
    assert modeljson.extract_object(raw) is None


def test_finding_fields_are_coerced_not_rejected():
    data = modeljson.extract_object(
        '{"verdict":"rework","findings":['
        '{"severity":"critical","description":"a"},'          # unknown severity, no id
        '{"id":"F-09","level":"low","message":"b","owner":"sys-sads"},'   # alias keys
        '"clause 6.4.2 not cited"]}')                          # a bare string
    out = modeljson.coerce_verdict(data, "HARA", "rev")
    assert [f["severity"] for f in out["findings"]] == ["blocker", "minor", "major"]
    assert [f["id"] for f in out["findings"]] == ["F-01", "F-09", "F-03"]
    assert out["findings"][1]["returns_to"] == "sys-sads"
    assert out["findings"][2]["description"] == "clause 6.4.2 not cited"


@pytest.mark.parametrize("review,expected", [
    ('Here is my review:\n```json\n{"verdict":"approved","findings":[]}\n```', "reviewed"),
    ('<thinking>ok</thinking>{"verdict":"approved","findings":[]}', "reviewed"),
    ('{"verdict":"rework","findings":[{"severity":"critical","description":"d"}]}', "rework"),
    ('', "rework"),
    ('The document looks fine to me.', "rework"),
])
def test_chain_survives_every_review_reply_shape(workspace, monkeypatch, review, expected):
    from fusa.agents.llm import LLM
    from fusa.orchestrator import Orchestrator

    monkeypatch.setattr(LLM, "complete", lambda self, s, u, stub=None:
                        review if "independent functional-safety reviewer" in s else HARA)
    st = Orchestrator(root=workspace, dry_run=False).run("sys-hara", log=lambda *a: None)
    assert st.value == expected


def test_unreadable_review_keeps_the_raw_reply_for_inspection(workspace, monkeypatch):
    from fusa.agents.llm import LLM
    from fusa.orchestrator import Orchestrator

    monkeypatch.setattr(LLM, "complete", lambda self, s, u, stub=None:
                        "I think it's fine." if "independent functional-safety reviewer" in s else HARA)
    orch = Orchestrator(root=workspace, dry_run=False)
    orch.run("sys-hara", log=lambda *a: None)
    raw = workspace / "_generated" / "HARA" / "HARA.review-raw.txt"
    assert raw.read_text() == "I think it's fine."
    assert orch.reg.process.get("HARA").review.findings[0].id == "F-PARSE"


# ---- provider replies -------------------------------------------------------

@pytest.mark.parametrize("payload,fragment", [
    ({"error": {"message": "content filtered"}}, "no choices"),
    ({"choices": []}, "no choices"),
    ({"choices": [{"message": {"role": "assistant"}}]}, "empty completion"),
])
def test_openai_style_reply_without_content_is_explained(monkeypatch, payload, fragment):
    from fusa.agents.llm import LLM, LLMResponseError
    monkeypatch.setattr(httpx, "post", lambda url, headers=None, json=None, timeout=None:
                        httpx.Response(200, json=payload, request=httpx.Request("POST", url)))
    with pytest.raises(LLMResponseError, match=fragment):
        LLM(provider="groq", dry_run=False, api_key="k").complete("s", "u")


def test_non_json_body_is_explained(monkeypatch):
    from fusa.agents.llm import LLM, LLMResponseError
    monkeypatch.setattr(httpx, "post", lambda url, headers=None, json=None, timeout=None:
                        httpx.Response(200, text="<html>gateway</html>", request=httpx.Request("POST", url)))
    with pytest.raises(LLMResponseError, match="non-JSON"):
        LLM(provider="groq", dry_run=False, api_key="k").complete("s", "u")


def test_asking_for_a_provider_uses_its_own_default_model():
    from fusa.agents.llm import LLM
    assert LLM(provider="groq", dry_run=True).model == "openai/gpt-oss-120b"   # not claude-sonnet-5
    assert LLM(provider="gemini", dry_run=True).model == "gemini-3.1-pro"


# ---- unknown / disabled agents ----------------------------------------------

def test_unknown_agent_id_suggests_near_matches(workspace):
    from fusa.orchestrator import Orchestrator, UnknownAgent
    with pytest.raises(UnknownAgent, match="did you mean sys-hara"):
        Orchestrator(root=workspace, dry_run=True).run("sys-har")


def test_disabled_agent_says_so(workspace):
    from fusa.orchestrator import Orchestrator, UnknownAgent
    with pytest.raises(UnknownAgent, match="enabled: false"):
        Orchestrator(root=workspace, dry_run=True).run("sw-arch")


def test_cli_reports_both_without_a_traceback(workspace, capsys):
    import fusa.cli
    assert fusa.cli.main(["--dry-run", "run", "sys-har"]) == 2
    assert "unknown agent" in capsys.readouterr().err
    assert fusa.cli.main(["--dry-run", "run", "sw-arch"]) == 2
    assert "enabled: false" in capsys.readouterr().err


# ---- damaged inputs ---------------------------------------------------------

def test_corrupt_status_board_is_set_aside_not_fatal(workspace):
    from fusa.orchestrator import Orchestrator
    (workspace / "_generated" / "process-status.json").write_text("{ truncated")
    orch = Orchestrator(root=workspace, dry_run=True)          # used to raise JSONDecodeError
    assert "unreadable" in orch.reg.process.load_warning
    assert (workspace / "_generated" / "process-status.corrupt.json").exists()
    assert orch.status()                                        # board still renders


@pytest.mark.parametrize("csv_text,fragment", [
    ("Element,Failure Mode,FIT\nx,y,1.0\n", "missing column"),
    ("element,mode,lam_fit,category\nx,y,not-a-number,SR\n", "row 2"),
    ("element,mode,lam_fit,category\nx,y,1.0,NOPE\n", "unknown category"),
    ("element,mode,lam_fit,category\n", "no data rows"),
])
def test_bad_fmeda_csv_names_the_problem(tmp_path, csv_text, fragment):
    from fusa.tools import metrics
    path = tmp_path / "f.csv"
    path.write_text(csv_text)
    with pytest.raises(ValueError, match=fragment):             # used to be KeyError / ValueError
        metrics.load_csv(path)


@pytest.mark.parametrize("fmt,text,fragment", [
    ("sarif", '{"runs":[', "not readable SARIF"),
    ("sarif", "[]", "must be an object"),
    ("cppcheck-xml", "<results", "not readable cppcheck"),
])
def test_damaged_tool_report_is_reported_not_parsed(tmp_path, fmt, text, fragment):
    from fusa.runners.parsers import PARSERS, ReportUnreadable
    path = tmp_path / "report"
    path.write_text(text)
    with pytest.raises(ReportUnreadable, match=fragment):
        PARSERS[fmt](path)


def test_a_crashed_analyser_leaves_pending_not_a_clean_scan(workspace, monkeypatch):
    """A truncated report must never read as 'no findings'."""
    from fusa.orchestrator import Orchestrator
    orch = Orchestrator(root=workspace, dry_run=True)
    spec, agent = orch.resolve("sec-scan")
    report = workspace / agent.cfg["report"]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text('{"runs":[')                   # analyser died mid-write
    content = agent.run()
    from fusa.tools import ids
    assert any("not readable SARIF" in p for p in ids.find_pending(content))
    assert not ids.parse_items(content)              # and no findings were invented


@pytest.mark.parametrize("text,fragment", [
    ("agents:\n  - id: x\n   bad indent: y\n", "could not be read"),
    ("agents:\n  - id: x\n    title: t\n", "agent 'x' is invalid"),
    ("- just\n- a list\n", "must be a mapping"),
])
def test_malformed_agents_yaml_names_the_row(tmp_path, text, fragment):
    from fusa.agents.registry import AgentsFileError, load_specs
    path = tmp_path / "agents.yaml"
    path.write_text(text)
    with pytest.raises(AgentsFileError, match=fragment):
        load_specs(path)


def test_bad_reqif_is_reported_cleanly(workspace, tmp_path, capsys):
    import fusa.cli
    path = tmp_path / "r.reqif"
    path.write_text("<REQ-IF")
    assert fusa.cli.main(["import-reqif", str(path), "--work-product", "SYS-REQ", "--prefix", "CR"]) == 2
    assert "not readable ReqIF" in capsys.readouterr().err


def test_ui_rejects_a_disabled_agent_up_front(workspace):
    from fastapi.testclient import TestClient
    from fusa.ui.server import create_app
    with TestClient(create_app(root=workspace, dry_run=True)) as c:
        assert c.post("/api/run/sw-arch").status_code == 404      # not a silent failure in a thread
        assert c.post("/api/run/sys-har").status_code == 404


def test_cli_metrics_exits_cleanly_on_a_bad_csv(workspace, tmp_path, capsys):
    import fusa.cli
    path = tmp_path / "f.csv"
    path.write_text("Element,FIT\nx,1.0\n")
    assert fusa.cli.main(["metrics", str(path)]) == 2
    assert "missing column" in capsys.readouterr().err
