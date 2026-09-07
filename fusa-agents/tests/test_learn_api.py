import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(workspace):
    from fusa.ui.server import create_app
    with TestClient(create_app(root=workspace, dry_run=True)) as c:
        yield c


def test_content_serves_the_bundle_the_browser_needs(client):
    b = client.get("/api/learn/content").json()
    assert set(b) >= {"groups", "modules", "paths", "glossary"}
    assert len(b["groups"]) == 12
    assert any(m["id"] == "concept.hara" for m in b["modules"])


def test_content_reports_its_own_rule_violations_rather_than_hiding_them(client):
    """A malformed course should say so in the UI, not render half of itself in silence."""
    assert client.get("/api/learn/content").json()["content_errors"] == []


def test_progress_starts_empty(client):
    assert client.get("/api/learn/progress").json()["modules"] == {}


def test_recording_a_score_is_readable_back(client):
    r = client.post("/api/learn/progress", json={"module_id": "concept.hara", "score": 0.9})
    assert r.status_code == 200 and r.json()["status"] == "passed"
    assert client.get("/api/learn/progress").json()["modules"]["concept.hara"]["best"] == 0.9


def test_recording_against_an_unknown_module_is_rejected(client):
    """Otherwise a typo silently accumulates progress against a module nobody can open."""
    r = client.post("/api/learn/progress", json={"module_id": "no.such.module", "score": 1.0})
    assert r.status_code == 404


def test_a_score_outside_zero_to_one_is_rejected(client):
    r = client.post("/api/learn/progress", json={"module_id": "concept.hara", "score": 4})
    assert r.status_code == 400


def test_progress_is_written_under_generated(client, workspace):
    client.post("/api/learn/progress", json={"module_id": "concept.hara", "score": 0.5})
    assert (workspace / "_generated" / "learning-progress.json").exists()


def test_the_learn_page_is_served(client):
    r = client.get("/learn")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert 'id="learn-nav"' in r.text


def test_the_workbench_is_untouched_by_all_this(client):
    assert client.get("/").status_code == 200
    assert client.get("/api/agents").status_code == 200
