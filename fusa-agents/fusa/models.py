"""Typed records shared across registers, agents, gate and orchestrator."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

PREFIX_RE = re.compile(r"\A[A-Z][A-Z0-9]{1,7}\Z")     # must match ids.ID_RE's prefix group


class Status(str, Enum):
    NOT_STARTED = "not_started"
    BLOCKED = "blocked"          # upstream missing or (strict mode) pending
    DRAFTED = "drafted"          # agent wrote it, gate not yet run
    GATE_FAILED = "gate_failed"  # structural check blocked it
    GATE_PASSED = "gate_passed"  # structure OK, awaiting review
    REWORK = "rework"            # reviewer (or feedback loop) sent it back
    REVIEWED = "reviewed"        # approved by independent reviewer


class AgentSpec(BaseModel):
    """One row of config/agents.yaml. One agent, one work product."""
    id: str
    work_product: str                       # e.g. TSR, TSC, SM-CATALOG
    title: str
    phase: int                              # 1..7 as in the diagram
    kind: Literal["authoring", "review", "runner"] = "authoring"
    requires: list[str] = Field(default_factory=list)   # upstream work products
    covers: list[str] = Field(default_factory=list)     # upstream WPs every item of which must have a child here
    item_prefixes: list[str] = Field(default_factory=list)  # allowed `### PREFIX-nnn` ids; default [work_product]
    inputs: list[str] = Field(default_factory=list)     # files under input/
    clauses: list[str] = Field(default_factory=list)    # clause ids or prefixes
    method: str | None = None               # method skill in _reference-register/methods
    conventions: list[str] = Field(default_factory=list)
    checklist: str | None = None            # _checklist-register/<name>.yaml
    tools: list[str] = Field(default_factory=list)      # deterministic tools to run
    runner: dict | None = None              # kind=runner: {command, report, format, cwd, min_severity}
    reviewed_by: str | None = "verification-review"
    enabled: bool = True

    @property
    def prefixes(self) -> list[str]:
        """Declared prefixes, else one derived from the work product — legal by construction.
        `HW-DESIGN` as a prefix would be rejected by the id grammar, silently costing the work
        product every traceable item, so the hyphen is dropped rather than passed through."""
        if self.item_prefixes:
            return self.item_prefixes
        derived = re.sub(r"[^A-Z0-9]", "", self.work_product.upper())[:8]
        return [derived if PREFIX_RE.match(derived) else "ITEM"]


class Finding(BaseModel):
    id: str
    severity: Literal["blocker", "major", "minor"]
    checklist_item: str | None = None
    clause: str | None = None
    description: str
    returns_to: str | None = None           # agent id — drives the feedback loop


class ReviewVerdict(BaseModel):
    work_product: str
    verdict: Literal["approved", "rework"]
    findings: list[Finding] = Field(default_factory=list)
    reviewer: str = "verification-review"


class GateResult(BaseModel):
    work_product: str
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)


class WorkProductRecord(BaseModel):
    work_product: str
    agent: str
    status: Status = Status.NOT_STARTED
    path: str | None = None
    pending_count: int = 0
    gate: GateResult | None = None
    review: ReviewVerdict | None = None
    updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
