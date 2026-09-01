"""ClauseRegister — any standard, cited clause by clause.

Files: _clause-register/<standard>[-<part>].yaml  (iso26262-4.yaml, iso21434.yaml, aspice-swe.yaml ...)
    part: 3
    clauses:
      - id: "26262-3:5.4.1"
        topic: item definition content
        text: ""        # fill from your licensed copy; never distributed with this repo

Agents cite the responsible clause id. If `text` is empty the agent is told the
topic only, and the citation stays clause-precise regardless.
"""
from __future__ import annotations

from pathlib import Path

import yaml


class ClauseRegister:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._clauses: dict[str, dict] = {}
        for f in sorted(self.path.glob("*.yaml")):
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            for c in data.get("clauses", []):
                self._clauses[c["id"]] = c

    def __len__(self) -> int:
        return len(self._clauses)

    def standards(self) -> set[str]:
        """'26262-4', '21434', ... — everything before the colon."""
        return {cid.split(":")[0] for cid in self._clauses}

    def get(self, clause_id: str) -> dict | None:
        return self._clauses.get(clause_id)

    def select(self, patterns: list[str]) -> list[dict]:
        """Exact ids or prefixes such as '26262-4:6' (all of part 4 clause 6)."""
        def matches(cid: str, p: str) -> bool:
            if cid == p:
                return True
            return cid.startswith(p) and (p.endswith(":") or cid[len(p)] in ".:")

        return [c for cid, c in self._clauses.items() if any(matches(cid, p) for p in patterns)]

    def render(self, patterns: list[str]) -> str:
        sel = self.select(patterns)
        if not sel:
            return "(no clauses registered for this work product — cite by id from the list in agents.yaml)"
        lines = []
        for c in sel:
            body = c.get("text") or f"[topic: {c.get('topic', 'n/a')} — normative text not loaded]"
            lines.append(f"- **{c['id']}** — {body}")
        return "\n".join(lines)
