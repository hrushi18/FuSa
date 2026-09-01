"""Tool-runner agents: execute an external analyser, normalise its report into the ID grammar.

Static analysis, security scanning and platform test results all have the same shape:
run something deterministic → parse its report → one `### <PREFIX>-nnn` item per finding →
gate → independent review → findings that need a design change `returns_to` an upstream agent.
The model is only used (optionally) to triage/route findings, never to produce them.
"""
from .base import ToolRunnerAgent
from . import parsers

__all__ = ["ToolRunnerAgent", "parsers"]
