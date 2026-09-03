"""fusa ui — dashboard server.

    GET  /                    single-page dashboard
    GET  /api/meta            provider, model, dry-run flag, root
    GET  /api/settings        LLM backend: provider, model, whether a key is configured (never the key)
    POST /api/settings        switch provider/model, set API key (kept in memory only; 409 while busy)
    POST /api/settings/test   one tiny live completion to verify the configured backend
    GET  /api/agents          every declared agent (enabled or not) + live status
    GET  /api/plan            creation order of enabled producing agents
    GET  /api/status          work-product records + running flag
    GET  /api/logs?since=N    log lines appended since N (long-poll style)
    GET  /api/wp/{WP}         generated markdown + record (+ metrics.md if present)
    GET  /api/aspice          base-practice coverage table (markdown)
    GET  /api/input           files under input/ (name, size, modified)
    POST /api/input/fmeda     upload failure-mode CSV (validated) -> saves + runs the chain
    GET  /api/template/requirements   download the safety-requirements Excel template
    POST /api/input/requirements      upload filled template -> SYS-REQ + runs the chain
                                      (blank Requirement IDs are auto-assigned and written back)
    GET  /report.xlsx         Excel results workbook (summary, requirements, evidence)
    GET  /api/report          live release validation (verdict + evidence)
    POST /api/report          same, and writes _generated/VALIDATION-REPORT.md
    GET  /report              printable HTML validation report (print -> PDF)
    POST /api/run/{agent-id}  run one agent in the background (409 while busy)
    POST /api/run-all         walk the dependency sequence in the background
"""
from __future__ import annotations

import csv
import io
import threading

import yaml
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from ..agents.llm import PROVIDERS
from ..models import Status
from ..orchestrator import Orchestrator, UnknownAgent
from ..report import render_html, validate, write_report
from ..tools import reqtable

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

STATIC = Path(__file__).parent / "static"
FMEDA_COLUMNS = reqtable.FMEDA_COLUMNS        # one home for the column registry


def validate_fmeda_csv(text: str) -> tuple[int, list[str]]:
    """Row count + errors; same semantics as tools.metrics.load_csv."""
    from ..tools.metrics import FailureMode, uncommented
    reader = csv.DictReader(uncommented(io.StringIO(text)))
    missing = set(FMEDA_COLUMNS) - set(reader.fieldnames or [])
    if missing:
        return 0, ["missing column(s): " + ", ".join(sorted(missing))]
    rows, errors = 0, []
    for n, rec in enumerate(reader, start=2):        # header is line 1
        rows += 1
        try:
            FailureMode(element=rec["element"], mode=rec["mode"], lam=float(rec["lam_fit"]),
                        category=rec["category"].strip().upper(), dc=float(rec.get("dc") or 0.0))
        except (ValueError, TypeError) as e:
            errors.append(f"row {n}: {e}")
    if not rows:
        errors.append("no data rows")
    return rows, errors


class Runner:
    """One background run at a time; log lines buffered for the dashboard to poll."""

    def __init__(self):
        self.lock = threading.Lock()
        self.lines: list[str] = []

    @property
    def busy(self) -> bool:
        return self.lock.locked()

    def log(self, *parts) -> None:
        self.lines.append(" ".join(str(p) for p in parts))

    def start(self, label: str, fn) -> None:
        if not self.lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="a run is already in progress")

        def work():
            try:
                self.log(f"=== {label} ===")
                fn(self.log)
            except Exception as e:                       # surface, never kill the server
                self.log(f"[error] {e!r}")
            finally:
                self.log(f"=== {label} finished ===")
                self.lock.release()

        threading.Thread(target=work, daemon=True).start()


def create_app(root: Path | None = None, dry_run: bool | None = None,
               author: str | None = None, reviewer: str | None = None) -> FastAPI:
    orch = Orchestrator(root=root, dry_run=dry_run, author=author, reviewer=reviewer)
    runner = Runner()
    app = FastAPI(title="FuSa Agent Framework")
    app.state.orchestrator = orch
    app.state.runner = runner

    def record(wp: str) -> dict | None:
        r = orch.reg.process.get(wp)
        return r.model_dump(mode="json") if r else None

    @app.get("/api/meta")
    def meta():
        return {"dry_run": orch.llm.dry_run, "provider": orch.llm.provider, "model": orch.llm.model,
                "reviewer": orch.reviewer_kind, "author": orch.author_kind, "root": str(orch.root), "strict_pending": orch.strict}

    @app.get("/api/settings")
    def settings():
        return {"provider": orch.llm.provider, "model": orch.llm.model, "dry_run": orch.llm.dry_run,
                "api_key_set": bool(orch.llm.resolved_key()),
                "providers": {pid: {"label": p["label"], "default_model": p["default_model"],
                                    "key_env": list(p["key_env"])}
                              for pid, p in PROVIDERS.items()}}

    @app.post("/api/settings")
    async def settings_post(request: Request):
        data = await request.json()
        if runner.busy:
            raise HTTPException(status_code=409, detail="a run is in progress — change the backend when it finishes")
        try:
            orch.llm.configure(provider=data.get("provider"), model=(data.get("model") or "").strip() or None,
                               api_key=(data.get("api_key") or "").strip() or None)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return settings()                             # the key itself is never echoed back

    @app.post("/api/settings/test")
    def settings_test():
        if orch.llm.dry_run:
            return {"ok": True, "note": "dry-run mode — no model call made"}
        try:
            reply = orch.llm.complete("Reply with exactly: OK", "ping")
            return {"ok": True, "reply": reply.strip()[:80]}
        except Exception as e:                        # surface to the settings panel, never 500
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    @app.get("/api/agents")
    def agents():
        return [s.model_dump(mode="json")
                | {"status": orch.reg.process.status(s.work_product).value,
                   "blockers": orch.gating(s) if s.enabled else []}
                for s in orch.specs]

    @app.get("/api/plan")
    def plan():
        return [{"id": s.id, "work_product": s.work_product, "phase": s.phase} for s in orch.plan()]

    @app.get("/api/status")
    def status():
        return {"running": runner.busy,
                "records": {s.work_product: record(s.work_product) for s in orch.plan()}}

    @app.get("/api/logs")
    def logs(since: int = 0):
        return {"lines": runner.lines[since:], "next": len(runner.lines), "running": runner.busy}

    @app.get("/api/wp/{wp}")
    def workproduct(wp: str):
        if not orch.reg.generated.exists(wp):
            raise HTTPException(status_code=404, detail=f"{wp} not generated yet")
        aux = orch.reg.generated.path / wp / "metrics.md"
        return {"work_product": wp, "content": orch.reg.generated.read(wp),
                "record": record(wp),
                "metrics": aux.read_text(encoding="utf-8") if aux.exists() else None}

    @app.get("/api/aspice")
    def aspice():
        return {"table": orch.aspice()}

    @app.get("/api/input")
    def input_files():
        d = orch.root / "input"
        return [{"name": p.name, "size": p.stat().st_size,
                 "modified": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")}
                for p in sorted(d.iterdir()) if p.is_file()] if d.is_dir() else []

    @app.post("/api/input/fmeda", status_code=202)
    async def upload_fmeda(request: Request):
        text = (await request.body()).decode("utf-8", errors="replace")
        rows, errors = validate_fmeda_csv(text)
        if errors:
            raise HTTPException(status_code=400, detail=errors)
        if runner.busy:
            raise HTTPException(status_code=409, detail="a run is already in progress")
        path = orch.root / "input" / "fmeda-failure-modes.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        runner.start("run-all (new FMEDA input)", lambda log: orch.run_all(log=log))
        return {"saved": str(path), "rows": rows, "started": "run-all"}

    @app.get("/api/template/requirements")
    def template():
        return Response(reqtable.template_bytes(), media_type=XLSX,
                        headers={"content-disposition": 'attachment; filename="safety-requirements-template.xlsx"'})

    @app.get("/api/template/fmeda")
    def template_fmeda():
        return Response(reqtable.fmeda_template_text(), media_type="text/csv",
                        headers={"content-disposition": 'attachment; filename="fmeda-failure-modes-template.csv"'})

    @app.post("/api/input/requirements", status_code=202)
    async def upload_requirements(request: Request):
        body = await request.body()
        try:
            rows = reqtable.parse(io.BytesIO(body))
        except Exception:
            raise HTTPException(status_code=400, detail=["not a readable .xlsx workbook"])
        notes = reqtable.normalise_ids(rows)     # ids are repaired here, never a reason to reject
        errors = reqtable.validate_rows(rows)
        if not rows:
            errors.append("no requirement rows found")
        if errors:
            raise HTTPException(status_code=400, detail=errors)
        if runner.busy:
            raise HTTPException(status_code=409, detail="a run is already in progress")
        if notes:                                # persist them: the saved file is the id record
            body = reqtable.apply_ids(body, rows)
        path = orch.root / "input" / "safety-requirements.xlsx"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        wp_path = orch.reg.generated.write("SYS-REQ", reqtable.to_work_product(rows))
        orch.reg.process.update("SYS-REQ", "reqtable-import", status=Status.GATE_PASSED, path=str(wp_path))
        runner.start("run-all (new requirements input)", lambda log: orch.run_all(log=log))
        return {"saved": str(path), "rows": len(rows), "fusa_relevant": len(reqtable.fusa_rows(rows)),
                "id_notes": notes, "work_product": "SYS-REQ", "started": "run-all"}

    @app.get("/report.xlsx")
    def report_xlsx(asil: str = "B"):
        xls = orch.root / "input" / "safety-requirements.xlsx"
        rows = reqtable.parse(xls) if xls.exists() else []
        return Response(reqtable.results_bytes(validate(orch, asil=asil.upper()), rows), media_type=XLSX,
                        headers={"content-disposition": 'attachment; filename="fusa-validation-report.xlsx"'})

    @app.get("/api/report")
    def report(asil: str = "B"):
        return validate(orch, asil=asil.upper()).model_dump(mode="json")

    @app.post("/api/report")
    def report_write(asil: str = "B"):
        rep = validate(orch, asil=asil.upper())
        return rep.model_dump(mode="json") | {"markdown_path": str(write_report(orch, rep))}

    @app.get("/report")
    def report_page(asil: str = "B"):
        return HTMLResponse(render_html(validate(orch, asil=asil.upper())))

    @app.post("/api/run/{agent_id}", status_code=202)
    def run(agent_id: str):
        try:
            orch.resolve(agent_id)          # disabled/unknown fails here, not in the worker thread
        except UnknownAgent as e:
            raise HTTPException(status_code=404, detail=str(e))
        runner.start(f"run {agent_id}", lambda log: orch.run(agent_id, log=log))
        return {"started": agent_id}

    @app.post("/api/run-all", status_code=202)
    async def run_all(request: Request):
        """Optionally pick how the chain runs in the same call, so a mode is never half applied:
        `{"author": "deterministic", "reviewer": "rules"}` runs it with no model at all."""
        raw = await request.body()
        if raw.strip():
            data = await request.json()
            if data.get("author") or data.get("reviewer"):
                orch.set_modes(author=data.get("author"), reviewer=data.get("reviewer"))
        modes = f"{orch.author_kind} authoring · {orch.reviewer_kind} review"
        runner.start(f"run-all ({modes})", lambda log: orch.run_all(log=log))
        return {"started": "run-all", "author": orch.author_kind, "reviewer": orch.reviewer_kind}

    # ---- what a newcomer needs to see: what is ready, how content is made, how it is checked ----

    @app.get("/api/readiness")
    def readiness():
        """Everything the project needs from the user, and whether it has it yet."""
        import shutil as sh
        from ..generators.kinds import ASIL_TABLE_FILE, load_asil_table
        table = load_asil_table(orch.reg)
        total = len(yaml.safe_load((orch.reg.reference.path / ASIL_TABLE_FILE).read_text(encoding="utf-8"))
                    .get("table", {})) if (orch.reg.reference.path / ASIL_TABLE_FILE).exists() else 0
        tools = []
        for spec in orch.specs:
            if spec.kind == "runner" and spec.enabled and spec.runner:
                exe = (spec.runner.get("command") or "").split(" ")[0]
                tools.append({"agent": spec.id, "tool": exe, "installed": bool(exe and sh.which(exe)),
                              "work_product": spec.work_product})
        sources = {"table": 0, "tool": 0, "model": 0}
        for spec in orch.plan():
            if spec.kind == "runner":
                sources["tool"] += 1
            elif spec.generator and orch.author_kind == "deterministic":
                sources["table"] += 1
            else:
                sources["model"] += 1
        return {
            "author": orch.author_kind, "reviewer": orch.reviewer_kind, "dry_run": orch.llm.dry_run,
            "provider": orch.llm.provider, "model": orch.llm.model,
            "api_key_set": bool(orch.llm.resolved_key()),
            "needs_key": orch.author_kind != "deterministic" or orch.reviewer_kind != "rules",
            "asil_table": {"filled": len(table), "total": total, "file": ASIL_TABLE_FILE},
            "tools": tools, "sources": sources,
        }

    @app.post("/api/modes")
    async def modes(request: Request):
        """Switch how work products are written and reviewed, without restarting."""
        if runner.busy:
            raise HTTPException(status_code=409, detail="a run is in progress — switch when it finishes")
        data = await request.json()
        return orch.set_modes(author=data.get("author"), reviewer=data.get("reviewer"))

    @app.get("/api/checks")
    def checks(work_product: str | None = None):
        """Every checklist item, and what decides it — the gate, a rule, a person, or a model."""
        out = []
        for spec in orch.plan():
            if work_product and spec.work_product != work_product:
                continue
            items = []
            for entry in orch.reg.checklists.items(spec.checklist or spec.work_product):
                if entry.get("check") == "structural":
                    decided, detail = "gate", "structural check on every commit"
                elif entry.get("rule"):
                    decided, detail = "rule", entry["rule"].get("kind", "")
                elif orch.reviewer_kind == "model":
                    decided, detail = "model", f"{orch.llm.provider} · {orch.llm.model}"
                else:
                    decided, detail = "human", "confirmation review (ISO 26262-8 §9)"
                items.append({"id": entry.get("id"), "text": entry.get("text"),
                              "clause": entry.get("clause"), "decided_by": decided, "detail": detail})
            counts = {k: sum(1 for i in items if i["decided_by"] == k) for k in ("gate", "rule", "human", "model")}
            out.append({"work_product": spec.work_product, "agent": spec.id, "phase": spec.phase,
                        "source": ("tool" if spec.kind == "runner" else
                                   "table" if spec.generator and orch.author_kind == "deterministic" else "model"),
                        "generator": (spec.generator or {}).get("kind"),
                        "input": (spec.generator or {}).get("input"),
                        "status": orch.reg.process.status(spec.work_product).value,
                        "counts": counts, "items": items})
        return out

    RESULT_COLUMNS = ["phase", "work_product", "agent", "written_by", "input_table", "status",
                      "gate_passed", "gate_errors", "gate_warnings", "open_points", "review_verdict",
                      "blocker_findings", "major_findings", "minor_findings",
                      "checks_by_gate", "checks_by_rule", "checks_by_model", "checks_awaiting_you",
                      "authoring_mode", "review_mode", "exported"]

    def _result_rows() -> list[list]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = []
        for w in checks():
            rec = orch.reg.process.get(w["work_product"])
            gate = rec.gate if rec else None
            findings = rec.review.findings if rec and rec.review else []
            sev = {k: sum(1 for f in findings if f.severity == k) for k in ("blocker", "major", "minor")}
            rows.append([
                w["phase"], w["work_product"], w["agent"], w["source"], w.get("input") or "",
                w["status"],
                "" if gate is None else ("yes" if gate.passed else "no"),
                "; ".join(gate.errors) if gate else "", "; ".join(gate.warnings) if gate else "",
                "; ".join(gate.pending) if gate else "",
                rec.review.verdict if rec and rec.review else "",
                sev["blocker"], sev["major"], sev["minor"],
                w["counts"]["gate"], w["counts"]["rule"], w["counts"]["model"], w["counts"]["human"],
                orch.author_kind, orch.reviewer_kind, now,
            ])
        return rows

    def _csv(header: list[str], rows: list[list], name: str) -> Response:
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"content-disposition": f'attachment; filename="{name}"'})

    @app.get("/results.csv")
    def results_csv():
        """One row per work product: what produced it, how it fared, and under which mode — so a
        run with a model and a run without one diff against each other line for line."""
        return _csv(RESULT_COLUMNS, _result_rows(),
                    f"fusa-results-{orch.author_kind}-{orch.reviewer_kind}.csv")

    @app.get("/checks.csv")
    def checks_csv():
        """One row per checklist item and what decides it — the rule/model/human split as data."""
        rows = [[w["phase"], w["work_product"], w["agent"], i["id"], i["decided_by"], i["detail"],
                 i["clause"] or "", i["text"]]
                for w in checks() for i in w["items"]]
        return _csv(["phase", "work_product", "agent", "check_id", "decided_by", "detail",
                     "clause", "check"], rows, "fusa-checks.csv")

    @app.get("/api/asil-table")
    def asil_table():
        from ..generators.kinds import ASIL_TABLE_FILE
        path = orch.reg.reference.path / ASIL_TABLE_FILE
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {"table": {}}
        return {"file": ASIL_TABLE_FILE, "values": data.get("table", {}),
                "allowed": ["QM", "A", "B", "C", "D"]}

    @app.post("/api/asil-table")
    async def asil_table_save(request: Request):
        """Save the determination table the engineer transcribed from their licensed standard.

        Deliberately no 'fill with AI' path: a model reproducing a normative table is copying
        content it has not licensed, and a hallucinated ASIL is wrong all the way down the chain
        with nothing downstream able to notice."""
        from ..generators.kinds import ASIL_TABLE_FILE
        values = (await request.json()).get("values", {})
        path = orch.reg.reference.path / ASIL_TABLE_FILE
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {"table": {}}
        bad = [f"{k}={v}" for k, v in values.items()
               if str(v).strip() and str(v).strip().upper() not in ("QM", "A", "B", "C", "D")]
        if bad:
            raise HTTPException(status_code=400, detail=[f"not an ASIL: {', '.join(bad)}"])
        unknown = [k for k in values if k not in data.get("table", {})]
        if unknown:
            raise HTTPException(status_code=400, detail=[f"not an S×E×C key: {', '.join(sorted(unknown))}"])
        data["table"].update({k: str(v).strip().upper() for k, v in values.items()})
        header = path.read_text(encoding="utf-8").split("table:")[0] if path.exists() else ""
        path.write_text(header + "table:\n" + "".join(
            f'  {k}: "{v}"\n' for k, v in data["table"].items()), encoding="utf-8")
        return {"saved": str(path), "filled": sum(1 for v in data["table"].values() if str(v).strip())}

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app


def serve(host: str = "127.0.0.1", port: int = 8000, dry_run: bool | None = None,
          author: str | None = None, reviewer: str | None = None) -> None:
    import uvicorn
    uvicorn.run(create_app(dry_run=dry_run, author=author, reviewer=reviewer),
                host=host, port=port, log_level="warning")
