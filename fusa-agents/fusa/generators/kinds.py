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


GENERATORS = {"hara": generate_hara, "safety-goals": generate_safety_goals}
