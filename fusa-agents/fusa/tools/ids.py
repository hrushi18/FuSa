"""ID grammar, item parsing, pending markers.

Work-product grammar (house convention, see _reference-register/conventions/ids.md):

    ---
    id: TSR
    agent: sys-tsr
    ...
    ---
    ### TSR-001
    - parent: SG-001
    - asil: B
    - sm: SM-003
    - text: The system shall ...

A missing upstream is written as   [PENDING: <what is missing> <- <agent-id>]   and never invented.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

ID_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,7})-(\d{3,})\b")
ITEM_HEADING_RE = re.compile(r"^###\s+([A-Z][A-Z0-9]{1,7}-\d{3,})\s*$", re.MULTILINE)
FIELD_RE = re.compile(r"^-\s+([a-z_]+):\s*(.*?)\s*$")
PENDING_RE = re.compile(r"\[PENDING:\s*([^\]]+?)\s*\]")
FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class Item:
    id: str
    fields: dict[str, str] = field(default_factory=dict)
    body: str = ""

    @property
    def prefix(self) -> str:
        return self.id.rsplit("-", 1)[0]

    def refs(self, key: str) -> list[str]:
        """Comma-separated ID references in a field, e.g. sm: SM-001, SM-004."""
        raw = self.fields.get(key, "")
        return [m.group(0) for m in ID_RE.finditer(raw)]


def parse_front_matter(text: str) -> dict[str, str]:
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def parse_items(text: str) -> list[Item]:
    """Split a work product into ### ID blocks and their key/value bullets."""
    items: list[Item] = []
    matches = list(ITEM_HEADING_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        item = Item(id=m.group(1), body=block.strip())
        for line in block.splitlines():
            fm = FIELD_RE.match(line.strip())
            if fm:
                item.fields[fm.group(1)] = fm.group(2)
        items.append(item)
    return items


def find_pending(text: str) -> list[str]:
    return [m.group(1) for m in PENDING_RE.finditer(text)]


def find_refs(text: str, prefix: str) -> set[str]:
    """All IDs with a given prefix mentioned anywhere in the text."""
    return {f"{p}-{n}" for p, n in ID_RE.findall(text) if p == prefix}


def all_ids(text: str) -> set[str]:
    return {i.id for i in parse_items(text)}
