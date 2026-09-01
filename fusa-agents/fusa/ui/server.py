"""fusa ui — dashboard server.

    GET  /                    single-page dashboard
    GET  /api/meta            model, dry-run flag, root
    GET  /api/agents          every declared agent (enabled or not) + live status
    GET  /api/plan            creation order of enabled producing agents
    GET  /api/status          work-product records + running flag
    GET  /api/logs?since=N    log lines appended since N (long-poll style)
    GET  /api/wp/{WP}         generated markdown + record (+ metrics.md if present)
    GET  /api/aspice          base-practice coverage table (markdown)
    POST /api/run/{agent-id}  run one agent in the background (409 while busy)
    POST /api/run-all         walk the dependency sequence in the background
"""
from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from ..orchestrator import Orchestrator

STATIC = Path(__file__).parent / "static"


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


def create_app(root: Path | None = None, dry_run: bool | None = None) -> FastAPI:
    orch = Orchestrator(root=root, dry_run=dry_run)
    runner = Runner()
    app = FastAPI(title="FuSa Agent Framework")
    app.state.orchestrator = orch
    app.state.runner = runner

    def record(wp: str) -> dict | None:
        r = orch.reg.process.get(wp)
        return r.model_dump(mode="json") if r else None

    @app.get("/api/meta")
    def meta():
        return {"dry_run": orch.llm.dry_run, "model": orch.llm.model,
                "root": str(orch.root), "strict_pending": orch.strict}

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

    @app.post("/api/run/{agent_id}", status_code=202)
    def run(agent_id: str):
        if agent_id not in orch.by_id:
            raise HTTPException(status_code=404, detail=f"unknown agent '{agent_id}'")
        runner.start(f"run {agent_id}", lambda log: orch.run(agent_id, log=log))
        return {"started": agent_id}

    @app.post("/api/run-all", status_code=202)
    def run_all():
        runner.start("run-all", lambda log: orch.run_all(log=log))
        return {"started": "run-all"}

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app


def serve(host: str = "127.0.0.1", port: int = 8000, dry_run: bool | None = None) -> None:
    import uvicorn
    uvicorn.run(create_app(dry_run=dry_run), host=host, port=port, log_level="warning")
