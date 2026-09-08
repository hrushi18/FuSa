"""What the interactive tools need from the project, and nothing they could compute themselves.

The ASIL calculator is the reason this module exists. It performs no determination of its own:
it calls the same `determine_asil` the HARA generator calls, over the same table the engineer
transcribed from their licensed standard. A learner is therefore taught the mapping their own
chain applies, and an unfilled cell says so instead of guessing.
"""
from __future__ import annotations

from ..generators.kinds import ASIL_TABLE_FILE, determine_asil, load_asil_table

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
