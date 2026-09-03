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

# Any heading that opens with something id-shaped: `## HZ-1 — Loss of signal`, `### HZ-nnn`, …
# Group 1 hashes, 2 prefix, 3 number or placeholder, 4 trailing title text.
HEADING_ID_RE = re.compile(
    r"^(#{1,6})\s+([A-Z][A-Z0-9]{1,7})-(\d{1,9}|[nN]{2,4}|#{2,4}|[xX]{2,4})\s*(?:[-–—:|)]\s*)?(.*?)\s*$")
PLACEHOLDER_RE = re.compile(r"\A(?:[nN]{2,4}|#{2,4}|[xX]{2,4})\Z")

# Anything a human might type for an id, in a spreadsheet cell or a heading.
LOOSE_ID_RE = re.compile(r"\A\s*([A-Za-z][A-Za-z0-9]{1,7})[\s_\-–—.:]*(\d{1,9})\s*\Z")


def canonical(raw: str | None) -> str | None:
    """One id spelling for the whole application: `sr 1`, `SR_001`, `sr-1` → `SR-001`.

    None when there is nothing id-shaped to salvage — the caller then assigns a fresh id
    rather than refusing the input. Nothing in the framework rejects work over an id.
    """
    m = LOOSE_ID_RE.match(raw or "")
    return f"{m.group(1).upper()}-{int(m.group(2)):03d}" if m else None


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


def normalise_items(text: str, allowed: list[str], work_product: str,
                    owners: dict[str, tuple[str, str]] | None = None) -> tuple[str, list[str]]:
    """Deterministic id pass — the framework owns item ids, the model owns the content.

    A model is good at hazards and bad at bookkeeping, so nothing downstream depends on it
    getting ids right. Applied to every authored work product before the gate sees it:

      `## HZ-1 — Loss of signal`  ->  `### HZ-001` + `- title: Loss of signal`  (level, padding, title)
      `### HZ-nnn`                ->  `### HZ-004`      placeholder numbered by the framework
      `### HZ-001` (twice)        ->  second becomes the next free number
      `### AOU-001` in HARA       ->  demoted to `####` + a line naming the owning work product,
                                      because AOU is not a HARA id — the text is kept, the false
                                      trace is not (this is what used to fail the gate outright)

    Numbers are assigned above the highest already claimed for that prefix, never reused, and
    references to ids the pass merely re-padded are rewritten with it. Returns (text, notes).
    """
    owners = owners or {}
    allowed_set = set(allowed)
    lines = text.splitlines()

    claimed: dict[str, set[int]] = {}          # first pass: numbers the document already holds
    for line in lines:
        m = HEADING_ID_RE.match(line)
        if m and m.group(2) in allowed_set and not PLACEHOLDER_RE.match(m.group(3)):
            claimed.setdefault(m.group(2), set()).add(int(m.group(3)))

    def next_free(prefix: str) -> int:
        used = claimed.setdefault(prefix, set())
        n = max(used, default=0) + 1
        used.add(n)
        return n

    out: list[str] = []
    notes: list[str] = []
    remap: dict[str, str] = {}                 # only pure re-paddings — safe to rewrite in the body
    seen: set[str] = set()

    for line in lines:
        m = HEADING_ID_RE.match(line)
        if not m:
            out.append(line)
            continue
        hashes, prefix, number, title = m.groups()
        old = f"{prefix}-{number}"

        if prefix not in allowed_set:          # belongs to another work product — never a local item
            wp, agent = owners.get(prefix, (None, None))
            home = f"{wp} (owner `{agent}`)" if wp else "another work product"
            out.append(f"{'#' * max(4, len(hashes))} {old}" + (f" — {title}" if title else ""))
            out.append(f"_Not a {work_product} item: `{prefix}-nnn` ids belong to {home}. Text kept as commentary._")
            notes.append(f"{old}: {prefix} is not a {work_product} prefix — demoted to commentary, belongs to {wp or 'another work product'}")
            continue

        if PLACEHOLDER_RE.match(number):
            new = f"{prefix}-{next_free(prefix):03d}"
            notes.append(f"{old} -> {new} (id assigned by the framework)")
        else:
            new = f"{prefix}-{int(number):03d}"
            if new in seen:                    # duplicate: keep the first, renumber this one
                new = f"{prefix}-{next_free(prefix):03d}"
                notes.append(f"{old}: duplicate id -> {new}")
            elif new != old:
                remap[old] = new
                notes.append(f"{old} -> {new} (numbering normalised)")

        seen.add(new)
        out.append(f"### {new}")
        if title:                              # a trailing [PENDING: …] marker stays a line of its own
            out.append(title if title.startswith("[") else f"- title: {title}")

    result = "\n".join(out)
    if remap:                                  # simultaneous substitution — no cascading rewrites
        pattern = re.compile(r"\b(?:" + "|".join(re.escape(k) for k in remap) + r")\b")
        result = pattern.sub(lambda m: remap[m.group(0)], result)
    return result, notes


def find_pending(text: str) -> list[str]:
    return [m.group(1) for m in PENDING_RE.finditer(text)]


def find_refs(text: str, prefix: str) -> set[str]:
    """All IDs with a given prefix mentioned anywhere in the text."""
    return {f"{p}-{n}" for p, n in ID_RE.findall(text) if p == prefix}


def all_ids(text: str) -> set[str]:
    return {i.id for i in parse_items(text)}
