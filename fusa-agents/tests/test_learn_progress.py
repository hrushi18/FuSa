"""Progress is the only state this platform keeps, and it is a plain file a person may edit or
lose. Every read has to survive that: a missing or damaged file means "nothing started yet",
never a stack trace in the middle of a lesson."""
import json

from fusa.learn.progress import ProgressStore


def store(tmp_path, **kw):
    return ProgressStore(tmp_path / "learning-progress.json", **kw)


def test_nothing_started_before_anything_is_recorded(tmp_path):
    s = store(tmp_path)
    assert s.status("concept.hara") == "not_started"
    assert s.summary() == {}


def test_seeing_cards_puts_a_module_in_progress(tmp_path):
    s = store(tmp_path)
    s.record("concept.hara", cards_seen=2)
    assert s.status("concept.hara") == "in_progress"


def test_a_score_at_the_pass_mark_passes(tmp_path):
    s = store(tmp_path, pass_mark=0.8)
    s.record("concept.hara", score=0.8)
    assert s.status("concept.hara") == "passed"


def test_a_score_below_the_pass_mark_needs_review(tmp_path):
    s = store(tmp_path, pass_mark=0.8)
    s.record("concept.hara", score=0.5)
    assert s.status("concept.hara") == "needs_review"


def test_the_best_score_is_kept_not_the_latest(tmp_path):
    """Retakes are encouraged, so a bad retake must not erase a pass."""
    s = store(tmp_path)
    s.record("concept.hara", score=0.9)
    s.record("concept.hara", score=0.2)
    rec = s.load()["modules"]["concept.hara"]
    assert rec["best"] == 0.9 and rec["attempts"] == 2
    assert s.status("concept.hara") == "passed"


def test_attempts_count_only_scored_submissions(tmp_path):
    s = store(tmp_path)
    s.record("concept.hara", cards_seen=3)
    s.record("concept.hara", score=0.5)
    assert s.load()["modules"]["concept.hara"]["attempts"] == 1


def test_progress_survives_a_reload(tmp_path):
    store(tmp_path).record("concept.hara", score=0.9)
    assert store(tmp_path).status("concept.hara") == "passed"


def test_a_corrupt_file_reads_as_nothing_started(tmp_path):
    (tmp_path / "learning-progress.json").write_text("{ not json", encoding="utf-8")
    assert store(tmp_path).status("concept.hara") == "not_started"


def test_a_corrupt_file_is_replaced_on_the_next_write_not_appended(tmp_path):
    p = tmp_path / "learning-progress.json"
    p.write_text("{ not json", encoding="utf-8")
    store(tmp_path).record("concept.hara", score=1.0)
    assert json.loads(p.read_text(encoding="utf-8"))["modules"]["concept.hara"]["best"] == 1.0


def test_a_record_carries_when_it_was_last_seen(tmp_path):
    rec = store(tmp_path).record("concept.hara", cards_seen=1)
    assert rec["last_seen"].endswith("+00:00")
