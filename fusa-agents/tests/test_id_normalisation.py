"""Deterministic id pass — the framework owns item ids, the model owns the content."""
import json

from fusa.tools import ids

OWNERS = {"HZ": ("HARA", "sys-hara"), "SG": ("SADS", "sys-sads"), "AOU": ("SADS", "sys-sads")}


def norm(text, allowed=("HZ",), wp="HARA"):
    return ids.normalise_items(text, list(allowed), wp, OWNERS)


def test_placeholder_ids_are_numbered_by_the_framework():
    text, notes = norm("### HZ-nnn\n- text: a\n\n### HZ-nnn\n- text: b\n")
    assert [i.id for i in ids.parse_items(text)] == ["HZ-001", "HZ-002"]
    assert all("assigned by the framework" in n for n in notes)


def test_short_numbers_are_padded_and_references_follow():
    text, _ = norm("### HZ-1\n- text: a\n\n### SG-000\n- parent: HZ-1\n", allowed=("HZ", "SG"))
    assert "### HZ-001" in text
    assert "- parent: HZ-001" in text                 # body reference rewritten with the heading


def test_wrong_heading_level_and_trailing_title_are_recovered():
    text, _ = norm("## HZ-002 — Loss of pressure signal\n- asil: D\n")
    item = ids.parse_items(text)[0]
    assert item.id == "HZ-002"                        # `##` would have been invisible to the gate
    assert item.fields["title"] == "Loss of pressure signal"
    assert item.fields["asil"] == "D"


def test_duplicate_ids_are_renumbered_above_the_highest_claimed():
    text, notes = norm("### HZ-001\n- text: a\n\n### HZ-001\n- text: b\n\n### HZ-007\n- text: c\n")
    assert [i.id for i in ids.parse_items(text)] == ["HZ-001", "HZ-008", "HZ-007"]
    assert any("duplicate" in n for n in notes)


def test_foreign_prefix_is_demoted_not_claimed():
    """The screenshot case: sys-hara emitted AOU-001..003 and the gate failed the whole run."""
    text, notes = norm("### HZ-001\n- text: hazard\n\n### AOU-001 — host checks the status word\n"
                       "- text: assumption\n\n### AOU-002\n- text: another\n")
    assert [i.id for i in ids.parse_items(text)] == ["HZ-001"]      # AOU is no longer a HARA item
    assert "#### AOU-001 — host checks the status word" in text    # text kept, verbatim
    assert "SADS" in text and "sys-sads" in text                   # and pointed at its real owner
    assert len([n for n in notes if "AOU" in n]) == 2


def test_pending_marker_on_a_heading_is_never_dropped():
    text, _ = norm("### HZ-nnn [PENDING: exposure rating <- project]\n- text: a\n")
    assert ids.find_pending(text) == ["exposure rating <- project"]


def test_valid_document_is_left_alone():
    src = "### HZ-001\n- text: a\n\n### HZ-002\n- text: b\n"
    text, notes = norm(src)
    assert text == src.rstrip("\n") and notes == []


def test_non_item_headings_are_untouched():
    src = "# HARA\n## Assumptions\n### 3-axis mounting\n- text: a\n"
    text, notes = norm(src)
    assert text == src.rstrip("\n") and notes == []


# ---- every declared agent can actually own an id ----------------------------

def test_every_agent_has_a_prefix_the_grammar_accepts(workspace):
    """A prefix the id grammar rejects costs the work product every traceable item."""
    from fusa.agents.registry import load_specs
    from fusa.models import PREFIX_RE
    bad = {s.id: s.prefixes for s in load_specs(workspace / "config" / "agents.yaml")
           if s.kind != "review" and not all(PREFIX_RE.match(p) for p in s.prefixes)}
    assert bad == {}


def test_prefixes_are_owned_by_exactly_one_agent(workspace):
    from fusa.agents.registry import load_specs, prefix_owners
    specs = [s for s in load_specs(workspace / "config" / "agents.yaml") if s.kind != "review"]
    declared = [p for s in specs for p in s.prefixes]
    assert len(declared) == len(set(declared))              # no prefix claimed twice
    assert prefix_owners(specs)["AOU"] == ("SADS", "sys-sads")


def test_derived_prefix_drops_the_hyphen():
    from fusa.models import AgentSpec
    spec = AgentSpec(id="x", work_product="HW-DESIGN", title="t", phase=3)
    assert spec.prefixes == ["HWDESIGN"]                    # never the unusable 'HW-DESIGN'


# ---- end to end: the run from the screenshot --------------------------------

MODEL_HARA = """---
id: HARA
title: Hazard Analysis and Risk Assessment (assumed, SEooC)
agent: sys-hara
clauses: 26262-3:6
status: draft
---

# HARA

## HZ-1 — Loss of pressure signal
- function: pressure sensing
- severity: S3
- exposure: E4
- controllability: C3
- asil: D

### AOU-001
- text: the host evaluates the status word every cycle

### AOU-002
- text: the module is mounted rigidly

### AOU-003
- text: supply stays within 4.5-5.5 V
"""


def test_agent_run_survives_the_ids_a_model_actually_invents(workspace, monkeypatch):
    """Same output that produced `AOU-001: prefix not allowed in HARA` — now it gates through."""
    from fusa.agents.llm import LLM
    from fusa.models import Status
    from fusa.orchestrator import Orchestrator

    def fake_complete(self, system, user, *, stub=None):
        return json.dumps({"verdict": "approved", "findings": []}) \
            if "independent functional-safety reviewer" in system else MODEL_HARA

    monkeypatch.setattr(LLM, "complete", fake_complete)
    orch = Orchestrator(root=workspace, dry_run=False)
    logs: list[str] = []

    assert orch.run("sys-hara", log=logs.append) == Status.REVIEWED

    content = (workspace / "_generated" / "HARA" / "HARA.md").read_text()
    assert [i.id for i in ids.parse_items(content)] == ["HZ-001"]   # the one real hazard, padded
    assert "#### AOU-001" in content                                # assumptions kept as commentary
    rec = orch.reg.process.get("HARA")
    assert rec.gate.passed and not rec.gate.errors
    assert any("AOU-001" in w and "SADS" in w for w in rec.gate.warnings)
    assert any("id fixed" in line and "AOU-001" in line for line in logs)
