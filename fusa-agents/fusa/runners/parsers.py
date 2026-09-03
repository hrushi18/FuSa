"""Report parsers → list[Finding]. Add one function per tool format and register it in PARSERS."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}


@dataclass
class ToolFinding:
    tool: str
    rule: str
    severity: str            # info | warning | error
    message: str
    file: str = ""
    line: int | None = None
    tags: list[str] = field(default_factory=list)   # e.g. CWE-121, MISRA-C:2012 Rule 17.7, security


class ReportUnreadable(ValueError):
    """The analyser produced a file we cannot parse — usually because it crashed mid-write.
    Treated like a missing report (a PENDING marker), never as zero findings."""


def parse_sarif(path: Path) -> list[ToolFinding]:
    """SARIF 2.1.0 — emitted by CodeQL, Semgrep, clang-tidy (via converters), PC-lint Plus, Coverity, etc."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeDecodeError) as e:
        raise ReportUnreadable(f"{Path(path).name} is not readable SARIF: {e}") from None
    if not isinstance(doc, dict):
        raise ReportUnreadable(f"{Path(path).name}: SARIF root must be an object, got {type(doc).__name__}")
    out: list[ToolFinding] = []
    for run in doc.get("runs", []):
        tool = run.get("tool", {}).get("driver", {})
        tname = tool.get("name", "sarif")
        rules = {r.get("id"): r for r in tool.get("rules", [])}
        for res in run.get("results", []):
            rid = res.get("ruleId", "")
            level = res.get("level") or rules.get(rid, {}).get("defaultConfiguration", {}).get("level", "warning")
            sev = {"note": "info", "none": "info"}.get(level, level)
            loc = (res.get("locations") or [{}])[0].get("physicalLocation", {})
            f = loc.get("artifactLocation", {}).get("uri", "")
            line = loc.get("region", {}).get("startLine")
            tags = list(rules.get(rid, {}).get("properties", {}).get("tags", []))
            out.append(ToolFinding(tname, rid, sev if sev in SEVERITY_ORDER else "warning",
                                   res.get("message", {}).get("text", ""), f, line, tags))
    return out


def parse_cppcheck_xml(path: Path) -> list[ToolFinding]:
    """cppcheck --xml --xml-version=2 output (also carries MISRA addon results as rule ids)."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as e:
        raise ReportUnreadable(f"{Path(path).name} is not readable cppcheck XML: {e}") from None
    out: list[ToolFinding] = []
    for e in root.iter("error"):
        loc = e.find("location")
        sev = e.get("severity", "warning")
        sev = {"style": "info", "performance": "info", "portability": "info", "information": "info"}.get(sev, sev)
        tags = [f"CWE-{e.get('cwe')}"] if e.get("cwe") else []
        out.append(ToolFinding("cppcheck", e.get("id", ""), sev if sev in SEVERITY_ORDER else "warning",
                               e.get("msg", ""), loc.get("file", "") if loc is not None else "",
                               int(loc.get("line")) if loc is not None and loc.get("line") else None, tags))
    return out


PARSERS = {"sarif": parse_sarif, "cppcheck-xml": parse_cppcheck_xml}
