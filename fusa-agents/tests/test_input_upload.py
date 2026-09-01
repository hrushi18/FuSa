import pytest
from fastapi.testclient import TestClient

from test_ui import wait_idle

GOOD_CSV = """element,mode,lam_fit,category,dc,safety_mechanism
sense IC,open output,8.0,SR,0.99,SM-001
core,wrong computation,5.0,SR,0.99,SM-002
"""

UNCOVERED_CSV = """element,mode,lam_fit,category,dc,safety_mechanism
sense IC,open output,50.0,SR,0.0,
"""


@pytest.fixture
def client(workspace):
    from fusa.ui.server import create_app
    app = create_app(root=workspace, dry_run=True)
    with TestClient(app) as c:
        yield c


def upload(client, text: str):
    return client.post("/api/input/fmeda", content=text.encode(),
                       headers={"content-type": "text/csv"})


def test_valid_csv_saved_and_chain_started(client, workspace):
    r = upload(client, GOOD_CSV)
    assert r.status_code == 202
    assert r.json()["rows"] == 2
    assert (workspace / "input" / "fmeda-failure-modes.csv").read_text() == GOOD_CSV
    assert client.get("/api/logs").json()["running"]
    wait_idle(client)
    assert client.get("/api/status").json()["records"]["SADS"]["status"] == "reviewed"


def test_uploaded_data_drives_the_verdict(client):
    upload(client, UNCOVERED_CSV)                 # one uncovered SPF -> SPFM 0%
    wait_idle(client)
    rep = client.get("/api/report").json()
    assert rep["verdict"] == "NOT_RELEASABLE"
    assert any("SPFM" in v for v in rep["metrics_violations"])


def test_bad_category_rejected_row_named_file_untouched(client, workspace):
    before = (workspace / "input" / "fmeda-failure-modes.csv").read_text()
    r = upload(client, "element,mode,lam_fit,category,dc,safety_mechanism\nx,y,1.0,BOGUS,0.5,SM-1\n")
    assert r.status_code == 400
    assert any("row 2" in d and "BOGUS" in d for d in r.json()["detail"])
    assert (workspace / "input" / "fmeda-failure-modes.csv").read_text() == before


def test_missing_column_rejected(client):
    r = upload(client, "element,mode,lam_fit\nx,y,1.0\n")
    assert r.status_code == 400
    assert any("category" in d for d in r.json()["detail"])


def test_non_numeric_lam_rejected(client):
    r = upload(client, "element,mode,lam_fit,category,dc,safety_mechanism\nx,y,abc,SR,0.5,SM-1\n")
    assert r.status_code == 400
    assert any("row 2" in d for d in r.json()["detail"])


def test_empty_csv_rejected(client):
    r = upload(client, "element,mode,lam_fit,category,dc,safety_mechanism\n")
    assert r.status_code == 400
    assert any("no data rows" in d for d in r.json()["detail"])


def test_upload_rejected_while_busy(client, workspace):
    before = (workspace / "input" / "fmeda-failure-modes.csv").read_text()
    runner = client.app.state.runner
    assert runner.lock.acquire(blocking=False)
    try:
        assert upload(client, GOOD_CSV).status_code == 409
    finally:
        runner.lock.release()
    assert (workspace / "input" / "fmeda-failure-modes.csv").read_text() == before


def test_api_input_lists_files(client):
    names = [f["name"] for f in client.get("/api/input").json()]
    assert "fmeda-failure-modes.csv" in names
    assert "item-definition.md" in names


def test_dashboard_has_inputs_panel(client):
    html = client.get("/").text
    assert 'id="inputs"' in html
    assert "/api/input/fmeda" in html
