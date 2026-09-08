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
