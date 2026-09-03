"""safety-orchestrator — creation order, gating rules, status write-back.

    run(agent)      gate-check upstream → author → structural gate → independent review → write status
    run_all()       walk the dependency sequence
    feedback loop   a reviewer finding with `returns_to` puts that upstream agent into REWORK
"""
from __future__ import annotations

import difflib
from pathlib import Path

from . import config
from .agents import LLM, load_specs, build_agents
from .agents.registry import build_reviewer
from .gate import run_gate
from .models import AgentSpec, Status
from .registers import Registers

READY_FOR_DOWNSTREAM = {Status.GATE_PASSED, Status.REVIEWED}


class UnknownAgent(LookupError):
    """No such runnable agent id — a typo, a disabled row, or the reviewer."""


class Orchestrator:
    def __init__(self, root: Path | None = None, dry_run: bool | None = None, strict_pending: bool | None = None,
                 reviewer: str | None = None, author: str | None = None):
        self.root = Path(root or config.ROOT)
        self.reg = Registers.load(self.root)
        self.llm = LLM(dry_run=dry_run)
        self.reviewer_kind = reviewer or config.REVIEWER
        self.author_kind = author or config.AUTHOR
        self.strict = config.STRICT_PENDING if strict_pending is None else strict_pending
        self.specs = load_specs(self.root / "config" / "agents.yaml")
        self.by_id = {s.id: s for s in self.specs}
        self.by_wp = {s.work_product: s for s in self.specs}
        self.agents = build_agents(self.specs, self.reg, self.llm, self.author_kind)
        self.review_spec = next((s for s in self.specs if s.kind == "review"), None)

    def set_modes(self, author: str | None = None, reviewer: str | None = None) -> dict:
        """Switch authoring or review without a restart. Changing the author rebuilds the agents,
        because that choice *is* which agent object each work product gets."""
        if reviewer in ("model", "rules"):
            self.reviewer_kind = reviewer
        if author in ("model", "deterministic") and author != self.author_kind:
            self.author_kind = author
            self.agents = build_agents(self.specs, self.reg, self.llm, self.author_kind)
        return {"author": self.author_kind, "reviewer": self.reviewer_kind}

    # ---- planning ----------------------------------------------------------
    def plan(self) -> list[AgentSpec]:
        producing = [s for s in self.specs if s.kind in ("authoring", "runner") and s.enabled]
        return self.reg.process.dependency_sequence(producing)

    def resolve(self, agent_id: str):
        """(spec, agent) for a runnable agent id. A typo and a disabled agent are both ordinary
        mistakes, so they get an explanation instead of the KeyError they used to raise."""
        if agent_id not in self.by_id:
            close = difflib.get_close_matches(agent_id, self.by_id, n=3)
            raise UnknownAgent(f"unknown agent '{agent_id}'"
                               + (f" — did you mean {', '.join(close)}?" if close else "")
                               + f" ({len(self.by_id)} declared in config/agents.yaml)")
        spec = self.by_id[agent_id]
        if agent_id not in self.agents:
            why = "kind 'review' is not run directly" if spec.kind == "review" else \
                  "it is declared with `enabled: false` in config/agents.yaml"
            raise UnknownAgent(f"agent '{agent_id}' cannot be run: {why}")
        return spec, self.agents[agent_id]

    def spec_for(self, wp: str) -> AgentSpec:
        """The declared spec, or one synthesised for an imported work product (SYS-REQ via Excel
        or ReqIF has no agent). Nothing owns its prefix rule, so the ids present define it —
        gating an import checks structure and traceability without inventing a convention."""
        if wp in self.by_wp:
            return self.by_wp[wp]
        if not self.reg.generated.exists(wp):
            raise KeyError(wp)
        found = sorted({i.prefix for i in self.reg.generated.items(wp)})
        return AgentSpec(id=f"{wp.lower()}-import", work_product=wp, title=f"{wp} (imported)",
                         phase=1, item_prefixes=found or None, reviewed_by=None)

    def gating(self, spec: AgentSpec) -> list[str]:
        """Why this agent may not start yet (empty = go)."""
        reasons = []
        for up in spec.requires:
            st = self.reg.process.status(up)
            if st not in READY_FOR_DOWNSTREAM:
                if up in self.by_wp and self.by_wp[up].enabled:
                    # name the agent to run next: "HSR is blocked" alone leaves the reader
                    # to work out which of 30 agents produces HSR
                    owner = self.by_wp[up].id
                    reasons.append(f"{up} is {st.value} — run {owner} first"
                                   if owner in self.agents else f"{up} is {st.value}")
                # disabled upstream: allowed, the author will mark PENDING
            elif self.strict:
                rec = self.reg.process.get(up)
                if rec and rec.pending_count:
                    reasons.append(f"{up} has {rec.pending_count} pending marker(s) (strict mode)")
        return reasons

    # ---- execution ---------------------------------------------------------
    def run(self, agent_id: str, *, force: bool = False, review: bool = True, log=print) -> Status:
        spec, agent = self.resolve(agent_id)
        wp = spec.work_product
        proc = self.reg.process

        blockers = self.gating(spec)
        if blockers and not force:
            proc.update(wp, agent_id, status=Status.BLOCKED)
            log(f"[{agent_id}] BLOCKED: " + "; ".join(blockers))
            return Status.BLOCKED

        log(f"[{agent_id}] authoring {wp} ...")
        content = agent.run()
        path = self.reg.generated.write(wp, content)
        proc.update(wp, agent_id, status=Status.DRAFTED, path=str(path))

        # deterministic id pass already rewrote what the model got wrong; say what changed
        notes = list(getattr(agent, "last_notes", ()))
        for n in notes:
            log(f"[{agent_id}]   id fixed     {n}")

        # deterministic tools declared for this agent (e.g. metrics for hw-fmeda)
        for tool in spec.tools:
            self._run_tool(tool, spec, log)

        gate = run_gate(spec, content, self.reg.generated, extra_warnings=notes)
        proc.update(wp, agent_id, gate=gate, pending_count=len(gate.pending),
                    status=Status.GATE_PASSED if gate.passed else Status.GATE_FAILED)
        for e in gate.errors:
            log(f"[{agent_id}]   gate ERROR   {e}")
        for w in gate.warnings:
            log(f"[{agent_id}]   gate warning {w}")
        if gate.pending:
            log(f"[{agent_id}]   {len(gate.pending)} pending marker(s)")
        if not gate.passed:
            log(f"[{agent_id}] GATE FAILED — review not started")
            return Status.GATE_FAILED

        # feedback loop from the work product itself: items carrying `- returns_to: <agent>`
        # (uncovered failure modes, missed metric targets, tool findings routed to a design owner)
        for item in self.reg.generated.items(wp):
            target = item.fields.get("returns_to")
            if target in self.by_id and target != agent_id:
                up_wp = self.by_id[target].work_product
                if proc.status(up_wp) in READY_FOR_DOWNSTREAM:
                    proc.update(up_wp, target, status=Status.REWORK)
                    log(f"[{agent_id}]   {item.id} -> {target} ({up_wp}) set to REWORK")

        if review and spec.reviewed_by and self.review_spec:
            reviewer = build_reviewer(self.review_spec, spec, self.reg, self.llm, self.reviewer_kind)
            log(f"[{reviewer.id}] reviewing {wp} ...")
            verdict = reviewer.run(content)
            self.reg.generated.write_aux(wp, f"{wp}.review.json", verdict.model_dump_json(indent=2))
            status = Status.REVIEWED if verdict.verdict == "approved" else Status.REWORK
            proc.update(wp, agent_id, review=verdict, status=status)
            for f in verdict.findings:
                log(f"[{reviewer.id}]   {f.severity:7} {f.id}: {f.description}")
                if f.returns_to and f.returns_to in self.by_id:          # feedback loop
                    up_wp = self.by_id[f.returns_to].work_product
                    proc.update(up_wp, f.returns_to, status=Status.REWORK)
                    log(f"[{reviewer.id}]   -> {f.returns_to} ({up_wp}) set to REWORK")
            log(f"[{agent_id}] {status.value.upper()}")
            return status

        return Status.GATE_PASSED

    def run_all(self, *, stop_on_block: bool = False, log=print) -> None:
        for spec in self.plan():
            st = self.run(spec.id, log=log)
            if st in {Status.BLOCKED, Status.GATE_FAILED} and stop_on_block:
                break

    def _run_tool(self, tool: str, spec: AgentSpec, log) -> None:
        if tool == "metrics":
            from .tools import metrics
            csv_path = config.INPUT_DIR / "fmeda-failure-modes.csv"
            if not csv_path.exists():
                log(f"[{spec.id}]   metrics: input/fmeda-failure-modes.csv missing — [PENDING] left in place")
                return
            m = metrics.compute(metrics.load_csv(csv_path))
            asil = "B"
            table = metrics.render(m, asil)
            self.reg.generated.write_aux(spec.work_product, "metrics.md", table)
            log(f"[{spec.id}]   metrics: SPFM={m.spfm and f'{m.spfm:.2%}'} LFM={m.lfm and f'{m.lfm:.2%}'} PMHF={m.pmhf_fit:.2f} FIT")
        else:
            log(f"[{spec.id}]   unknown tool '{tool}' (declare it in orchestrator._run_tool)")

    def status(self) -> str:
        return self.reg.process.board(self.plan())

    def aspice(self) -> str:
        """Process-outcome coverage: which ASPICE base practices have a reviewed work product behind them."""
        import yaml
        mp = self.root / "config" / "aspice-map.yaml"
        if not mp.exists():
            return "(config/aspice-map.yaml not found)"
        data = yaml.safe_load(mp.read_text(encoding="utf-8")) or {}
        rows = ["| Process | Base practice | Work product(s) | Status |", "|---|---|---|---|"]
        for proc_id, proc in data.get("processes", {}).items():
            for bp in proc.get("base_practices", []):
                wps = bp.get("work_products", [])
                sts = [self.reg.process.status(w).value for w in wps]
                agg = ("reviewed" if sts and all(x == "reviewed" for x in sts)
                       else "in progress" if any(x not in ("not_started",) for x in sts) else "not started")
                rows.append(f"| {proc_id} {proc.get('name', '')} | {bp['id']} {bp['name']} | {', '.join(wps) or '—'} | {agg} |")
        return "\n".join(rows)
