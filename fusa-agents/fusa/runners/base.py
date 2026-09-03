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
import shutil
import subprocess
from datetime import date
from pathlib import Path

from .. import config
from ..models import AgentSpec
from ..registers import Registers
from .parsers import PARSERS, SEVERITY_ORDER, ReportUnreadable, ToolFinding


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
    def executable(self) -> str:
        """The program the command starts, e.g. `cppcheck` — checked before running so a
        missing analyser is named as such instead of writing the shell's complaint into the
        report file (these commands redirect stderr into it) and failing to parse that."""
        cmd = self.cfg.get("command") or ""
        try:
            return (shlex.split(cmd) or [""])[0]
        except ValueError:                 # unbalanced quotes: let the shell judge it
            return cmd.split()[0] if cmd else ""

    def run(self) -> str:
        report = config.ROOT / self.cfg["report"]
        cmd = self.cfg.get("command")
        result = None
        if cmd and not self.dry_run:
            exe = self.executable()
            if exe and shutil.which(exe) is None:
                return self._render([], pending=f"{exe} is not installed or not on PATH — install it, "
                                                f"or set `enabled: false` for {self.spec.id} "
                                                f"<- {self.spec.id}")
            report.parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(cmd.format(report=report), shell=True,
                                    cwd=config.ROOT / self.cfg.get("cwd", "."), check=False)
        if not report.exists():
            failed = f" ({self.executable()} exited {result.returncode})" if result and result.returncode else ""
            return self._render([], pending=f"report {self.cfg['report']} not produced{failed} <- {self.spec.id}")
        fmt = self.cfg.get("format", "sarif")
        if fmt not in PARSERS:
            return self._render([], pending=f"unknown report format '{fmt}' (have: {', '.join(PARSERS)}) "
                                            f"<- {self.spec.id}")
        try:
            findings = PARSERS[fmt](report)
        except ReportUnreadable as e:      # a crashed analyser must not read as a clean scan
            return self._render([], pending=f"{e}{self._why(report, result)} <- {self.spec.id}")
        floor = SEVERITY_ORDER.get(self.cfg.get("min_severity", "info"), 0)
        findings = [f for f in findings if SEVERITY_ORDER.get(f.severity, 1) >= floor]
        return self._render(findings)

    def _why(self, report: Path, result) -> str:
        """What the unreadable report actually says. These commands send stderr to the report,
        so its first line is usually the real explanation ('cppcheck: not found')."""
        parts = []
        if result is not None and result.returncode:
            parts.append(f"{self.executable()} exited {result.returncode}")
        try:
            first = next((l.strip() for l in report.read_text(encoding="utf-8", errors="replace").splitlines()
                          if l.strip()), "")
        except OSError:
            first = ""
        if first:
            parts.append(f"file begins: {first[:120]}")
        return (" — " + "; ".join(parts)) if parts else ""

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
