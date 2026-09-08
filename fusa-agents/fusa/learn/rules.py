"""What content has to satisfy before it is worth showing anyone.

Two of these are load-bearing rather than cosmetic. A module naming a work product the chain
does not produce teaches a lifecycle this project cannot validate, and the platform's whole
claim is that the two are the same list. And this repository is public while the content that
drives it may be an employer's: an internal hostname in the shipped sample publishes it.
"""
from __future__ import annotations

from .tools import CONTROLLABILITY, EXPOSURE, SEVERITY

WORD_CAP = 80          # a card should read in under twenty seconds, not be a specification

# C4 — nothing that names an internal system may reach the shipped sample.
INTERNAL_PATTERNS = ("sharepoint.com", "srv.volvo.com", "setoolgtt", "swap://",
                     "Navigator", "FS-QDPR", "WBS", "Volvo")

CARD_TYPES = {"concept", "example", "why", "diagram"}

# The spec's data model also has `numeric` and `match`, but only these two have a renderer and
# a scorer today; the other two arrive with the ASIL calculator in M3. Validation describes what
# the product can do now, so content the quiz would crash on is rejected instead of shipped.
QUESTION_TYPES = {"single", "multi"}

# Likewise one diagram: `vmodel.js` is the only asset this milestone can draw.
DIAGRAM_ASSET = "vmodel"

# The HARA builder's guidewords. The tool offers exactly these, so an answer key naming
# anything else is one no learner could ever reach; a test holds the two lists together.
GUIDEWORDS = ("too late", "too early", "omission", "commission",
              "too high", "too low", "reverse", "other")

# The sequence the builder walks, and how each step's answer is shaped. The order is the
# method — item, then what it does, then how that goes wrong, then where — and a scenario
# missing a step in the middle would leave the learner with a row it cannot finish.
CHOOSE, TEXT, GUIDEWORD, RATING = "choose", "text", "guideword", "rating"
SCENARIO_STEPS = {"function": CHOOSE, "guideword": GUIDEWORD, "malfunction": TEXT,
                  "situation": CHOOSE, "hazardous_event": TEXT, "rating": RATING,
                  "rationale": TEXT, "safety_goal": TEXT}
REVEAL_MODES = ("always", "submit", "never")
SCENARIO_TOOLS = ("hara",)


def check_module(m: dict) -> list[str]:
    mid = m.get("id", "<no id>")
    errs: list[str] = []
    cards = m.get("cards") or []
    for n, c in enumerate(cards):
        where = f"{mid} card {n}"
        if c.get("type") not in CARD_TYPES:
            errs.append(f"{where}: unknown card type {c.get('type')!r}")
        if c.get("type") == "diagram":
            if not (c.get("alt") or "").strip():
                errs.append(f"{where}: a diagram needs alt text — it is the only version some readers get")
            asset = c.get("asset") or DIAGRAM_ASSET
            if asset != DIAGRAM_ASSET:
                errs.append(f"{where}: asset {asset!r} — custom diagram assets arrive in a later"
                            f" milestone; only {DIAGRAM_ASSET!r} renders today")
        words = len((c.get("body") or "").split())
        if words > WORD_CAP:
            errs.append(f"{where}: {words} words, over the {WORD_CAP}-word cap")

    for q in m.get("quiz") or []:
        where = f"{mid} {q.get('id', '<no id>')}"
        if q.get("type") not in QUESTION_TYPES:
            errs.append(f"{where}: unknown question type {q.get('type')!r}")
        if not (q.get("explanation") or "").strip():
            errs.append(f"{where}: needs an explanation — a wrong answer with no reason teaches nothing")
        options = q.get("options") or []
        answer = q.get("answer")
        wanted = answer if isinstance(answer, list) else [answer]
        if q.get("type") in ("single", "multi"):
            if isinstance(answer, list) != (q["type"] == "multi"):
                errs.append(f"{where}: a {q['type']} answer has the wrong shape")
            elif not wanted:               # an empty answer scores an empty submission as right
                errs.append(f"{where}: a multi answer with no correct option passes anyone")
            elif any(not isinstance(a, int) or not 0 <= a < len(options) for a in wanted):
                errs.append(f"{where}: answer {answer!r} is not an index into {len(options)} options")
        ref = q.get("card_ref")
        if ref is not None and not 0 <= ref < len(cards):
            errs.append(f"{where}: card_ref {ref} is past the end of {len(cards)} cards")

    check = m.get("inline_check")
    if check:
        opts = check.get("options") or []
        if not isinstance(check.get("answer"), int) or not 0 <= check["answer"] < len(opts):
            errs.append(f"{mid} inline check: answer is not an index into its options")
        if not (check.get("explanation") or "").strip():
            errs.append(f"{mid} inline check: needs an explanation — the learner sees it the"
                        " moment they answer")
    return errs


def check_bundle(reg, work_products: set[str], checklists: set[str]) -> list[str]:
    """Every module's rules, plus the two links to the chain that must not rot."""
    errs: list[str] = []
    for m in reg.modules():
        errs += check_module(m)
        for wp in m.get("work_products") or []:
            if wp not in work_products:
                errs.append(f"{m['id']}: work product {wp!r} is not produced by any agent")
        ref = m.get("checklist_ref")
        if ref and ref not in checklists:
            errs.append(f"{m['id']}: checklist_ref {ref!r} has no register file")
    for tool in SCENARIO_TOOLS:
        errs += check_scenarios(reg.scenarios(tool), tool)
    return errs


def _check_answer(where: str, kind: str, step: dict) -> list[str]:
    answer = step.get("answer")
    if kind == CHOOSE:
        options = step.get("options") or []
        if isinstance(answer, bool) or not isinstance(answer, int):
            return [f"{where}: answer {answer!r} is not an index into its options"]
        if not 0 <= answer < len(options):
            return [f"{where}: answer {answer} is not an index into {len(options)} options"]
        return []
    if kind == GUIDEWORD:
        return [] if answer in GUIDEWORDS else [
            f"{where}: guideword {answer!r} is not one of {', '.join(GUIDEWORDS)}"]
    if kind == RATING:
        if not isinstance(answer, dict):
            return [f"{where}: a rating answer is severity, exposure and controllability"]
        errs = []
        for field, scale in (("severity", SEVERITY), ("exposure", EXPOSURE),
                             ("controllability", CONTROLLABILITY)):
            if answer.get(field) not in scale:
                errs.append(f"{where}: {field} {answer.get(field)!r} is not one of "
                            f"{', '.join(scale)}")
        return errs
    return [] if str(answer or "").strip() else [f"{where}: needs an answer"]


def check_scenario(s: dict, tool: str) -> list[str]:
    """One case for an interactive tool.

    The rule worth the file: a scenario that says it has no answer key must not ship one. A key
    sent to the browser and merely hidden there is one view-source away from being the answer,
    so the unassisted exercise stops being unassisted.
    """
    sid = s.get("id", "<no id>")
    where0 = f"{tool} scenario {sid}"
    errs: list[str] = []
    for field in ("id", "title", "item", "hazard_id"):
        if not str(s.get(field) or "").strip():
            errs.append(f"{where0}: missing required field \"{field}\"")
    reveal = s.get("reveal")
    if reveal not in REVEAL_MODES:
        errs.append(f"{where0}: reveal {reveal!r} is not one of {', '.join(REVEAL_MODES)}")
    steps = s.get("steps")
    if not isinstance(steps, dict):
        return errs + [f"{where0}: steps must be an object keyed by step name"]
    for name in steps:
        if name not in SCENARIO_STEPS:
            errs.append(f"{where0}: unknown step {name!r}")
    for name, kind in SCENARIO_STEPS.items():
        step = steps.get(name) or {}
        where = f"{where0} step {name}"
        if not isinstance(step, dict):
            errs.append(f"{where}: must be an object")
            continue
        if kind == CHOOSE and not (step.get("options") or []):
            errs.append(f"{where}: a choice needs options to choose between")
        if reveal == "never":
            errs += [f"{where}: ships an {k!r} although this case has no answer key"
                     for k in ("answer", "why") if k in step]
        elif reveal in REVEAL_MODES:
            errs += _check_answer(where, kind, step)
    return errs


def check_scenarios(items, tool: str) -> list[str]:
    if not isinstance(items, list):
        return [f"{tool} scenarios: the file must be a list of cases"]
    errs: list[str] = []
    seen: set[str] = set()
    for s in items:
        if not isinstance(s, dict):
            errs.append(f"{tool} scenarios: every case must be an object")
            continue
        sid = str(s.get("id") or "")
        if sid in seen:                    # the id addresses the case; two of them hides one
            errs.append(f"{tool} scenarios: duplicate id {sid!r}")
        seen.add(sid)
        errs += check_scenario(s, tool)
    return errs
