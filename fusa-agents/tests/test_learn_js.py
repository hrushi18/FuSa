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
