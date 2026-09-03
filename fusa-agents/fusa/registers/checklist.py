"""ChecklistRegister — norm-derived definition of done, one file per work product.

  _checklist-register/<WP>.yaml
    work_product: TSR
    items:
      - id: TSR-CL-01
        text: every requirement has exactly one parent safety goal
        clause: "26262-4:6.4.1"
        check: structural | review        # structural = gate checks it; review = human/agent judgement
"""
from __future__ import annotations

from pathlib import Path

import yaml


class ChecklistRegister:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self, name: str) -> dict:
        p = self.path / f"{name}.yaml"
        if not p.exists():
            p = self.path / "generic.yaml"
        return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {"items": []}

    def items(self, name: str, check: str | None = None, _seen: frozenset = frozenset()) -> list[dict]:
        """A checklist's own items, preceded by those of the checklist it `extends:`.

        Front matter, id convention, open points and clause citation are house-wide requirements,
        so a work product with its own checklist inherits them rather than restating them. An id
        redefined locally wins, and inheritance is opt-in: nothing changes for a checklist that
        does not ask for it.
        """
        data = self.load(name)
        items = list(data.get("items", []))
        base = data.get("extends")
        if base and base not in _seen and base != name:
            own = {i.get("id") for i in items}
            items = [i for i in self.items(base, _seen=_seen | {name}) if i.get("id") not in own] + items
        return [i for i in items if check is None or i.get("check") == check]

    def render(self, name: str) -> str:
        items = self.items(name)
        if not items:
            return "(no checklist)"
        return "\n".join(f"- [{i['id']}] {i['text']}  (clause {i.get('clause', '—')}; {i.get('check', 'review')})" for i in items)
