"""Content cannot be reviewed by running it, so the rules that keep it honest live here.

Two of them are not style: a card that drifts from the chain teaches a work product that does
not exist, and an internal URL in the shipped sample publishes an employer's material from a
public repository.
"""
import pathlib

import yaml

from fusa.learn import ContentRegistry
from fusa.learn.rules import (INTERNAL_PATTERNS, WORD_CAP, check_bundle,
                              check_module, check_scenarios)

ROOT = pathlib.Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "fusa" / "ui" / "content-sample"


def module(**over):
    m = {"id": "g.m", "group": "0", "order": 1, "title": "T", "vmodel_position": "concept",
         "clauses": [], "cards": [{"type": "concept", "title": "C", "body": "short body"}],
         "inline_check": None, "quiz": [], "work_products": [], "checklist_ref": None}
    m.update(over)
    return m


def test_a_card_body_over_the_word_cap_is_an_error():
    long_body = " ".join(["word"] * (WORD_CAP + 1))
    errs = check_module(module(cards=[{"type": "concept", "title": "C", "body": long_body}]))
    assert any(str(WORD_CAP) in e for e in errs)


def test_a_diagram_card_without_alt_text_is_an_error():
    errs = check_module(module(cards=[{"type": "diagram", "asset": "vmodel"}]))
    assert any("alt" in e for e in errs)


def test_a_question_without_an_explanation_is_an_error():
    errs = check_module(module(quiz=[
        {"id": "q1", "type": "single", "prompt": "p", "options": ["a", "b"], "answer": 0}]))
    assert any("explanation" in e for e in errs)


def test_an_answer_index_outside_the_options_is_an_error():
    errs = check_module(module(quiz=[
        {"id": "q1", "type": "single", "prompt": "p", "options": ["a", "b"],
         "answer": 5, "explanation": "x"}]))
    assert any("answer" in e for e in errs)


def test_a_multi_answer_must_be_a_list_of_valid_indices():
    errs = check_module(module(quiz=[
        {"id": "q1", "type": "multi", "prompt": "p", "options": ["a", "b"],
         "answer": [0, 9], "explanation": "x"}]))
    assert any("answer" in e for e in errs)


def test_a_card_ref_past_the_end_of_the_cards_is_an_error():
    errs = check_module(module(quiz=[
        {"id": "q1", "type": "single", "prompt": "p", "options": ["a", "b"],
         "answer": 0, "explanation": "x", "card_ref": 7}]))
    assert any("card_ref" in e for e in errs)


def test_a_well_formed_module_has_no_errors():
    assert check_module(module()) == []


def test_a_diagram_card_naming_an_asset_this_milestone_cannot_draw_is_an_error():
    """The renderer draws one diagram. Content authored for another must say so loudly rather
    than silently getting the V-model with somebody else's alt text."""
    errs = check_module(module(cards=[
        {"type": "diagram", "asset": "hara-anatomy.svg", "alt": "the anatomy of a HARA"}]))
    assert any("hara-anatomy.svg" in e and "milestone" in e for e in errs)


def test_a_diagram_card_asking_for_the_vmodel_is_fine():
    assert check_module(module(cards=[
        {"type": "diagram", "asset": "vmodel", "alt": "the V-model"}])) == []


def test_a_numeric_question_is_rejected_until_the_platform_can_render_one():
    errs = check_module(module(quiz=[
        {"id": "q1", "type": "numeric", "prompt": "p", "answer": 3, "explanation": "x"}]))
    assert any("numeric" in e for e in errs)


def test_an_inline_check_without_an_explanation_is_an_error():
    """It renders as the literal string "undefined" to a learner who got it wrong."""
    errs = check_module(module(inline_check={
        "prompt": "p", "options": ["a", "b"], "answer": 1}))
    assert any("explanation" in e for e in errs)


def test_a_multi_question_with_an_empty_answer_is_an_error():
    """An empty answer scores an empty submission as correct."""
    errs = check_module(module(quiz=[
        {"id": "q1", "type": "multi", "prompt": "p", "options": ["a", "b"],
         "answer": [], "explanation": "x"}]))
    assert any("answer" in e for e in errs)


# ---- the two that are not style ----

def test_a_work_product_the_chain_does_not_produce_is_an_error(tmp_path):
    reg = ContentRegistry(SAMPLE, tmp_path)
    assert check_bundle(reg, work_products={"HARA"}, checklists={"HARA"}) == []
    errs = check_bundle(reg, work_products=set(), checklists={"HARA"})
    assert any("HARA" in e for e in errs)


def test_a_checklist_ref_with_no_register_file_is_an_error(tmp_path):
    reg = ContentRegistry(SAMPLE, tmp_path)
    errs = check_bundle(reg, work_products={"HARA"}, checklists=set())
    assert any("checklist" in e.lower() for e in errs)


def test_the_shipped_sample_names_no_internal_system():
    """C4. This repository is public; the sample must be publishable."""
    text = "\n".join(p.read_text(encoding="utf-8") for p in SAMPLE.rglob("*.json"))
    for pattern in INTERNAL_PATTERNS:
        assert pattern.lower() not in text.lower(), f"sample content names {pattern!r}"


def test_the_shipped_sample_passes_every_rule():
    reg = ContentRegistry(SAMPLE, None)
    specs = yaml.safe_load((ROOT / "config" / "agents.yaml").read_text(encoding="utf-8"))
    wps = {a["work_product"] for a in specs["agents"]}
    checklists = {p.stem for p in (ROOT / "_checklist-register").glob("*.yaml")}
    assert check_bundle(reg, work_products=wps, checklists=checklists) == []


# ---- the boundaries: a cap is the longest allowed, an index stops one short of the count ----

def test_a_card_body_of_exactly_the_word_cap_is_allowed():
    body = " ".join(["word"] * WORD_CAP)
    assert check_module(module(cards=[{"type": "concept", "title": "C", "body": body}])) == []


def test_an_answer_index_equal_to_the_option_count_is_an_error():
    """Options are numbered from zero, so len(options) is one past the last of them."""
    errs = check_module(module(quiz=[
        {"id": "q1", "type": "single", "prompt": "p", "options": ["a", "b"],
         "answer": 2, "explanation": "x"}]))
    assert any("answer" in e for e in errs)


def test_a_card_ref_equal_to_the_card_count_is_an_error():
    errs = check_module(module(quiz=[
        {"id": "q1", "type": "single", "prompt": "p", "options": ["a", "b"],
         "answer": 0, "explanation": "x", "card_ref": 1}]))       # the module has one card
    assert any("card_ref" in e for e in errs)


def test_an_inline_check_answered_by_its_first_option_is_valid():
    assert check_module(module(inline_check={
        "prompt": "p", "options": ["a", "b"], "answer": 0, "explanation": "why"})) == []


def test_an_inline_check_answering_past_its_last_option_is_an_error():
    errs = check_module(module(inline_check={
        "prompt": "p", "options": ["a", "b"], "answer": 2, "explanation": "why"}))
    assert any("index" in e for e in errs)


def test_an_inline_check_with_no_answer_at_all_is_an_error_not_a_crash():
    """Hand-authored content omits fields; the author needs to be told which, not a KeyError."""
    errs = check_module(module(inline_check={
        "prompt": "p", "options": ["a", "b"], "explanation": "why"}))
    assert any("index" in e for e in errs)


# ---- scenarios: the cases the interactive tools walk a learner through ----

def scenario(**over):
    s = {"id": "s1", "title": "A case", "reveal": "always", "hazard_id": "HZ-101",
         "item": "An item that does one thing.",
         "steps": {"function": {"options": ["do the thing", "log a fault"], "answer": 0},
                   "guideword": {"answer": "too late"},
                   "malfunction": {"answer": "the thing is done late"},
                   "situation": {"options": ["at speed", "parked"], "answer": 0},
                   "hazardous_event": {"answer": "at speed, the thing is done too late"},
                   "rating": {"answer": {"severity": "S3", "exposure": "E3",
                                         "controllability": "C2"}},
                   "rationale": {"answer": "S3 because; E3 because; C2 because"},
                   "safety_goal": {"answer": "The item shall do the thing in time."}}}
    s.update(over)
    return s


def test_a_well_formed_scenario_has_nothing_to_report():
    assert check_scenarios([scenario()], "hara") == []


def test_a_scenario_promising_answers_that_omits_one_is_an_error():
    """A worked example missing a step's answer strands the learner on that step."""
    s = scenario()
    del s["steps"]["guideword"]["answer"]
    errs = check_scenarios([s], "hara")
    assert any("guideword" in e for e in errs)


def test_a_scenario_with_no_answer_key_that_ships_one_is_an_error():
    """The unassisted case is unassisted because the key is not in the payload — a key sent to
    the browser and hidden there is one view-source away from being the answer."""
    errs = check_scenarios([scenario(reveal="never")], "hara")
    assert any("answer" in e for e in errs)


def test_a_choose_answer_past_the_end_of_its_options_is_an_error():
    s = scenario()
    s["steps"]["situation"]["answer"] = 2
    assert any("situation" in e for e in check_scenarios([s], "hara"))


def test_a_guideword_outside_the_fixed_list_is_an_error():
    """The tool offers eight; an answer it cannot offer can never be reached."""
    s = scenario()
    s["steps"]["guideword"]["answer"] = "sideways"
    assert any("sideways" in e for e in check_scenarios([s], "hara"))


def test_a_rating_class_outside_the_scales_is_an_error():
    s = scenario()
    s["steps"]["rating"]["answer"]["exposure"] = "E9"
    assert any("E9" in e for e in check_scenarios([s], "hara"))


def test_an_unknown_reveal_mode_is_an_error():
    assert any("reveal" in e for e in check_scenarios([scenario(reveal="sometimes")], "hara"))


def test_a_scenario_without_a_hazard_id_is_an_error():
    """The id is the first column of the row the exercise produces."""
    assert any("hazard_id" in e for e in check_scenarios([scenario(hazard_id="")], "hara"))


def test_two_scenarios_sharing_an_id_is_an_error():
    errs = check_scenarios([scenario(), scenario(title="Another")], "hara")
    assert any("s1" in e for e in errs)


def test_the_shipped_scenarios_pass_every_rule():
    reg = ContentRegistry(SAMPLE, None)
    assert check_scenarios(reg.scenarios("hara"), "hara") == []


def test_a_choose_answer_of_true_is_not_an_index_into_its_options():
    """`True` is an int in Python, so an unguarded index check would quietly select option 1."""
    s = scenario()
    s["steps"]["function"]["answer"] = True
    assert any("function" in e for e in check_scenarios([s], "hara"))


def test_a_scenario_whose_steps_are_not_an_object_is_reported_not_raised():
    """Hand-written content gets shapes wrong; a traceback in the course loader takes the whole
    page down, and every other case with it."""
    assert any("steps" in e for e in check_scenarios([scenario(steps=[])], "hara"))
