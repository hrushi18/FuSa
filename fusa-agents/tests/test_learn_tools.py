"""The calculator teaches the lookup the chain performs, by performing the same one.

Reimplementing the determination rule here — even as the well-known S+E+C mnemonic, which
does reproduce the table exactly — would put normative content this project deliberately does
not ship into the source, and would disagree with whatever the engineer actually transcribed.
"""
import csv
import pathlib
import re

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(workspace):
    from fusa.ui.server import create_app
    with TestClient(create_app(root=workspace, dry_run=True)) as c:
        yield c


def fill(client, **cells):
    r = client.post("/api/asil-table", json={"values": cells})
    assert r.status_code == 200, r.text
    return r


def test_a_zero_class_is_qm_without_consulting_the_table(client):
    """S0/E0/C0 is QM by the definition of the class, which is why it needs no licensed value."""
    r = client.get("/api/learn/asil", params={"s": "S0", "e": "E4", "c": "C3"}).json()
    assert r["asil"] == "QM" and "class definition" in r["why"]


def test_a_filled_cell_comes_back_from_the_table(client):
    fill(client, **{"S3-E4-C3": "D"})
    r = client.get("/api/learn/asil", params={"s": "S3", "e": "E4", "c": "C3"}).json()
    assert r["asil"] == "D" and r["key"] == "S3-E4-C3"
    assert "table" in r["why"]


def test_an_unfilled_cell_is_reported_as_unfilled_never_guessed(client):
    """The whole reason the calculator reads a file instead of applying a formula."""
    r = client.get("/api/learn/asil", params={"s": "S2", "e": "E3", "c": "C2"}).json()
    assert r["asil"] is None
    assert r["key"] == "S2-E3-C2"


def test_the_answer_matches_what_the_chain_would_derive_for_the_same_hazard(client, workspace):
    """One lookup, two callers. If these ever disagree the platform is teaching a fiction."""
    from fusa.generators.kinds import determine_asil, load_asil_table
    from fusa.orchestrator import Orchestrator
    fill(client, **{"S3-E4-C3": "D", "S1-E1-C1": "QM"})
    orch = Orchestrator(root=workspace, dry_run=True)
    table = load_asil_table(orch.reg)
    for s, e, c in [("S3", "E4", "C3"), ("S1", "E1", "C1"), ("S2", "E2", "C2"), ("S0", "E1", "C1")]:
        chain, _ = determine_asil(s, e, c, table)
        api = client.get("/api/learn/asil", params={"s": s, "e": e, "c": c}).json()["asil"]
        assert api == chain, f"{s}-{e}-{c}: calculator said {api}, chain said {chain}"


def test_the_endpoint_reports_how_much_of_the_table_is_transcribed(client):
    before = client.get("/api/learn/asil", params={"s": "S1", "e": "E1", "c": "C1"}).json()
    assert before["filled"] == 0 and before["total"] == 36
    fill(client, **{"S1-E1-C1": "QM"})
    after = client.get("/api/learn/asil", params={"s": "S1", "e": "E1", "c": "C1"}).json()
    assert after["filled"] == 1 and after["total"] == 36


@pytest.mark.parametrize("s,e,c", [("S9", "E1", "C1"), ("", "E1", "C1"), ("S1", "E9", "C1")])
def test_a_class_outside_the_scales_is_rejected_not_looked_up(client, s, e, c):
    assert client.get("/api/learn/asil", params={"s": s, "e": e, "c": c}).status_code == 400


def test_no_source_file_implements_a_determination_rule():
    """R2, asserted rather than trusted: the mnemonic must not appear in this codebase."""
    import pathlib, re
    root = pathlib.Path(__file__).resolve().parents[1] / "fusa"
    pattern = re.compile(r"(sev\s*\+\s*exp|s\s*\+\s*e\s*\+\s*c)", re.I)
    for p in list(root.rglob("*.py")) + list(root.rglob("*.js")):
        assert not pattern.search(p.read_text(encoding="utf-8")), f"{p} looks like an ASIL formula"


def test_the_calculator_asks_the_server_rather_than_deriving_an_answer(client):
    """If the browser ever computes an ASIL itself, the licensed table stops being the source."""
    js = client.get("/static/learn/tools/asil.js")
    assert js.status_code == 200
    assert "/api/learn/asil" in js.text, "the calculator must ask the server"
    for formula in ("S+E+C", "s + e + c", "sum 7", "= 7", "severity + exposure"):
        assert formula not in js.text, f"asil.js appears to derive an ASIL: {formula!r}"


def test_the_shell_routes_to_a_tool(client):
    assert "#/tool/" in client.get("/static/learn/app.js").text


def test_the_breadcrumb_and_the_nav_read_the_tool_titles_from_one_list(client):
    """The router used to spell the breadcrumb from the raw route id ('Tools → asil'). The
    fix has to be one shared list, not app.js growing its own copy of nav.js's titles."""
    nav_js = client.get("/static/learn/nav.js").text
    app_js = client.get("/static/learn/app.js").text
    assert "ASIL Calculator" in nav_js and "HARA Builder" in nav_js
    assert "ASIL Calculator" not in app_js and "HARA Builder" not in app_js, \
        "app.js carries its own spelling of a tool title instead of importing nav.js's"
    assert "TOOLS" in app_js, "the breadcrumb must read the nav's exported list"


# ---- the HARA builder ----

ROOT = pathlib.Path(__file__).resolve().parents[1]
HARA_JS = ROOT / "fusa" / "ui" / "static" / "learn" / "tools" / "hara.js"


def hazards_header() -> list[str]:
    """The header of the real input table, read exactly the way the chain reads it."""
    from fusa.tools.metrics import uncommented
    with open(ROOT / "input" / "hazards.csv", newline="", encoding="utf-8") as f:
        return [h.strip() for h in csv.DictReader(uncommented(f)).fieldnames]


def js_array(name: str) -> list[str]:
    text = HARA_JS.read_text(encoding="utf-8")
    m = re.search(rf"export const {name} = \[(.*?)\];", text, re.S)
    assert m, f"hara.js no longer declares {name} — update this test with it"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_the_builders_row_has_exactly_the_columns_of_the_real_hazard_table():
    """The promise of the tool is that an exercise pastes into input/hazards.csv. If the two
    lists ever drift, that should fail here rather than in front of a learner."""
    assert js_array("COLUMNS") == hazards_header()


def test_the_builder_asks_the_server_for_the_asil_rather_than_deriving_one():
    text = HARA_JS.read_text(encoding="utf-8")
    assert "/api/learn/asil" in text, "the builder must ask the server for the rating"
    for formula in ("S+E+C", "s + e + c", "sum 7", "= 7", "severity + exposure"):
        assert formula not in text, f"hara.js appears to derive an ASIL: {formula!r}"


def test_the_guideword_list_the_tool_offers_is_the_one_content_is_checked_against():
    """Two copies of one list rot apart; content validated against a list the tool does not
    offer would reject a scenario the learner could have completed."""
    from fusa.learn.rules import GUIDEWORDS
    assert js_array("GUIDEWORDS") == list(GUIDEWORDS)


def test_the_shell_serves_the_builder(client):
    assert client.get("/static/learn/tools/hara.js").status_code == 200


def test_the_builders_cases_are_content_rather_than_code(client):
    """Three scenarios per the spec, and not one of them written into the JS."""
    scenarios = client.get("/api/learn/scenarios/hara").json()["scenarios"]
    assert len(scenarios) == 3
    assert {s["reveal"] for s in scenarios} == {"always", "submit", "never"}
    text = HARA_JS.read_text(encoding="utf-8")
    for s in scenarios:
        assert s["item"] not in text, f"scenario {s['id']} is hardcoded in the tool"


def test_the_scenario_with_no_answer_key_ships_no_answers(client):
    """'No answer key' has to mean the key is absent, not hidden behind a flag in the browser."""
    scenarios = client.get("/api/learn/scenarios/hara").json()["scenarios"]
    unassisted = next(s for s in scenarios if s["reveal"] == "never")
    for step in unassisted["steps"].values():
        assert "answer" not in step and "why" not in step


def test_the_shipped_scenarios_break_no_rule(client):
    assert client.get("/api/learn/scenarios/hara").json()["errors"] == []


def test_a_tool_with_no_scenario_file_has_none_rather_than_an_error(client):
    r = client.get("/api/learn/scenarios/trace")
    assert r.status_code == 200 and r.json()["scenarios"] == []


@pytest.mark.parametrize("name", ["..", "hara.json", "har a"])
def test_a_tool_name_that_could_name_a_file_is_refused(client, name):
    """The name indexes a path under the content directory; only a plain id may."""
    assert client.get(f"/api/learn/scenarios/{name}").status_code == 404


# ---- the Traceability Lab ----

TRACE_JS = ROOT / "fusa" / "ui" / "static" / "learn" / "tools" / "trace.js"


@pytest.fixture
def traced(workspace):
    """A project whose chain has actually been run — the lab has nothing to teach without one."""
    from fusa.orchestrator import Orchestrator
    orch = Orchestrator(root=workspace, dry_run=True, author="deterministic", reviewer="rules")
    orch.run_all(log=lambda *a: None)
    return orch


@pytest.fixture
def traced_client(traced, workspace):
    from fusa.ui.server import create_app
    with TestClient(create_app(root=workspace, dry_run=True)) as c:
        yield c


def broken_link(case) -> str:
    q = case["questions"]["link"]
    return q["options"][q["answer"]]["text"]


LINK_RE = re.compile(r"(\S+) → (\S+)\s+\((\S+) → (\S+)\)")


def links(case) -> list[tuple[str, str, str, str]]:
    """(parent id, child id, parent work product, child work product) for every offered link."""
    return [LINK_RE.match(o["text"]).groups() for o in case["questions"]["link"]["options"]]


def test_a_case_carries_exactly_one_broken_link(traced):
    """Replay the branch: an item traces if and only if its parent does and this is not the one
    link that was cut. More than one break and neither the question nor the fix has one answer."""
    from fusa.learn.tools import trace_case
    for seed in range(12):
        case = trace_case(traced, seed)
        cut = case["questions"]["link"]["answer"]
        shown = {r["id"] for r in case["rows"] if r["id"]}
        assert shown >= {case["goal"]["id"]}
        reached = {case["goal"]["id"]}
        for i, (parent, child, _, _) in enumerate(links(case)):
            if i != cut and parent in reached:
                reached.add(child)
        assert shown == reached, f"seed {seed}: {shown} traced, but one cut link explains {reached}"
        assert len(shown) < len(links(case)) + 1, f"seed {seed}: nothing was actually broken"


def test_the_same_seed_gives_the_same_case(traced):
    """An instructor sets a seed and a room full of learners gets one case."""
    from fusa.learn.tools import trace_case
    assert trace_case(traced, 41) == trace_case(traced, 41)


def test_different_seeds_give_different_cases(traced):
    from fusa.learn.tools import trace_case
    seen = {(trace_case(traced, s)["goal"]["id"], broken_link(trace_case(traced, s)))
            for s in range(20)}
    assert len(seen) > 1


def test_the_phase_that_owns_the_fix_is_a_real_phase_of_the_project(traced):
    """A made-up phase would send the learner to a part of the lifecycle this project has not."""
    from fusa.learn.tools import trace_case
    real = {s.phase for s in traced.specs}
    for seed in range(12):
        q = trace_case(traced, seed)["questions"]["phase"]
        for option in q["options"]:
            assert int(option["text"].split()[1]) in real


def test_the_phase_named_is_the_phase_of_the_agent_that_writes_the_missing_link(traced):
    """The fix lands where the work product is authored, not where the gap was noticed."""
    from fusa.learn.tools import trace_case
    for seed in range(12):
        case = trace_case(traced, seed)
        wp = links(case)[case["questions"]["link"]["answer"]][3]
        owner = next(s for s in traced.specs if s.work_product == wp)
        q = case["questions"]["phase"]
        assert q["options"][q["answer"]]["text"].startswith(f"Phase {owner.phase} ")


def test_every_work_product_a_case_cites_is_one_an_agent_produces(traced):
    """The lab may only describe the file the learner can go and open."""
    from fusa.learn.tools import trace_case
    declared = {s.work_product for s in traced.specs}
    for seed in range(12):
        case = trace_case(traced, seed)
        assert case["goal"]["work_product"] in declared
        for row in case["rows"]:
            assert row["work_product"] in declared
            assert row["agent"] in {s.id for s in traced.specs}


def test_every_id_a_case_shows_comes_from_the_generated_work_products(traced):
    """The point of reading `_generated/` rather than inventing a case: the ids are real."""
    from fusa.learn.tools import trace_case
    real = set(traced.reg.generated.all_ids())
    for seed in range(12):
        case = trace_case(traced, seed)
        assert case["goal"]["id"] in real
        for row in case["rows"]:
            assert row["id"] is None or row["id"] in real


def test_every_part_of_the_rubric_ships_a_reason_for_every_option(traced):
    """A wrong answer with no reason teaches nothing — the same rule the quiz content obeys."""
    from fusa.learn.tools import trace_case, TRACE_PARTS
    case = trace_case(traced, 5)
    assert list(case["questions"]) == list(TRACE_PARTS)
    for q in case["questions"].values():
        assert q["prompt"].strip() and q["title"].strip()
        assert len(q["options"]) > 1
        for option in q["options"]:
            assert option["text"].strip() and option["why"].strip()


def test_the_answer_to_the_evidence_question_is_not_always_the_first_option(traced):
    """An answer that never moves is a lesson about lists rather than about evidence."""
    from fusa.learn.tools import trace_case
    assert len({trace_case(traced, s)["questions"]["evidence"]["answer"]
                for s in range(20)}) > 1


def test_with_nothing_generated_the_lab_says_to_run_the_chain(client):
    """No chain, no trace. Inventing a case would teach a file the learner cannot open."""
    r = client.get("/api/learn/trace", params={"seed": 1}).json()
    assert r["ready"] is False
    assert r["reason"] == "SADS has not been produced yet"
    assert r["missing"] == ["SADS", "TSR", "TSC", "HSR", "HW-DESIGN", "TEST-SPEC"]


def test_a_safety_goal_with_nothing_under_it_is_passed_over_not_crashed_on(traced, workspace):
    """A goal nobody has written a requirement for yet is the commonest state of a live project,
    and it is a branch with no links in it — there is nothing there to break."""
    from fusa.learn.tools import trace_case
    from fusa.orchestrator import Orchestrator
    sads = traced.reg.generated.read("SADS")
    traced.reg.generated.write("SADS", sads + "\n### SG-099\n- parent: HZ-001\n- asil: B\n"
                                              "- text: Nothing has been written under this one.\n")
    orch = Orchestrator(root=workspace, dry_run=True)
    for seed in range(20):
        assert trace_case(orch, seed)["goal"]["id"] != "SG-099"


def test_a_chain_run_only_partway_still_yields_a_case_from_what_exists(traced, workspace):
    """The lab is for a project mid-run as much as a finished one, and a level that was never
    produced is simply a level nothing hangs off."""
    import shutil
    from fusa.learn.tools import trace_case
    from fusa.orchestrator import Orchestrator
    shutil.rmtree(workspace / "_generated" / "TSC")
    orch = Orchestrator(root=workspace, dry_run=True)
    for seed in range(8):
        levels = [r["work_product"] for r in trace_case(orch, seed)["rows"]]
        assert "TSC" not in levels and levels[:2] == ["SADS", "TSR"]


def test_the_goal_a_case_opens_with_is_the_one_the_project_wrote(traced):
    """The ASIL and the wording are the safety goal's own — a neighbouring goal's would put the
    wrong rating in front of the learner with nothing to reveal it."""
    from fusa.learn.tools import trace_case
    for seed in range(8):
        goal = trace_case(traced, seed)["goal"]
        item = next(i for i in traced.reg.generated.items("SADS") if i.id == goal["id"])
        assert goal["asil"] == item.fields["asil"] and goal["text"] == item.fields["text"]


def test_the_reason_offered_for_each_link_says_where_that_link_stands(traced):
    """The reasons are the teaching. Attached to the wrong options they would tell a learner who
    found the break that they had found a consequence of it."""
    from fusa.learn.tools import trace_case
    for seed in range(8):
        case = trace_case(traced, seed)
        q = case["questions"]["link"]
        firsts = [i for i, o in enumerate(q["options"]) if "first item in the branch" in o["why"]]
        assert firsts == [q["answer"]]
        traced_ids = {r["id"] for r in case["rows"] if r["id"]}
        for i, (option, (_, child, _, _)) in enumerate(zip(q["options"], links(case))):
            if i == q["answer"]:
                continue
            still = "still traces" in option["why"]
            assert still is (child in traced_ids), f"seed {seed} option {i} explains the wrong side"


def test_a_phase_the_learner_might_pick_is_explained_by_what_it_really_authors(traced):
    """A distractor that misdescribes a phase teaches the lifecycle wrong on the way to teaching
    traceability."""
    from fusa.learn.tools import trace_case
    case = trace_case(traced, 5)
    q = case["questions"]["phase"]
    for i, option in enumerate(q["options"]):
        phase = int(option["text"].split()[1])
        if i == q["answer"]:
            assert "is produced by" in option["why"] and f"in phase {phase}" in option["why"]
            continue
        authored = [s.work_product for s in traced.specs
                    if s.phase == phase and s.kind in ("authoring", "runner")]
        listed = option["why"].split("owns ", 1)[1].split(". None", 1)[0]
        assert listed == ", ".join(authored[:3]) + ("…" if len(authored) > 3 else "")


def test_the_lab_reads_the_chain_off_the_traceability_agent_and_not_off_some_other(traced):
    """Both the lab and the agent take the chain from one place, so a project that shortens it
    shortens the lesson too."""
    from fusa.learn.tools import trace_case
    spec = next(s for s in traced.specs if (s.generator or {}).get("kind") == "traceability")
    spec.generator["chain"] = ["SADS", "TSR"]
    levels = {r["work_product"] for r in trace_case(traced, 4)["rows"]}
    assert levels == {"SADS", "TSR"}


def test_the_endpoint_serves_a_case_once_the_chain_has_run(traced_client):
    r = traced_client.get("/api/learn/trace", params={"seed": 9})
    assert r.status_code == 200 and r.json()["ready"] is True
    assert r.json()["seed"] == 9


def test_the_endpoint_hands_back_a_different_case_for_a_different_seed(traced_client):
    get = lambda s: traced_client.get("/api/learn/trace", params={"seed": s}).json()
    assert get(9) == get(9)
    assert len({(get(s)["goal"]["id"], broken_link(get(s))) for s in range(8)}) > 1


def test_the_lab_walks_the_chain_the_traceability_agent_declares(traced):
    """Two spellings of the chain would let the lab teach a V the project does not build."""
    from fusa.learn.tools import trace_case
    spec = next(s for s in traced.specs if (s.generator or {}).get("kind") == "traceability")
    from fusa.generators.kinds import TRACE_CHAIN
    chain = spec.generator.get("chain") or TRACE_CHAIN
    for seed in range(6):
        levels = [r["work_product"] for r in trace_case(traced, seed)["rows"]]
        assert levels == [wp for wp in chain if wp in levels]


def test_the_break_is_a_link_the_project_really_has(traced):
    """`parent:` is the only thing the matrix is built from, so a case must break one of those."""
    from fusa.learn.tools import trace_case
    for seed in range(12):
        case = trace_case(traced, seed)
        parent, child, _, _ = links(case)[case["questions"]["link"]["answer"]]
        wp = traced.reg.generated.all_ids()[child]
        item = next(i for i in traced.reg.generated.items(wp) if i.id == child)
        assert parent in item.refs("parent"), f"{child} never named {parent} in the first place"


def test_the_phase_names_the_lab_offers_are_the_ones_the_board_prints():
    """Two copies of one list rot apart, and a learner sent to 'phase 3' should find the same
    column on the workbench they were just looking at."""
    from fusa.learn.tools import PHASE_NAMES
    board = (ROOT / "fusa" / "ui" / "static" / "index.html").read_text(encoding="utf-8")
    m = re.search(r"const PHASES = \{(.*?)\};", board, re.S)
    assert m, "the board no longer declares PHASES — update this test with it"
    printed = {int(n): t.split("·", 1)[1].strip() for n, t in re.findall(r'(\d+):\s*"([^"]+)"', m.group(1))}
    assert printed == PHASE_NAMES


def test_the_lab_asks_the_server_for_its_case_rather_than_shipping_one(traced_client):
    js = traced_client.get("/static/learn/tools/trace.js")
    assert js.status_code == 200 and "/api/learn/trace" in js.text
    for hardcoded in ("SG-001", "TSR-001", "HSR-001"):
        assert hardcoded not in js.text, f"trace.js hardcodes {hardcoded}"


def test_the_three_parts_the_browser_scores_are_the_three_the_server_builds():
    from fusa.learn.tools import TRACE_PARTS
    m = re.search(r"export const PARTS = \[(.*?)\];", TRACE_JS.read_text(encoding="utf-8"), re.S)
    assert m, "trace.js no longer declares PARTS — update this test with it"
    assert re.findall(r'"([^"]+)"', m.group(1)) == list(TRACE_PARTS)


# ---- the oracle that cannot be fooled by how a formula is spelled --------------------------

# The S+E+C mnemonic reproduces the determination table exactly, so any test using real values
# cannot tell a lookup from a derivation. These use a table that DISAGREES with the mnemonic:
# whatever an implementation derives, it will not be this. A source grep can be evaded by
# renaming; this cannot.
WRONG_TABLE = {"S3-E4-C3": "A",    # the mnemonic yields D
               "S1-E1-C1": "D",    # the mnemonic yields QM
               "S2-E2-C2": "D"}    # the mnemonic yields QM


def test_the_endpoint_reports_the_table_even_where_the_table_is_surprising(client):
    """The table is the authority. An implementation that derived the answer would disagree
    with these cells, which is the only way to catch one that has been renamed."""
    fill(client, **WRONG_TABLE)
    for key, expected in WRONG_TABLE.items():
        s, e, c = key.split("-")
        got = client.get("/api/learn/asil", params={"s": s, "e": e, "c": c}).json()["asil"]
        assert got == expected, f"{key}: table says {expected}, endpoint said {got} — derived?"


# ---- the gap report: the release report, read by phase --------------------------------------

def test_the_gap_report_agrees_with_the_release_report(client, workspace):
    """No new engine. If these ever disagree, one of them is lying to an assessor."""
    from fusa.orchestrator import Orchestrator
    from fusa.report import validate
    from fusa.learn.tools import gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    rep = validate(orch)
    gaps = gap_report(orch)
    assert gaps["verdict"] == rep.verdict
    flat = {r["work_product"]: r for p in gaps["phases"] for r in p["rows"]}
    assert set(flat) == {a.work_product for a in rep.work_products}
    for a in rep.work_products:
        assert (flat[a.work_product]["state"] == "ok") == a.ok


def test_a_blocked_work_product_is_missing_not_merely_warned(client, workspace):
    from fusa.models import GateResult, Status
    from fusa.orchestrator import Orchestrator
    from fusa.learn.tools import gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    orch.reg.process.update("HARA", "sys-hara", status=Status.GATE_FAILED,
                            gate=GateResult(work_product="HARA", passed=False,
                                            errors=["HZ-001 has no parent"]))
    flat = {r["work_product"]: r for p in gap_report(orch)["phases"] for r in p["rows"]}
    assert flat["HARA"]["state"] == "missing"
    assert any("parent" in w for w in flat["HARA"]["why"])


def test_a_pending_marker_warns_rather_than_reading_as_missing(client, workspace):
    """The line between 'not written' and 'written, with a hole in it' is the whole point of
    three states rather than two."""
    from fusa.models import GateResult, Status
    from fusa.orchestrator import Orchestrator
    from fusa.learn.tools import gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    orch.reg.process.update("HARA", "sys-hara", status=Status.GATE_PASSED, pending_count=1,
                            gate=GateResult(work_product="HARA", passed=True,
                                            pending=["[PENDING] exposure for HZ-001"]))
    flat = {r["work_product"]: r for p in gap_report(orch)["phases"] for r in p["rows"]}
    assert flat["HARA"]["state"] == "warn"
    assert any("PENDING" in w for w in flat["HARA"]["why"])


def test_an_open_blocker_finding_is_missing_even_though_the_gate_passed(client, workspace):
    from fusa.models import Finding, GateResult, ReviewVerdict, Status
    from fusa.orchestrator import Orchestrator
    from fusa.learn.tools import gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    orch.reg.process.update("HARA", "sys-hara", status=Status.REWORK,
                            gate=GateResult(work_product="HARA", passed=True),
                            review=ReviewVerdict(work_product="HARA", verdict="rework",
                                                 findings=[Finding(id="F-1", severity="blocker",
                                                                   description="no controllability rationale")]))
    flat = {r["work_product"]: r for p in gap_report(orch)["phases"] for r in p["rows"]}
    assert flat["HARA"]["state"] == "missing"


def test_a_minor_finding_only_warns(client, workspace):
    from fusa.models import Finding, GateResult, ReviewVerdict, Status
    from fusa.orchestrator import Orchestrator
    from fusa.learn.tools import gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    orch.reg.process.update("HARA", "sys-hara", status=Status.REWORK,
                            gate=GateResult(work_product="HARA", passed=True),
                            review=ReviewVerdict(work_product="HARA", verdict="rework",
                                                 findings=[Finding(id="F-2", severity="minor",
                                                                   description="wording")]))
    flat = {r["work_product"]: r for p in gap_report(orch)["phases"] for r in p["rows"]}
    assert flat["HARA"]["state"] == "warn"


def test_a_work_product_nothing_has_written_yet_is_missing(client, workspace):
    """A fresh project is all holes, and the report says so before anything has run."""
    from fusa.orchestrator import Orchestrator
    from fusa.learn.tools import gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    gaps = gap_report(orch)
    rows = [r for p in gaps["phases"] for r in p["rows"]]
    assert rows and all(r["state"] == "missing" for r in rows)
    assert gaps["totals"] == {"ok": 0, "warn": 0, "missing": len(rows)}


def test_a_row_names_the_checklist_its_gate_will_be_read_against(client, workspace):
    from fusa.orchestrator import Orchestrator
    from fusa.learn.tools import gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    flat = {r["work_product"]: r for p in gap_report(orch)["phases"] for r in p["rows"]}
    assert flat["HARA"]["checklist_ref"] == "HARA"
    assert flat["HSR"]["checklist_ref"] == "generic"      # its agent declares the shared one


def test_every_row_carries_the_phase_its_agent_belongs_to(client, workspace):
    from fusa.orchestrator import Orchestrator
    from fusa.learn.tools import gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    by_wp = {s.work_product: s.phase for s in orch.specs}
    for p in gap_report(orch)["phases"]:
        for r in p["rows"]:
            assert by_wp[r["work_product"]] == p["phase"]


def test_a_phase_is_titled_the_way_the_board_titles_it(client, workspace):
    from fusa.orchestrator import Orchestrator
    from fusa.learn.tools import PHASE_NAMES, gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    for p in gap_report(orch)["phases"]:
        assert p["title"] == PHASE_NAMES[p["phase"]]


def test_a_row_links_to_the_module_that_taught_its_checklist(client, workspace):
    """The loop that makes the course and the gap report one list rather than two."""
    from fusa.orchestrator import Orchestrator
    from fusa.learn.tools import gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    flat = {r["work_product"]: r for p in gap_report(orch)["phases"] for r in p["rows"]}
    assert flat["HARA"]["module_id"] == "concept.hara"       # the sample module teaches HARA


def test_a_work_product_with_no_lesson_yet_is_not_an_error(client, workspace):
    from fusa.orchestrator import Orchestrator
    from fusa.learn.tools import gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    flat = {r["work_product"]: r for p in gap_report(orch)["phases"] for r in p["rows"]}
    assert flat["TSC"]["module_id"] is None


def test_the_totals_count_the_states_the_rows_actually_carry(client, workspace):
    from fusa.orchestrator import Orchestrator
    from fusa.learn.tools import gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    gaps = gap_report(orch)
    rows = [r for p in gaps["phases"] for r in p["rows"]]
    for state in ("ok", "warn", "missing"):
        assert gaps["totals"][state] == sum(1 for r in rows if r["state"] == state)


def test_the_endpoint_serves_the_gap_report_for_the_asil_it_is_asked_about(client):
    r = client.get("/api/learn/gaps", params={"asil": "D"})
    assert r.status_code == 200
    body = r.json()
    assert body["asil"] == "D"
    assert [p["phase"] for p in body["phases"]] == sorted(p["phase"] for p in body["phases"])
