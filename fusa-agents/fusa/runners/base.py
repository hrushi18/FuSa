"""ToolRunnerAgent — a `kind: runner` row in agents.yaml.

    runner:
      command: "cppcheck --xml --xml-version=2 --enable=all src/ 2> {report}"   # optional; omit to ingest an existing report
      report:  input/reports/cppcheck.xml
      format:  cppcheck-xml | sarif
      min_severity: warning
      route:   {error: sw-arch}      # severity → agent that must react (feedback loop)
      tags_to: {security: cs-tara}   # tag substring → agent
In dry-run (or when `command` is absent) the report file is read as-is, so canned reports drive the chain offline.
"""
from __future__ import annotations

import shlex
import subprocess
from datetime import date
from pathlib import Path

from .. import config
from ..models import AgentSpec
from ..registers import Registers
from .parsers import PARSERS, SEVERITY_ORDER, ToolFinding


class ToolRunnerAgent:
    def __init__(self, spec: AgentSpec, registers: Registers, dry_run: bool):
        assert spec.kind == "runner" and spec.runner, f"{spec.id}: kind=runner needs a `runner:` block"
        self.spec = spec
        self.reg = registers
        self.dry_run = dry_run
        self.cfg = spec.runner

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def work_product(self) -> str:
        return self.spec.work_product

    # ---- execution -------------------------------------------------------
    def run(self) -> str:
        report = config.ROOT / self.cfg["report"]
        cmd = self.cfg.get("command")
        if cmd and not self.dry_run:
            report.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(cmd.format(report=report), shell=True, cwd=config.ROOT / self.cfg.get("cwd", "."), check=False)
        if not report.exists():
            return self._render([], pending=f"report {self.cfg['report']} not produced <- {self.spec.id}")
        findings = PARSERS[self.cfg.get("format", "sarif")](report)
        floor = SEVERITY_ORDER[self.cfg.get("min_severity", "info")]
        findings = [f for f in findings if SEVERITY_ORDER[f.severity] >= floor]
        return self._render(findings)

    def route(self, f: ToolFinding) -> str | None:
        for tag_sub, agent in (self.cfg.get("tags_to") or {}).items():
            if any(tag_sub.lower() in t.lower() for t in f.tags):
                return agent
        return (self.cfg.get("route") or {}).get(f.severity)

    def _render(self, findings: list[ToolFinding], pending: str | None = None) -> str:
        s, px = self.spec, self.spec.prefixes[0]
        lines = [f"---\nid: {s.work_product}\ntitle: {s.title}\nagent: {s.id}\ndate: {date.today().isoformat()}\n"
                 f"clauses: {', '.join(s.clauses) or '—'}\nstatus: draft\ntool: {self.cfg.get('format')}\n---\n",
                 f"# {s.title}\n",
                 f"Source report: `{self.cfg['report']}`. Findings normalised by `fusa.runners`; counts by severity: "
                 + ", ".join(f"{k}={sum(1 for f in findings if f.severity == k)}" for k in SEVERITY_ORDER) + ".\n"]
        if pending:
            lines.append(f"[PENDING: {pending}]\n")
        lines.append("## Items\n")
        for n, f in enumerate(findings, 1):
            lines += [f"### {px}-{n:03d}",
                      f"- tool: {f.tool}", f"- rule: {f.rule}", f"- severity: {f.severity}",
                      f"- location: {f.file}{f':{f.line}' if f.line else ''}",
                      f"- text: {f.message}"]
            if f.tags:
                lines.append(f"- tags: {', '.join(f.tags)}")
            r = self.route(f)
            if r:
                lines.append(f"- returns_to: {r}")
            lines.append("")
        return "\n".join(lines)
