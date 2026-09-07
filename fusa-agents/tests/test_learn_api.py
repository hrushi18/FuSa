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


def test_both_pages_share_one_token_file(client):
    """One design system means one place the colours are defined, not two that drift."""
    css = client.get("/static/tokens.css")
    assert css.status_code == 200
    for token in ("--bg:", "--p-model:", "--asil-d:"):
        assert token in css.text
    assert "tokens.css" in client.get("/").text
    assert "tokens.css" in client.get("/learn").text


def test_the_shell_offers_the_nav_the_top_bar_and_the_content_region(client):
    html = client.get("/learn").text
    for marker in ('id="learn-nav"', 'id="learn-main"', 'id="learn-crumb"',
                   'id="learn-progress"', "app.js"):
        assert marker in html


def test_a_passing_score_flips_the_module_to_passed(client):
    """The engine posts a fraction; the server owns what counts as a pass."""
    r = client.post("/api/learn/progress", json={"module_id": "concept.hara", "score": 1.0})
    assert r.json()["status"] == "passed"


def test_a_failing_score_flips_the_module_to_needs_review(client):
    r = client.post("/api/learn/progress", json={"module_id": "concept.hara", "score": 0.33})
    assert r.json()["status"] == "needs_review"


def test_a_retake_cannot_lose_an_earned_pass(client):
    client.post("/api/learn/progress", json={"module_id": "concept.hara", "score": 1.0})
    r = client.post("/api/learn/progress", json={"module_id": "concept.hara", "score": 0.0})
    assert r.json()["status"] == "passed" and r.json()["attempts"] == 2


def test_a_hand_edited_progress_file_still_serves_a_page(client, workspace):
    """The file is meant to be readable and editable; a wrong shape inside it is a nuisance,
    not a 500 in the middle of a lesson."""
    (workspace / "_generated" / "learning-progress.json").write_text(
        '{"version": 1, "modules": {"concept.hara": "passed"}}', encoding="utf-8")
    r = client.get("/api/learn/progress")
    assert r.status_code == 200 and r.json()["modules"] == {}


# ---- a malformed body is the caller's mistake, and the reply should say which field ----

def test_a_body_that_is_not_a_json_object_is_rejected(client):
    r = client.request("POST", "/api/learn/progress", json=[1, 2])
    assert r.status_code == 400


def test_a_body_that_is_not_json_at_all_is_rejected(client):
    r = client.post("/api/learn/progress", content="nope",
                    headers={"content-type": "application/json"})
    assert r.status_code == 400


def test_a_non_numeric_score_is_rejected_by_name(client):
    r = client.post("/api/learn/progress", json={"module_id": "concept.hara", "score": "abc"})
    assert r.status_code == 400 and "score" in str(r.json()["detail"])


def test_a_non_numeric_cards_seen_is_rejected_by_name(client):
    r = client.post("/api/learn/progress",
                    json={"module_id": "concept.hara", "cards_seen": "abc"})
    assert r.status_code == 400 and "cards_seen" in str(r.json()["detail"])


def test_a_negative_cards_seen_is_rejected_rather_than_silently_clamped(client):
    r = client.post("/api/learn/progress", json={"module_id": "concept.hara", "cards_seen": -5})
    assert r.status_code == 400 and "cards_seen" in str(r.json()["detail"])


def test_a_module_id_that_is_not_a_string_is_rejected(client):
    r = client.post("/api/learn/progress", json={"module_id": 7, "score": 1.0})
    assert r.status_code == 400 and "module_id" in str(r.json()["detail"])


def test_one_module_owns_saving_progress_and_both_renderers_go_through_it(client):
    """Spec §6: the UI reaches storage through one seam, so a different store stays addable —
    and so a failed save is reported once rather than swallowed in two places."""
    assert client.get("/static/learn/progress.js").status_code == 200
    for page in ("module.js", "quiz.js"):
        js = client.get(f"/static/learn/{page}").text
        assert "/api/learn/progress" not in js, f"{page} still posts progress itself"
        assert "./progress.js" in js


def test_a_course_that_fails_to_load_says_so_instead_of_showing_a_blank_page(client):
    js = client.get("/static/learn/app.js").text
    assert "load()" in js and ".catch(" in js
    assert "banner" in js
