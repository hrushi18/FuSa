"""Hardware architectural metrics (SPFM, LFM) and PMHF from a failure-mode table.

Deterministic where it counts: the model classifies failure modes and proposes
diagnostic coverage; this module does the arithmetic. Formulas follow the
standard definitions; targets are the commonly published ASIL thresholds and
should be confirmed against the licensed norm text in the clause register.

Input rows (one per failure mode of a safety-related element):
    lam           failure rate in FIT (1e-9/h)
    category      SR   — can violate the safety goal on its own; split by dc into RF (1-dc) and MPF_D (dc);
                         dc = 0 makes it a single-point fault (SPF)
                  MPF  — violates the safety goal only with a second fault; split by dc into MPF_L (1-dc) and MPF_D (dc)
                  SAFE — cannot contribute to a safety-goal violation
                  (pre-split rows SPF | RF | MPF_L | MPF_D | MPF_P are also accepted verbatim)
    dc            diagnostic coverage 0..1 claimed against `safety_mechanism` (an SM id)
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SPLIT_CATEGORIES = {"SR", "MPF"}
FINAL_CATEGORIES = {"SPF", "RF", "MPF_L", "MPF_D", "MPF_P", "SAFE"}
CATEGORIES = SPLIT_CATEGORIES | FINAL_CATEGORIES

TARGETS = {
    #  ASIL: (SPFM min, LFM min, PMHF max FIT)
    "B": (0.90, 0.60, 100.0),
    "C": (0.97, 0.80, 100.0),
    "D": (0.99, 0.90, 10.0),
}


@dataclass
class FailureMode:
    element: str
    mode: str
    lam: float
    category: str
    dc: float = 0.0
    safety_mechanism: str = ""

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"{self.element}/{self.mode}: unknown category {self.category!r}")
        if not 0.0 <= self.dc <= 1.0:
            raise ValueError(f"{self.element}/{self.mode}: dc must be 0..1")


@dataclass
class Metrics:
    lam_sr: float       # total safety-related
    lam_spf: float
    lam_rf: float
    lam_mpf_l: float
    lam_mpf_d: float
    lam_mpf_p: float
    lam_safe: float
    spfm: float | None
    lfm: float | None
    pmhf_fit: float

    def check(self, asil: str) -> list[str]:
        """Return human-readable target violations (empty list = all met)."""
        if asil not in TARGETS:
            return [f"no quantitative targets for ASIL {asil}"]
        spfm_t, lfm_t, pmhf_t = TARGETS[asil]
        out = []
        if self.spfm is not None and self.spfm < spfm_t:
            out.append(f"SPFM {self.spfm:.2%} < {spfm_t:.0%} required for ASIL {asil}")
        if self.lfm is not None and self.lfm < lfm_t:
            out.append(f"LFM {self.lfm:.2%} < {lfm_t:.0%} required for ASIL {asil}")
        if self.pmhf_fit >= pmhf_t:
            out.append(f"PMHF {self.pmhf_fit:.2f} FIT >= {pmhf_t:.0f} FIT limit for ASIL {asil}")
        return out


def split(r: FailureMode) -> dict[str, float]:
    """Deterministic Annex-C style classification of one row into final categories."""
    if r.category == "SR":
        if r.dc == 0.0:
            return {"SPF": r.lam}
        return {"RF": r.lam * (1 - r.dc), "MPF_D": r.lam * r.dc}
    if r.category == "MPF":
        return {"MPF_L": r.lam * (1 - r.dc), "MPF_D": r.lam * r.dc}
    return {r.category: r.lam}


def compute(rows: Iterable[FailureMode]) -> Metrics:
    s = {c: 0.0 for c in FINAL_CATEGORIES}
    for r in rows:
        for cat, lam in split(r).items():
            s[cat] += lam
    lam_sr = sum(s.values())
    non_safe = lam_sr - s["SAFE"]
    spfm = None if non_safe == 0 else 1.0 - (s["SPF"] + s["RF"]) / non_safe
    lfm_den = non_safe - s["SPF"] - s["RF"]
    lfm = None if lfm_den <= 0 else 1.0 - s["MPF_L"] / lfm_den
    # Simplified PMHF: single-point + residual dominate; latent dual-point faults are
    # added as their own contribution (conservative). Refine with exposure time if needed.
    pmhf = s["SPF"] + s["RF"] + s["MPF_L"]
    return Metrics(lam_sr, s["SPF"], s["RF"], s["MPF_L"], s["MPF_D"], s["MPF_P"], s["SAFE"], spfm, lfm, pmhf)


def load_csv(path: str | Path) -> list[FailureMode]:
    rows: list[FailureMode] = []
    with open(path, newline="", encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            rows.append(FailureMode(
                element=rec["element"], mode=rec["mode"], lam=float(rec["lam_fit"]),
                category=rec["category"].strip().upper(),
                dc=float(rec.get("dc") or 0.0),
                safety_mechanism=rec.get("safety_mechanism", ""),
            ))
    return rows


def render(m: Metrics, asil: str) -> str:
    lines = [
        "| Metric | Value |", "|---|---|",
        f"| λ safety-related | {m.lam_sr:.2f} FIT |",
        f"| λ SPF | {m.lam_spf:.2f} FIT |",
        f"| λ RF | {m.lam_rf:.2f} FIT |",
        f"| λ MPF latent | {m.lam_mpf_l:.2f} FIT |",
        f"| SPFM | {'n/a' if m.spfm is None else f'{m.spfm:.2%}'} |",
        f"| LFM | {'n/a' if m.lfm is None else f'{m.lfm:.2%}'} |",
        f"| PMHF | {m.pmhf_fit:.2f} FIT |",
    ]
    viol = m.check(asil)
    lines.append("")
    lines.append("**Targets met.**" if not viol else "**Target violations:** " + "; ".join(viol))
    return "\n".join(lines)
