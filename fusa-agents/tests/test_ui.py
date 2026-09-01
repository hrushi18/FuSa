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
    monkeypatch.setattr(fusa.ui.server, "serve",
                        lambda host, port, dry_run: called.update(host=host, port=port, dry_run=dry_run))
    assert fusa.cli.main(["--dry-run", "ui", "--port", "9123"]) == 0
    assert called == {"host": "127.0.0.1", "port": 9123, "dry_run": True}
