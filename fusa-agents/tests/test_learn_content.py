"""Content is read from the user's local directory first and the shipped sample second, so
employer-internal material can drive the course without ever entering this repository."""
import json

import pytest

from fusa.learn import ContentRegistry


def write_module(d, mid, group="0", order=1, title="T"):
    (d / "modules").mkdir(parents=True, exist_ok=True)
    (d / "modules" / f"{mid}.json").write_text(json.dumps({
        "id": mid, "group": group, "order": order, "title": title,
        "vmodel_position": "concept", "clauses": [], "cards": [],
        "quiz": [], "work_products": [], "checklist_ref": None}), encoding="utf-8")


@pytest.fixture
def sample(tmp_path):
    d = tmp_path / "sample"
    d.mkdir()
    (d / "groups.json").write_text(json.dumps(
        [{"id": "0", "title": "Orientation", "order": 0},
         {"id": "2", "title": "Concept Phase", "order": 2}]), encoding="utf-8")
    (d / "paths.json").write_text("[]", encoding="utf-8")
    (d / "glossary.json").write_text(json.dumps({"ASIL": "a risk classification"}), encoding="utf-8")
    write_module(d, "orientation.intro", group="0", order=1, title="Sample intro")
    return d


def test_the_sample_is_served_when_there_is_no_local_content(sample, tmp_path):
    reg = ContentRegistry(sample, tmp_path / "nothing-here")
    assert [m["id"] for m in reg.modules()] == ["orientation.intro"]
    assert reg.module("orientation.intro")["title"] == "Sample intro"
    assert reg.glossary()["ASIL"] == "a risk classification"


def test_local_content_adds_to_the_sample(sample, tmp_path):
    local = tmp_path / "content"
    write_module(local, "concept.hara", group="2", order=1, title="HARA")
    reg = ContentRegistry(sample, local)
    assert [m["id"] for m in reg.modules()] == ["orientation.intro", "concept.hara"]


def test_a_local_module_overrides_the_sample_module_of_the_same_id(sample, tmp_path):
    local = tmp_path / "content"
    write_module(local, "orientation.intro", group="0", order=1, title="Mine")
    reg = ContentRegistry(sample, local)
    assert len(reg.modules()) == 1
    assert reg.module("orientation.intro")["title"] == "Mine"


def test_local_groups_replace_the_sample_groups_wholesale(sample, tmp_path):
    """Group order is a single editorial decision; merging two lists would interleave them."""
    local = tmp_path / "content"
    local.mkdir()
    (local / "groups.json").write_text(json.dumps(
        [{"id": "0", "title": "My orientation", "order": 0}]), encoding="utf-8")
    reg = ContentRegistry(sample, local)
    assert [g["title"] for g in reg.groups()] == ["My orientation"]


def test_modules_come_back_in_group_then_module_order(sample, tmp_path):
    local = tmp_path / "content"
    write_module(local, "concept.b", group="2", order=2)
    write_module(local, "concept.a", group="2", order=1)
    reg = ContentRegistry(sample, local)
    assert [m["id"] for m in reg.modules()] == ["orientation.intro", "concept.a", "concept.b"]


def test_an_unknown_module_id_is_none_not_an_error(sample, tmp_path):
    assert ContentRegistry(sample, tmp_path).module("no.such.module") is None


def test_the_bundle_is_everything_the_browser_needs_in_one_payload(sample, tmp_path):
    b = ContentRegistry(sample, tmp_path).bundle()
    assert set(b) == {"groups", "modules", "paths", "glossary"}
    assert b["modules"] and b["groups"]


def test_a_module_file_that_is_not_json_is_reported_not_swallowed(sample, tmp_path):
    local = tmp_path / "content"
    (local / "modules").mkdir(parents=True)
    (local / "modules" / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="broken.json"):
        ContentRegistry(sample, local).modules()


def test_a_module_file_with_no_id_is_reported_by_name_not_a_bare_key_error(sample, tmp_path):
    """A missing "id" is at least as likely a hand-authoring slip as a missing brace, and the
    author needs to be told which file and which field."""
    local = tmp_path / "content"
    (local / "modules").mkdir(parents=True)
    (local / "modules" / "no-id.json").write_text('{"title": "no id here"}', encoding="utf-8")
    with pytest.raises(ValueError, match=r"no-id\.json.*id"):
        ContentRegistry(sample, local).modules()


def test_a_module_file_that_is_not_an_object_is_reported_by_name(sample, tmp_path):
    local = tmp_path / "content"
    (local / "modules").mkdir(parents=True)
    (local / "modules" / "a-list.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match=r"a-list\.json"):
        ContentRegistry(sample, local).modules()


def test_a_mis_encoded_file_is_reported_by_name_too(sample, tmp_path):
    local = tmp_path / "content"
    (local / "modules").mkdir(parents=True)
    (local / "modules" / "latin1.json").write_bytes(b'{"id": "x", "title": "caf\xe9"}')
    with pytest.raises(ValueError, match=r"latin1\.json"):
        ContentRegistry(sample, local).modules()


def test_no_local_directory_at_all_still_serves_the_sample(sample):
    """A fresh clone sets no FUSA_CONTENT_DIR, and that is the default way to run the course."""
    reg = ContentRegistry(sample, None)
    assert [m["id"] for m in reg.modules()] == ["orientation.intro"]
    assert reg.groups() and reg.glossary()
