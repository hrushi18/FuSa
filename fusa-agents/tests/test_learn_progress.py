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


# ---- a hand-edited file is valid JSON with the wrong shape far more often than it is garbage ----

def write(tmp_path, data):
    (tmp_path / "learning-progress.json").write_text(json.dumps(data), encoding="utf-8")


def test_a_record_that_is_a_string_instead_of_an_object_reads_as_nothing_started(tmp_path):
    write(tmp_path, {"version": 1, "modules": {"concept.hara": "passed"}})
    s = store(tmp_path)
    assert s.status("concept.hara") == "not_started"
    assert s.summary() == {}


def test_a_best_score_that_is_a_string_reads_as_nothing_started(tmp_path):
    write(tmp_path, {"version": 1, "modules": {"concept.hara": {"best": "0.9", "attempts": 1}}})
    assert store(tmp_path).status("concept.hara") == "not_started"


def test_a_null_best_score_still_reads_the_rest_of_the_record(tmp_path):
    write(tmp_path, {"version": 1,
                     "modules": {"concept.hara": {"best": None, "cards_seen": 2}}})
    assert store(tmp_path).status("concept.hara") == "in_progress"


def test_a_record_missing_attempts_is_still_a_record(tmp_path):
    write(tmp_path, {"version": 1, "modules": {"concept.hara": {"best": 0.9}}})
    s = store(tmp_path)
    assert s.status("concept.hara") == "passed"
    assert s.summary()["concept.hara"]["attempts"] == 0


def test_modules_as_a_list_reads_as_nothing_started(tmp_path):
    write(tmp_path, {"version": 1, "modules": [{"id": "concept.hara"}]})
    s = store(tmp_path)
    assert s.status("concept.hara") == "not_started"
    assert s.summary() == {}


def test_one_bad_record_does_not_cost_the_learner_the_sound_ones(tmp_path):
    write(tmp_path, {"version": 1, "modules": {
        "concept.hara": "passed",
        "orientation.what-is-fusa": {"best": 1.0, "attempts": 1, "cards_seen": 3}}})
    s = store(tmp_path)
    assert s.status("concept.hara") == "not_started"
    assert s.status("orientation.what-is-fusa") == "passed"
    assert set(s.summary()) == {"orientation.what-is-fusa"}


def test_a_negative_cards_seen_in_the_file_reads_as_nothing_started(tmp_path):
    write(tmp_path, {"version": 1, "modules": {"concept.hara": {"cards_seen": -4}}})
    assert store(tmp_path).status("concept.hara") == "not_started"


def test_a_bad_record_is_replaced_rather_than_crashing_the_next_write(tmp_path):
    write(tmp_path, {"version": 1, "modules": {"concept.hara": {"best": "0.9"}}})
    assert store(tmp_path).record("concept.hara", score=1.0)["best"] == 1.0


def test_a_cards_seen_of_true_reads_as_nothing_started(tmp_path):
    """`True` is an `int` in Python, so a hand edit of `"cards_seen": true` would otherwise
    count as one card seen and open a module the learner has never touched."""
    write(tmp_path, {"version": 1, "modules": {"concept.hara": {"cards_seen": True}}})
    s = store(tmp_path)
    assert s.status("concept.hara") == "not_started"
    assert s.summary() == {}


def test_an_attempts_count_that_is_not_a_number_costs_the_count_not_the_pass(tmp_path):
    """A tally nobody reads is not worth losing a recorded pass over."""
    write(tmp_path, {"version": 1, "modules": {"concept.hara": {"best": 0.9, "attempts": "many"}}})
    s = store(tmp_path)
    assert s.status("concept.hara") == "passed"
    assert s.summary()["concept.hara"]["attempts"] == 0


def test_a_negative_attempts_count_is_reset_to_zero(tmp_path):
    write(tmp_path, {"version": 1, "modules": {"concept.hara": {"best": 0.9, "attempts": -3}}})
    assert store(tmp_path).summary()["concept.hara"]["attempts"] == 0


def test_seeing_fewer_cards_on_a_revisit_does_not_undo_the_ones_already_seen(tmp_path):
    """Reopening a module and closing it early is normal; progress going backwards reads as
    lost work."""
    s = store(tmp_path)
    s.record("concept.hara", cards_seen=5)
    s.record("concept.hara", cards_seen=2)
    assert s.load()["modules"]["concept.hara"]["cards_seen"] == 5


def test_progress_is_written_even_when_its_directory_does_not_exist_yet(tmp_path):
    """The file lands beside the rest of a project's generated state, which a fresh clone has
    not created yet."""
    s = ProgressStore(tmp_path / "_generated" / "learn" / "learning-progress.json")
    s.record("concept.hara", score=1.0)
    assert s.status("concept.hara") == "passed"
