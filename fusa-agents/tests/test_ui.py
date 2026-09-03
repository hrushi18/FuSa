import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(workspace):
    from fusa.ui.server import create_app
    app = create_app(root=workspace, dry_run=True)
    with TestClient(app) as c:
        yield c


def wait_idle(client, timeout=15.0):
    """Poll until the background run finishes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not client.get("/api/logs").json()["running"]:
            return
        time.sleep(0.05)
    raise AssertionError("run did not finish in time")


def test_agents_lists_every_declared_agent_with_status(client):
    rows = client.get("/api/agents").json()
    by_id = {a["id"]: a for a in rows}
    assert "sys-sads" in by_id and "sys-tsr" in by_id
    assert by_id["sys-tsr"]["requires"] == ["SADS"]
    assert by_id["sys-sads"]["status"] == "not_started"
    assert any(not a["enabled"] for a in rows)          # disabled agents are visible too


def test_plan_returns_creation_order(client):
    plan = client.get("/api/plan").json()
    ids = [row["id"] for row in plan]
    assert ids.index("sys-sads") < ids.index("sys-tsr") < ids.index("sys-tsc")


def test_run_agent_executes_and_status_reflects_it(client):
    r = client.post("/api/run/sys-hara")
    assert r.status_code == 202
    wait_idle(client)
    r = client.post("/api/run/sys-sads")
    assert r.status_code == 202
    wait_idle(client)
    status = client.get("/api/status").json()
    assert status["records"]["SADS"]["status"] == "reviewed"
    log_text = "\n".join(client.get("/api/logs").json()["lines"])
    assert "authoring SADS" in log_text


def test_run_unknown_agent_is_404(client):
    assert client.post("/api/run/no-such-agent").status_code == 404


def test_run_rejected_while_busy(client):
    runner = client.app.state.runner
    assert runner.lock.acquire(blocking=False)
    try:
        assert client.post("/api/run/sys-sads").status_code == 409
    finally:
        runner.lock.release()


def test_run_all_then_workproduct_content_and_review(client):
    client.post("/api/run-all")
    wait_idle(client)
    wp = client.get("/api/wp/TSR").json()
    assert wp["content"].startswith("---")
    assert wp["record"]["status"] == "reviewed"
    assert wp["record"]["review"]["findings"]
    assert client.get("/api/wp/NOPE").status_code == 404


def test_index_serves_dashboard_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "FuSa" in r.text


def test_meta_reports_dry_run(client):
    meta = client.get("/api/meta").json()
    assert meta["dry_run"] is True
    assert meta["model"]


def test_cli_ui_subcommand_invokes_server(monkeypatch):
    import fusa.cli, fusa.ui.server
    called = {}
    monkeypatch.setattr(fusa.ui.server, "serve", lambda **kw: called.update(kw))
    assert fusa.cli.main(["--dry-run", "ui", "--port", "9123"]) == 0
    assert called == {"host": "127.0.0.1", "port": 9123, "dry_run": True,
                      "author": None, "reviewer": None}
    # the modes chosen on the command line must reach the dashboard, not be dropped on the way
    called.clear()
    assert fusa.cli.main(["--author", "deterministic", "--reviewer", "rules", "ui"]) == 0
    assert called["author"] == "deterministic" and called["reviewer"] == "rules"


# ---- the left panel: what a newcomer needs to see ---------------------------

def test_readiness_reports_what_the_project_still_needs(client):
    r = client.get("/api/readiness").json()
    assert r["asil_table"]["total"] == 36                 # the licensed table, unfilled by design
    assert {t["tool"] for t in r["tools"]} == {"cppcheck", "semgrep"}
    assert set(r["sources"]) == {"table", "tool", "model"}


def test_readiness_says_no_key_is_needed_in_deterministic_mode(workspace):
    from fastapi.testclient import TestClient
    from fusa.ui.server import create_app
    with TestClient(create_app(root=workspace, dry_run=True,
                               author="deterministic", reviewer="rules")) as c:
        r = c.get("/api/readiness").json()
        assert r["needs_key"] is False and r["sources"]["model"] == 0


def test_every_check_says_what_decides_it(client):
    rows = client.get("/api/checks").json()
    assert rows and all(set(w["counts"]) == {"gate", "rule", "human", "model"} for w in rows)
    for w in rows:
        for item in w["items"]:
            assert item["decided_by"] in ("gate", "rule", "human", "model")
            assert item["id"] and item["text"]
    hara = next(w for w in rows if w["work_product"] == "HARA")
    assert hara["counts"]["rule"] >= 3 and hara["counts"]["gate"] >= 1


def test_judgement_items_go_to_a_person_under_rule_review(workspace):
    """The segregation the panel shows: with rules on, what is left is yours, not a model's."""
    from fastapi.testclient import TestClient
    from fusa.ui.server import create_app
    with TestClient(create_app(root=workspace, dry_run=True, reviewer="rules")) as c:
        rows = c.get("/api/checks").json()
        assert sum(w["counts"]["human"] for w in rows) > 0
        assert sum(w["counts"]["model"] for w in rows) == 0
    with TestClient(create_app(root=workspace, dry_run=True, reviewer="model")) as c:
        rows = c.get("/api/checks").json()
        assert sum(w["counts"]["human"] for w in rows) == 0
        assert sum(w["counts"]["model"] for w in rows) > 0


def test_modes_can_be_switched_from_the_dashboard(client):
    before = client.get("/api/readiness").json()
    r = client.post("/api/modes", json={"author": "deterministic", "reviewer": "rules"}).json()
    assert r == {"author": "deterministic", "reviewer": "rules"}
    after = client.get("/api/readiness").json()
    assert before["sources"]["model"] > after["sources"]["model"]     # tables took over
    assert after["needs_key"] is False


def test_modes_are_refused_mid_run(client):
    runner = client.app.state.runner
    assert runner.lock.acquire(blocking=False)
    try:
        assert client.post("/api/modes", json={"author": "deterministic"}).status_code == 409
    finally:
        runner.lock.release()


def test_the_asil_table_is_editable_and_validated(client, workspace):
    t = client.get("/api/asil-table").json()
    assert len(t["values"]) == 36 and t["allowed"] == ["QM", "A", "B", "C", "D"]
    assert client.post("/api/asil-table", json={"values": {"S3-E4-C3": "E"}}).status_code == 400
    assert client.post("/api/asil-table", json={"values": {"S9-E9-C9": "D"}}).status_code == 400
    r = client.post("/api/asil-table", json={"values": {"S3-E4-C3": "d"}}).json()
    assert r["filled"] == 1
    from fusa.generators.kinds import load_asil_table
    from fusa.registers import Registers
    assert load_asil_table(Registers.load(workspace))["S3-E4-C3"] == "D"   # normalised and saved


def test_the_dashboard_page_carries_the_provenance_key(client):
    html = client.get("/").text
    for marker in ("Where every answer comes from", "How it is checked", "Needs you",
                   "/api/readiness", "/api/checks", "/api/asil-table"):
        assert marker in html
