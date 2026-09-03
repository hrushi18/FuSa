"""GeneratorAgent — renders one work product from a table, in the house grammar.

Same interface as AuthoringAgent (`run() -> markdown`), so the orchestrator, gate, reviewer and
status board treat a generated work product exactly like an authored one.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .. import config
from ..models import AgentSpec
from ..registers import Registers
from ..tools import ids


class InputMissing(FileNotFoundError):
    """A table the generator needs is not there. Becomes a PENDING marker, never a guess."""


@dataclass
class Row:
    """One generated item: an id (or None to be assigned) and its `- key: value` bullets."""
    fields: dict[str, str]
    id: str | None = None
    prefix: str = ""
    note: str | None = None                       # free text under the bullets, e.g. a PENDING
    parent_of: "Row | None" = None                # link to another row; resolved once ids exist


@dataclass
class Result:
    rows: list[Row] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)   # "<what is missing> <- <owner>"
    intro: str = ""


def read_table(path: Path, required: list[str]) -> list[dict]:
    """A CSV of engineering decisions. Comments and blank lines are skipped, as in the FMEDA input."""
    if not path.exists():
        raise InputMissing(f"input/{path.name} not provided")
    from ..tools.metrics import uncommented
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(uncommented(f))
        header = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in required if c not in header]
        if missing:
            raise ValueError(f"{path.name}: missing column(s) {', '.join(missing)}; found "
                             f"{', '.join(header) or '(no header row)'}")
        rows = []
        for n, rec in enumerate(reader, start=2):
            clean = {(k or "").strip(): (v or "").strip() for k, v in rec.items() if k}
            if any(clean.values()):
                clean["_row"] = str(n)
                rows.append(clean)
    if not rows:
        raise ValueError(f"{path.name}: no data rows")
    return rows


class GeneratorAgent:
    def __init__(self, spec: AgentSpec, registers: Registers):
        assert spec.generator, f"{spec.id}: deterministic authoring needs a `generator:` block"
        self.spec = spec
        self.reg = registers
        self.cfg = spec.generator
        self.last_notes: list[str] = []

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def work_product(self) -> str:
        return self.spec.work_product

    def run(self) -> str:
        from .kinds import GENERATORS
        kind = self.cfg.get("kind")
        fn = GENERATORS.get(kind)
        if fn is None:
            return self._render(Result(pending=[f"unknown generator kind '{kind}' "
                                                f"(have: {', '.join(sorted(GENERATORS))}) <- {self.spec.id}"]))
        try:
            result = fn(self.cfg, self.reg, self.spec)
        except (InputMissing, ValueError) as e:   # a missing or malformed table is a PENDING, not a crash
            result = Result(pending=[f"{e} <- project"])
        return self._render(result)

    def _assign_ids(self, rows: list[Row]) -> None:
        """Ids given in the table are kept; the rest are numbered above the highest already held,
        so adding a row later never renumbers an existing item (`ids.canonical` spelling rules)."""
        default = self.spec.prefixes[0]
        for r in rows:
            r.id = ids.canonical(r.id) if r.id else None
            r.prefix = (r.id.rsplit("-", 1)[0] if r.id else (r.prefix or default))
        used: dict[str, int] = {}
        for r in rows:
            if r.id:
                px, num = r.id.rsplit("-", 1)
                used[px] = max(used.get(px, 0), int(num))
        seen: set[str] = set()
        for r in rows:
            if not r.id or r.id in seen:
                if r.id in seen:
                    self.last_notes.append(f"{r.id}: duplicate id in the input table")
                used[r.prefix] = used.get(r.prefix, 0) + 1
                r.id = f"{r.prefix}-{used[r.prefix]:03d}"
            seen.add(r.id)
        for r in rows:                            # links are made after every id is known
            if r.parent_of is not None:
                r.fields["parent"] = r.parent_of.id

    @staticmethod
    def _open_points(content: str) -> str:
        """One index of everything still open. The markers themselves stay where they belong,
        beside the item they concern; this lists them without repeating the `[PENDING: …]`
        syntax, so nothing is counted twice."""
        pending = ids.find_pending(content)
        if not pending:
            return ""
        return "\n## Open points\n\n" + "\n".join(f"- {p}" for p in pending) + "\n"

    def _render(self, result: Result) -> str:
        s = self.spec
        self._assign_ids(result.rows)
        out = [f"---\nid: {s.work_product}\ntitle: {s.title}\nagent: {s.id}\n"
               f"date: {date.today().isoformat()}\nclauses: {', '.join(s.clauses) or '—'}\n"
               f"status: draft\ngenerated_from: {self.cfg.get('input', '—')}\n---\n",
               f"# {s.title}\n",
               result.intro or f"Generated deterministically from input/{self.cfg.get('input', '—')}. "
                               "Every value here was entered or derived, never inferred by a model.\n",
               f"Produced under {', '.join(s.clauses)}.\n" if s.clauses else ""]
        for p in result.pending:
            out.append(f"[PENDING: {p}]\n")
        for r in result.rows:
            out.append(f"### {r.id}")
            out += [f"- {k}: {v}" for k, v in r.fields.items() if v]
            if r.note:
                out.append(r.note)
            out.append("")
        content = "\n".join(out)
        content += self._open_points(content)
        content, notes = ids.normalise_items(content, s.prefixes, s.work_product, {})
        self.last_notes += notes
        return content.rstrip() + "\n"
