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


def pdf_text(data: bytes) -> str:
    from io import BytesIO
    from pypdf import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(data)).pages)


def report_for(workspace, author="deterministic", reviewer="rules"):
    from fusa.orchestrator import Orchestrator
    from fusa.report import validate
    return validate(Orchestrator(root=workspace, dry_run=True, author=author, reviewer=reviewer))


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

