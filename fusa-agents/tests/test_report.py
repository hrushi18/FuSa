import re
import time

import pytest
from fastapi.testclient import TestClient

from fusa.models import Finding, GateResult, ReviewVerdict, Status


@pytest.fixture
def orch(workspace):
    from fusa.orchestrator import Orchestrator
    return Orchestrator(root=workspace, dry_run=True)


def mark_all_reviewed(orch):
    """Put every planned work product into the release-clean state."""
    for s in orch.plan():
        orch.reg.process.update(
            s.work_product, s.id, status=Status.REVIEWED, pending_count=0,
            gate=GateResult(work_product=s.work_product, passed=True),
            review=ReviewVerdict(work_product=s.work_product, verdict="approved"))


def test_all_reviewed_chain_is_releasable(orch):
    from fusa.report import validate
    mark_all_reviewed(orch)
    rep = validate(orch)
    assert rep.verdict == "RELEASABLE"
    assert rep.reasons == []
    assert all(a.ok for a in rep.work_products)


def test_not_started_work_product_blocks_release(orch):
    from fusa.report import validate
    rep = validate(orch)
    assert rep.verdict == "NOT_RELEASABLE"
    assert any("SADS" in r and "not_started" in r for r in rep.reasons)


def test_pending_markers_block_release(orch):
    from fusa.report import validate
    mark_all_reviewed(orch)
    orch.reg.process.update("TSR", "sys-tsr", pending_count=2)
    rep = validate(orch)
    assert rep.verdict == "NOT_RELEASABLE"
    assert any("TSR" in r and "2" in r and "PENDING" in r for r in rep.reasons)


def test_gate_errors_block_release(orch):
    from fusa.report import validate
    mark_all_reviewed(orch)
    orch.reg.process.update("TSC", "sys-tsc", gate=GateResult(
        work_product="TSC", passed=False, errors=["TSC-001 cites undefined SM-999"]))
    rep = validate(orch)
    assert rep.verdict == "NOT_RELEASABLE"
    assert any("TSC" in r and "SM-999" in r for r in rep.reasons)


def test_open_major_finding_blocks_release(orch):
    from fusa.report import validate
    mark_all_reviewed(orch)
    orch.reg.process.update("TARA", "cs-tara", review=ReviewVerdict(
        work_product="TARA", verdict="approved",
        findings=[Finding(id="F-07", severity="major", description="threat scenario TS-3 has no risk treatment")]))
    rep = validate(orch)
    assert rep.verdict == "NOT_RELEASABLE"
    assert any("TARA" in r and "F-07" in r for r in rep.reasons)


def test_minor_findings_do_not_block_release(orch):
    from fusa.report import validate
    mark_all_reviewed(orch)
    orch.reg.process.update("TSR", "sys-tsr", review=ReviewVerdict(
        work_product="TSR", verdict="approved",
        findings=[Finding(id="F-01", severity="minor", description="typo in TSR-002")]))
    assert validate(orch).verdict == "RELEASABLE"


def test_metric_target_violations_block_release(orch):
    from fusa.report import validate
    mark_all_reviewed(orch)
    rep = validate(orch, asil="D")            # sample FMEDA meets ASIL B, not D
    assert rep.metrics_violations
    assert rep.verdict == "NOT_RELEASABLE"


def test_markdown_report_written(orch, workspace):
    from fusa.report import validate, write_report
    mark_all_reviewed(orch)
    path = write_report(orch, validate(orch))
    assert path == workspace / "_generated" / "VALIDATION-REPORT.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "RELEASABLE" in text
    assert "| Work product |" in text


# ---- dashboard endpoints ----------------------------------------------------

@pytest.fixture
def client(workspace):
    from fusa.ui.server import create_app
    app = create_app(root=workspace, dry_run=True)
    with TestClient(app) as c:
        yield c


def test_api_report_returns_live_verdict(client):
    rep = client.get("/api/report").json()
    assert rep["verdict"] == "NOT_RELEASABLE"
    assert rep["work_products"]


def test_post_report_writes_markdown(client, workspace):
    r = client.post("/api/report")
    assert r.status_code == 200
    assert (workspace / "_generated" / "VALIDATION-REPORT.md").exists()
    assert r.json()["markdown_path"].endswith("VALIDATION-REPORT.md")


def test_report_page_serves_printable_html(client):
    r = client.get("/report")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Validation Report" in r.text


def test_dashboard_has_validation_panel(client):
    html = client.get("/").text
    assert 'id="verdict"' in html                 # live release-verdict badge
    assert "/report" in html                      # opens the printable report


# ---- CLI --------------------------------------------------------------------

def test_cli_report_exit_code_reflects_verdict(workspace, capsys):
    import fusa.cli
    assert fusa.cli.main(["--dry-run", "report"]) == 1          # nothing run yet
    out = capsys.readouterr().out
    assert "NOT_RELEASABLE" in out
    assert (workspace / "_generated" / "VALIDATION-REPORT.md").exists()


# ---- what an assessor needs first: how much of this a model wrote ----------

import pytest


@pytest.mark.parametrize("author,reviewer,must_say,must_not_say", [
    ("deterministic", "rules",  "No language model produced or judged", "marked MODEL"),
    ("model",         "model",  "every verdict here, are a language model's judgement", None),
    ("deterministic", "model",  "No work product was written by a language model", "marked MODEL"),
    ("model",         "rules",  "checklist was executed as rules", None),
])
def test_the_report_states_its_basis_accurately_for_the_run(workspace, author, reviewer,
                                                            must_say, must_not_say):
    """Naming model-written work products when there are none is the same misdirection as
    crediting a model that never ran."""
    from fusa.orchestrator import Orchestrator
    from fusa.report import validate
    rep = validate(Orchestrator(root=workspace, dry_run=True, author=author, reviewer=reviewer))
    assert must_say in rep.basis
    if must_not_say:
        assert must_not_say not in rep.basis
    assert rep.author_mode == author and rep.reviewer_mode == reviewer


def test_the_report_does_not_credit_a_model_that_never_ran(workspace):
    from fusa.orchestrator import Orchestrator
    from fusa.report import render_html, render_markdown, validate
    rep = validate(Orchestrator(root=workspace, dry_run=True,
                                author="deterministic", reviewer="rules"))
    assert "model: none" in render_markdown(rep)
    assert rep.model not in render_html(rep)          # the provider is not named at all


def test_every_evidence_row_says_what_wrote_it(workspace):
    from fusa.orchestrator import Orchestrator
    from fusa.report import EVIDENCE_HEADER, _evidence_rows, validate
    o = Orchestrator(root=workspace, dry_run=True, author="deterministic", reviewer="rules")
    rep = validate(o)
    assert EVIDENCE_HEADER[2] == "Written by"
    kinds = {row[2] for row in _evidence_rows(rep)}
    assert kinds and kinds <= {"TABLE", "TOOL", "MODEL"}
    assert "MODEL" not in kinds                       # nothing in this run was written by one


def test_the_printable_report_marks_model_written_rows(workspace):
    from fusa.orchestrator import Orchestrator
    from fusa.report import render_html, validate
    html = render_html(validate(Orchestrator(root=workspace, dry_run=True,
                                             author="model", reviewer="model")))
    assert "p-model" in html and "class='basis mixed'" in html


# ---- PDF export -------------------------------------------------------------

def test_md_rows_drops_the_separator_and_keeps_the_cells():
    from fusa.report import md_rows
    md = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
    assert md_rows(md) == [["A", "B"], ["1", "2"], ["3", "4"]]


reportlab = pytest.importorskip("reportlab")       # the PDF export is an optional extra
pypdf = pytest.importorskip("pypdf")


def pdf_pages(data: bytes) -> list[str]:
    from io import BytesIO
    from pypdf import PdfReader
    return [p.extract_text() or "" for p in PdfReader(BytesIO(data)).pages]


def pdf_text(data: bytes) -> str:
    return "\n".join(pdf_pages(data))


def _hex(*rgb) -> str:
    return "#" + "".join(f"{round(float(v) * 255):02x}" for v in rgb)


PAINTED = re.compile(r"([\d.]+) ([\d.]+) ([\d.]+) rg|/(F\d+) [\d.]+ Tf|\((.*?)(?<!\\)\) Tj")
FILLED = re.compile(r"([\d.]+) ([\d.]+) ([\d.]+) rg\s+n [-\d.\s]+ re f\*")


def pdf_drawn(data: bytes) -> list[tuple[str, str, str]]:
    """(text, font, colour) for every string the PDF paints, in the order it paints them.

    Colour and weight are what this document has that a CSV row does not, and neither
    survives text extraction — so read them off the content stream a viewer actually paints.
    """
    from io import BytesIO
    from pypdf import PdfReader
    out = []
    for page in PdfReader(BytesIO(data)).pages:
        fonts = {k: str(v["/BaseFont"]).lstrip("/") for k, v in page["/Resources"]["/Font"].items()}
        font = colour = ""
        for m in PAINTED.finditer(page.get_contents().get_data().decode("latin-1")):
            if m.group(3) is not None:
                colour = _hex(m.group(1), m.group(2), m.group(3))
            elif m.group(4) is not None:
                font = fonts.get("/" + m.group(4), m.group(4))
            else:
                out.append((m.group(5).replace(r"\(", "(").replace(r"\)", ")"), font, colour))
    return out


def pdf_fills(data: bytes) -> set[str]:
    """Colours the PDF paints solid blocks in — the tint behind the basis panel is one."""
    from io import BytesIO
    from pypdf import PdfReader
    return {_hex(*m.groups()) for page in PdfReader(BytesIO(data)).pages
            for m in FILLED.finditer(page.get_contents().get_data().decode("latin-1"))}


def report_for(workspace, author="deterministic", reviewer="rules"):
    from fusa.orchestrator import Orchestrator
    from fusa.report import validate
    return validate(Orchestrator(root=workspace, dry_run=True, author=author, reviewer=reviewer))


def hand_built(**over):
    """A report assembled by hand, for the page layouts a fixture run cannot produce: a
    hundred work products, a basis long enough to break a page, a table with no note under it."""
    from fusa.report import Assessment, ValidationReport
    base = dict(verdict="RELEASABLE", asil="B", generated="2026-01-01T00:00:00+00:00",
                model="none", dry_run=True, author_mode="deterministic", reviewer_mode="rules",
                basis="No language model produced or judged any part of this report.",
                work_products=[Assessment(work_product="HARA", agent="cs-hara", ok=True,
                                          status="reviewed", written_by="table",
                                          reviewed_by="rules")])
    return ValidationReport(**(base | over))


def test_render_pdf_returns_a_real_pdf(workspace):
    from fusa.pdf import render_pdf
    data = render_pdf(report_for(workspace))
    assert data.startswith(b"%PDF-")


def test_the_pdf_carries_the_verdict_and_the_basis_summary(workspace):
    from fusa.pdf import render_pdf
    rep = report_for(workspace)
    text = pdf_text(render_pdf(rep))
    assert rep.verdict in text
    assert "No language model produced or judged" in text     # rep.basis, the summary line


def test_every_work_product_appears_in_the_pdf_evidence(workspace):
    from fusa.pdf import render_pdf
    rep = report_for(workspace)
    text = pdf_text(render_pdf(rep))
    for a in rep.work_products:
        assert a.work_product in text


def test_the_pdf_does_not_credit_a_model_that_never_ran(workspace):
    from fusa.pdf import render_pdf
    rep = report_for(workspace, author="deterministic", reviewer="rules")
    assert rep.model not in pdf_text(render_pdf(rep))


def test_the_pdf_names_the_model_when_one_ran(workspace):
    from fusa.pdf import render_pdf
    rep = report_for(workspace, author="model", reviewer="model")
    assert rep.model in pdf_text(render_pdf(rep))


def test_the_pdf_summarises_what_wrote_the_work_products(workspace):
    """The summary block is the thing a PDF has that a CSV row does not."""
    from fusa.pdf import render_pdf
    text = pdf_text(render_pdf(report_for(workspace)))
    assert "Summary" in text
    for label in ("Written from your tables", "Read from an analyser", "Written by a model"):
        assert label in text


def test_release_blockers_are_listed_in_the_pdf(workspace):
    from fusa.pdf import render_pdf
    rep = report_for(workspace)
    assert rep.reasons                                  # nothing has run: plenty to block on
    assert "Release blockers" in pdf_text(render_pdf(rep))


def test_report_pdf_endpoint_serves_a_downloadable_pdf(client):
    r = client.get("/report.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")
    assert "attachment" in r.headers["content-disposition"]


def test_the_pdf_filename_records_the_mode_that_produced_it(client):
    """A with-model and a without-model run must land as two files, not one overwritten."""
    def name(author, reviewer):
        client.post("/api/modes", json={"author": author, "reviewer": reviewer})
        return client.get("/report.pdf").headers["content-disposition"]
    without = name("deterministic", "rules")
    with_model = name("model", "model")
    assert "fusa-validation-report-deterministic-rules.pdf" in without
    assert "fusa-validation-report-model-model.pdf" in with_model


def test_report_pdf_without_reportlab_explains_the_extra(client, monkeypatch):
    from fusa import pdf
    def missing(_rep):
        raise ModuleNotFoundError(pdf.INSTALL_HINT)
    monkeypatch.setattr("fusa.ui.server.render_pdf", missing)
    r = client.get("/report.pdf")
    assert r.status_code == 503
    assert "reportlab" in r.json()["detail"]



# ---- the summary block: the one section a CSV row does not have ------------

def test_the_pdf_summary_counts_every_work_product_exactly_once(workspace):
    """Labels with the wrong numbers beside them are worse than no summary at all: this block
    is what a reader away from the dashboard decides on."""
    from fusa.pdf import WRITTEN_BY, _summary_rows, render_pdf
    rep = report_for(workspace)
    rows = dict(_summary_rows(rep))
    total = len(rep.work_products)
    assert rows["Work products"] == str(total)
    assert sum(int(rows[label]) for _kind, label in WRITTEN_BY) == total
    assert int(rows["Release-clean"]) + int(rows["Blocked"]) == total
    assert rows["Written by a model"] == "0"          # a deterministic run: none of them
    assert "Written by a model\n0" in pdf_text(render_pdf(rep))   # and the number reaches the page


@pytest.mark.parametrize("reviewer,says", [("rules", "rules"), ("model", "a language model")])
def test_the_pdf_summary_says_what_decided_the_checklist(workspace, reviewer, says):
    from fusa.pdf import _summary_rows
    assert dict(_summary_rows(report_for(workspace, reviewer=reviewer)))[
        "Checklist decided by"] == says


def test_the_pdf_summary_counts_only_the_findings_that_block_a_release(workspace, orch):
    """Counting typos alongside blockers would make a releasable report look unsafe."""
    from fusa.pdf import _summary_rows
    from fusa.report import validate
    mark_all_reviewed(orch)
    orch.reg.process.update("TSR", "sys-tsr", review=ReviewVerdict(
        work_product="TSR", verdict="approved", findings=[
            Finding(id="F-01", severity="minor", description="typo in TSR-002"),
            Finding(id="F-02", severity="major", description="TSR-003 has no verification"),
            Finding(id="F-03", severity="minor", description="TSR-004 reads awkwardly")]))
    assert dict(_summary_rows(validate(orch)))["Open blocker/major findings"] == "1"


@pytest.mark.parametrize("author,reviewer", [("model", "rules"), ("deterministic", "model")])
def test_the_pdf_names_the_model_when_either_half_of_the_run_used_one(workspace, author, reviewer):
    """A model that wrote nothing but judged everything still has to be named."""
    from fusa.pdf import render_pdf
    rep = report_for(workspace, author=author, reviewer=reviewer)
    assert rep.model in pdf_text(render_pdf(rep))


# ---- colour: this report's claim is that you can see who decided what ------

@pytest.mark.parametrize("verdict,colour", [("RELEASABLE", "#1d9a4e"),
                                            ("NOT_RELEASABLE", "#c0392b")])
def test_the_verdict_is_printed_in_the_colour_of_its_answer(verdict, colour):
    """Green or red is what a reader takes in before any word of the verdict."""
    from fusa.pdf import render_pdf
    painted = {c for text, _font, c in pdf_drawn(render_pdf(hand_built(verdict=verdict)))
               if text == verdict}
    assert painted == {colour}


@pytest.mark.parametrize("author,reviewer,tint", [
    ("deterministic", "rules", "#f3faf9"),           # teal: nothing here was a model's doing
    ("model", "rules", "#f7f4fd"),
    ("deterministic", "model", "#f7f4fd"),
    ("model", "model", "#f7f4fd")])
def test_the_basis_panel_is_tinted_by_whether_a_model_was_involved(workspace, author, reviewer, tint):
    """The panel is the first thing on the page, and its tint is read before its sentence."""
    from fusa.pdf import render_pdf
    fills = pdf_fills(render_pdf(report_for(workspace, author=author, reviewer=reviewer)))
    assert fills & {"#f3faf9", "#f7f4fd"} == {tint}


@pytest.mark.parametrize("author,expected", [
    ("model", {"MODEL": "#6b46c1", "TOOL": "#1d7a72"}),
    ("deterministic", {"TABLE": "#1d7a72", "TOOL": "#1d7a72"})])
def test_every_evidence_row_is_coloured_by_what_wrote_it(workspace, author, expected):
    """Purple for a model, teal for a table or an analyser. Reading the word is the fallback;
    seeing the colour is the point."""
    from fusa.pdf import render_pdf
    rep = report_for(workspace, author=author, reviewer="rules")
    painted = {text: colour for text, _font, colour in pdf_drawn(render_pdf(rep))
               if text in {"MODEL", "TOOL", "TABLE"}}
    assert painted == expected


def test_a_blocked_row_is_red_and_a_clean_one_green(workspace, orch):
    """One failed gate among sixteen rows has to be findable without reading sixteen rows."""
    from fusa.pdf import render_pdf
    from fusa.report import validate
    mark_all_reviewed(orch)
    orch.reg.process.update("TSC", "sys-tsc", gate=GateResult(
        work_product="TSC", passed=False, errors=["TSC-001 cites undefined SM-999"]))
    painted = {text: colour for text, _font, colour in pdf_drawn(render_pdf(validate(orch)))
               if text in {"OK", "BLOCKED"}}
    assert painted == {"OK": "#1d9a4e", "BLOCKED": "#c0392b"}


# ---- layout: a document read on paper, away from the tool ------------------

def test_a_multi_page_evidence_table_carries_its_header_onto_every_page():
    """A page of rows with no header is a page of unlabelled columns."""
    from fusa.pdf import render_pdf
    from fusa.report import Assessment
    rep = hand_built(work_products=[
        Assessment(work_product=f"WP-{n:03d}", agent=f"ag-{n:03d}", ok=True, status="reviewed",
                   written_by="table", reviewed_by="rules") for n in range(120)])
    pages = pdf_pages(render_pdf(rep))
    assert len(pages) > 2                              # it really did run past one page
    assert all("Written by" in p for p in pages[1:])


def test_the_summary_block_never_repeats_its_first_row_as_a_header():
    """The summary has no header row — its first line is a count — so a break across pages
    must not turn "Work products" into a heading on the next one."""
    from fusa.pdf import render_pdf
    pages = pdf_pages(render_pdf(hand_built(basis="word " * 1000)))
    first = [n for n, p in enumerate(pages) if "Work products" in p]
    last = [n for n, p in enumerate(pages) if "Unresolved" in p]
    assert first and last and first != last            # the block really did split
    assert len(first) == 1


def test_the_metrics_table_header_is_set_apart_from_its_numbers(workspace):
    """A header row that reads as another row of data is a table you have to count."""
    from fusa.pdf import render_pdf
    rep = report_for(workspace)
    assert rep.metrics_table                           # the sample FMEDA is in the workspace
    fonts = {text: font for text, font, _colour in pdf_drawn(render_pdf(rep))}
    assert fonts["Metric"] == "Helvetica-Bold"
    assert fonts["SPFM"] == "Helvetica"


def test_the_note_under_a_metrics_table_is_carried_over_with_it():
    from fusa.pdf import render_pdf
    rep = hand_built(metrics_table="| Metric | Value |\n|---|---|\n| SPFM | 92% |\n\n"
                                   "**Targets met.**")
    assert "Targets met." in pdf_text(render_pdf(rep))


def test_a_metrics_table_with_no_note_under_it_does_not_repeat_its_last_row():
    """The note is prose. A table row printed again beneath the table reads as stray markdown."""
    from fusa.pdf import render_pdf
    rep = hand_built(metrics_table="| Metric | Value |\n|---|---|\n| SPFM | 92% |")
    assert "| SPFM | 92% |" not in pdf_text(render_pdf(rep))


def test_a_metrics_table_with_a_short_row_still_prints_every_cell():
    """Markdown tables are hand-edited; a missing cell must not cost the reader the row."""
    from fusa.pdf import render_pdf
    rep = hand_built(metrics_table="| Metric | Value | Target |\n|---|---|---|\n| SPFM | 92% |")
    text = pdf_text(render_pdf(rep))
    for cell in ("Metric", "Value", "Target", "SPFM", "92%"):
        assert cell in text


def test_a_finding_in_the_pdf_says_which_agent_it_goes_back_to(workspace, orch):
    """A finding without the agent it returns to is a complaint rather than an instruction."""
    from fusa.pdf import render_pdf
    from fusa.report import validate
    mark_all_reviewed(orch)
    orch.reg.process.update("TSR", "sys-tsr", review=ReviewVerdict(
        work_product="TSR", verdict="rework",
        findings=[Finding(id="F-09", severity="major", description="TSR-004 cites no clause",
                          returns_to="sys-tsr")]))
    text = pdf_text(render_pdf(validate(orch)))
    assert "TSR F-09 (major): TSR-004 cites no clause" in text
    assert "returns to sys-tsr" in text
