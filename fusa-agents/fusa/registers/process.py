"""ProcessRegister — live status board with dependency sequence and pending markers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from graphlib import TopologicalSorter
from pathlib import Path

from ..models import AgentSpec, Status, WorkProductRecord


class ProcessRegister:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._rec: dict[str, WorkProductRecord] = {}
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._rec = {k: WorkProductRecord.model_validate(v) for k, v in raw.items()}

    def save(self) -> None:
        self.path.write_text(json.dumps({k: v.model_dump(mode="json") for k, v in self._rec.items()}, indent=2), encoding="utf-8")

    def get(self, wp: str) -> WorkProductRecord | None:
        return self._rec.get(wp)

    def status(self, wp: str) -> Status:
        r = self._rec.get(wp)
        return r.status if r else Status.NOT_STARTED

    def update(self, wp: str, agent: str, **changes) -> WorkProductRecord:
        rec = self._rec.get(wp) or WorkProductRecord(work_product=wp, agent=agent)
        rec = rec.model_copy(update={**changes, "agent": agent})
        rec.updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._rec[wp] = rec
        self.save()
        return rec

    @staticmethod
    def dependency_sequence(specs: list[AgentSpec]) -> list[AgentSpec]:
        """Creation order: topological sort on `requires`, phase as tie-breaker."""
        by_wp = {s.work_product: s for s in specs}
        ts = TopologicalSorter({s.work_product: [r for r in s.requires if r in by_wp] for s in specs})
        order = list(ts.static_order())
        return sorted((by_wp[w] for w in order), key=lambda s: (order.index(s.work_product)))

    def board(self, specs: list[AgentSpec]) -> str:
        rows = ["| # | Agent | Work product | Status | Pending | Findings |", "|---|---|---|---|---|---|"]
        for s in specs:
            r = self._rec.get(s.work_product)
            st = r.status.value if r else Status.NOT_STARTED.value
            pend = r.pending_count if r else 0
            fnd = len(r.review.findings) if r and r.review else 0
            rows.append(f"| {s.phase} | {s.id} | {s.work_product} | {st} | {pend} | {fnd} |")
        return "\n".join(rows)
