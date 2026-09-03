"""Deterministic authoring of the hardware branch: HSR, HW-DESIGN, HW-FMEDA."""
import pytest

from fusa.tools import ids

CONCEPT = ("sys-hara", "sys-sads", "sys-tsr", "sm-catalog", "sys-tsc")


@pytest.fixture
def chain(workspace):
    from fusa.orchestrator import Orchestrator
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic", reviewer="rules")
    for agent_id in (*CONCEPT, "hw-hsr"):
        o.reg.generated.write(o.by_id[agent_id].work_product, o.resolve(agent_id)[1].run())
    return o


def items(orch, agent_id):
    return ids.parse_items(orch.resolve(agent_id)[1].run())


# ---- HSR --------------------------------------------------------------------

def test_each_allocation_is_refined_by_a_hardware_requirement(chain):
    allocations = {i.id for i in chain.reg.generated.items("TSC")}
    hsr = items(chain, "hw-hsr")
    assert len(hsr) == 5
    assert {h.fields["parent"] for h in hsr} == allocations


def test_asil_element_and_mechanism_come_from_the_allocation(chain):
    allocations = {i.id: i for i in chain.reg.generated.items("TSC")}
    for h in items(chain, "hw-hsr"):
        alloc = allocations[h.fields["parent"]]
        assert h.fields["asil"] == alloc.fields["asil"]
        assert h.fields["sm"] == alloc.fields["sm"]


def test_the_requirement_sentence_is_assembled_from_the_row(chain):
    hsr = items(chain, "hw-hsr")[0]
    assert hsr.fields["text"].startswith("The sense IC shall run its internal self test")
    assert hsr.fields["text"].endswith("within 10 ms.")


def test_an_allocation_with_no_hardware_requirement_is_reported(chain, workspace):
    (workspace / "input" / "hardware-requirements.csv").write_text(
        "allocation,behaviour,verification\nTSC-001,do the thing,test\n")
    pending = ids.find_pending(chain.resolve("hw-hsr")[1].run())
    assert any("TSC-002 has no HSR row" in p for p in pending)


# ---- HW-DESIGN --------------------------------------------------------------

def test_each_element_names_the_requirement_it_implements(chain):
    design = items(chain, "hw-design")
    reqs = {i.id for i in chain.reg.generated.items("HSR")}
    assert len(design) == 5
    assert {d.fields["parent"] for d in design} == reqs
    assert design[0].fields["part"].startswith("PSX-42")


def test_a_requirement_no_element_implements_is_reported(chain, workspace):
    (workspace / "input" / "hardware-design.csv").write_text(
        "element,part,function,implements\nsense IC,PSX-42,converts,HSR-001\n")
    pending = ids.find_pending(chain.resolve("hw-design")[1].run())
    assert any("HSR-002 is not implemented" in p for p in pending)


def test_design_pointing_at_a_requirement_that_does_not_exist_is_reported(chain, workspace):
    (workspace / "input" / "hardware-design.csv").write_text(
        "element,part,function,implements\nsense IC,PSX-42,converts,HSR-404\n")
    out = chain.resolve("hw-design")[1].run()
    assert any("HSR-404, which is not in HSR" in p for p in ids.find_pending(out))
    assert not ids.parse_items(out)


# ---- HW-FMEDA ---------------------------------------------------------------

def test_items_come_from_the_same_csv_the_metrics_tool_reads(chain, workspace):
    from fusa.tools import metrics
    rows = metrics.load_csv(workspace / "input" / "fmeda-failure-modes.csv")
    generated = [i for i in items(chain, "hw-fmeda") if i.fields.get("finding") != "target_missed"]
    assert len(generated) == len(rows)                     # the table and metrics.md cannot disagree
    assert generated[0].fields["element"] == rows[0].element
    assert generated[0].fields["category"] == rows[0].category


def test_the_mission_profile_is_carried_onto_every_item(chain):
    for i in items(chain, "hw-fmeda"):
        if i.fields.get("finding") != "target_missed":
            assert "55 C" in i.fields["mission_profile"]


def test_a_rate_with_no_cited_source_is_pending(chain, workspace):
    (workspace / "input" / "fmeda-failure-modes.csv").write_text(
        "element,mode,lam_fit,category,dc,safety_mechanism\nsense IC,drift,6.0,SR,0.99,SM-001\n")
    assert any("source for the sense IC drift failure rate" in p
               for p in ids.find_pending(chain.resolve("hw-fmeda")[1].run()))


def test_a_missed_target_becomes_an_item_that_returns_to_the_design(chain, workspace):
    """The checklist asks for missed targets to be findings with returns_to, not prose."""
    from fusa.generators import GeneratorAgent
    (workspace / "input" / "fmeda-failure-modes.csv").write_text(
        "element,mode,lam_fit,category,dc,safety_mechanism,source\n"
        "sense IC,stuck-at,900.0,SR,0.10,SM-001,estimate\n")          # far below any ASIL D target
    spec = chain.by_id["hw-fmeda"].model_copy(
        update={"generator": {**chain.by_id["hw-fmeda"].generator, "asil": "D"}})
    missed = [i for i in ids.parse_items(GeneratorAgent(spec, chain.reg).run())
              if i.fields.get("finding") == "target_missed"]
    assert missed and missed[0].fields["returns_to"] == "sys-tsc"
    assert "SPFM" in missed[0].fields["text"] or "PMHF" in missed[0].fields["text"]


def test_targets_that_are_met_produce_no_finding(chain):
    assert not [i for i in items(chain, "hw-fmeda") if i.fields.get("finding") == "target_missed"]


# ---- the where filter on rules ----------------------------------------------

@pytest.mark.parametrize("where,expected", [
    ({"field": "dc", "gt": 0}, ["HF-001"]),
    ({"field": "category", "not_in": ["SAFE"]}, ["HF-001", "HF-003"]),
    ({"field": "category", "is": "SAFE"}, ["HF-002"]),
    ({"field": "category", "not": "SAFE"}, ["HF-001", "HF-003"]),
    ({"field": "dc", "present": True}, ["HF-001", "HF-002"]),
])
def test_a_rule_can_be_scoped_to_the_items_its_checklist_item_means(where, expected):
    from fusa.agents.rulereview import Ctx
    text = ("### HF-001\n- category: SR\n- dc: 0.99\n\n"
            "### HF-002\n- category: SAFE\n- dc: 0.0\n\n"
            "### HF-003\n- category: MPF\n")
    ctx = Ctx(target=None, content=text, generated=None, cfg={"where": where})
    assert [i.id for i in ctx.scoped()] == expected


# ---- the whole chain --------------------------------------------------------

def test_every_enabled_authoring_agent_has_a_generator(workspace):
    from fusa.agents.registry import load_specs
    on_the_model = [s.id for s in load_specs(workspace / "config" / "agents.yaml")
                    if s.enabled and s.kind == "authoring" and not s.generator]
    assert on_the_model == []


def test_the_entire_chain_runs_with_no_api_key(workspace, monkeypatch):
    from fusa.models import Status
    from fusa.orchestrator import Orchestrator
    for var in ("ANTHROPIC_API_KEY", "XAI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic", reviewer="rules")
    o.run_all(log=lambda *a: None)
    statuses = {s.work_product: o.reg.process.status(s.work_product) for s in o.plan()}
    # every mode in the sample is covered, so nothing is returned and nothing waits behind it
    assert all(st is Status.REVIEWED for st in statuses.values()), \
        {wp: st.value for wp, st in statuses.items() if st is not Status.REVIEWED}
    assert len(statuses) == 16
