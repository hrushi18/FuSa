from fusa.models import Status


def test_dry_run_chain_reaches_review(workspace):
    from fusa.orchestrator import Orchestrator
    orch = Orchestrator(root=workspace, dry_run=True)
    orch.run_all(log=lambda *_: None)
    for spec in orch.plan():
        expected = Status.REWORK if spec.work_product == "TARA" else Status.REVIEWED   # sec-scan sends a CWE finding back to cs-tara
        assert orch.reg.process.status(spec.work_product) == expected, spec.id
    assert (workspace / "_generated" / "HW-FMEDA" / "metrics.md").exists()


def test_downstream_blocked_until_upstream_ready(workspace):
    from fusa.orchestrator import Orchestrator
    orch = Orchestrator(root=workspace, dry_run=True)
    assert orch.run("sys-tsc", log=lambda *_: None) == Status.BLOCKED


def test_reviewer_has_no_method_access(workspace):
    from fusa.orchestrator import Orchestrator
    from fusa.agents.registry import build_reviewer
    orch = Orchestrator(root=workspace, dry_run=True)
    r = build_reviewer(orch.review_spec, orch.by_id["sys-tsr"], orch.reg, orch.llm)
    assert not hasattr(r.conv, "method")
    assert "## Method" not in r.system_prompt()
    assert "## Method" in orch.agents["sys-tsr"].system_prompt()


def test_feedback_loop_sets_upstream_to_rework(workspace, monkeypatch):
    from fusa.orchestrator import Orchestrator
    import fusa.agents.base as base
    orch = Orchestrator(root=workspace, dry_run=True)
    orch.run("sys-sads", log=lambda *_: None)
    # make the TSR reviewer send a finding upstream
    monkeypatch.setattr(base.ReviewAgent, "_dry_stub", lambda self, c: (
        '{"verdict":"rework","findings":[{"id":"F-01","severity":"major","description":"SG-002 has no FTTI","returns_to":"sys-sads"}]}'))
    assert orch.run("sys-tsr", log=lambda *_: None) == Status.REWORK
    assert orch.reg.process.status("SADS") == Status.REWORK
