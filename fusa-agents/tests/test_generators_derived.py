"""Work products that are pure derivations: cybersecurity goals, closure, tests, traceability.

None of these takes an input table. Everything they contain is already implied by the work
products upstream, which is exactly why they should never have been a model's job.
"""
import pytest

from fusa.models import Status
from fusa.tools import ids

CHAIN = ("sys-hara", "sys-sads", "sys-tsr", "sm-catalog", "sys-tsc",
         "hw-hsr", "hw-design", "hw-fmeda", "sys-fmea", "cs-tara")


@pytest.fixture
def chain(workspace):
    from fusa.orchestrator import Orchestrator
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic", reviewer="rules")
    for agent_id in CHAIN:
        wp = o.by_id[agent_id].work_product
        o.reg.generated.write(wp, o.resolve(agent_id)[1].run())
        o.reg.process.update(wp, agent_id, status=Status.REVIEWED)
    return o


def items(orch, agent_id):
    return ids.parse_items(orch.resolve(agent_id)[1].run())


# ---- cybersecurity goals ----------------------------------------------------

def test_one_goal_per_treated_threat_scenario(chain):
    threats = {i.id: i for i in chain.reg.generated.items("TARA") if i.prefix == "TS"}
    treated = [t for t in threats.values() if t.fields["treatment"] in ("avoid", "reduce", "share")]
    goals = items(chain, "cs-goals")
    assert len(goals) == len(treated) == 4
    assert {g.fields["parent"] for g in goals} == {t.id for t in treated}


def test_a_retained_risk_carries_no_goal(chain):
    retained = [i.id for i in chain.reg.generated.items("TARA") if i.fields.get("treatment") == "retain"]
    assert retained
    assert not [g for g in items(chain, "cs-goals") if g.fields["parent"] in retained]


def test_the_goal_states_the_property_of_the_asset_it_protects(chain):
    goal = items(chain, "cs-goals")[0]
    assert goal.fields["text"].startswith("The item shall protect the integrity of")
    assert goal.fields["asset"].startswith("AS-")
    assert goal.fields["risk"] and goal.fields["treatment"] == "reduce"


def test_cybersecurity_goals_need_the_tara_first(workspace):
    from fusa.orchestrator import Orchestrator
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic")
    assert any("TARA has not been produced" in p for p in ids.find_pending(o.resolve("cs-goals")[1].run()))


# ---- closure ----------------------------------------------------------------

def test_every_analysis_finding_is_carried_back(chain):
    flagged = [i for wp in ("SYS-FMEA", "HW-FMEDA") for i in chain.reg.generated.items(wp)
               if i.fields.get("finding")]
    closure = items(chain, "tsc-close-the-loop")
    assert len(closure) == len(flagged) == 1                 # the uncovered supply droop
    assert closure[0].fields["parent"] == "SFM-007"
    assert closure[0].fields["returns_to"] == "sys-tsc" and closure[0].fields["status"] == "open"


def test_no_findings_means_an_empty_closure_not_a_fabricated_one(chain, workspace):
    (workspace / "input" / "failure-modes.csv").write_text(
        "element,function,failure_mode,local_effect,item_effect,classification,violated_sg,sm\n"
        "sense IC,f,m,l,i,SR,SG-001,SM-001\n")
    chain.reg.generated.write("SYS-FMEA", chain.resolve("sys-fmea")[1].run())
    content = chain.resolve("tsc-close-the-loop")[1].run()
    assert not ids.parse_items(content)
    assert "raised no findings" in content


# ---- test specification -----------------------------------------------------

def test_one_test_case_per_requirement_using_its_own_verification_method(chain):
    reqs = [i for wp in ("TSR", "HSR") for i in chain.reg.generated.items(wp)]
    tests = items(chain, "test-spec-agent")
    assert len(tests) == len(reqs) == 10
    assert {t.fields["parent"] for t in tests} == {r.id for r in reqs}
    first = next(t for t in tests if t.fields["parent"] == "TSR-001")
    assert first.fields["method"] == "fault injection test on the sense-IC interface"
    assert first.fields["text"].startswith("Verify that The sense IC shall")


def test_a_requirement_naming_no_verification_method_is_reported(chain, workspace):
    chain.reg.generated.write("TSR", "---\nid: TSR\n---\n\n### TSR-009\n- text: something\n")
    assert any("TSR-009 (TSR) names no verification method" in p
               for p in ids.find_pending(chain.resolve("test-spec-agent")[1].run()))


# ---- traceability -----------------------------------------------------------

def test_the_matrix_is_derived_from_the_parent_links(chain):
    chain.reg.generated.write("TEST-SPEC", chain.resolve("test-spec-agent")[1].run())
    content = chain.resolve("traceability-agent")[1].run()
    assert "| Safety goal | ASIL | TSR | TSC | HSR | HW-DESIGN | TEST-SPEC | complete |" in content
    row = next(l for l in content.splitlines() if l.startswith("| SG-001 "))
    assert "TSR-001, TSR-002" in row and "HWD-001" in row and "| yes |" in row


def test_one_item_per_safety_goal_carrying_its_chain(chain):
    traces = items(chain, "traceability-agent")
    goals = [i for i in chain.reg.generated.items("SADS") if i.prefix == "SG"]
    assert len(traces) == len(goals) == 4
    assert traces[0].fields["complete"] == "yes"
    assert traces[0].fields["tsr"] == "TSR-001, TSR-002"


def test_a_break_in_the_chain_shows_as_a_gap_not_a_claim(chain, workspace):
    """A goal nothing refines must read as incomplete, not silently vanish from the matrix."""
    chain.reg.generated.write("TSR", "---\nid: TSR\n---\n\n### TSR-001\n- parent: SG-001\n- text: t\n")
    content = chain.resolve("traceability-agent")[1].run()
    incomplete = [i for i in ids.parse_items(content) if i.fields["complete"] == "no"]
    assert {i.fields["parent"] for i in incomplete} == {"SG-002", "SG-003", "SG-004"}
    assert any("has no TSR" in p for p in ids.find_pending(content))


def test_traceability_needs_its_root(workspace):
    from fusa.orchestrator import Orchestrator
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic")
    assert any("SADS has not been produced" in p
               for p in ids.find_pending(o.resolve("traceability-agent")[1].run()))


# ---- the extended chain -----------------------------------------------------

def test_sixteen_work_products_are_produced_with_no_api_key(workspace, monkeypatch):
    from fusa.orchestrator import Orchestrator
    for var in ("ANTHROPIC_API_KEY", "XAI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic", reviewer="rules")
    o.run_all(log=lambda *a: None)
    o.reg.process.update("TSC", "sys-tsc", status=Status.REVIEWED)   # finding addressed by the engineer
    for agent_id in ("test-spec-agent", "traceability-agent", "tsc-close-the-loop"):
        assert o.run(agent_id, log=lambda *a: None) is Status.REVIEWED, agent_id
    assert len(o.plan()) == 16
