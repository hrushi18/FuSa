"""Agent base classes.

AuthoringAgent  — writes exactly one work product. Prompt = principles + method
                  + conventions + responsible clauses + upstream work products.
ReviewAgent     — reviews one work product against the checklist and clauses.
                  Deliberately built WITHOUT the method skill (ConventionsView only),
                  so the reviewer stays independent of the author (ISO 26262-8 §9).
"""
from __future__ import annotations

import json
import re
from datetime import date

from .. import config
from ..models import AgentSpec, ReviewVerdict
from ..registers import Registers, ConventionsView
from ..tools import ids
from .llm import LLM

PRINCIPLES = """\
KEY PRINCIPLES (non-negotiable)
1. One home per knowledge type: norm text, house conventions, project data and rendering never mix.
   Do not restate the norm; cite it. Do not invent conventions; follow the ones given.
2. Clause-precise citation: every normative statement names the responsible clause id (e.g. 26262-4:6.4.2).
3. Defined once, referenced everywhere: safety mechanisms exist only in SM-CATALOG; everywhere else use the SM-nnn id.
4. Pending is a valid state: if an upstream input is missing or incomplete, write
   [PENDING: <what is missing> <- <owning agent id>]  in its place. NEVER invent upstream content.
5. Deterministic where it counts: do not compute metrics or IDs by hand. Use the IDs and structure exactly as the
   house convention prescribes so tooling can parse them. Leave numbers to the metrics tool.
6. Independent review: you are the author, not the reviewer. Do not self-approve.
"""


class Agent:
    def __init__(self, spec: AgentSpec, llm: LLM):
        self.spec = spec
        self.llm = llm

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def work_product(self) -> str:
        return self.spec.work_product


class AuthoringAgent(Agent):
    def __init__(self, spec: AgentSpec, registers: Registers, llm: LLM):
        super().__init__(spec, llm)
        self.reg = registers

    # ---- prompt assembly -------------------------------------------------
    def system_prompt(self) -> str:
        s = self.spec
        parts = [
            f"You are `{s.id}`, a specialised engineering authoring agent (safety / cybersecurity / process). You produce exactly one work product: "
            f"**{s.work_product} — {s.title}** (phase {s.phase}) for a Safety Element out of Context (SEooC) developed under ISO 26262 and ISO/SAE 21434.",
            PRINCIPLES,
            "## Responsible clauses\n" + self.reg.clauses.render(s.clauses),
        ]
        if s.method:
            parts.append("## Method\n" + self.reg.reference.method(s.method))
        if s.conventions:
            parts.append("## House conventions\n" + self.reg.reference.render_conventions(s.conventions))
        if s.checklist:
            parts.append("## Definition of done (you will be reviewed against this)\n" + self.reg.checklists.render(s.checklist))
        parts.append(self._output_contract())
        return "\n\n".join(parts)

    def _output_contract(self) -> str:
        s = self.spec
        return f"""## Output contract
Return ONLY the work product as Markdown, starting with this front matter:
---
id: {s.work_product}
title: {s.title}
agent: {s.id}
date: {date.today().isoformat()}
clauses: {", ".join(s.clauses) or "—"}
status: draft
---
Then the content. Every identifiable item is a `### <PREFIX>-nnn` heading (allowed prefixes: {", ".join(s.prefixes)}) followed by `- key: value` bullets
(see conventions). Use [PENDING: ... <- agent-id] for anything you cannot derive from the inputs given."""

    def user_prompt(self) -> str:
        blocks = ["# Inputs available to you"]
        for name in self.spec.inputs:
            p = config.INPUT_DIR / name
            blocks.append(f"## input/{name}\n" + (p.read_text(encoding="utf-8") if p.exists() else f"[PENDING: input file {name} not provided <- project]"))
        for wp in self.spec.requires:
            if self.reg.generated.exists(wp):
                blocks.append(f"## Upstream work product {wp}\n" + self.reg.generated.read(wp))
            else:
                blocks.append(f"## Upstream work product {wp}\n[PENDING: {wp} not yet produced <- {self._owner(wp)}]")
        blocks.append(f"# Task\nProduce {self.spec.work_product} now, following the output contract.")
        return "\n\n".join(blocks)

    def _owner(self, wp: str) -> str:
        return getattr(self, "_owners", {}).get(wp, "unknown-agent")

    # ---- execution -------------------------------------------------------
    def run(self) -> str:
        content = self.llm.complete(self.system_prompt(), self.user_prompt(), stub=self._dry_stub)
        return self._normalise(content)

    def _normalise(self, content: str) -> str:
        content = re.sub(r"^```(?:markdown|md)?\s*\n|\n```\s*$", "", content.strip())
        if not content.startswith("---"):
            fm = self._output_contract().split("---", 1)[1].split("---")[0]
            content = f"---{fm}---\n\n" + content
        return content.rstrip() + "\n"

    def _dry_stub(self) -> str:
        """Plausible offline output: two items, parent links into the first upstream, one PENDING marker."""
        wp, s = self.spec.work_product, self.spec
        px = s.prefixes[0]
        parent = None
        for up in s.covers or s.requires:
            items = self.reg.generated.items(up)
            if items:
                parent = items[0].id
                break
        sm = "- sm: SM-001\n" if "SM-CATALOG" in s.requires else ""
        parent_line = f"- parent: {parent}\n" if parent else ""
        missing = [u for u in s.requires if not self.reg.generated.exists(u)]
        pending = f"\n[PENDING: derivation from {missing[0]} <- {self._owner(missing[0])}]\n" if missing else ""
        return f"""---
id: {wp}
title: {s.title}
agent: {s.id}
date: {date.today().isoformat()}
clauses: {", ".join(s.clauses) or "—"}
status: draft
---

# {s.title}

Dry-run content generated without a model call. Responsible clause: {s.clauses[0] if s.clauses else "n/a"}.
{pending}
### {px}-001
{parent_line}- asil: B
{sm}- text: First {wp} item (dry run).

### {px}-002
{parent_line}- asil: B
{sm}- text: Second {wp} item (dry run).
"""


class ReviewAgent(Agent):
    """Per-work-product reviewer. Receives ConventionsView (no methods) by construction."""

    def __init__(self, spec: AgentSpec, target: AgentSpec, conventions: ConventionsView, registers: Registers, llm: LLM):
        super().__init__(spec, llm)
        assert not hasattr(conventions, "method"), "reviewer must not receive the authoring method"
        self.target = target
        self.conv = conventions
        self.clauses = registers.clauses
        self.checklists = registers.checklists
        self.generated = registers.generated

    def system_prompt(self) -> str:
        return "\n\n".join([
            f"You are `{self.spec.id}`, an independent functional-safety reviewer (ISO 26262-8 confirmation measures). "
            f"You review one work product: **{self.target.work_product} — {self.target.title}**, authored by `{self.target.id}`. "
            "You did not author it and you do not share the author's method. Judge form, traceability and norm compliance.",
            "## Responsible clauses\n" + self.clauses.render(self.target.clauses),
            "## House conventions\n" + self.conv.render_conventions(self.target.conventions),
            "## Checklist (definition of done)\n" + self.checklists.render(self.target.checklist or self.target.work_product),
            "## Rules\n- [PENDING: ...] markers are acceptable; a PENDING is never a finding by itself.\n"
            "- Invented upstream content (no PENDING where an input was missing) is a blocker.\n"
            "- Structural checks (duplicate ids, orphans) were already run by tooling; do not repeat them.\n"
            "- If a finding must be fixed upstream (e.g. a missed safety goal), set `returns_to` to that agent id.",
            '## Output contract\nReturn ONLY JSON: {"verdict": "approved"|"rework", "findings": [{"id": "F-01", "severity": "blocker"|"major"|"minor", '
            '"checklist_item": "...", "clause": "...", "description": "...", "returns_to": null|"agent-id"}]}',
        ])

    def user_prompt(self, content: str) -> str:
        return f"# Work product under review: {self.target.work_product}\n\n{content}\n\n# Task\nReview and return the JSON verdict."

    def run(self, content: str) -> ReviewVerdict:
        raw = self.llm.complete(self.system_prompt(), self.user_prompt(content), stub=lambda: self._dry_stub(content))
        raw = re.sub(r"^```(?:json)?\s*\n|\n```\s*$", "", raw.strip())
        data = json.loads(raw)
        data.setdefault("work_product", self.target.work_product)
        data["reviewer"] = self.spec.id
        return ReviewVerdict.model_validate(data)

    def _dry_stub(self, content: str) -> str:
        n_pending = len(ids.find_pending(content))
        findings = [{"id": "F-01", "severity": "minor", "checklist_item": None, "clause": None,
                     "description": f"dry-run review: {n_pending} pending marker(s) noted, resolve before release", "returns_to": None}]
        return json.dumps({"verdict": "approved", "findings": findings})
