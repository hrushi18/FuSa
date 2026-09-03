"""FTA and DFA: the house methods, and the checklists that decide them.

The methods are engineering procedure and cannot be tested. What can be tested is that the
checklists which enforce them pass a well-formed analysis and catch a sloppy one — otherwise the
rules would be decoration.
"""
import pytest

GOOD_FTA = """---
id: SYS-FTA
---

# System FTA

Produced under 26262-4:7.4.3, 26262-9:8.

### FTA-001
- top_event: SG-001 violated — the item reports a pressure lower than actual with no invalid status
- parent: SG-001
- gate: OR

### FTA-002
- parent: FTA-001
- basic_event: sense IC reports a biased low value
- element: sense IC
- failure_mode: SFM-002
- sm: SM-001
- cut_set_order: 1

### FTA-003
- parent: FTA-001
- basic_event: supply droops slowly below the qualified band
- element: supply monitor
- failure_mode: SFM-007
- cut_set_order: 1
- finding: single_point_cut_set
- returns_to: sys-tsc
"""

GOOD_DFA = """---
id: SYS-DFA
---

# System DFA

Produced under 26262-9:7.

### DFA-001
- claim: the SM-002 plausibility check is independent of the sense IC it monitors
- elements: sense IC, signal processing
- parent: TSC-002

### DFA-002
- parent: DFA-001
- coupling_factor: shared supply
- category: common_cause
- initiator: the 5 V rail droops slowly below the qualified band
- effect: the sense IC biases low and the check sees a consistent gradient
- measure: SM-004
- sm: SM-004
- verdict: mitigated

### DFA-003
- parent: DFA-001
- coupling_factor: common temperature environment
- category: common_cause
- initiator: both parts sit on one board above the qualified ambient
- effect: both drift in the same direction, so the check cannot see the deviation
- verdict: open
- finding: dependent_failure
- returns_to: sys-tsc
"""


@pytest.fixture
def review(workspace):
    from fusa.agents.registry import build_reviewer
    from fusa.orchestrator import Orchestrator
    o = Orchestrator(root=workspace, dry_run=True, reviewer="rules")
    o.reg.generated.write("SM-CATALOG", "---\nid: SM-CATALOG\n---\n\n### SM-001\n- text: x\n\n"
                                        "### SM-004\n- text: supply monitor\n")

    def run(agent_id, content):
        return build_reviewer(o.review_spec, o.by_id[agent_id], o.reg, o.llm, "rules").run(content)
    return run


def majors(verdict):
    return {f.id.split(".")[0]: f.description for f in verdict.findings if f.severity == "major"}


# ---- the methods exist and say something --------------------------------------

@pytest.mark.parametrize("name", ["fta", "dfa"])
def test_the_method_is_written_not_a_placeholder(workspace, name):
    text = (workspace / "_reference-register" / "methods" / f"{name}.md").read_text(encoding="utf-8")
    assert "placeholder" not in text.lower()
    assert len(text) > 800                          # comparable to the other house methods
    assert "26262-9:" in text                       # cites the clause it implements


def test_the_method_prescribes_the_fields_its_checklist_decides(workspace):
    import yaml
    for name, wp in (("fta", "FTA"), ("dfa", "DFA")):
        method = (workspace / "_reference-register" / "methods" / f"{name}.md").read_text()
        checklist = yaml.safe_load((workspace / "_checklist-register" / f"{wp}.yaml").read_text())
        for item in checklist["items"]:
            rule = item.get("rule") or {}
            for field in rule.get("require", []) + ([rule["field"]] if rule.get("field") else []):
                assert field in method, f"{wp}/{item['id']}: rule checks `{field}`, method never names it"


# ---- the checklists decide -----------------------------------------------------

@pytest.mark.parametrize("agent,content", [("sys-fta", GOOD_FTA), ("sys-dfa", GOOD_DFA)])
def test_a_well_formed_analysis_is_approved(review, agent, content):
    verdict = review(agent, content)
    assert verdict.verdict == "approved", majors(verdict)


def test_a_sloppy_fault_tree_is_caught(review):
    bad = (GOOD_FTA.replace("- gate: OR", "- gate: MAJORITY")
                   .replace("- element: sense IC\n", "")
                   .replace("- returns_to: sys-tsc\n", "")
                   .replace("Produced under 26262-4:7.4.3, 26262-9:8.\n", ""))
    found = majors(review("sys-fta", bad))
    assert "not one of AND, OR" in found["FTA-02"]              # a gate that is not a gate
    assert "missing element" in found["FTA-03"]                 # a basic event standing for nothing
    assert "missing returns_to" in found["FTA-04"]              # a single-point cut set not routed
    assert "never cited in the body" in found["GEN-06"]         # inherited from the generic checklist


def test_a_sloppy_dependent_failure_analysis_is_caught(review):
    bad = (GOOD_DFA.replace("- elements: sense IC, signal processing\n", "")
                   .replace("- measure: SM-004\n", "")
                   .replace("- category: common_cause\n- initiator: both parts",
                            "- category: systematic\n- initiator: both parts")
                   .replace("- returns_to: sys-tsc\n", ""))
    found = majors(review("sys-dfa", bad))
    assert "missing elements" in found["DFA-01"]                # a claim with only one side
    assert "not one of common_cause, cascading" in found["DFA-03"]
    assert "missing measure" in found["DFA-05"]                 # mitigated by argument alone
    assert "missing returns_to" in found["DFA-06"]              # an open coupling factor not routed


def test_a_mechanism_that_does_not_exist_is_caught(review):
    bad = GOOD_DFA.replace("- sm: SM-004", "- sm: SM-404")
    assert "SM-404 does not exist" in majors(review("sys-dfa", bad))["DFA-07"]


# ---- checklist inheritance -----------------------------------------------------

def test_a_checklist_inherits_the_house_wide_items(workspace):
    from fusa.registers import Registers
    reg = Registers.load(workspace)
    fta = {i["id"] for i in reg.checklists.items("FTA")}
    assert {"GEN-05", "GEN-06"} <= fta and {"FTA-01", "FTA-08"} <= fta
    assert len(fta) == len(reg.checklists.items("FTA"))          # no duplicates


def test_inheritance_is_opt_in(workspace):
    from fusa.registers import Registers
    reg = Registers.load(workspace)
    assert not [i for i in reg.checklists.items("HARA") if i["id"].startswith("GEN-")]


def test_a_local_item_wins_over_the_inherited_one(workspace):
    from fusa.registers import Registers
    (workspace / "_checklist-register" / "X.yaml").write_text(
        "work_product: X\nextends: generic\nitems:\n"
        "  - {id: GEN-05, text: local override, check: structural}\n")
    reg = Registers.load(workspace)
    gen05 = [i for i in reg.checklists.items("X") if i["id"] == "GEN-05"]
    assert len(gen05) == 1 and gen05[0]["text"] == "local override"


def test_a_cycle_in_extends_does_not_hang(workspace):
    from fusa.registers import Registers
    for name in ("A", "B"):
        other = "B" if name == "A" else "A"
        (workspace / "_checklist-register" / f"{name}.yaml").write_text(
            f"work_product: {name}\nextends: {other}\nitems:\n  - {{id: {name}-01, text: t, check: review}}\n")
    ids = {i["id"] for i in Registers.load(workspace).checklists.items("A")}
    assert ids == {"A-01", "B-01"}


# ---- the six agents that use them ----------------------------------------------

def test_the_fta_and_dfa_agents_point_at_the_new_checklists(workspace):
    from fusa.agents.registry import load_specs
    specs = {s.id: s for s in load_specs(workspace / "config" / "agents.yaml")}
    for agent_id in ("sys-fta", "hw-fta", "sw-fta"):
        assert specs[agent_id].checklist == "FTA"
    for agent_id in ("sys-dfa", "hw-dfa", "sw-dfa"):
        assert specs[agent_id].checklist == "DFA"


def test_no_enabled_agent_still_uses_a_placeholder_method(workspace):
    from fusa.agents.registry import load_specs
    for spec in load_specs(workspace / "config" / "agents.yaml"):
        if spec.method:
            text = (workspace / "_reference-register" / "methods" / f"{spec.method}.md").read_text()
            assert "placeholder" not in text.lower(), spec.id
