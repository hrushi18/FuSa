"""Deterministic authoring of SYS-FMEA and TARA — coverage gaps and risk, derived not asserted."""
import pytest

from fusa.tools import ids

UPSTREAM = ("sys-hara", "sys-sads", "sys-tsr", "sm-catalog", "sys-tsc")


@pytest.fixture
def chain(workspace):
    from fusa.orchestrator import Orchestrator
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic", reviewer="rules")
    for agent_id in UPSTREAM:
        o.reg.generated.write(o.by_id[agent_id].work_product, o.resolve(agent_id)[1].run())
    return o


def items(orch, agent_id):
    return ids.parse_items(orch.resolve(agent_id)[1].run())


# ---- SYS-FMEA ---------------------------------------------------------------

def test_every_row_carries_what_the_checklist_demands(chain):
    rows = items(chain, "sys-fmea")
    assert len(rows) == 8
    for r in rows:
        assert all(r.fields[k] for k in ("element", "function", "failure_mode",
                                         "local_effect", "item_effect", "classification"))


def test_a_mode_with_no_mechanism_is_flagged_uncovered_and_returned(chain):
    """A blank `sm` cell against a violated goal is what makes it uncovered — not a judgement."""
    uncovered = [r for r in items(chain, "sys-fmea") if r.fields.get("finding") == "uncovered"]
    assert [r.id for r in uncovered] == ["SFM-007"]
    assert uncovered[0].fields["returns_to"] == "sys-tsc"
    assert uncovered[0].fields["violated_sg"] == "SG-001" and not uncovered[0].fields.get("sm")


def test_a_covered_mode_carries_no_finding(chain):
    covered = [r for r in items(chain, "sys-fmea") if r.fields.get("sm")]
    assert covered and all("finding" not in r.fields for r in covered)


def test_a_safe_mode_violating_no_goal_is_not_uncovered(chain):
    safe = [r for r in items(chain, "sys-fmea") if r.fields["classification"] == "SAFE"]
    assert safe and all("finding" not in r.fields for r in safe)


def test_the_uncovered_mode_sends_the_concept_back(chain):
    """The framework's feedback loop, fired by a blank cell rather than by a model's opinion."""
    from fusa.models import Status
    for wp, agent in (("TSC", "sys-tsc"), ("SM-CATALOG", "sm-catalog")):     # sys-fmea's upstream
        chain.reg.process.update(wp, agent, status=Status.REVIEWED)
    chain.run("sys-fmea", log=lambda *a: None)
    assert chain.reg.process.status("TSC") is Status.REWORK


def test_an_element_allocated_in_the_concept_but_never_analysed_is_reported(chain, workspace):
    (workspace / "input" / "failure-modes.csv").write_text(
        "element,function,failure_mode,local_effect,item_effect,classification\n"
        "sense IC,f,m,l,i,SR\n")
    pending = ids.find_pending(chain.resolve("sys-fmea")[1].run())
    assert any("'CAN transceiver'" in p and "no failure-mode row" in p for p in pending)


def test_a_violated_goal_that_does_not_exist_is_reported(chain, workspace):
    (workspace / "input" / "failure-modes.csv").write_text(
        "element,function,failure_mode,local_effect,item_effect,classification,violated_sg,sm\n"
        "sense IC,f,m,l,i,SR,SG-404,SM-001\n")
    assert any("SG-404, which is not a safety goal" in p
               for p in ids.find_pending(chain.resolve("sys-fmea")[1].run()))


# ---- TARA -------------------------------------------------------------------

def test_assets_and_threats_become_their_own_item_kinds(chain):
    rows = items(chain, "cs-tara")
    assert [r.prefix for r in rows].count("AS") == 4
    assert [r.prefix for r in rows].count("TS") == 5


def test_a_threat_is_parented_to_its_asset(chain):
    rows = {r.id: r for r in items(chain, "cs-tara")}
    ts = rows["TS-001"]
    assert ts.fields["parent"] == "AS-001" and rows["AS-001"].prefix == "AS"


def test_the_parent_link_survives_ids_being_assigned(workspace):
    """Assets with no id column still get linked: the link is resolved after numbering."""
    from fusa.orchestrator import Orchestrator
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic")
    (workspace / "input" / "assets.csv").write_text(
        "name,property,damage_scenario\npressure signal,integrity,forged value\n")
    (workspace / "input" / "threat-scenarios.csv").write_text(
        "asset,stride,attack_path,feasibility,impact_safety,rationale,treatment,safety_goal\n"
        "pressure signal,T,spoofed frame,medium,severe,needs bus access,reduce,SG-001\n")
    rows = ids.parse_items(o.resolve("cs-tara")[1].run())
    ts = next(r for r in rows if r.prefix == "TS")
    assert ts.fields["parent"] == "AS-001"


def test_risk_is_looked_up_from_the_house_matrix(chain):
    ts = {r.id: r for r in items(chain, "cs-tara")}["TS-001"]
    assert ts.fields["risk"] == "4"                       # severe × medium
    assert "house matrix" in ts.fields["risk_basis"]


def test_the_worst_of_the_four_categories_drives_the_lookup(chain):
    ts = {r.id: r for r in items(chain, "cs-tara")}["TS-005"]
    assert ts.fields["impact"] == "S=negligible, F=moderate, O=negligible, P=negligible"
    assert ts.fields["risk"] == "3"                       # moderate (the worst) × high


def test_a_combination_missing_from_the_matrix_is_pending(chain, workspace):
    import yaml
    path = workspace / "_reference-register" / "risk-matrix.yaml"
    data = yaml.safe_load(path.read_text())
    del data["matrix"]["severe"]["medium"]
    path.write_text(yaml.safe_dump(data))
    out = chain.resolve("cs-tara")[1].run()
    assert any("impact severe × feasibility medium is not in the house matrix" in p
               for p in ids.find_pending(out))


def test_an_unknown_impact_word_is_pending_not_guessed(chain, workspace):
    (workspace / "input" / "threat-scenarios.csv").write_text(
        "asset,stride,attack_path,feasibility,impact_safety,rationale,treatment\n"
        "AS-001,T,path,medium,catastrophic,why,reduce\n")
    assert any("impact rating catastrophic is not one of" in p
               for p in ids.find_pending(chain.resolve("cs-tara")[1].run()))


def test_a_safety_impact_with_no_safety_goal_is_pending(chain, workspace):
    (workspace / "input" / "threat-scenarios.csv").write_text(
        "asset,stride,attack_path,feasibility,impact_safety,rationale,treatment\n"
        "AS-001,T,path,medium,major,why,reduce\n")
    assert any("cites no safety goal" in p for p in ids.find_pending(chain.resolve("cs-tara")[1].run()))


def test_treated_risks_are_owed_to_the_cybersecurity_goals_agent(chain):
    pending = ids.find_pending(chain.resolve("cs-tara")[1].run())
    assert any("cybersecurity goal derivation for 4 treated" in p and "cs-goals" in p for p in pending)


def test_a_threat_against_an_unknown_asset_is_reported(chain, workspace):
    (workspace / "input" / "threat-scenarios.csv").write_text(
        "asset,stride,attack_path,feasibility,rationale,treatment\n"
        "AS-404,T,path,medium,why,retain\n")
    out = chain.resolve("cs-tara")[1].run()
    assert any("'AS-404', which is not an asset" in p for p in ids.find_pending(out))
    assert not [r for r in ids.parse_items(out) if r.prefix == "TS"]


# ---- both, through the chain ------------------------------------------------

def test_seven_work_products_reach_reviewed_with_no_api_key(workspace, monkeypatch):
    from fusa.models import Status
    from fusa.orchestrator import Orchestrator
    for var in ("ANTHROPIC_API_KEY", "XAI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    o = Orchestrator(root=workspace, dry_run=False, author="deterministic", reviewer="rules")
    for agent_id in (*UPSTREAM, "cs-tara", "sys-fmea"):
        assert o.run(agent_id, log=lambda *a: None) is Status.REVIEWED, agent_id
    assert o.reg.process.status("TSC") is Status.REWORK      # the uncovered mode sent it back
