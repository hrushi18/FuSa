"""What the interactive tools need from the project, and nothing they could compute themselves.

The ASIL calculator is the reason this module exists. It performs no determination of its own:
it calls the same `determine_asil` the HARA generator calls, over the same table the engineer
transcribed from their licensed standard. A learner is therefore taught the mapping their own
chain applies, and an unfilled cell says so instead of guessing.
"""
from __future__ import annotations

import random

from ..generators.kinds import (ASIL_TABLE_FILE, TRACE_CHAIN, determine_asil,
                                load_asil_table)

SEVERITY = ("S0", "S1", "S2", "S3")
EXPOSURE = ("E0", "E1", "E2", "E3", "E4")
CONTROLLABILITY = ("C0", "C1", "C2", "C3")


class UnknownClass(ValueError):
    """A class outside the scales. Looking it up would silently return 'not transcribed yet'
    for a combination that does not exist, which reads as a gap in the user's table."""


def asil_lookup(reg, sev: str, exp: str, ctr: str) -> dict:
    s, e, c = (v.strip().upper() for v in (sev, exp, ctr))
    for value, scale, name in ((s, SEVERITY, "severity"), (e, EXPOSURE, "exposure"),
                               (c, CONTROLLABILITY, "controllability")):
        if value not in scale:
            raise UnknownClass(f"{name} {value!r} is not one of {', '.join(scale)}")
    table = load_asil_table(reg)
    asil, why = determine_asil(s, e, c, table)
    return {"asil": asil, "why": why, "key": f"{s}-{e}-{c}", "file": ASIL_TABLE_FILE,
            "filled": sum(1 for v in table.values() if str(v).strip()),
            "total": len(SEVERITY[1:]) * len(EXPOSURE[1:]) * len(CONTROLLABILITY[1:])}


# The lifecycle phases, named. `config/agents.yaml` carries the number on every agent and the
# workbench board prints the names; a test holds these two spellings together so the lab cannot
# offer a learner a phase the board calls something else.
PHASE_NAMES = {1: "Concept & Requirements", 2: "System Analysis", 3: "Hardware Analysis",
               4: "Software Analysis", 5: "Quantitative Analysis", 6: "Safety Solution",
               7: "Verification & Validation"}

# The three things a broken trace asks of a reviewer, scored apart from one another because
# they are three different pieces of knowledge.
TRACE_PARTS = ("link", "phase", "evidence")


class NoTrace(LookupError):
    """No chain to break. Not an error the learner caused, so the caller reports it as a state."""


def _trace_generator(orch) -> dict:
    """The traceability agent's own configuration — one chain, walked by the agent and the lab."""
    for spec in orch.specs:
        if (spec.generator or {}).get("kind") == "traceability":
            return spec.generator
    return {}


def _children(reg, levels: list[str]) -> dict[str, list[tuple[str, str]]]:
    """parent id -> the (work product, id) of everything declaring it. The whole trace is this."""
    kids: dict[str, list[tuple[str, str]]] = {}
    for wp in levels:
        for item in reg.generated.items(wp):
            for parent in item.refs("parent"):
                kids.setdefault(parent, []).append((wp, item.id))
    return kids


def _branch(kids, goal_id: str, levels: list[str], rng) -> list[dict]:
    """One item per level, each a child of something already on the branch.

    A whole trace fans out; a case is one path through it, which is what makes it readable in a
    lab. TEST-SPEC hangs off TSR as often as off HSR, so a child of *any* node already chosen
    counts — the branch follows the links, not a straight line down the page. A level nothing
    hangs off is skipped rather than ending the branch, for the same reason the agent walks a
    frontier: a project halfway through its chain still has a trace worth reading.
    """
    path = [{"work_product": levels[0], "id": goal_id, "parent": None}]
    chosen = {goal_id}
    for wp in levels[1:]:
        options = sorted({(node, child) for node in chosen
                          for w, child in kids.get(node, []) if w == wp})
        if not options:
            continue
        parent, child = options[rng.randrange(len(options))]
        path.append({"work_product": wp, "id": child, "parent": parent})
        chosen.add(child)
    return path


def _link_question(path: list[dict], cut: int, goal_id: str, reached: set[str]) -> dict:
    """Which link is broken. The lesson is that the lowest empty level is the symptom.

    Which side of the break a link is on is a question about what still reaches the goal, not
    about how far down the page it sits: a test case hung off a requirement above the break
    traces perfectly well while the level between them is empty.
    """
    wp_of = {n["id"]: n["work_product"] for n in path}
    options = []
    for i, node in enumerate(path[1:], 1):
        parent, child = node["parent"], node["id"]
        text = f"{parent} → {child}  ({wp_of[parent]} → {node['work_product']})"
        if i == cut:
            why = (f"{child} is the first item in the branch that no longer traces. {parent} still "
                   f"reaches {goal_id}, and nothing under it names {child}. Every empty level "
                   f"below is a consequence of this one link.")
        elif child in reached:
            why = (f"{child} still traces to {goal_id} — the matrix shows it. A link you can "
                   f"still see is not the one that broke.")
        else:
            why = (f"{child} does name {parent}, but {parent} itself no longer reaches "
                   f"{goal_id}, so this level is empty as a consequence. Repairing it here would "
                   f"leave the real break in place and the level still empty.")
        options.append({"text": text, "why": why})
    return {"title": "Which link is broken?",
            "prompt": f"{len(options) - 1} of these {len(options)} links are intact. Name the one "
                      f"that stopped {goal_id} from reaching the levels below it.",
            "options": options, "answer": cut - 1}


def _phase_question(orch, path: list[dict], cut: int) -> dict:
    """Which lifecycle phase owns the fix — the phase of the agent that writes the missing link."""
    broken = path[cut]
    owner = orch.by_wp[broken["work_product"]]
    phases = sorted({s.phase for s in orch.specs if s.kind in ("authoring", "runner")})
    options = []
    for phase in phases:
        wps = [s.work_product for s in orch.specs if s.phase == phase
               and s.kind in ("authoring", "runner")]
        named = ", ".join(wps[:3]) + ("…" if len(wps) > 3 else "")
        if phase == owner.phase:
            why = (f"{broken['work_product']} is produced by `{owner.id}` in phase {phase}. The "
                   f"missing `parent:` is written into that work product, so that is the phase "
                   f"the rework lands in — not the phase that noticed the gap.")
        else:
            why = (f"Phase {phase} owns {named}. None of those is where a missing "
                   f"{broken['work_product']} link would be written.")
        options.append({"text": f"Phase {phase} · {PHASE_NAMES.get(phase, 'unnamed')}", "why": why})
    return {"title": "Which phase owns the fix?",
            "prompt": "A gap is closed where the work product is authored. Which phase of "
                      "config/agents.yaml is that?",
            "options": options, "answer": phases.index(owner.phase)}


def _evidence_question(orch, path: list[dict], cut: int, goal_id: str, rng) -> dict:
    """What would actually close the gap — as against what merely documents or verifies it."""
    broken = path[cut]
    parent, wp = broken["parent"], broken["work_product"]
    owner = orch.by_wp[wp]
    options = [
        {"text": f"A {wp} item from `{owner.id}` carrying `parent: {parent}`.",
         "why": f"The link is the evidence. The matrix is derived from `parent:` fields, so a "
                f"{wp} item that names {parent} is what makes {goal_id} reach this level again — "
                f"and it is the only thing that does."},
        {"text": f"An independent review sign-off on {parent}.",
         "why": f"A review says {parent} is sound. It says nothing about what hangs beneath it, "
                f"and it writes no `parent:` field, so the level stays empty."},
        {"text": "A line in the traceability matrix recording the gap as accepted.",
         "why": "The matrix is derived from the identifiers, never maintained by hand — a line "
                "written into it is overwritten on the next run. Recording a gap is not closing "
                "one either way."},
        {"text": f"A test case that exercises {parent}.",
         "why": f"A test verifies that {parent} is met. Verification of a requirement that "
                f"exists cannot supply the one that does not."},
    ]
    # Shuffled, because an answer that is always first is a lesson about lists, not about
    # evidence. The seed makes the order reproducible all the same.
    key = options[0]
    rng.shuffle(options)
    return {"title": "What evidence closes the gap?",
            "prompt": "One of these makes the branch trace again. The other three are things a "
                      "project reaches for instead.",
            "options": options, "answer": options.index(key)}


def trace_case(orch, seed: int) -> dict:
    """One safety goal's branch down the V, with exactly one `parent:` link removed.

    The branch is walked over the same links `generate_traceability` walks, in the same order, so
    the case describes this project's own safety file rather than an invented one. Removing a
    link high in the branch empties every level below it, and that is the misreading the lab
    exists to correct: the lowest empty level is the symptom, the first one is the break.

    Raises NoTrace when nothing has been generated — with no chain there is nothing to break,
    and inventing a case would teach a file the learner cannot go and read.
    """
    cfg = _trace_generator(orch)
    chain = cfg.get("chain") or TRACE_CHAIN
    root, root_prefix = cfg.get("root", "SADS"), cfg.get("root_prefix", "SG")
    reg = orch.reg
    if not (root in orch.by_wp and reg.generated.exists(root)):
        raise NoTrace(f"{root} has not been produced yet")
    # Only work products an agent declares: a level nothing owns has no phase to answer with.
    # An ungenerated one needs no filtering — it has no items, so nothing can hang off it.
    levels = [root] + [wp for wp in chain[1:] if wp in orch.by_wp]
    goals = sorted(i.id for i in reg.generated.items(root) if i.prefix == root_prefix)
    if not goals:
        raise NoTrace(f"{root} holds no {root_prefix} item to trace from")

    rng = random.Random(seed)
    kids = _children(reg, levels)
    branches = [_branch(kids, g, levels, rng) for g in goals]
    usable = [b for b in branches if len(b) > 1]
    if not usable:
        raise NoTrace("no safety goal has anything declaring it as a parent yet")

    path = usable[rng.randrange(len(usable))]
    cut = rng.randrange(1, len(path))          # never the goal: nothing links down into it
    goal_id = path[0]["id"]

    reached = {goal_id}                        # the walk again, this time with the link gone
    for i, node in enumerate(path[1:], 1):
        if i != cut and node["parent"] in reached:
            reached.add(node["id"])

    rows = []
    for node in path:
        spec = orch.by_wp[node["work_product"]]
        rows.append({"work_product": node["work_product"], "agent": spec.id, "phase": spec.phase,
                     "title": spec.title, "id": node["id"] if node["id"] in reached else None})
    goal = next(i for i in reg.generated.items(root) if i.id == goal_id)
    return {
        "ready": True, "seed": seed,
        "goal": {"id": goal_id, "asil": goal.fields.get("asil", ""),
                 "text": goal.fields.get("text", goal.fields.get("title", "")),
                 "work_product": root},
        "rows": rows, "parts": list(TRACE_PARTS),
        "questions": {"link": _link_question(path, cut, goal_id, reached),
                      "phase": _phase_question(orch, path, cut),
                      "evidence": _evidence_question(orch, path, cut, goal_id, rng)},
    }
