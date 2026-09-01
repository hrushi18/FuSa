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

    def items(self, name: str, check: str | None = None) -> list[dict]:
        items = self.load(name).get("items", [])
        return [i for i in items if check is None or i.get("check") == check]

    def render(self, name: str) -> str:
        items = self.items(name)
        if not items:
            return "(no checklist)"
        return "\n".join(f"- [{i['id']}] {i['text']}  (clause {i.get('clause', '—')}; {i.get('check', 'review')})" for i in items)
