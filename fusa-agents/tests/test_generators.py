"""Deterministic authoring — work products rendered from engineer-authored tables, no model."""
import pytest
import yaml

from fusa.generators.kinds import determine_asil
from fusa.tools import ids


@pytest.fixture
def orch(workspace):
    from fusa.orchestrator import Orchestrator
    return Orchestrator(root=workspace, dry_run=True, author="deterministic", reviewer="rules")


def content(orch, agent_id):
    _, agent = orch.resolve(agent_id)
    return agent.run()


# ---- HARA -------------------------------------------------------------------

def test_hazards_come_from_the_table_verbatim(orch):
    items = ids.parse_items(content(orch, "sys-hara"))
    assert len(items) == 5                                   # one per row of input/hazards.csv
    hz1 = items[0]
    assert hz1.id == "HZ-001"                                # the table pins it
    assert hz1.fields["malfunction"] == "reports pressure lower than actual"
    assert hz1.fields["severity"] == "S3" and hz1.fields["asil"] == "D"
    assert hz1.fields["asil_basis"] == "stated in the input table"


def test_s0_is_qm_by_class_definition_not_by_lookup(orch):
    qm = [i for i in ids.parse_items(content(orch, "sys-hara")) if i.fields["severity"] == "S0"]
    assert qm and qm[0].fields["asil"] == "QM"
    assert "by class definition" in qm[0].fields["asil_basis"]


def test_asil_is_looked_up_when_the_table_is_filled(workspace):
    from fusa.orchestrator import Orchestrator
    table = workspace / "_reference-register" / "asil-table.yaml"
    data = yaml.safe_load(table.read_text())
    data["table"]["S2-E2-C2"] = "A"
    table.write_text(yaml.safe_dump(data))
    rows = ("id,function,malfunction,hazardous_event,situation,severity,exposure,controllability,rationale\n"
            ",f,m,h,s,S2,E2,C2,r\n")
    (workspace / "input" / "hazards.csv").write_text(rows)
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic")
    item = ids.parse_items(o.resolve("sys-hara")[1].run())[0]
    assert item.fields["asil"] == "A" and "S×E×C table" in item.fields["asil_basis"]


def test_an_unfilled_combination_is_pending_never_guessed(workspace):
    from fusa.orchestrator import Orchestrator
    (workspace / "input" / "hazards.csv").write_text(
        "function,malfunction,hazardous_event,situation,severity,exposure,controllability,rationale\n"
        "f,m,h,s,S2,E2,C2,r\n")
    out = Orchestrator(root=workspace, dry_run=True, author="deterministic").resolve("sys-hara")[1].run()
    assert any("asil for S2-E2-C2" in p for p in ids.find_pending(out))


def test_a_stated_asil_that_contradicts_the_table_is_flagged(workspace):
    from fusa.orchestrator import Orchestrator
    table = workspace / "_reference-register" / "asil-table.yaml"
    data = yaml.safe_load(table.read_text())
    data["table"]["S2-E2-C2"] = "A"
    table.write_text(yaml.safe_dump(data))
    (workspace / "input" / "hazards.csv").write_text(
        "function,malfunction,hazardous_event,situation,severity,exposure,controllability,rationale,asil\n"
        "f,m,h,s,S2,E2,C2,r,D\n")
    out = Orchestrator(root=workspace, dry_run=True, author="deterministic").resolve("sys-hara")[1].run()
    assert any("stated asil D disagrees" in p for p in ids.find_pending(out))


def test_a_missing_input_table_is_pending_not_a_crash(workspace):
    from fusa.orchestrator import Orchestrator
    (workspace / "input" / "hazards.csv").unlink()
    out = Orchestrator(root=workspace, dry_run=True, author="deterministic").resolve("sys-hara")[1].run()
    assert any("hazards.csv not provided" in p for p in ids.find_pending(out))
    assert not ids.parse_items(out)                          # and nothing invented


def test_rows_without_an_id_are_numbered_above_the_pinned_ones(workspace):
    from fusa.orchestrator import Orchestrator
    (workspace / "input" / "hazards.csv").write_text(
        "id,function,malfunction,hazardous_event,situation,severity,exposure,controllability,rationale,asil\n"
        "HZ-007,f,m,h,s,S1,E1,C1,r,A\n"
        ",f2,m2,h2,s2,S1,E1,C1,r2,A\n")
    out = Orchestrator(root=workspace, dry_run=True, author="deterministic").resolve("sys-hara")[1].run()
    assert [i.id for i in ids.parse_items(out)] == ["HZ-007", "HZ-008"]


@pytest.mark.parametrize("sec,expected", [(("S0", "E4", "C3"), "QM"), (("S3", "E0", "C3"), "QM"),
                                          (("S3", "E4", "C0"), "QM"), (("S3", "E4", "C3"), None)])
def test_asil_determination_rules(sec, expected):
    assert determine_asil(*sec, {})[0] == expected           # empty table: only the QM classes decide


# ---- SADS -------------------------------------------------------------------

def test_one_safety_goal_per_hazard_that_carries_an_asil(orch):
    orch.reg.generated.write("HARA", content(orch, "sys-hara"))
    items = ids.parse_items(content(orch, "sys-sads"))
    goals = [i for i in items if i.prefix == "SG"]
    assert len(goals) == 4                                   # five hazards, the QM one carries none
    assert "HZ-005" not in {g.fields["parent"] for g in goals}


def test_goals_inherit_the_hazard_asil_and_trace_to_it(orch):
    orch.reg.generated.write("HARA", content(orch, "sys-hara"))
    hazards = {i.id: i for i in orch.reg.generated.items("HARA")}
    for g in [i for i in ids.parse_items(content(orch, "sys-sads")) if i.prefix == "SG"]:
        assert g.fields["asil"] == hazards[g.fields["parent"]].fields["asil"]
        assert g.fields["assumed"] == "true"
        assert g.fields["safe_state"] and g.fields["ftti"]


def test_assumptions_of_use_become_aou_items(orch):
    orch.reg.generated.write("HARA", content(orch, "sys-hara"))
    aou = [i for i in ids.parse_items(content(orch, "sys-sads")) if i.prefix == "AOU"]
    assert len(aou) == 3 and all(i.fields["confirmed_by"] == "integrator" for i in aou)


def test_a_goal_without_a_safe_state_is_pending_not_invented(workspace):
    from fusa.orchestrator import Orchestrator
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic")
    o.reg.generated.write("HARA", o.resolve("sys-hara")[1].run())
    (workspace / "input" / "safety-goals.csv").write_text("hazard,safe_state,ftti\nHZ-001,,\n")
    out = o.resolve("sys-sads")[1].run()
    assert any("safe_state, ftti for the goal mitigating HZ-001" in p for p in ids.find_pending(out))


def test_missing_upstream_is_pending(workspace):
    from fusa.orchestrator import Orchestrator
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic")
    assert any("HARA has not been produced" in p for p in ids.find_pending(o.resolve("sys-sads")[1].run()))


# ---- the agent itself -------------------------------------------------------

def test_an_unknown_generator_kind_is_pending_not_a_crash(workspace):
    from fusa.generators import GeneratorAgent
    from fusa.orchestrator import Orchestrator
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic")
    spec = o.by_id["sys-hara"].model_copy(update={"generator": {"kind": "no-such-generator"}})
    assert any("unknown generator kind" in p for p in ids.find_pending(GeneratorAgent(spec, o.reg).run()))


def test_the_generator_holds_no_model(orch):
    _, agent = orch.resolve("sys-hara")
    assert not hasattr(agent, "llm")


def test_agents_without_a_generator_still_use_the_model(orch):
    """The modes mix: a work product with no table to render from keeps its authoring agent.

    Every shipped agent now declares a generator, so this checks the choice itself rather than
    the current config — adding an agent without one must not require code changes."""
    from fusa.agents.base import AuthoringAgent
    from fusa.agents.registry import build_agents
    from fusa.generators import GeneratorAgent

    specs = [s.model_copy(update={"generator": None}) if s.id == "sys-hara" else s for s in orch.specs]
    agents = build_agents(specs, orch.reg, orch.llm, "deterministic")
    assert isinstance(agents["sys-hara"], AuthoringAgent)      # no table: the model writes it
    assert isinstance(agents["sys-sads"], GeneratorAgent)      # a table: rendered from it


def test_the_whole_path_runs_with_no_api_key(workspace, monkeypatch):
    """Generated content, structural gate, rule review — end to end, no provider key present."""
    from fusa.models import Status
    from fusa.orchestrator import Orchestrator
    for var in ("ANTHROPIC_API_KEY", "XAI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    o = Orchestrator(root=workspace, dry_run=False, author="deterministic", reviewer="rules")
    assert o.run("sys-hara", log=lambda *a: None) is Status.REVIEWED
    assert o.run("sys-sads", log=lambda *a: None) is Status.REVIEWED
    rec = o.reg.process.get("SADS")
    assert rec.gate.passed and rec.review.verdict == "approved"
    assert all(f.severity == "minor" for f in rec.review.findings)     # only human sign-off left
