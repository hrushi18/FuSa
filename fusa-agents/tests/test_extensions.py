from pathlib import Path
from fusa.models import Status

ROOT = Path(__file__).resolve().parents[1]


def test_reqif_import_roundtrip(tmp_path):
    from fusa.adapters import reqif
    objs = reqif.parse(ROOT / "input" / "customer-requirements.reqif")
    assert len(objs) == 3
    md = reqif.to_work_product(objs, "SYS-REQ", "CR", id_attribute="req_id")
    assert "### CR-003" in md and "- parent: CR-002" in md and "±2 %" in md
    xml = reqif.from_work_product(md)
    back = reqif.parse_string(xml) if hasattr(reqif, "parse_string") else reqif.parse(_write(tmp_path, xml))
    ids_ = {o.attributes["house_id"] for o in back}
    assert ids_ == {"CR-001", "CR-002", "CR-003"}
    assert any(o.parents == ["cb-1002"] or o.parents == ["obj-CR-002"] for o in back)


def _write(tmp_path, xml):
    p = tmp_path / "x.reqif"; p.write_text(xml, encoding="utf-8"); return p


def test_parsers():
    from fusa.runners import parsers
    cpp = parsers.parse_cppcheck_xml(ROOT / "input/reports/cppcheck.xml")
    assert {f.severity for f in cpp} == {"error", "info"} and cpp[0].tags == ["CWE-788"]
    sar = parsers.parse_sarif(ROOT / "input/reports/semgrep.sarif")
    assert sar[0].severity == "error" and "CWE-120" in sar[0].tags and sar[1].severity == "info"


def test_runner_routes_security_finding_back_to_tara(workspace):
    from fusa.orchestrator import Orchestrator
    orch = Orchestrator(root=workspace, dry_run=True)
    quiet = lambda *_: None
    orch.run("sys-sads", log=quiet); orch.run("cs-tara", log=quiet)
    assert orch.reg.process.status("TARA") == Status.REVIEWED
    assert orch.run("sec-scan", log=quiet) == Status.REVIEWED
    assert orch.reg.process.status("TARA") == Status.REWORK          # CWE-tagged finding → cs-tara
    items = orch.reg.generated.items("SEC-SCAN")
    assert len(items) == 1 and items[0].fields["returns_to"] == "cs-tara"   # min_severity=warning dropped the note


def test_second_standard_uses_same_registers(workspace):
    from fusa.orchestrator import Orchestrator
    orch = Orchestrator(root=workspace, dry_run=True)
    assert {"21434", "26262-4", "ASPICE"} <= orch.reg.clauses.standards()
    prompt = orch.agents["cs-tara"].system_prompt()
    assert "**21434:15.5**" in prompt and "### Method: TARA" in prompt and "**26262-4:6.4.2**" not in prompt
