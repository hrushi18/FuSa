"""Load config/agents.yaml into AgentSpec objects and instantiate agents.

Adding an agent = adding a row to agents.yaml (plus its method/checklist files).
Specialised behaviour (e.g. running the metrics tool) is keyed by `tools:`.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..models import AgentSpec
from ..registers import Registers
from .base import AuthoringAgent, ReviewAgent
from .llm import LLM


def load_specs(path: Path) -> list[AgentSpec]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return [AgentSpec.model_validate(a) for a in data.get("agents", [])]


def build_agents(specs: list[AgentSpec], registers: Registers, llm: LLM) -> dict:
    owners = {s.work_product: s.id for s in specs}
    agents: dict[str, AuthoringAgent] = {}
    for s in specs:
        if not s.enabled or s.kind == "review":
            continue
        if s.kind == "runner":
            from ..runners import ToolRunnerAgent
            agents[s.id] = ToolRunnerAgent(s, registers, llm.dry_run)
            continue
        a = AuthoringAgent(s, registers, llm)
        a._owners = owners
        agents[s.id] = a
    return agents


def build_reviewer(review_spec: AgentSpec, target: AgentSpec, registers: Registers, llm: LLM) -> ReviewAgent:
    """One reviewer instance per work product, never the author's instance."""
    per_wp = review_spec.model_copy(update={"id": f"{review_spec.id}:{target.work_product}"})
    return ReviewAgent(per_wp, target, registers.reference.conventions_only(), registers, llm)
