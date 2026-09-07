"""fusa pdf — the validation report as a paginated PDF.

Same document as `report.render_html`, section for section, so the file an assessor is
handed and the page an engineer reads on screen say the same thing. Adds one section the
HTML does not have: a summary block counting what wrote each work product, because a PDF
is read once and away from the tool, and "how much of this did a model write" is the first
thing its reader needs.

Renders from the ValidationReport model — never from the HTML — so it needs no browser and
works from the CLI and CI. reportlab is an optional extra; the import is deferred to
`render_pdf` so importing this module never fails.
"""
from __future__ import annotations

from .report import BLOCKING_SEVERITIES, EVIDENCE_HEADER, ValidationReport, _evidence_rows, md_rows

INSTALL_HINT = "PDF export needs reportlab — pip install 'fusa-agents[ui]'"

OK_GREEN = "#1d9a4e"
NOT_RED = "#c0392b"
INK = "#1c2330"
DIM = "#5b6b80"
LINE = "#d8dee8"
HEAD_BG = "#f2f5fa"
MACHINE = "#1d7a72"        # table / tool — reproducible, the teal of the dashboard chips
MODEL = "#6b46c1"          # model — the purple, everywhere it appears

WRITTEN_BY = [("table", "Written from your tables"),
              ("tool", "Read from an analyser"),
              ("model", "Written by a model")]


def _require_reportlab():
    try:
        import reportlab  # noqa: F401
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(INSTALL_HINT) from e


def _meta_line(rep: ValidationReport) -> str:
    parts = [f"generated {rep.generated}", f"ASIL {rep.asil}",
             f"authoring {rep.author_mode}", f"review {rep.reviewer_mode}"]
    if rep.author_mode == "model" or rep.reviewer_mode == "model":
        parts.append(f"model {rep.model}")           # never named when no model ran
    if rep.dry_run:
        parts.append("dry run")
    return " · ".join(parts)


def _summary_rows(rep: ValidationReport) -> list[list[str]]:
    """What a reader away from the dashboard needs before reading anything else."""
    wps = rep.work_products
    findings = [f for a in wps for f in a.findings]
    rows = [["Work products", str(len(wps))],
            ["Release-clean", str(sum(1 for a in wps if a.ok))],
            ["Blocked", str(sum(1 for a in wps if not a.ok))]]
    for kind, label in WRITTEN_BY:
        rows.append([label, str(sum(1 for a in wps if a.written_by == kind))])
    rows += [["Checklist decided by", "a language model" if rep.reviewer_mode == "model" else "rules"],
             ["Open blocker/major findings",
              str(sum(1 for f in findings if f.severity in BLOCKING_SEVERITIES))],
             ["Unresolved [PENDING] markers", str(sum(a.pending_count for a in wps))]]
    return rows


def render_pdf(rep: ValidationReport) -> bytes:
    """The report as PDF bytes. Raises ModuleNotFoundError with an install hint if the
    optional reportlab extra is missing."""
    _require_reportlab()
    import io

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (ListFlowable, ListItem, LongTable, Paragraph,
                                    SimpleDocTemplate, Spacer, TableStyle)

    ok = rep.verdict == "RELEASABLE"
    base = getSampleStyleSheet()
    S = {
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=16, leading=20,
                             textColor=colors.HexColor(INK), spaceAfter=2),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=11, leading=14,
                             textColor=colors.HexColor(INK), spaceBefore=14, spaceAfter=6),
        "meta": ParagraphStyle("meta", parent=base["BodyText"], fontSize=8, leading=11,
                               textColor=colors.HexColor(DIM), spaceAfter=10),
        "basis": ParagraphStyle("basis", parent=base["BodyText"], fontSize=9, leading=13,
                                textColor=colors.HexColor(INK), alignment=TA_LEFT,
                                borderPadding=(6, 8, 6, 8), leftIndent=3,
                                backColor=colors.HexColor("#f7f4fd" if rep.author_mode == "model"
                                                          or rep.reviewer_mode == "model"
                                                          else "#f3faf9")),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontSize=8.5, leading=12,
                               textColor=colors.HexColor(INK)),
        "cell": ParagraphStyle("cell", parent=base["BodyText"], fontSize=7.2, leading=9,
                               textColor=colors.HexColor(INK)),
        "cellhead": ParagraphStyle("cellhead", parent=base["BodyText"], fontSize=7.2, leading=9,
                                   fontName="Helvetica-Bold", textColor=colors.HexColor(INK)),
    }

    def para(text: str, style="cell", colour: str | None = None) -> Paragraph:
        safe = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return Paragraph(f"<font color='{colour}'>{safe}</font>" if colour else safe, S[style])

    def grid(data, widths, head_repeat=True, extra=()) -> LongTable:
        t = LongTable(data, colWidths=widths, repeatRows=1 if head_repeat else 0)
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(HEAD_BG)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            *extra,
        ]))
        return t

    def md_grid(md: str, width: float) -> LongTable | Paragraph:
        rows = md_rows(md)
        if not rows:
            return para(md, "body")
        cols = max(len(r) for r in rows)
        rows = [r + [""] * (cols - len(r)) for r in rows]
        data = [[para(c, "cellhead" if i == 0 else "cell") for c in r] for i, r in enumerate(rows)]
        return grid(data, [width / cols] * cols)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"FuSa Validation Report — {rep.verdict}", author="fusa-agents")
    width = doc.width

    story: list = [
        Paragraph(f"FuSa Validation Report &nbsp;"
                  f"<font color='{OK_GREEN if ok else NOT_RED}'>{rep.verdict}</font>", S["h1"]),
        Paragraph(_meta_line(rep), S["meta"]),
        Paragraph(rep.basis, S["basis"]),
        Paragraph("Summary", S["h2"]),
        grid([[para(k, "cell"), para(v, "cellhead")] for k, v in _summary_rows(rep)],
             [width * 0.62, width * 0.38], head_repeat=False,
             extra=[("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT")]),
    ]

    if rep.reasons:
        story += [Paragraph("Release blockers", S["h2"]),
                  ListFlowable([ListItem(para(r, "body"), leftIndent=12) for r in rep.reasons],
                               bulletType="bullet", start="•", leftIndent=10)]

    ev_widths = [0.13, 0.13, 0.09, 0.11, 0.08, 0.08, 0.12, 0.1, 0.16]
    ev = [[para(c, "cellhead") for c in EVIDENCE_HEADER]]
    for row in _evidence_rows(rep):
        # The colour goes on the paragraph, not into a TableStyle TEXTCOLOR: a cell holding a
        # flowable paints itself, so the style command never reaches it and the two columns
        # this report is built around came out plain ink.
        cells = [para(c) for c in row]
        cells[2] = para(row[2], colour=MODEL if row[2] == "MODEL" else MACHINE)
        cells[8] = para(row[8], colour=OK_GREEN if row[8] == "OK" else NOT_RED)
        ev.append(cells)
    story += [Paragraph("Work-product evidence", S["h2"]),
              grid(ev, [width * w for w in ev_widths])]

    findings = [(a.work_product, f) for a in rep.work_products for f in a.findings]
    if findings:
        story += [Paragraph("Review findings", S["h2"]),
                  ListFlowable([ListItem(para(
                      f"{wp} {f.id} ({f.severity}): {f.description}"
                      + (f" → returns to {f.returns_to}" if f.returns_to else ""), "body"),
                      leftIndent=12) for wp, f in findings],
                      bulletType="bullet", start="•", leftIndent=10)]

    pending = [(a.work_product, p) for a in rep.work_products for p in a.pending]
    if pending:
        story += [Paragraph("Pending markers", S["h2"]),
                  ListFlowable([ListItem(para(f"{wp}: {p}", "body"), leftIndent=12)
                                for wp, p in pending],
                               bulletType="bullet", start="•", leftIndent=10)]

    if rep.metrics_table:
        story += [Paragraph(f"HW architectural metrics (ASIL {rep.asil})", S["h2"]),
                  md_grid(rep.metrics_table, width)]
        tail = rep.metrics_table.splitlines()[-1].replace("**", "")
        if tail and not tail.strip().startswith("|"):
            story += [Spacer(1, 4), para(tail, "body")]

    if rep.aspice:
        story += [Paragraph("ASPICE base-practice coverage", S["h2"]), md_grid(rep.aspice, width)]

    footer = (f"FuSa Validation Report · {rep.verdict} · {rep.author_mode} authoring · "
              f"{rep.reviewer_mode} review · {rep.generated}")

    def decorate(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor(DIM))
        canvas.drawString(doc_.leftMargin, 10 * mm, footer)
        canvas.drawRightString(A4[0] - doc_.rightMargin, 10 * mm, f"page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buf.getvalue()
