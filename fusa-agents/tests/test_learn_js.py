"""The browser half of the platform, actually executed rather than grepped.

The rest of the JS coverage is structural — it asserts that `module.js` no longer contains the
endpoint string, that `app.js` contains a `.catch`. That shape is worth pinning, but a string
appearing in a file is not evidence the code behind it runs, and this suite already shipped one
Critical bug behind a test that passed while covering nothing.

There is no JS test runner here and none can be added: the platform ships as ES modules with no
build step, so a runner would mean npm. Node is already a dev tool (it type-checks these files),
so the modules are run under it directly with a stub DOM and a scripted fetch. If node is not
installed the tests skip rather than fail — they are an addition to CI, not a new requirement.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LEARN = ROOT / "fusa" / "ui" / "static" / "learn"
HARNESS = Path(__file__).parent / "js" / "progress-paths.mjs"

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node is not installed; the JS paths go unexercised")


def run_harness(learn_dir: Path = LEARN) -> dict:
    r = subprocess.run(["node", str(HARNESS), str(learn_dir)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"harness failed:\n{r.stderr}"
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def paths() -> dict:
    return run_harness()


def test_a_saved_score_comes_back_as_the_stored_record(paths):
    assert paths["saved"] == {"best": 0.9, "status": "passed"}


def test_a_failed_save_is_reported_in_the_banner_not_dropped(paths):
    """A learner who answered a quiz and lost the score deserves to know it was lost."""
    assert paths["failed_returns"] is None
    assert "progress not saved" in paths["failed_banner"]
    assert "disk full" in paths["failed_banner"], "the server's reason must survive to the banner"


def test_an_html_error_page_still_reaches_the_learner_as_words(paths):
    """A 500 from the server arrives as an HTML page, not JSON; parsing it as JSON and giving
    up would put a blank banner in front of the one person who needs the message."""
    assert "Internal Server Error" in paths["html_error_banner"]


def test_the_harness_fails_when_the_catch_is_removed(tmp_path):
    """The guard on this whole file: a harness that cannot fail proves nothing. Copy the real
    modules, delete the error path, and confirm the harness notices."""
    broken = tmp_path / "learn"
    shutil.copytree(LEARN, broken)
    src = (broken / "progress.js").read_text(encoding="utf-8")
    without_catch = src.replace(
        """  }).catch(err => {
    banner(`progress not saved — ${err.message}`);
    return null;
  });""", "  });")
    assert without_catch != src, "progress.js changed shape — update this test with it"
    (broken / "progress.js").write_text(without_catch, encoding="utf-8")
    with pytest.raises(AssertionError):
        run_harness(broken)


# ---- a lesson card launching straight into a tool ----

MODULE = Path(__file__).parent / "js" / "module-paths.mjs"


def run_module(learn_dir: Path = LEARN) -> dict:
    r = subprocess.run(["node", str(MODULE), str(learn_dir)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"harness failed:\n{r.stderr}"
    return json.loads(r.stdout)


def test_a_tool_card_renders_a_launch_button_linking_to_the_tool():
    html = run_module()["html"]
    assert 'href="#/tool/hara"' in html
    assert "Open the HARA Builder and finish the row." in html


def test_the_harness_notices_a_tool_card_that_stops_linking_to_the_tool(tmp_path):
    """The guard on the test above: a harness that cannot fail proves nothing."""
    broken = tmp_path / "learn"
    shutil.copytree(LEARN, broken)
    src = (broken / "module.js").read_text(encoding="utf-8")
    unlinked = src.replace('href="#/tool/${esc(card.tool)}"', 'href="#"')
    assert unlinked != src, "module.js changed shape — update this test with it"
    (broken / "module.js").write_text(unlinked, encoding="utf-8")
    assert 'href="#/tool/hara"' not in run_module(broken)["html"]


# ---- the HARA builder's session, driven step by step ----

TOOLS = Path(__file__).parent / "js" / "tools-paths.mjs"
SCENARIOS = ROOT / "fusa" / "ui" / "content-sample" / "scenarios" / "hara.json"


def run_tools(learn_dir: Path = LEARN) -> dict:
    r = subprocess.run(["node", str(TOOLS), str(learn_dir), str(SCENARIOS)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"harness failed:\n{r.stderr}"
    return json.loads(r.stdout)


def hazards_header() -> list[str]:
    """The header of the real input table, read exactly the way the chain reads it."""
    from fusa.tools.metrics import uncommented
    with open(ROOT / "input" / "hazards.csv", newline="", encoding="utf-8") as f:
        return [h.strip() for h in csv.DictReader(uncommented(f)).fieldnames]


@pytest.fixture(scope="module")
def walk() -> dict:
    return run_tools()


def test_the_walk_runs_from_the_item_to_the_finished_row(walk):
    assert walk["steps"] == ["item", "function", "guideword", "malfunction", "situation",
                             "hazardous_event", "rating", "rationale", "asil", "safety_goal",
                             "row"]


def test_a_step_will_not_let_the_learner_past_until_it_is_answered(walk):
    """Skipping a step would produce a row with a hole in it and no sign of where."""
    assert walk["refused_until_answered"] == ["function", "guideword", "malfunction",
                                             "situation", "hazardous_event", "rating",
                                             "rationale", "safety_goal"]


def test_the_finished_row_serialises_in_the_column_order_of_the_real_hazard_table(walk):
    """The exercise is meant to paste into input/hazards.csv, so the order is not decorative."""
    header = hazards_header()
    assert walk["row_keys"] == header
    cells = next(csv.reader([walk["csv"]]))
    assert cells == [walk["row"][c] for c in header]


def test_a_rationale_carrying_a_comma_survives_the_serialisation(walk):
    """The rationale column routinely contains commas and the odd quoted word; unescaped, one
    exercise would arrive in the chain as three columns too many."""
    assert ", " in walk["row"]["rationale"] and '"' in walk["row"]["rationale"]
    assert next(csv.reader([walk["csv"]]))[8] == walk["row"]["rationale"]


def test_the_asil_in_the_row_is_the_one_the_server_gave(walk):
    """The scripted server answered D for S1/E1/C1 — a combination no determination rule maps
    to D. A browser doing its own arithmetic could not produce this row."""
    assert walk["row"]["severity"] == "S1" and walk["row"]["asil"] == "D"


def test_an_untranscribed_rating_leaves_the_asil_cell_empty(walk):
    """Blank is what the chain reads as 'derive it', which then marks the row PENDING. A guess
    here would travel the whole chain with nothing downstream able to notice."""
    assert walk["untranscribed_asil_cell"] == ""


def test_a_case_with_no_answer_key_offers_the_browser_no_answers(walk):
    assert walk["unassisted_model_answers"] == []
    assert walk["worked_model_answer"] == "reverse", "the worked case does have a key"


def test_the_harness_notices_a_row_that_invents_an_asil(tmp_path):
    """The guard on the claim above: a check that cannot fail proves nothing."""
    broken = tmp_path / "learn"
    shutil.copytree(LEARN, broken)
    src = (broken / "tools" / "hara.js").read_text(encoding="utf-8")
    invented = src.replace("        asil: asil?.asil,", '        asil: "D",')
    assert invented != src, "hara.js changed shape — update this test with it"
    (broken / "tools" / "hara.js").write_text(invented, encoding="utf-8")
    assert run_tools(broken)["untranscribed_asil_cell"] == "D"


# ---- the Traceability Lab's rubric, scored under node ----

TRACE = Path(__file__).parent / "js" / "trace-paths.mjs"


def run_trace(case: dict, tmp_path: Path, learn_dir: Path = LEARN) -> dict:
    payload = tmp_path / "case.json"
    payload.write_text(json.dumps(case), encoding="utf-8")
    r = subprocess.run(["node", str(TRACE), str(learn_dir), str(payload)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"harness failed:\n{r.stderr}"
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def case(tmp_path_factory) -> dict:
    """A case the server really built, from a project whose chain has been run."""
    import shutil as sh
    root = tmp_path_factory.mktemp("traced")
    for d in ["_clause-register", "_reference-register", "_checklist-register", "config", "input"]:
        sh.copytree(ROOT / d, root / d)
    (root / "_generated").mkdir()
    from fusa.learn.tools import trace_case
    from fusa.orchestrator import Orchestrator
    orch = Orchestrator(root=root, dry_run=True, author="deterministic", reviewer="rules")
    orch.run_all(log=lambda *a: None)
    return trace_case(orch, 3)


@pytest.fixture(scope="module")
def scored(case, tmp_path_factory) -> dict:
    return run_trace(case, tmp_path_factory.mktemp("trace-js"))


def test_the_rubric_is_scored_in_three_independent_parts(scored):
    assert scored["parts"] == ["link", "phase", "evidence"]
    assert scored["all_right"]["right"] == 3 and scored["all_right"]["score"] == 1.0
    assert scored["all_wrong"]["right"] == 0 and scored["all_wrong"]["score"] == 0.0


def test_a_partly_correct_answer_is_reported_as_partly_correct(scored):
    """The reason the parts are scored apart: finding the break and knowing who owns the fix
    are two different things to have learned, and one number would hide which one is missing."""
    partly = scored["partly"]
    assert partly["right"] == 2 and partly["of"] == 3
    assert {p["key"]: p["right"] for p in partly["parts"]} == {
        "link": True, "phase": False, "evidence": True}
    assert "the broken link" in partly["verdict"] and "the evidence that closes it" in partly["verdict"]
    assert "wrong about the phase that owns the fix" in partly["verdict"]


def test_the_part_the_learner_got_wrong_carries_both_reasons(scored):
    """Why the pick was wrong, and what was right — a wrong answer with no reason teaches
    nothing, and the reason for the right answer is the whole lesson of the part."""
    phase = scored["partly_phase"]
    assert phase["right"] is False
    assert phase["why"].strip() and phase["keyWhy"].strip()
    assert phase["why"] != phase["keyWhy"] and phase["keyText"].startswith("Phase ")


def test_a_part_left_unanswered_is_wrong_rather_than_a_crash(scored):
    un = scored["unanswered"]
    assert un["right"] == 1
    assert [p["answered"] for p in un["parts"]] == [True, False, False]
    assert "unanswered" in next(p["why"] for p in un["parts"] if p["key"] == "phase")


def test_the_lab_draws_the_branch_it_was_given(scored, case):
    html = scored["ready_html"]
    assert case["goal"]["id"] in html and case["goal"]["text"] in html
    for row in case["rows"]:
        assert row["work_product"] in html and row["agent"] in html
    assert "—" in html, "a broken link shows as an empty cell, which is the whole exercise"
    assert f'id="seed" class="seedbox" type="number" value="{case["seed"]}"' in html, \
        "the seed is on the page, because an instructor sets one for a whole class"


def test_with_nothing_generated_the_lab_says_to_run_the_chain_and_links_to_the_board(scored):
    html = scored["empty_html"]
    assert "Run the chain first" in html
    assert 'href="/"' in html, "the learner needs somewhere to go, not just a refusal"
    assert "SADS has not been produced yet" in html and "SADS, TSR" in html


def test_what_the_server_sends_is_escaped_before_it_reaches_the_page(scored):
    assert "&lt;script&gt;" in scored["hostile_html"]
    assert "<script>" not in scored["hostile_html"]


def test_the_harness_notices_a_scorer_that_collapses_the_three_parts(case, tmp_path):
    """The guard on all of the above: a harness that cannot fail proves nothing."""
    broken = tmp_path / "learn"
    shutil.copytree(LEARN, broken)
    src = (broken / "tools" / "trace.js").read_text(encoding="utf-8")
    collapsed = src.replace("      right: answered && chose === q.answer,",
                            "      right: answered,")
    assert collapsed != src, "trace.js changed shape — update this test with it"
    (broken / "tools" / "trace.js").write_text(collapsed, encoding="utf-8")
    assert run_trace(case, tmp_path, broken)["partly"]["right"] == 3


# ---- the ASIL calculator, executed --------------------------------------------------------

ASIL_HARNESS = Path(__file__).parent / "js" / "asil-paths.mjs"


def run_asil(learn_dir: Path = LEARN) -> dict:
    r = subprocess.run(["node", str(ASIL_HARNESS), str(learn_dir)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"harness failed:\n{r.stderr}"
    return json.loads(r.stdout)


def badge_of(html: str) -> str | None:
    m = re.search(r"asil-badge[^>]*>\s*([A-D]|QM)\s*<", html)
    return m.group(1) if m else None


@pytest.fixture(scope="module")
def asil_paths() -> dict:
    return run_asil()


def test_the_calculator_shows_the_table_even_where_the_table_is_surprising(asil_paths):
    """The oracle. S+E+C reproduces the determination table exactly, so a calculator that
    derives its answer is indistinguishable from one that reads it — for every real value.
    These two cells disagree with the mnemonic, so a derivation cannot survive them however it
    is spelled or renamed. A source grep can be evaded; arithmetic cannot lie about its output."""
    assert badge_of(asil_paths["surprising"]) == "A"        # the mnemonic would say D
    assert badge_of(asil_paths["surprising_low"]) == "D"    # the mnemonic would say QM


def test_an_untranscribed_cell_never_becomes_a_letter_on_the_page(asil_paths):
    """The failure this guards is silent: a plausible ASIL for a cell nobody transcribed is
    wrong all the way down the chain with nothing downstream able to notice."""
    assert badge_of(asil_paths["unfilled"]) is None
    assert "not transcribed" in asil_paths["unfilled"]


def test_the_asil_harness_fails_when_the_calculator_derives_an_answer(tmp_path):
    """The guard on the two tests above. A harness that cannot catch a derivation would leave
    R2 enforced by nothing — which is exactly the state a review already found this repo in."""
    broken = tmp_path / "learn"
    shutil.copytree(LEARN, broken)
    src = (broken / "tools" / "asil.js").read_text(encoding="utf-8")
    ladder = ("\nconst L = {7:'A',8:'B',9:'C',10:'D'};\n"
              "function rate(p){const n=Number(p.s[1])+Number(p.e[1])+Number(p.c[1]);\n"
              "  if(p.s[1]==='0'||p.e[1]==='0'||p.c[1]==='0')return 'QM';\n"
              "  return n<=6?'QM':L[n];}\n")
    src = src.replace("export function renderAsil(host) {", ladder + "export function renderAsil(host) {")
    src = src.replace("  const verdictHtml = r => {",
                      "  const verdictHtml = r => {\n    r = {...r, asil: r.asil ?? rate(pick)};")
    (broken / "tools" / "asil.js").write_text(src, encoding="utf-8")
    got = run_asil(broken)
    assert badge_of(got["unfilled"]) is not None, "a derived answer went unnoticed"


def test_a_lesson_card_does_not_borrow_a_grid_class_from_another_component():
    """`.tool` is the calculator's three-column layout. A lesson card wearing that class renders
    in three columns with its launch button orphaned — confirmed on screen before this test."""
    css = (LEARN / "index.html").read_text(encoding="utf-8")
    assert "grid-template-columns" in css, "wrong stylesheet — this test would pass vacuously"
    module_js = (LEARN / "module.js").read_text(encoding="utf-8")
    grid_classes = re.findall(r"\.([a-z-]+)\s*\{[^}]*grid-template-columns", css)
    for cls in grid_classes:
        assert f'class="card {cls}"' not in module_js, \
            f"a lesson card uses .{cls}, which is a grid layout defined for another component"


def test_an_untranscribed_cell_offers_a_way_to_transcribe_it(asil_paths):
    """Spec §7. Telling an engineer a cell is missing and giving them nowhere to put it is the
    difference between a lesson and a tool — and the workbench's only other route is a bare grid."""
    assert asil_paths.get("offers_fill") is True


def test_filling_a_cell_writes_the_selected_key_and_then_re_reads_the_table(asil_paths):
    """The value must land on the cell the learner is looking at, and the answer shown after
    must come from the table rather than from what they just typed."""
    posted = asil_paths.get("posted") or []
    assert posted, "nothing was posted"
    assert posted[0]["url"] == "/api/asil-table"
    assert posted[0]["body"]["values"] == {"S3-E4-C3": "C"}
    # the harness types C and has the re-read answer B: only a genuine re-read shows B
    assert badge_of(asil_paths["after_fill"]) == "B", "the input was echoed, not re-read"


# ---- the gap report's view, rendered under node -------------------------------------------

VALIDATE = Path(__file__).parent / "js" / "validate-paths.mjs"


def run_validate(learn_dir: Path = LEARN) -> dict:
    r = subprocess.run(["node", str(VALIDATE), str(learn_dir)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"harness failed:\n{r.stderr}"
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def gaps_view() -> dict:
    return run_validate()


def test_the_phases_come_out_in_lifecycle_order_under_their_own_names(gaps_view):
    """A gap report the learner reads down the V. Map order would put them in whatever order
    the assessments happened to arrive, which is not an order anyone reviews a project in."""
    assert gaps_view["sections"] == ["Phase 1 · Concept &amp; Requirements",
                                     "Phase 2 · System Analysis"]   # read out of the markup


def test_each_state_gets_its_own_mark_and_never_borrows_another(gaps_view):
    assert {r["wp"]: r["icon"] for r in gaps_view["rows"]} == {
        "HARA": "✅", "HSR": "⚠️", "SADS": "❌"}


def test_a_row_links_to_its_lesson_and_a_row_without_one_shows_no_link(gaps_view):
    """The loop that makes the course and the gap report one list. A row with no lesson yet is
    normal — inventing a link for it would send the learner to a page that does not exist."""
    assert {r["wp"]: r["link"] for r in gaps_view["rows"]} == {
        "HARA": "concept.hara", "HSR": None, "SADS": "system.sads"}
    assert {r["wp"]: r["offered"] for r in gaps_view["rows"]} == {
        "HARA": True, "HSR": False, "SADS": True}


def test_the_view_states_the_same_basis_the_pdf_states(gaps_view):
    """Whether a model wrote any of this is the first question an assessor asks, and two
    different answers on two surfaces is worse than neither."""
    assert "No language model produced or judged any part of this report" in gaps_view["html"]


def test_with_nothing_generated_the_report_says_so_and_links_to_the_board(gaps_view):
    """Every row missing is a project nobody has run, not a finding about their safety file."""
    html = gaps_view["first_run_html"]
    assert "Nothing has been generated yet" in html
    assert 'href="/"' in html, "the learner needs somewhere to go, not just a verdict"
    assert "NOT_RELEASABLE" not in html, "a verdict on an empty project reads as a judgement"


def test_what_the_gap_report_sends_is_escaped_before_it_reaches_the_page(gaps_view):
    assert "&lt;script&gt;" in gaps_view["hostile_html"]
    assert "<script>" not in gaps_view["hostile_html"]


def test_the_harness_notices_an_inverted_icon_mapping(tmp_path):
    """The guard on the mapping test: a harness that cannot fail proves nothing."""
    broken = tmp_path / "learn"
    shutil.copytree(LEARN, broken)
    src = (broken / "tools" / "validate.js").read_text(encoding="utf-8")
    swapped = src.replace('ok: "✅", warn: "⚠️", missing: "❌"',
                          'ok: "❌", warn: "⚠️", missing: "✅"')
    assert swapped != src, "validate.js changed shape — update this test with it"
    (broken / "tools" / "validate.js").write_text(swapped, encoding="utf-8")
    assert run_validate(broken)["rows"][0]["icon"] == "❌"


# ---- every tool, reached through the router rather than by name ---------------------------

ROUTES = Path(__file__).parent / "js" / "tool-routes.mjs"


def run_routes(learn_dir: Path = LEARN) -> dict:
    r = subprocess.run(["node", str(ROUTES), str(learn_dir)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"harness failed:\n{r.stderr}"
    return json.loads(r.stdout)


def test_every_tool_in_the_nav_draws_something_when_routed_to():
    """The gap the other harnesses leave: they import a view's render function by name, so the
    router never runs. A fourth tool the router's list of names did not mention rendered a blank
    pane with all of them green — confirmed on screen before this test existed."""
    drawn = run_routes()
    assert set(drawn) == {"asil", "hara", "trace", "validate"}, \
        "a tool was added to the nav without being routed here"
    for tool, got in drawn.items():
        assert got["chars"] > 200, f"{tool} routed to an empty pane"
        assert got["crumb"].startswith("Tools \u2192 ")


# ---- the loop back from the lesson to the project's own file ------------------------------

def test_a_lesson_names_how_this_project_fares_against_the_checklist_it_just_taught():
    """The other half of the loop: the gap report links to the lesson, and the lesson says what
    the project's own file looks like. Without this the course is a course and the report is a
    report, kept in step by whoever remembers to look at both."""
    html = run_module()["taught"]
    assert "⚠️" in html and "HARA" in html
    assert "1 unresolved [PENDING] marker(s)" in html
    assert 'href="#/tool/validate"' in html, "the state is only useful next to the whole report"


def test_a_lesson_with_no_work_product_says_nothing_about_the_project():
    """Absence of the block, not just absence of a mark: an empty "Right now in this project"
    with nothing after it is a claim that the project has nothing to say."""
    html = run_module()["untaught"]
    assert "wp-state" not in html
    assert "⚠️" not in html and "✅" not in html and "❌" not in html


def test_a_work_product_the_report_has_no_row_for_puts_no_mark_on_the_page():
    """Content can run ahead of the chain. A lesson for a work product no agent produces yet
    must not be given a state, because there is no assessment behind it."""
    html = run_module()["unknown"]
    assert "wp-state" not in html
    assert "⚠️" not in html and "✅" not in html and "❌" not in html


def test_with_nothing_generated_the_lesson_shows_no_state_rather_than_a_false_verdict():
    """Every row missing is a chain nobody has run. Marking each lesson ❌ would read as a
    finding about the learner's safety file when there is no file to have a finding about."""
    html = run_module()["fresh"]
    assert "❌" not in html and "✅" not in html
    assert "has not been run" in html, "silence with no explanation is its own confusion"


def test_the_reasons_the_report_gives_are_escaped_into_the_lesson():
    assert "&lt;script&gt;" in run_module()["hostile"]
    assert "<script>" not in run_module()["hostile"]
