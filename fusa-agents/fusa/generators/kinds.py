"""The generator kinds. One function per work product, registered in GENERATORS.

Each takes the `generator:` block from agents.yaml, the registers, and its own spec, and returns
a Result. Nothing here invents engineering content: a value is either read from the input table,
derived from it by a stated rule, or left as a PENDING marker naming who owes it.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .. import config
from ..models import AgentSpec
from ..registers import Registers
from ..tools import ids as from_base          # id spelling rules, shared with the gate
from .base import InputMissing, Result, Row, read_table

ASIL_TABLE_FILE = "asil-table.yaml"
HAZARD_COLUMNS = ["function", "malfunction", "hazardous_event", "situation",
                  "severity", "exposure", "controllability", "rationale"]
SG_COLUMNS = ["hazard", "safe_state", "ftti"]


def load_asil_table(reg: Registers) -> dict[str, str]:
    """S×E×C → ASIL. The framework ships the keys; the values come from your licensed copy of
    ISO 26262-3, exactly as the clause register ships ids without text."""
    path = Path(reg.reference.path) / ASIL_TABLE_FILE
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k).upper(): str(v).strip().upper() for k, v in (data.get("table") or {}).items() if str(v).strip()}


def determine_asil(sev: str, exp: str, ctr: str, table: dict[str, str]) -> tuple[str | None, str]:
    """(asil, why). S0, E0 or C0 is QM by definition of the class; every other combination is a
    lookup in the table — never re-derived, per the HARA method."""
    s, e, c = (v.strip().upper() for v in (sev, exp, ctr))
    if "S0" in (s,) or "E0" in (e,) or "C0" in (c,):
        return "QM", f"{s}/{e}/{c} is QM by class definition"
    key = f"{s}-{e}-{c}"
    if key in table:
        return table[key], f"{key} from the S×E×C table"
    return None, key


def generate_hara(cfg: dict, reg: Registers, spec: AgentSpec) -> Result:
    """Hazards from the engineer's function × malfunction table; ASIL by S×E×C lookup."""
    rows = read_table(config.INPUT_DIR / cfg.get("input", "hazards.csv"), HAZARD_COLUMNS)
    table = load_asil_table(reg)
    out, pending = [], []
    if not table:
        pending.append(f"S×E×C table empty — fill _reference-register/{ASIL_TABLE_FILE} from your "
                       "licensed copy of ISO 26262-3, or give each row an `asil` column <- project")
    for rec in rows:
        given = rec.get("asil", "").strip().upper()
        asil, why = determine_asil(rec["severity"], rec["exposure"], rec["controllability"], table)
        note = None
        if given:
            asil, why = given, "stated in the input table"
            if (looked_up := determine_asil(rec["severity"], rec["exposure"], rec["controllability"], table)[0]):
                if looked_up != given:
                    note = (f"[PENDING: stated asil {given} disagrees with the S×E×C table "
                            f"({looked_up}) for row {rec['_row']} <- project]")
        elif asil is None:
            note = f"[PENDING: asil for {why} <- project]"
        fields = {k: rec[k] for k in HAZARD_COLUMNS}
        fields["asil"] = asil or ""
        fields["asil_basis"] = why if asil else ""
        out.append(Row(id=rec.get("id") or None, fields=fields, note=note))
    return Result(rows=out, pending=pending)


def generate_safety_goals(cfg: dict, reg: Registers, spec: AgentSpec) -> Result:
    """One safety goal per hazard rated ASIL A..D, plus the assumptions of use.

    The goal's text is templated from the hazard it mitigates and its ASIL is inherited, so the
    trace is exact by construction. Safe state and FTTI are engineering decisions and come from
    the input table; a hazard with neither is left PENDING rather than given a plausible default.
    """
    upstream = cfg.get("from", "HARA")
    if not reg.generated.exists(upstream):
        raise InputMissing(f"{upstream} has not been produced yet")
    hazards = [i for i in reg.generated.items(upstream) if i.prefix == cfg.get("hazard_prefix", "HZ")]

    decisions: dict[str, dict] = {}
    try:
        for rec in read_table(config.INPUT_DIR / cfg.get("input", "safety-goals.csv"), SG_COLUMNS):
            decisions[rec["hazard"].strip().upper()] = rec
    except InputMissing as e:
        decisions = {}
        missing_table = str(e)
    else:
        missing_table = ""

    out, pending = [], []
    if missing_table:
        pending.append(f"{missing_table}: safe state and FTTI per hazard <- project")
    for hz in hazards:
        asil = (hz.fields.get("asil") or "").strip().upper()
        if asil in ("", "QM"):
            continue                                   # QM hazards carry no safety goal
        d = decisions.get(hz.id, {})
        fields = {
            "parent": hz.id,
            "asil": asil,
            "assumed": "true",
            "safe_state": d.get("safe_state", ""),
            "ftti": d.get("ftti", ""),
            "text": d.get("text") or (f"The item shall prevent or detect "
                                      f"{hz.fields.get('malfunction', 'the hazardous malfunction')} "
                                      f"and reach the safe state within the FTTI."),
            "rationale": f"mitigates {hz.id}: {hz.fields.get('hazardous_event', '')}".strip(),
        }
        missing = [k for k in ("safe_state", "ftti") if not fields[k]]
        note = f"[PENDING: {', '.join(missing)} for the goal mitigating {hz.id} <- project]" if missing else None
        out.append(Row(id=d.get("id") or None, prefix="SG", fields=fields, note=note))

    for rec in _optional_table(cfg.get("assumptions", "assumptions.csv"), ["text"]):
        out.append(Row(id=rec.get("id") or None, prefix="AOU",
                       fields={"text": rec["text"], "confirmed_by": rec.get("confirmed_by", "integrator")}))
    if not hazards:
        pending.append(f"no hazards found in {upstream} <- {spec.id}")
    return Result(rows=out, pending=pending)


def _optional_table(name: str, required: list[str]) -> list[dict]:
    try:
        return read_table(config.INPUT_DIR / name, required)
    except (InputMissing, ValueError):
        return []


SM_COLUMNS = ["detects", "reaction", "dc_claim", "allocated_to", "source"]
TSR_COLUMNS = ["safety_goal", "element", "behaviour", "verification"]
ALLOCATION_COLUMNS = ["requirement", "element", "sm", "fdt", "frt"]


def generate_safety_mechanisms(cfg: dict, reg: Registers, spec: AgentSpec) -> Result:
    """The mechanism catalogue: defined once here, referenced by id everywhere else."""
    rows = read_table(config.INPUT_DIR / cfg.get("input", "safety-mechanisms.csv"), SM_COLUMNS)
    out = []
    for rec in rows:
        fields = {k: rec[k] for k in SM_COLUMNS}
        fields["text"] = rec.get("text", "")
        out.append(Row(id=rec.get("id") or None, fields=fields))
    return Result(rows=out)


def generate_technical_requirements(cfg: dict, reg: Registers, spec: AgentSpec) -> Result:
    """One TSR per row, traced to the safety goal it refines.

    The requirement sentence is assembled from the method's own pattern —
    `<element> shall <behaviour> [under <condition>] [within <time>]` — so the wording is the
    engineer's, not a paraphrase. ASIL and safe state are inherited from the parent goal, which
    is what makes the trace exact; a goal with no row here is reported rather than left silent.
    """
    upstream = cfg.get("from", "SADS")
    if not reg.generated.exists(upstream):
        raise InputMissing(f"{upstream} has not been produced yet")
    goals = {i.id: i for i in reg.generated.items(upstream) if i.prefix == cfg.get("goal_prefix", "SG")}
    rows = read_table(config.INPUT_DIR / cfg.get("input", "technical-requirements.csv"), TSR_COLUMNS)

    out, pending, refined = [], [], set()
    for rec in rows:
        sg_id = rec["safety_goal"].strip().upper()
        goal = goals.get(sg_id)
        if goal is None:
            pending.append(f"row {rec['_row']} refines {sg_id or '(blank)'}, which is not in {upstream} <- project")
            continue
        refined.add(sg_id)
        sentence = f"The {rec['element']} shall {rec['behaviour']}"
        if rec.get("condition"):
            sentence += f" under {rec['condition']}"
        if rec.get("within"):
            sentence += f" within {rec['within']}"
        out.append(Row(id=rec.get("id") or None, fields={
            "parent": sg_id,
            "asil": (goal.fields.get("asil") or "").upper(),          # inherited, never restated
            "element": rec["element"],
            "text": sentence.rstrip(".") + ".",
            "safe_state": goal.fields.get("safe_state", ""),
            "sm": rec.get("sm", ""),
            "verification": rec["verification"],
            "rationale": rec.get("rationale") or f"refines {sg_id} ({goal.fields.get('ftti', 'FTTI unstated')})",
        }))
    for sg_id in sorted(set(goals) - refined):
        pending.append(f"{sg_id} has no technical requirement in "
                       f"{cfg.get('input', 'technical-requirements.csv')} <- project")
    return Result(rows=out, pending=pending)


def generate_safety_concept(cfg: dict, reg: Registers, spec: AgentSpec) -> Result:
    """Allocation of each requirement to an element and its mechanisms, with the time budget.

    FTTI is not restated here: it is read through the requirement's parent safety goal, so the
    budget check compares the allocation against the goal that set it.
    """
    upstream = cfg.get("from", "TSR")
    if not reg.generated.exists(upstream):
        raise InputMissing(f"{upstream} has not been produced yet")
    reqs = {i.id: i for i in reg.generated.items(upstream)}
    goals = {i.id: i for wp in ("SADS",) if reg.generated.exists(wp) for i in reg.generated.items(wp)}
    rows = read_table(config.INPUT_DIR / cfg.get("input", "allocation.csv"), ALLOCATION_COLUMNS)

    out, pending, allocated = [], [], set()
    for rec in rows:
        tsr_id = rec["requirement"].strip().upper()
        req = reqs.get(tsr_id)
        if req is None:
            pending.append(f"row {rec['_row']} allocates {tsr_id or '(blank)'}, "
                           f"which is not in {upstream} <- project")
            continue
        allocated.add(tsr_id)
        parent_goal = goals.get(next(iter(req.refs("parent")), ""))
        ftti = (parent_goal.fields.get("ftti", "") if parent_goal else "")
        out.append(Row(id=rec.get("id") or None, fields={
            "parent": tsr_id,
            "asil": req.fields.get("asil", ""),
            "element": rec["element"],
            "sm": rec["sm"],
            "fdt": rec["fdt"],
            "frt": rec["frt"],
            "ftti": ftti,
            "text": f"{req.fields.get('element', rec['element'])}: {rec['sm']} detects the fault in "
                    f"{rec['fdt']} and the item reaches the safe state in {rec['frt']}.",
        }, note=None if ftti else f"[PENDING: ftti for {tsr_id} — its parent goal states none <- sys-sads]"))
    for tsr_id in sorted(set(reqs) - allocated):
        pending.append(f"{tsr_id} is not allocated in {cfg.get('input', 'allocation.csv')} <- project")
    return Result(rows=out, pending=pending, intro=_concept_intro(spec, out))


def _concept_intro(spec: AgentSpec, rows: list[Row]) -> str:
    """The architecture view the checklist asks for, drawn from the allocation itself."""
    by_element: dict[str, list[str]] = {}
    for r in rows:
        for sm in r.fields["sm"].replace(";", ",").split(","):
            if sm.strip():
                by_element.setdefault(r.fields["element"], []).append(sm.strip())
    lines = ["Generated deterministically from the allocation table; the diagram below is drawn "
             "from the same rows, so it cannot drift from them.\n",
             "```mermaid", "flowchart LR"]
    for n, (element, sms) in enumerate(sorted(by_element.items())):
        label = ", ".join(dict.fromkeys(sms))
        lines.append(f'  E{n}["{element}"] -->|{label}| SAFE["safe state"]')
    if not by_element:
        lines.append('  NONE["no allocation rows"] --> SAFE["safe state"]')
    lines.append("```\n")
    return "\n".join(lines)


RISK_MATRIX_FILE = "risk-matrix.yaml"
FMEA_COLUMNS = ["element", "function", "failure_mode", "local_effect", "item_effect", "classification"]
ASSET_COLUMNS = ["property", "damage_scenario"]
THREAT_COLUMNS = ["asset", "stride", "attack_path", "feasibility", "rationale", "treatment"]
IMPACT_CATEGORIES = ["safety", "financial", "operational", "privacy"]
IMPACT_ORDER = ["negligible", "moderate", "major", "severe"]


def generate_fmea(cfg: dict, reg: Registers, spec: AgentSpec) -> Result:
    """One row per failure mode. A mode with no mechanism and a violated goal is *uncovered*:
    it stays visible, carries `finding: uncovered`, and returns to the design agent — the
    framework's own feedback loop, triggered by a fact in the table rather than by a judgement."""
    rows = read_table(config.INPUT_DIR / cfg.get("input", "failure-modes.csv"), FMEA_COLUMNS)
    goals = {i.id for wp in ("SADS",) if reg.generated.exists(wp) for i in reg.generated.items(wp)}
    covered_elements = {i.fields.get("element", "") for wp in (cfg.get("elements_from", "TSC"),)
                        if reg.generated.exists(wp) for i in reg.generated.items(wp)}

    out, pending, seen_elements = [], [], set()
    for rec in rows:
        seen_elements.add(rec["element"])
        sm, violated = rec.get("sm", "").strip(), rec.get("violated_sg", "").strip().upper()
        fields = {k: rec[k] for k in FMEA_COLUMNS}
        fields["classification"] = rec["classification"].strip().upper()
        fields["violated_sg"] = violated
        fields["sm"] = sm
        fields["rationale"] = rec.get("rationale", "")
        if violated and not sm:                       # uncovered: named, not quietly dropped
            fields["finding"] = "uncovered"
            fields["returns_to"] = cfg.get("returns_to", "sys-tsc")
        if violated and goals and violated not in goals:
            pending.append(f"row {rec['_row']} violates {violated}, which is not a safety goal <- project")
        out.append(Row(id=rec.get("id") or None, fields=fields))
    for element in sorted(covered_elements - seen_elements):
        if element:
            pending.append(f"element '{element}' is allocated in {cfg.get('elements_from', 'TSC')} "
                           f"but has no failure-mode row <- project")
    return Result(rows=out, pending=pending)


def load_risk_matrix(reg: Registers) -> dict[str, dict[str, int]]:
    """impact × feasibility → risk. House policy, so it ships filled — but it ships as data,
    looked up and never re-derived (see the TARA method)."""
    path = Path(reg.reference.path) / RISK_MATRIX_FILE
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k).strip().lower(): {str(fk).strip().lower(): v for fk, v in (fv or {}).items()}
            for k, fv in (data.get("matrix") or {}).items()}


def generate_tara(cfg: dict, reg: Registers, spec: AgentSpec) -> Result:
    """Assets and threat scenarios; risk looked up from the house matrix.

    The overall impact is the worst of the four ISO/SAE 21434 categories, so the rating that
    drives the risk is derived from the four the analyst actually gave rather than restated.
    """
    matrix = load_risk_matrix(reg)
    goals = {i.id for wp in ("SADS",) if reg.generated.exists(wp) for i in reg.generated.items(wp)}
    assets = read_table(config.INPUT_DIR / cfg.get("input", "assets.csv"), ASSET_COLUMNS)
    threats = _optional_table(cfg.get("threats", "threat-scenarios.csv"), THREAT_COLUMNS)

    out, pending = [], []
    if not matrix:
        pending.append(f"impact × feasibility matrix empty — fill _reference-register/{RISK_MATRIX_FILE} <- project")
    by_name: dict[str, Row] = {}
    for rec in assets:
        row = Row(id=rec.get("id") or None, prefix="AS", fields={
            "text": rec.get("text") or rec.get("name", ""),
            "property": rec["property"],
            "damage_scenario": rec["damage_scenario"],
        })
        out.append(row)
        by_name[(rec.get("id") or rec.get("name", "")).strip().upper()] = row

    treated = []
    for rec in threats:
        key = rec["asset"].strip().upper()
        asset = by_name.get(key)
        if asset is None:
            pending.append(f"row {rec['_row']} attacks '{rec['asset']}', which is not an asset <- project")
            continue
        impacts = {c: (rec.get(f"impact_{c}", "") or "negligible").strip().lower() for c in IMPACT_CATEGORIES}
        unknown = [v for v in impacts.values() if v not in IMPACT_ORDER]
        worst = max(impacts.values(), key=lambda v: IMPACT_ORDER.index(v)) if not unknown else None
        feasibility = rec["feasibility"].strip().lower()
        risk = matrix.get(worst or "", {}).get(feasibility)
        note = None
        if unknown:
            note = f"[PENDING: impact rating {', '.join(sorted(set(unknown)))} is not one of " \
                   f"{', '.join(IMPACT_ORDER)} <- project]"
        elif risk is None:
            note = f"[PENDING: risk for impact {worst} × feasibility {feasibility} is not in the " \
                   f"house matrix <- project]"
        safety_goal = rec.get("safety_goal", "").strip().upper()
        if impacts["safety"] != "negligible" and not safety_goal:
            note = (note or "") + f"\n[PENDING: safety impact {impacts['safety']} cites no safety goal <- project]"
        elif safety_goal and goals and safety_goal not in goals:
            note = (note or "") + f"\n[PENDING: {safety_goal} is not a safety goal <- project]"
        row = Row(id=rec.get("id") or None, prefix="TS", parent_of=asset, fields={
            "parent": "",                          # filled from the asset once ids are assigned
            "stride": rec["stride"],
            "attack_path": rec["attack_path"],
            "feasibility": feasibility,
            "impact": ", ".join(f"{c[0].upper()}={impacts[c]}" for c in IMPACT_CATEGORIES),
            **{f"impact_{c}": impacts[c] for c in IMPACT_CATEGORIES},
            "safety_goal": safety_goal,
            "risk": str(risk) if risk is not None else "",
            "risk_basis": f"impact {worst} × feasibility {feasibility} from the house matrix" if risk else "",
            "rationale": rec["rationale"],
            "treatment": rec["treatment"].strip().lower(),
        }, note=note)
        out.append(row)
        if row.fields["treatment"] in ("avoid", "reduce", "share"):
            treated.append(row)

    # Only what is genuinely outstanding: a goal already derived is not still owed, and a marker
    # that can never clear blocks the release for ever. Matching is by id, so a scenario whose id
    # this run assigns (rather than the table pinning it) counts as owed — claiming a goal exists
    # for an id that did not exist when the goals were written is the error worth avoiding.
    goals_wp = cfg.get("goals_work_product", "CSG")
    covered = {p for i in reg.generated.items(goals_wp) for p in i.refs("parent")} \
        if reg.generated.exists(goals_wp) else set()
    owed = [r for r in treated if from_base.canonical(r.id or "") not in covered]
    if owed:
        pending.append(f"cybersecurity goal derivation for {len(owed)} treated threat scenario(s) "
                       f"<- {cfg.get('goals_agent', 'cs-goals')}")
    return Result(rows=out, pending=pending)


DERIVED_REQ_COLUMNS = ["allocation", "behaviour", "verification"]
HW_DESIGN_COLUMNS = ["element", "part", "function", "implements"]
FMEDA_ITEM_COLUMNS = ["element", "mode", "lam_fit", "category"]


def generate_derived_requirements(cfg: dict, reg: Registers, spec: AgentSpec) -> Result:
    """Hardware (or software) safety requirements refining a technical safety concept item.

    Same shape as the technical requirements, one level down: the parent is the TSC allocation,
    and ASIL, element and the mechanism come from it rather than being restated here.
    """
    upstream = cfg.get("from", "TSC")
    if not reg.generated.exists(upstream):
        raise InputMissing(f"{upstream} has not been produced yet")
    allocations = {i.id: i for i in reg.generated.items(upstream)}
    rows = read_table(config.INPUT_DIR / cfg.get("input", "hardware-requirements.csv"), DERIVED_REQ_COLUMNS)

    out, pending, refined = [], [], set()
    for rec in rows:
        alloc_id = rec["allocation"].strip().upper()
        alloc = allocations.get(alloc_id)
        if alloc is None:
            pending.append(f"row {rec['_row']} refines {alloc_id or '(blank)'}, "
                           f"which is not in {upstream} <- project")
            continue
        refined.add(alloc_id)
        element = rec.get("element") or alloc.fields.get("element", "")
        sentence = f"The {element} shall {rec['behaviour']}"
        if rec.get("condition"):
            sentence += f" under {rec['condition']}"
        if rec.get("within"):
            sentence += f" within {rec['within']}"
        out.append(Row(id=rec.get("id") or None, fields={
            "parent": alloc_id,
            "asil": alloc.fields.get("asil", ""),
            "element": element,
            "sm": rec.get("sm") or alloc.fields.get("sm", ""),
            "text": sentence.rstrip(".") + ".",
            "verification": rec["verification"],
            "rationale": rec.get("rationale") or f"refines {alloc_id}",
        }))
    for alloc_id in sorted(set(allocations) - refined):
        pending.append(f"{alloc_id} has no {spec.work_product} row in "
                       f"{cfg.get('input', 'hardware-requirements.csv')} <- project")
    return Result(rows=out, pending=pending)


def generate_hardware_design(cfg: dict, reg: Registers, spec: AgentSpec) -> Result:
    """The design elements, each naming the requirement it implements."""
    upstream = cfg.get("from", "HSR")
    if not reg.generated.exists(upstream):
        raise InputMissing(f"{upstream} has not been produced yet")
    reqs = {i.id: i for i in reg.generated.items(upstream)}
    rows = read_table(config.INPUT_DIR / cfg.get("input", "hardware-design.csv"), HW_DESIGN_COLUMNS)

    out, pending, implemented = [], [], set()
    for rec in rows:
        req_id = rec["implements"].strip().upper()
        req = reqs.get(req_id)
        if req is None:
            pending.append(f"row {rec['_row']} implements {req_id or '(blank)'}, "
                           f"which is not in {upstream} <- project")
            continue
        implemented.add(req_id)
        out.append(Row(id=rec.get("id") or None, fields={
            "parent": req_id,
            "asil": req.fields.get("asil", ""),
            "element": rec["element"],
            "part": rec["part"],
            "function": rec["function"],
            "sm": rec.get("sm") or req.fields.get("sm", ""),
            "text": f"{rec['element']} ({rec['part']}): {rec['function']}.",
            "rationale": rec.get("rationale") or f"implements {req_id}",
        }))
    for req_id in sorted(set(reqs) - implemented):
        pending.append(f"{req_id} is not implemented by any element in "
                       f"{cfg.get('input', 'hardware-design.csv')} <- project")
    return Result(rows=out, pending=pending)


def generate_fmeda(cfg: dict, reg: Registers, spec: AgentSpec) -> Result:
    """One item per failure mode of the quantitative analysis, over the same CSV the metrics
    tool reads — so the table in metrics.md and the items here can never disagree.

    The ASIL targets are checked here too: a missed target becomes an item carrying
    `returns_to`, which is the checklist's own instruction and fires the feedback loop.
    """
    from ..tools import metrics
    path = config.INPUT_DIR / cfg.get("input", "fmeda-failure-modes.csv")
    rows = read_table(path, FMEDA_ITEM_COLUMNS)
    modes = metrics.load_csv(path)                      # the same parse the metrics tool performs
    asil = str(cfg.get("asil", "B")).upper()
    profile = cfg.get("mission_profile", "")

    out, pending = [], []
    if not profile:
        pending.append("mission profile for the quoted failure rates <- project")
    for rec, mode in zip(rows, modes):
        fields = {k: rec[k] for k in FMEDA_ITEM_COLUMNS}
        fields["category"] = mode.category
        fields["dc"] = rec.get("dc", "")
        fields["sm"] = rec.get("safety_mechanism", "")
        fields["source"] = rec.get("source", "")
        fields["mission_profile"] = profile
        note = None
        if not fields["source"]:
            note = f"[PENDING: source for the {rec['element']} {rec['mode']} failure rate <- project]"
        out.append(Row(id=rec.get("id") or None, fields=fields, note=note))

    for why in metrics.compute(modes).check(asil):      # the same targets `fusa metrics` reports
        out.append(Row(prefix=spec.prefixes[0], fields={
            "element": "item", "mode": "quantitative target not met", "classification": "finding",
            "text": why, "finding": "target_missed", "returns_to": cfg.get("returns_to", "sys-tsc"),
        }))
    return Result(rows=out, pending=pending)


TREATED = ("avoid", "reduce", "share")


def generate_cybersecurity_goals(cfg: dict, reg: Registers, spec: AgentSpec) -> Result:
    """One cybersecurity goal per treated threat scenario (ISO/SAE 21434 clause 15.10).

    Nothing new is decided here: which scenarios are treated, and how, was decided in the TARA.
    This states the goal that treatment implies and traces it back, closing the PENDING the
    TARA raises.
    """
    upstream = cfg.get("from", "TARA")
    if not reg.generated.exists(upstream):
        raise InputMissing(f"{upstream} has not been produced yet")
    items = {i.id: i for i in reg.generated.items(upstream)}
    threats = [i for i in items.values() if i.prefix == "TS"]

    out, pending = [], []
    for ts in threats:
        if (ts.fields.get("treatment") or "").lower() not in TREATED:
            continue                                   # a retained risk carries no goal
        asset = items.get(next(iter(ts.refs("parent")), ""))
        prop = asset.fields.get("property", "the affected property") if asset else "the affected property"
        name = (asset.fields.get("text") or asset.id) if asset else "the asset"
        out.append(Row(id=None, fields={
            "parent": ts.id,
            "risk": ts.fields.get("risk", ""),
            "treatment": ts.fields.get("treatment", ""),
            "asset": asset.id if asset else "",
            "safety_goal": ts.fields.get("safety_goal", ""),
            "text": f"The item shall protect the {prop} of {name.rstrip('.')} against "
                    f"{ts.fields.get('attack_path', 'the threat scenario')}.",
            "rationale": f"treatment '{ts.fields.get('treatment', '')}' of {ts.id} "
                         f"(risk {ts.fields.get('risk', '?')})",
        }))
    if not threats:
        pending.append(f"no threat scenarios in {upstream} <- cs-tara")
    return Result(rows=out, pending=pending)


def generate_closure(cfg: dict, reg: Registers, spec: AgentSpec) -> Result:
    """Analysis findings carried back into the concept (26262-9:8.4.9).

    Reads what the analyses already flagged — uncovered failure modes, missed quantitative
    targets — and records one closure item per finding, still pointing at the design owner.
    A closure work product with nothing in it is the honest outcome when nothing was flagged.
    """
    out, pending = [], []
    for wp in cfg.get("from", ["SYS-FMEA", "HW-FMEDA"]):
        if not reg.generated.exists(wp):
            pending.append(f"{wp} has not been produced yet <- project")
            continue
        for item in reg.generated.items(wp):
            finding = item.fields.get("finding")
            if not finding:
                continue
            out.append(Row(id=None, fields={
                "parent": item.id,
                "source": wp,
                "finding": finding,
                "element": item.fields.get("element", ""),
                "violated_sg": item.fields.get("violated_sg", ""),
                "text": item.fields.get("text") or
                        f"{item.fields.get('failure_mode', finding)} on {item.fields.get('element', 'the item')} "
                        f"is {finding} and needs a concept change.",
                "returns_to": item.fields.get("returns_to", cfg.get("returns_to", "sys-tsc")),
                "status": "open",
            }))
    return Result(rows=out, pending=pending,
                  intro="Every finding the analyses raised, carried back to the concept that owns it. "
                        "Derived from the analyses themselves, so it cannot omit one.\n"
                  if out else "The analyses raised no findings to carry back.\n")


def generate_test_spec(cfg: dict, reg: Registers, spec: AgentSpec) -> Result:
    """One test case per requirement, from the verification method the requirement already names."""
    out, pending = [], []
    for wp in cfg.get("from", ["TSR", "HSR"]):
        if not reg.generated.exists(wp):
            pending.append(f"{wp} has not been produced yet <- project")
            continue
        for req in reg.generated.items(wp):
            method = req.fields.get("verification", "")
            if not method:
                pending.append(f"{req.id} ({wp}) names no verification method <- project")
                continue
            out.append(Row(id=None, fields={
                "parent": req.id,
                "asil": req.fields.get("asil", ""),
                "element": req.fields.get("element", ""),
                "method": method,
                "sm": req.fields.get("sm", ""),
                "text": f"Verify that {req.fields.get('text', req.id).rstrip('.')} — by {method}.",
                "status": "specified",
            }))
    return Result(rows=out, pending=pending)


TRACE_CHAIN = ["SADS", "TSR", "TSC", "HSR", "HW-DESIGN", "TEST-SPEC"]


def generate_traceability(cfg: dict, reg: Registers, spec: AgentSpec) -> Result:
    """The traceability matrix, derived from the identifiers rather than maintained by hand.

    One item per safety goal carrying its chain down the V, and the chain is walked over
    `parent:` links, so a break in it shows up as an empty level rather than as a claim.
    """
    chain = cfg.get("chain", TRACE_CHAIN)
    present = [wp for wp in chain if reg.generated.exists(wp)]
    children: dict[str, list] = {}
    for wp in present:
        for item in reg.generated.items(wp):
            for parent in item.refs("parent"):
                children.setdefault(parent, []).append((wp, item.id))

    root = cfg.get("root", "SADS")
    if root not in present:
        raise InputMissing(f"{root} has not been produced yet")
    goals = [i for i in reg.generated.items(root) if i.prefix == cfg.get("root_prefix", "SG")]

    out, pending, rows = [], [], []
    for goal in goals:
        levels: dict[str, list[str]] = {}
        frontier = [goal.id]
        while frontier:
            nxt = []
            for node in frontier:
                for wp, child in children.get(node, []):
                    levels.setdefault(wp, []).append(child)
                    nxt.append(child)
            frontier = nxt
        broken = [wp for wp in chain[1:] if wp in present and not levels.get(wp)]
        out.append(Row(id=None, fields={
            "parent": goal.id,
            "asil": goal.fields.get("asil", ""),
            **{wp.lower().replace("-", "_"): ", ".join(dict.fromkeys(levels.get(wp, []))) for wp in chain[1:]},
            "complete": "no" if broken else "yes",
            "text": f"Trace for {goal.id}: " + " → ".join(
                f"{wp} ({len(dict.fromkeys(levels.get(wp, [])))})" for wp in chain[1:] if wp in present),
        }, note=f"[PENDING: {goal.id} has no {', '.join(broken)} item <- project]" if broken else None))
        rows.append((goal.id, goal.fields.get("asil", ""), levels, broken))

    header = "| Safety goal | ASIL | " + " | ".join(wp for wp in chain[1:] if wp in present) + " | complete |"
    sep = "|---" * (len([wp for wp in chain[1:] if wp in present]) + 3) + "|"
    table = [header, sep] + [
        f"| {gid} | {asil} | " + " | ".join(
            ", ".join(dict.fromkeys(lv.get(wp, []))) or "—" for wp in chain[1:] if wp in present)
        + f" | {'no' if br else 'yes'} |" for gid, asil, lv, br in rows]
    return Result(rows=out, pending=pending,
                  intro="Derived from the `parent:` links in the work products themselves, never "
                        "maintained by hand — a break in the chain shows as an empty cell.\n\n"
                        + "\n".join(table) + "\n")


GENERATORS = {"hara": generate_hara, "safety-goals": generate_safety_goals,
              "safety-mechanisms": generate_safety_mechanisms,
              "technical-requirements": generate_technical_requirements,
              "safety-concept": generate_safety_concept,
              "fmea": generate_fmea, "tara": generate_tara,
              "derived-requirements": generate_derived_requirements,
              "hardware-design": generate_hardware_design,
              "fmeda": generate_fmeda,
              "cybersecurity-goals": generate_cybersecurity_goals,
              "closure": generate_closure,
              "test-spec": generate_test_spec,
              "traceability": generate_traceability}
