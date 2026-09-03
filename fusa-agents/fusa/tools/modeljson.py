"""Reading JSON out of model output.

`json.loads(reply)` only works for a model that answers with nothing but JSON. Real ones wrap
it in prose ("Here is my review:"), in fences, or behind a reasoning preamble, and they spell
enum values however they like. Both are handled here so the chain never dies on a reply it
could have understood — and never *misreads* one either: a verdict that cannot be understood
is rework, never approval.
"""
from __future__ import annotations

import json
import re

FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)\s*```", re.DOTALL)

APPROVE_WORDS = {"approved", "approve", "ok", "okay", "pass", "passed", "accept", "accepted", "yes"}
SEVERITIES = {"blocker", "major", "minor"}
SEVERITY_ALIASES = {
    "critical": "blocker", "high": "blocker", "fatal": "blocker", "error": "blocker", "severe": "blocker",
    "medium": "major", "moderate": "major", "warning": "major", "warn": "major", "significant": "major",
    "low": "minor", "info": "minor", "informational": "minor", "note": "minor", "nit": "minor",
    "observation": "minor", "suggestion": "minor",
}
DESCRIPTION_KEYS = ("description", "text", "message", "detail", "details", "finding", "issue", "comment")


def _balanced_objects(text: str):
    """Every top-level {...} span, brace-counted with strings and escapes respected."""
    depth = start = 0
    in_string = escaped = False
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0:
                yield text[start:i + 1]


def extract_object(text: str | None) -> dict | None:
    """The JSON object a model meant to send, wherever it put it. None if there is none."""
    if not text or not text.strip():
        return None
    candidates = [text.strip(), *FENCE_RE.findall(text), *_balanced_objects(text)]
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            return value
    return None


def coerce_verdict(data: dict, work_product: str, reviewer: str) -> dict:
    """Shape a parsed reply into what ReviewVerdict accepts.

    Anything not recognisably an approval becomes `rework`: a reviewer whose answer we cannot
    read has not approved anything, and guessing in that direction is the one guess a safety
    gate must never make.
    """
    raw_verdict = str(data.get("verdict", data.get("status", ""))).strip().lower()
    findings = data.get("findings", data.get("issues", []))
    if isinstance(findings, dict):
        findings = list(findings.values())
    if not isinstance(findings, list):
        findings = [findings] if findings else []

    out = []
    for n, f in enumerate(findings, 1):
        if not isinstance(f, dict):
            f = {"description": str(f)}
        severity = str(f.get("severity", f.get("level", "major"))).strip().lower()
        severity = severity if severity in SEVERITIES else SEVERITY_ALIASES.get(severity, "major")
        description = next((str(f[k]) for k in DESCRIPTION_KEYS if f.get(k)), "") or json.dumps(f)[:300]
        returns_to = f.get("returns_to") or f.get("owner")
        out.append({
            "id": str(f.get("id") or f.get("ref") or f"F-{n:02d}"),
            "severity": severity,
            "checklist_item": _opt_str(f.get("checklist_item") or f.get("checklist")),
            "clause": _opt_str(f.get("clause")),
            "description": description,
            "returns_to": _opt_str(returns_to),
        })
    return {"work_product": str(data.get("work_product") or work_product),
            "verdict": "approved" if raw_verdict in APPROVE_WORDS else "rework",
            "findings": out, "reviewer": reviewer}


def _opt_str(value) -> str | None:
    return str(value) if isinstance(value, (str, int, float)) and str(value).strip() else None
