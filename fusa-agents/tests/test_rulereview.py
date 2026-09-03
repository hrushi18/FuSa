"""Deterministic review — the checklist executed instead of read to a model."""
import pytest

from fusa.agents.rulereview import RuleReviewAgent, duration_ms

GOOD_HARA = """---
id: HARA
agent: sys-hara
---

### HZ-001
- function: measure master-cylinder pressure
- malfunction: reports a pressure lower than actual
- hazardous_event: brake ECU under-boosts, extended stopping distance
- situation: highway braking on a wet surface
- severity: S3
- exposure: E4
- controllability: C3
- rationale: S3 loss of braking; E4 continuous; C3 driver cannot compensate
- asil: D
"""


def reviewer(orch, agent_id="sys-hara"):
    from fusa.agents.registry import build_reviewer
    return build_reviewer(orch.review_spec, orch.by_id[agent_id], orch.reg, orch.llm, "rules")


@pytest.fixture
def orch(workspace):
    from fusa.orchestrator import Orchestrator
    return Orchestrator(root=workspace, dry_run=True, reviewer="rules")


# ---- verdicts ---------------------------------------------------------------

def test_a_well_formed_work_product_is_approved(orch):
    v = reviewer(orch).run(GOOD_HARA)
    assert v.verdict == "approved"
    assert {f.severity for f in v.findings} == {"minor"}          # only human sign-off left


def test_missing_fields_are_major_findings_and_force_rework(orch):
    v = reviewer(orch).run("---\nid: HARA\n---\n\n### HZ-001\n- asil: D\n- text: x\n")
    majors = [f for f in v.findings if f.severity == "major"]
    assert v.verdict == "rework"
    assert any("missing function" in f.description for f in majors)
    assert all(f.clause for f in majors)                          # every finding cites its clause


def test_judgment_items_are_minor_so_they_never_stall_the_chain(orch):
    from fusa.report import BLOCKING_SEVERITIES
    v = reviewer(orch).run(GOOD_HARA)
    assert [f.id for f in v.findings] == ["HARA-04", "HARA-05"]
    assert all(f.severity not in BLOCKING_SEVERITIES for f in v.findings)
    assert all("confirmation review required" in f.description for f in v.findings)


def test_structural_items_are_left_to_the_gate(orch):
    v = reviewer(orch).run(GOOD_HARA)
    assert "HARA-06" not in {f.id for f in v.findings}            # id convention is the gate's job


# ---- individual rule kinds --------------------------------------------------

def test_field_in_rejects_an_asil_outside_the_scale(orch):
    bad = GOOD_HARA.replace("- asil: D", "- asil: E")
    assert any("asil 'E' is not one of" in f.description for f in reviewer(orch).run(bad).findings)


def test_time_budget_catches_a_reaction_that_misses_the_ftti(orch):
    tsc = ("---\nid: TSC\n---\n\n### TSC-001\n- sm: SM-001\n"
           "- fdt: 8 ms\n- frt: 5 ms\n- ftti: 10 ms\n")
    out = [f.description for f in reviewer(orch, "sys-tsc").run(tsc).findings]
    assert any("fdt+frt 13 ms exceeds ftti 10 ms" in d for d in out)


def test_time_budget_accepts_a_budget_that_fits(orch):
    tsc = ("---\nid: TSC\n---\n\n### TSC-001\n- sm: SM-001\n"
           "- fdt: 4 ms\n- frt: 5 ms\n- ftti: 10 ms\n")
    assert not any("exceeds ftti" in f.description for f in reviewer(orch, "sys-tsc").run(tsc).findings)


@pytest.mark.parametrize("raw,ms", [("5 ms", 5), ("1 s", 1000), ("250us", 0.25), ("2 min", 120000),
                                    ("", None), ("soon", None)])
def test_duration_parsing(raw, ms):
    assert duration_ms(raw) == ms


def test_asil_inherit_flags_a_child_that_differs_without_decomposition(orch, workspace):
    orch.reg.generated.write("SADS", "---\nid: SADS\n---\n\n### SG-001\n- asil: D\n- text: goal\n")
    tsr = "---\nid: TSR\n---\n\n### TSR-001\n- parent: SG-001\n- asil: B\n- text: t\n- verification: test\n"
    out = [f.description for f in reviewer(orch, "sys-tsr").run(tsr).findings]
    assert any("asil B differs from parent SG-001 (D)" in d for d in out)


def test_asil_inherit_accepts_a_cited_decomposition(orch):
    orch.reg.generated.write("SADS", "---\nid: SADS\n---\n\n### SG-001\n- asil: D\n- text: goal\n")
    tsr = ("---\nid: TSR\n---\n\n### TSR-001\n- parent: SG-001\n- asil: B\n- text: t\n"
           "- verification: test\n- decomposition: ASIL D -> B(D) + B(D) per 26262-9:5\n")
    assert not any("differs from parent" in f.description for f in reviewer(orch, "sys-tsr").run(tsr).findings)


def test_refs_flags_a_safety_mechanism_that_does_not_exist(orch):
    tsc = "---\nid: TSC\n---\n\n### TSC-001\n- sm: SM-404\n"
    assert any("sm SM-404 does not exist" in f.description for f in reviewer(orch, "sys-tsc").run(tsc).findings)


def test_defined_once_flags_a_mechanism_described_outside_the_catalogue(orch):
    orch.reg.generated.write("TSC", "---\nid: TSC\n---\n\n### SM-009\n- text: described in the wrong place\n")
    sm = "---\nid: SM-CATALOG\n---\n\n### SM-001\n- detects: x\n- reaction: y\n- dc_claim: 99%\n- allocated_to: z\n"
    out = [f.description for f in reviewer(orch, "sm-catalog").run(sm).findings]
    assert any("SM items also defined in TSC" in d for d in out)


def test_aux_rule_wants_the_metrics_file_from_tooling(orch):
    fmeda = "---\nid: HW-FMEDA\n---\n\n### HFD-001\n- sm: SM-001\n"
    assert any("metrics.md is not attached" in f.description for f in reviewer(orch, "hw-fmeda").run(fmeda).findings)


def test_matches_rule_wants_the_architecture_diagram(orch):
    tsc = "---\nid: TSC\n---\n\n### TSC-001\n- sm: SM-001\n"
    assert any("Mermaid" in f.description for f in reviewer(orch, "sys-tsc").run(tsc).findings)


# ---- the reviewer itself ----------------------------------------------------

def test_an_unknown_rule_kind_is_reported_not_raised(orch):
    r = reviewer(orch)
    findings = r._apply({"id": "X-01", "check": "review", "rule": {"kind": "no-such-rule"}}, GOOD_HARA)
    assert findings[0].severity == "minor" and "unknown rule kind" in findings[0].description


def test_a_rule_that_raises_fails_the_work_product_rather_than_passing_it(orch):
    r = reviewer(orch)
    findings = r._apply({"id": "X-02", "check": "review", "rule": {"kind": "field_in"}}, GOOD_HARA)
    assert findings[0].severity == "major" and "could not be evaluated" in findings[0].description


def test_the_rule_reviewer_never_receives_the_authoring_method(orch):
    assert not hasattr(reviewer(orch).checklists, "method")       # same guarantee as ReviewAgent
    assert not hasattr(reviewer(orch), "llm")                     # and no model at all


def test_review_needs_no_api_key(workspace, monkeypatch):
    """The whole review path with every provider key removed and no dry-run stub for it."""
    from fusa.models import Status
    from fusa.orchestrator import Orchestrator
    for var in ("ANTHROPIC_API_KEY", "XAI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    o = Orchestrator(root=workspace, dry_run=True, reviewer="rules")
    assert o.run("sys-hara", log=lambda *a: None) is Status.REWORK      # stub content, honestly rejected
    rec = o.reg.process.get("HARA")
    assert rec.review.reviewer.startswith("verification-review")
    assert any(f.severity == "major" for f in rec.review.findings)


def test_reviewer_is_selectable_by_env_and_flag(workspace, monkeypatch):
    import importlib
    import fusa.config
    from fusa.orchestrator import Orchestrator
    monkeypatch.setenv("FUSA_REVIEWER", "rules")
    importlib.reload(fusa.config)
    try:
        assert Orchestrator(root=workspace, dry_run=True).reviewer_kind == "rules"
        assert Orchestrator(root=workspace, dry_run=True, reviewer="model").reviewer_kind == "model"
    finally:
        monkeypatch.delenv("FUSA_REVIEWER", raising=False)
        importlib.reload(fusa.config)


def test_every_shipped_rule_names_a_kind_that_exists():
    """A typo in a checklist rule would silently stop checking that item."""
    import yaml
    from pathlib import Path
    import fusa
    from fusa.agents.rulereview import RULES
    root = Path(fusa.__file__).resolve().parents[1] / "_checklist-register"
    for f in sorted(root.glob("*.yaml")):
        for item in yaml.safe_load(f.read_text(encoding="utf-8"))["items"]:
            if item.get("rule"):
                assert item["rule"]["kind"] in RULES, f"{f.stem}/{item['id']}"


# ---- the generic checklist: rules that apply to every work product ----------

GENERIC_CASES = [
    ("a pending with no section",  "[PENDING: x <- me]\n", "no `## Open points` section"),
    ("a section missing one",      "[PENDING: a <- me]\n[PENDING: b <- me]\n\n## Open points\n\n- a <- me\n",
                                   "open point not listed in the section: b <- me"),
]


@pytest.mark.parametrize("name,body,expected", GENERIC_CASES)
def test_open_points_must_list_every_pending(orch, name, body, expected):
    from fusa.agents.rulereview import Ctx, rule_pending_listed
    failures = rule_pending_listed(Ctx(orch.by_id["hw-hsr"], f"---\nid: HSR\n---\n\n{body}", None, {}))
    assert any(expected in f for f in failures), name


@pytest.mark.parametrize("body", ["[PENDING: x <- me]\n\n## Open points\n\n- x <- me\n",
                                  "### HSR-001\n- text: nothing open here\n"])
def test_a_complete_or_empty_open_points_section_passes(orch, body):
    from fusa.agents.rulereview import Ctx, rule_pending_listed
    assert rule_pending_listed(Ctx(orch.by_id["hw-hsr"], f"---\nid: HSR\n---\n\n{body}", None, {})) == []


def test_a_clause_listed_only_in_front_matter_is_not_cited(orch):
    """Naming a clause in the header is bookkeeping; citing it in the text is the claim."""
    from fusa.agents.rulereview import Ctx, rule_cites_clauses
    spec = orch.by_id["hw-hsr"]
    front_only = f"---\nid: HSR\nclauses: {', '.join(spec.clauses)}\n---\n\n### HSR-001\n- text: t\n"
    assert rule_cites_clauses(Ctx(spec, front_only, None, {}))
    cited = f"---\nid: HSR\n---\n\nProduced under {', '.join(spec.clauses)}.\n\n### HSR-001\n- text: t\n"
    assert rule_cites_clauses(Ctx(spec, cited, None, {})) == []


def test_generic_checklist_now_decides_two_of_its_items(workspace):
    import yaml
    items = yaml.safe_load((workspace / "_checklist-register" / "generic.yaml").read_text())["items"]
    ruled = {i["id"] for i in items if i.get("rule")}
    judged = {i["id"] for i in items if i.get("check") == "review" and not i.get("rule")}
    assert ruled == {"GEN-05", "GEN-06"}
    assert judged == {"GEN-03", "GEN-04"}          # per-statement citation and invention: judgement


def test_generated_work_products_satisfy_the_generic_rules(workspace):
    """The rules were added with the generators made to comply, not the other way round."""
    from fusa.orchestrator import Orchestrator
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic", reviewer="rules")
    for agent_id in ("sys-hara", "sys-sads", "sys-tsr", "sm-catalog", "sys-tsc", "hw-hsr"):
        wp = o.by_id[agent_id].work_product
        o.reg.generated.write(wp, o.resolve(agent_id)[1].run())
    verdict = reviewer(o, "hw-hsr").run(o.reg.generated.read("HSR"))
    assert {f.id for f in verdict.findings} == {"GEN-03", "GEN-04"}     # only the judgement ones
    assert verdict.verdict == "approved"
