"""fusa report — deterministic release validation over the status board.

Aggregates what the chain already produced — gate results, review verdicts,
PENDING markers, HW metrics, ASPICE coverage — into one release assessment.
Reads existing records only; never calls the model. A work product is
release-clean when it is reviewed, its gate passed, it has no PENDING markers
and no open blocker/major finding; HW metrics must meet the ASIL targets.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .models import Finding, Status

REPORT_NAME = "VALIDATION-REPORT.md"
BLOCKING_SEVERITIES = {"blocker", "major"}


class Assessment(BaseModel):
    work_product: str
    agent: str
    status: str
    ok: bool
    reasons: list[str] = Field(default_factory=list)
    gate_errors: list[str] = Field(default_factory=list)
    gate_warnings: list[str] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)
    pending_count: int = 0
    review_verdict: str | None = None
    findings: list[Finding] = Field(default_factory=list)


class ValidationReport(BaseModel):
    verdict: Literal["RELEASABLE", "NOT_RELEASABLE"]
    asil: str
    generated: str
    model: str
    dry_run: bool
    reasons: list[str] = Field(default_factory=list)
    work_products: list[Assessment] = Field(default_factory=list)
    metrics_violations: list[str] = Field(default_factory=list)
    metrics_table: str | None = None
    aspice: str | None = None


def _assess(spec, rec) -> Assessment:
    a = Assessment(work_product=spec.work_product, agent=spec.id, ok=True,
                   status=(rec.status.value if rec else Status.NOT_STARTED.value))
    if rec is None or rec.status is not Status.REVIEWED:
        a.reasons.append(f"status is {a.status}, expected reviewed")
    if rec and rec.gate:
        a.gate_errors, a.gate_warnings, a.pending = rec.gate.errors, rec.gate.warnings, rec.gate.pending
        if not rec.gate.passed:
            a.reasons.append("gate failed: " + "; ".join(rec.gate.errors))
    if rec and rec.pending_count:
        a.pending_count = rec.pending_count
        a.reasons.append(f"{rec.pending_count} unresolved [PENDING] marker(s)")
    if rec and rec.review:
        a.review_verdict, a.findings = rec.review.verdict, rec.review.findings
        for f in rec.review.findings:
            if f.severity in BLOCKING_SEVERITIES:
                a.reasons.append(f"open {f.severity} finding {f.id}: {f.description}")
    a.ok = not a.reasons
    return a


def validate(orch, asil: str = "B") -> ValidationReport:
    assessments = [_assess(s, orch.reg.process.get(s.work_product)) for s in orch.plan()]
    reasons = [f"{a.work_product}: {r}" for a in assessments for r in a.reasons]

    violations: list[str] = []
    table = None
    csv_path = orch.root / "input" / "fmeda-failure-modes.csv"
    if csv_path.exists():
        from .tools import metrics
        m = metrics.compute(metrics.load_csv(csv_path))
        table = metrics.render(m, asil)
        violations = m.check(asil)
        reasons += [f"HW-FMEDA metrics: {v}" for v in violations]

    return ValidationReport(
        verdict="RELEASABLE" if not reasons else "NOT_RELEASABLE",
        asil=asil,
        generated=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=orch.llm.model, dry_run=orch.llm.dry_run,
        reasons=reasons, work_products=assessments,
        metrics_violations=violations, metrics_table=table,
        aspice=orch.aspice())


EVIDENCE_HEADER = ["Work product", "Agent", "Status", "Gate", "Pending", "Review", "Open findings", "Verdict"]


def _evidence_rows(rep: ValidationReport) -> list[list[str]]:
    rows = []
    for a in rep.work_products:
        gate = "—" if a.status == "not_started" else ("failed" if a.gate_errors else "passed")
        open_f = sum(f.severity in BLOCKING_SEVERITIES for f in a.findings)
        rows.append([a.work_product, a.agent, a.status, gate, str(a.pending_count),
                     a.review_verdict or "—", str(open_f), "OK" if a.ok else "BLOCKED"])
    return rows


def render_markdown(rep: ValidationReport) -> str:
    lines = [
        "---", "id: VALIDATION-REPORT", f"generated: {rep.generated}",
        f"model: {rep.model}", f"dry_run: {str(rep.dry_run).lower()}", f"asil: {rep.asil}", "---",
        "", f"# FuSa Validation Report — **{rep.verdict}**", "",
    ]
    if rep.reasons:
        lines += ["## Release blockers", ""] + [f"- {r}" for r in rep.reasons] + [""]
    lines += ["## Work-product evidence", "",
              "| " + " | ".join(EVIDENCE_HEADER) + " |",
              "|" + "---|" * len(EVIDENCE_HEADER)]
    lines += ["| " + " | ".join(r) + " |" for r in _evidence_rows(rep)]
    findings = [(a.work_product, f) for a in rep.work_products for f in a.findings]
    if findings:
        lines += ["", "## Review findings", ""]
        lines += [f"- {wp} {f.id} ({f.severity}): {f.description}"
                  + (f" -> returns to {f.returns_to}" if f.returns_to else "")
                  for wp, f in findings]
    pending = [(a.work_product, p) for a in rep.work_products for p in a.pending]
    if pending:
        lines += ["", "## Pending markers", ""] + [f"- {wp}: {p}" for wp, p in pending]
    if rep.metrics_table:
        lines += ["", f"## HW architectural metrics (ASIL {rep.asil})", "", rep.metrics_table]
    if rep.aspice:
        lines += ["", "## ASPICE base-practice coverage", "", rep.aspice]
    return "\n".join(lines) + "\n"


def write_report(orch, rep: ValidationReport) -> Path:
    path = orch.root / "_generated" / REPORT_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(rep), encoding="utf-8")
    return path


def render_html(rep: ValidationReport) -> str:
    """Self-contained, print-styled rendering (browser print -> PDF)."""
    ok = rep.verdict == "RELEASABLE"

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def md_table(md: str) -> str:
        rows = [r for r in md.splitlines() if r.strip().startswith("|")]
        out = ["<table>"]
        for i, r in enumerate(rows):
            if set(r.replace("|", "").strip()) <= {"-", " ", ":"}:
                continue
            tag = "th" if i == 0 else "td"
            cells = [c.strip() for c in r.strip().strip("|").split("|")]
            out.append("<tr>" + "".join(f"<{tag}>{esc(c)}</{tag}>" for c in cells) + "</tr>")
        out.append("</table>")
        return "\n".join(out)

    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<title>FuSa Validation Report</title><style>",
        "body{font:14px/1.5 -apple-system,'Segoe UI',sans-serif;color:#1c2330;max-width:60rem;margin:2rem auto;padding:0 1rem}",
        "h1{font-size:1.4rem}h2{font-size:1.05rem;margin-top:2rem;border-bottom:1px solid #d8dee8;padding-bottom:.3rem}",
        "table{border-collapse:collapse;width:100%;font-size:.85rem}th,td{border:1px solid #d8dee8;padding:.35rem .5rem;text-align:left}",
        "th{background:#f2f5fa}.badge{display:inline-block;padding:.2rem .7rem;border-radius:4px;color:#fff;font-weight:600}",
        f".badge{{background:{'#1d9a4e' if ok else '#c0392b'}}}",
        "ul{padding-left:1.2rem}@media print{body{margin:0}}</style></head><body>",
        f"<h1>FuSa Validation Report <span class='badge'>{rep.verdict}</span></h1>",
        f"<p>generated {esc(rep.generated)} · model {esc(rep.model)} · dry-run {str(rep.dry_run).lower()} · ASIL {esc(rep.asil)}</p>",
    ]
    if rep.reasons:
        parts += ["<h2>Release blockers</h2><ul>"] + [f"<li>{esc(r)}</li>" for r in rep.reasons] + ["</ul>"]
    parts.append("<h2>Work-product evidence</h2><table>")
    parts.append("<tr>" + "".join(f"<th>{esc(c)}</th>" for c in EVIDENCE_HEADER) + "</tr>")
    parts += ["<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>" for row in _evidence_rows(rep)]
    parts.append("</table>")
    if rep.metrics_table:
        parts += [f"<h2>HW architectural metrics (ASIL {esc(rep.asil)})</h2>", md_table(rep.metrics_table)]
        tail = rep.metrics_table.splitlines()[-1]
        parts.append(f"<p>{esc(tail.replace('**', ''))}</p>")
    if rep.aspice:
        parts += ["<h2>ASPICE base-practice coverage</h2>", md_table(rep.aspice)]
    parts.append("</body></html>")
    return "\n".join(parts)
