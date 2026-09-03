"""Deterministic authoring of TSR, SM-CATALOG and TSC — derivation, not paraphrase."""
import pytest

from fusa.tools import ids


@pytest.fixture
def chain(workspace):
    """HARA → SADS → TSR → SM-CATALOG generated, so TSC has real upstream to derive from."""
    from fusa.orchestrator import Orchestrator
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic", reviewer="rules")
    for agent_id in ("sys-hara", "sys-sads", "sys-tsr", "sm-catalog"):
        o.reg.generated.write(o.by_id[agent_id].work_product, o.resolve(agent_id)[1].run())
    return o


def items(orch, agent_id):
    return ids.parse_items(orch.resolve(agent_id)[1].run())


# ---- TSR --------------------------------------------------------------------

def test_the_requirement_sentence_follows_the_method_pattern(chain):
    tsr = items(chain, "sys-tsr")[0]
    assert tsr.fields["text"] == (
        "The sense IC shall execute its built-in self test every conversion cycle and flag the "
        "pressure status invalid on failure within 10 ms.")


def test_asil_and_safe_state_are_inherited_from_the_parent_goal(chain):
    goals = {i.id: i for i in chain.reg.generated.items("SADS")}
    for tsr in items(chain, "sys-tsr"):
        goal = goals[tsr.fields["parent"]]
        assert tsr.fields["asil"] == goal.fields["asil"]           # never restated by hand
        assert tsr.fields["safe_state"] == goal.fields["safe_state"]


def test_a_goal_with_no_requirement_is_reported(workspace):
    from fusa.orchestrator import Orchestrator
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic")
    for a in ("sys-hara", "sys-sads"):
        o.reg.generated.write(o.by_id[a].work_product, o.resolve(a)[1].run())
    (workspace / "input" / "technical-requirements.csv").write_text(
        "safety_goal,element,behaviour,verification\nSG-001,e,b,test\n")
    pending = ids.find_pending(o.resolve("sys-tsr")[1].run())
    assert any("SG-002 has no technical requirement" in p for p in pending)   # coverage gap named


def test_a_requirement_pointing_at_a_goal_that_does_not_exist_is_reported(workspace):
    from fusa.orchestrator import Orchestrator
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic")
    for a in ("sys-hara", "sys-sads"):
        o.reg.generated.write(o.by_id[a].work_product, o.resolve(a)[1].run())
    (workspace / "input" / "technical-requirements.csv").write_text(
        "safety_goal,element,behaviour,verification\nSG-404,e,b,test\n")
    out = o.resolve("sys-tsr")[1].run()
    assert any("SG-404, which is not in SADS" in p for p in ids.find_pending(out))
    assert not ids.parse_items(out)                                # and no requirement invented


# ---- SM-CATALOG -------------------------------------------------------------

def test_the_catalogue_carries_what_the_checklist_demands(chain):
    sms = items(chain, "sm-catalog")
    assert len(sms) == 5 and sms[0].id == "SM-001"      # SM-005 covers the supply droop
    for sm in sms:
        assert all(sm.fields[k] for k in ("detects", "reaction", "dc_claim", "allocated_to", "source"))


# ---- TSC --------------------------------------------------------------------

def test_ftti_is_read_through_the_requirement_to_its_goal(chain):
    goals = {i.id: i for i in chain.reg.generated.items("SADS")}
    reqs = {i.id: i for i in chain.reg.generated.items("TSR")}
    for tsc in items(chain, "sys-tsc"):
        goal = goals[reqs[tsc.fields["parent"]].fields["parent"]]
        assert tsc.fields["ftti"] == goal.fields["ftti"]           # not restated in allocation.csv


def test_the_diagram_is_drawn_from_the_allocation_rows(chain):
    content = chain.resolve("sys-tsc")[1].run()
    assert "```mermaid" in content
    assert '-->|SM-001| SAFE' in content and 'E1["sense IC"]' in content


def test_a_budget_that_misses_the_ftti_is_caught_by_the_reviewer(chain, workspace):
    from fusa.agents.registry import build_reviewer
    (workspace / "input" / "allocation.csv").write_text(
        "id,requirement,element,sm,fdt,frt\nTSC-001,TSR-001,sense IC,SM-001,80 ms,50 ms\n")
    content = chain.resolve("sys-tsc")[1].run()                    # 80+50 = 130 ms against a 100 ms FTTI
    reviewer = build_reviewer(chain.review_spec, chain.by_id["sys-tsc"], chain.reg, chain.llm, "rules")
    verdict = reviewer.run(content)
    assert verdict.verdict == "rework"
    assert any("exceeds ftti 100 ms" in f.description for f in verdict.findings)


def test_an_unallocated_requirement_is_reported(chain, workspace):
    (workspace / "input" / "allocation.csv").write_text(
        "requirement,element,sm,fdt,frt\nTSR-001,sense IC,SM-001,10 ms,5 ms\n")
    pending = ids.find_pending(chain.resolve("sys-tsc")[1].run())
    assert any("TSR-002 is not allocated" in p for p in pending)


def test_tsc_without_its_upstream_is_pending(workspace):
    from fusa.orchestrator import Orchestrator
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic")
    assert any("TSR has not been produced" in p for p in ids.find_pending(o.resolve("sys-tsc")[1].run()))


# ---- the chain end to end ---------------------------------------------------

def test_five_work_products_reach_reviewed_with_no_api_key(workspace, monkeypatch):
    from fusa.models import Status
    from fusa.orchestrator import Orchestrator
    for var in ("ANTHROPIC_API_KEY", "XAI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    o = Orchestrator(root=workspace, dry_run=False, author="deterministic", reviewer="rules")
    for agent_id in ("sys-hara", "sys-sads", "sys-tsr", "sm-catalog", "sys-tsc"):
        assert o.run(agent_id, log=lambda *a: None) is Status.REVIEWED, agent_id
    for wp in ("TSR", "TSC"):
        rec = o.reg.process.get(wp)
        assert rec.gate.passed and not [f for f in rec.review.findings if f.severity != "minor"]
