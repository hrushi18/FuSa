from fusa.models import Status

quiet = lambda *_: None


def test_hara_and_design_agents_in_plan_before_dependents(workspace):
    from fusa.orchestrator import Orchestrator
    orch = Orchestrator(root=workspace, dry_run=True)
    ids = [s.id for s in orch.plan()]
    assert {"sys-hara", "hw-hsr", "hw-design"} <= set(ids)
    assert ids.index("sys-hara") < ids.index("sys-sads")          # hazards before safety goals
    assert ids.index("hw-hsr") < ids.index("hw-design")           # HSR before HW design


def test_chain_with_hara_and_design_stays_releasable(workspace):
    from fusa.orchestrator import Orchestrator
    from fusa.report import validate
    orch = Orchestrator(root=workspace, dry_run=True)
    orch.run_all(log=quiet)
    for spec in orch.plan():
        assert orch.reg.process.status(spec.work_product) == Status.REVIEWED, spec.id
    sads = orch.reg.generated.items("SADS")
    assert any(i.fields.get("parent", "").startswith("HZ-") for i in sads)   # goals trace to hazards
    rep = validate(orch)
    assert rep.verdict == "RELEASABLE"
    assert {"HARA", "HW-DESIGN"} <= {a.work_product for a in rep.work_products}


def test_lifecycle_stages_map_to_dedicated_work_products():
    from fusa.tools import reqtable
    status_wp = {stage: wp for stage, _, wp in reqtable.LIFECYCLE}
    assert status_wp["HARA"] == "HARA"
    assert status_wp["Design"] == "HW-DESIGN"


def test_hara_agent_cites_part3_and_uses_hara_method(workspace):
    from fusa.orchestrator import Orchestrator
    orch = Orchestrator(root=workspace, dry_run=True)
    prompt = orch.agents["sys-hara"].system_prompt()
    assert "26262-3:6" in prompt
    assert "Method: HARA" in prompt or "hara" in prompt.lower()
