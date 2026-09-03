"""Load config/agents.yaml into AgentSpec objects and instantiate agents.

Adding an agent = adding a row to agents.yaml (plus its method/checklist files).
Specialised behaviour (e.g. running the metrics tool) is keyed by `tools:`.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from ..models import AgentSpec
from ..registers import Registers
from .base import AuthoringAgent, ReviewAgent
from .llm import LLM
from .rulereview import RuleReviewAgent


class AgentsFileError(ValueError):
    """config/agents.yaml is malformed. Named row and reason, not a bare pydantic dump."""


def load_specs(path: Path) -> list[AgentSpec]:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        raise AgentsFileError(f"{path.name} could not be read: {e}") from None
    if not isinstance(data, dict) or not isinstance(data.get("agents", []), list):
        raise AgentsFileError(f"{path.name} must be a mapping with a list under `agents:`")
    specs = []
    for n, row in enumerate(data.get("agents", []), 1):
        try:
            specs.append(AgentSpec.model_validate(row))
        except ValidationError as e:
            named = row.get("id", f"#{n}") if isinstance(row, dict) else f"#{n}"
            fields = ", ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())
            raise AgentsFileError(f"{path.name}: agent '{named}' is invalid — {fields}") from None
    return specs


def prefix_owners(specs: list[AgentSpec]) -> dict[str, tuple[str, str]]:
    """Id prefix -> (work product, agent id). Disabled agents count: an id they own is still
    theirs, so an author is told where it belongs instead of claiming it."""
    out: dict[str, tuple[str, str]] = {}
    for s in specs:
        if s.kind == "review":
            continue
        for p in s.prefixes:
            out.setdefault(p, (s.work_product, s.id))
    return out


def build_agents(specs: list[AgentSpec], registers: Registers, llm: LLM) -> dict:
    owners = {s.work_product: s.id for s in specs}
    by_prefix = prefix_owners(specs)
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
        a._prefix_owners = by_prefix
        agents[s.id] = a
    return agents


def build_reviewer(review_spec: AgentSpec, target: AgentSpec, registers: Registers, llm: LLM,
                   kind: str = "model"):
    """One reviewer instance per work product, never the author's instance.

    kind="rules" reviews deterministically from the checklist and needs no model — the whole
    chain then runs with no API key at all."""
    per_wp = review_spec.model_copy(update={"id": f"{review_spec.id}:{target.work_product}"})
    if kind == "rules":
        return RuleReviewAgent(per_wp, target, registers.checklists, registers.generated)
    return ReviewAgent(per_wp, target, registers.reference.conventions_only(), registers, llm)
