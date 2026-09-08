"""The calculator teaches the lookup the chain performs, by performing the same one.

Reimplementing the determination rule here — even as the well-known S+E+C mnemonic, which
does reproduce the table exactly — would put normative content this project deliberately does
not ship into the source, and would disagree with whatever the engineer actually transcribed.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(workspace):
    from fusa.ui.server import create_app
    with TestClient(create_app(root=workspace, dry_run=True)) as c:
        yield c


def fill(client, **cells):
    r = client.post("/api/asil-table", json={"values": cells})
    assert r.status_code == 200, r.text
    return r


def test_a_zero_class_is_qm_without_consulting_the_table(client):
    """S0/E0/C0 is QM by the definition of the class, which is why it needs no licensed value."""
    r = client.get("/api/learn/asil", params={"s": "S0", "e": "E4", "c": "C3"}).json()
    assert r["asil"] == "QM" and "class definition" in r["why"]


def test_a_filled_cell_comes_back_from_the_table(client):
    fill(client, **{"S3-E4-C3": "D"})
    r = client.get("/api/learn/asil", params={"s": "S3", "e": "E4", "c": "C3"}).json()
    assert r["asil"] == "D" and r["key"] == "S3-E4-C3"
    assert "table" in r["why"]


def test_an_unfilled_cell_is_reported_as_unfilled_never_guessed(client):
    """The whole reason the calculator reads a file instead of applying a formula."""
    r = client.get("/api/learn/asil", params={"s": "S2", "e": "E3", "c": "C2"}).json()
    assert r["asil"] is None
    assert r["key"] == "S2-E3-C2"


def test_the_answer_matches_what_the_chain_would_derive_for_the_same_hazard(client, workspace):
    """One lookup, two callers. If these ever disagree the platform is teaching a fiction."""
    from fusa.generators.kinds import determine_asil, load_asil_table
    from fusa.orchestrator import Orchestrator
    fill(client, **{"S3-E4-C3": "D", "S1-E1-C1": "QM"})
    orch = Orchestrator(root=workspace, dry_run=True)
    table = load_asil_table(orch.reg)
    for s, e, c in [("S3", "E4", "C3"), ("S1", "E1", "C1"), ("S2", "E2", "C2"), ("S0", "E1", "C1")]:
        chain, _ = determine_asil(s, e, c, table)
        api = client.get("/api/learn/asil", params={"s": s, "e": e, "c": c}).json()["asil"]
        assert api == chain, f"{s}-{e}-{c}: calculator said {api}, chain said {chain}"


def test_the_endpoint_reports_how_much_of_the_table_is_transcribed(client):
    before = client.get("/api/learn/asil", params={"s": "S1", "e": "E1", "c": "C1"}).json()
    assert before["filled"] == 0 and before["total"] == 36
    fill(client, **{"S1-E1-C1": "QM"})
    after = client.get("/api/learn/asil", params={"s": "S1", "e": "E1", "c": "C1"}).json()
    assert after["filled"] == 1 and after["total"] == 36


@pytest.mark.parametrize("s,e,c", [("S9", "E1", "C1"), ("", "E1", "C1"), ("S1", "E9", "C1")])
def test_a_class_outside_the_scales_is_rejected_not_looked_up(client, s, e, c):
    assert client.get("/api/learn/asil", params={"s": s, "e": e, "c": c}).status_code == 400


def test_no_source_file_implements_a_determination_rule():
    """R2, asserted rather than trusted: the mnemonic must not appear in this codebase."""
    import pathlib, re
    root = pathlib.Path(__file__).resolve().parents[1] / "fusa"
    pattern = re.compile(r"(sev\s*\+\s*exp|s\s*\+\s*e\s*\+\s*c)", re.I)
    for p in list(root.rglob("*.py")) + list(root.rglob("*.js")):
        assert not pattern.search(p.read_text(encoding="utf-8")), f"{p} looks like an ASIL formula"


def test_the_calculator_asks_the_server_rather_than_deriving_an_answer(client):
    """If the browser ever computes an ASIL itself, the licensed table stops being the source."""
    js = client.get("/static/learn/tools/asil.js")
    assert js.status_code == 200
    assert "/api/learn/asil" in js.text, "the calculator must ask the server"
    for formula in ("S+E+C", "s + e + c", "sum 7", "= 7", "severity + exposure"):
        assert formula not in js.text, f"asil.js appears to derive an ASIL: {formula!r}"


def test_the_shell_routes_to_a_tool(client):
    assert "#/tool/" in client.get("/static/learn/app.js").text
