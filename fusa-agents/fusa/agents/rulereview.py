"""RuleReviewAgent — the independent review without a model.

The checklist is already a program: most of its items say "every X carries field Y", "this id
must resolve", "this number must not exceed that one". Those are decidable, so a rule executes
them and the result is reproducible, free, and identical on every run.

What is left is genuinely a matter of judgement — is the hazard list complete, is a rationale
sound — and no reviewer, model or otherwise, settles that on its own. Those items are reported
as `minor` findings naming the clause, so the confirmation review a person owes (ISO 26262-8 §9)
is visible in the work product, the dashboard and the release report instead of being implied.

A rule lives in the checklist entry, next to the item it decides:

    - {id: HARA-01, text: every hazard names ..., clause: "26262-3:6.4.2", check: review,
       rule: {kind: fields, require: [function, malfunction, hazardous_event, situation]}}
"""
from __future__ import annotations

import re

from ..models import AgentSpec, Finding, ReviewVerdict
from ..registers import ChecklistRegister, GeneratedStore
from ..tools import ids

ASIL_ORDER = ["QM", "A", "B", "C", "D"]
DURATION_RE = re.compile(r"([\d.]+)\s*(ms|milliseconds?|s|sec|seconds?|us|µs|microseconds?|min)\b", re.I)
UNIT_MS = {"us": 0.001, "µs": 0.001, "microsecond": 0.001, "microseconds": 0.001,
           "ms": 1.0, "millisecond": 1.0, "milliseconds": 1.0,
           "s": 1000.0, "sec": 1000.0, "second": 1000.0, "seconds": 1000.0, "min": 60000.0}


def duration_ms(raw: str) -> float | None:
    """`5 ms`, `1 s`, `250us` → milliseconds. None when there is no parsable duration."""
    m = DURATION_RE.search(raw or "")
    return float(m.group(1)) * UNIT_MS[m.group(2).lower()] if m else None


class Ctx:
    """What a rule may look at: the work product, its items, and the wider store."""

    def __init__(self, target: AgentSpec, content: str, generated: GeneratedStore, cfg: dict):
        self.target = target
        self.content = content
        self.generated = generated
        self.cfg = cfg
        self.items = ids.parse_items(content)

    def scoped(self) -> list[ids.Item]:
        """Items the rule applies to: all of them, one id prefix (`prefix: SG`), or those
        matching a `where:` filter — so a rule can say exactly what its checklist item says.
        A SAFE failure mode has no safety mechanism by definition, and demanding one of it
        would be the rule disagreeing with the analysis rather than checking it."""
        prefix = self.cfg.get("prefix")
        items = [i for i in self.items if not prefix or i.prefix == prefix]
        where = self.cfg.get("where")
        if not where:
            return items
        field = where["field"]

        def keep(item: ids.Item) -> bool:
            value = (item.fields.get(field) or "").strip()
            if "gt" in where or "lt" in where:          # a claim of 0 is no claim at all
                try:
                    number = float(value.rstrip("%"))
                except ValueError:
                    return False
                return number > where["gt"] if "gt" in where else number < where["lt"]
            if "is" in where:
                return value.upper() == str(where["is"]).upper()
            if "not" in where:
                return value.upper() != str(where["not"]).upper()
            if "in" in where:
                return value.upper() in [str(v).upper() for v in where["in"]]
            if "not_in" in where:
                return value.upper() not in [str(v).upper() for v in where["not_in"]]
            return bool(value) if where.get("present", True) else not value

        return [i for i in items if keep(i)]


def rule_fields(ctx: Ctx) -> list[str]:
    """Every item in scope carries these `- key:` bullets, non-empty."""
    required = ctx.cfg.get("require", [])
    out = []
    for item in ctx.scoped():
        missing = [f for f in required if not (item.fields.get(f) or "").strip()]
        if missing:
            out.append(f"{item.id}: missing {', '.join(missing)}")
    return out


def rule_field_in(ctx: Ctx) -> list[str]:
    """A field's value is one of a fixed set (asil, classification, treatment …)."""
    field, allowed = ctx.cfg["field"], [str(v) for v in ctx.cfg["values"]]
    out = []
    for item in ctx.scoped():
        value = (item.fields.get(field) or "").strip()
        if value and value not in allowed:
            out.append(f"{item.id}: {field} '{value}' is not one of {', '.join(allowed)}")
    return out


def rule_refs(ctx: Ctx) -> list[str]:
    """Every id referenced in a field exists somewhere in the store."""
    field = ctx.cfg["field"]
    known = set(ctx.generated.all_ids()) | {i.id for i in ctx.items}
    out = []
    for item in ctx.scoped():
        if ctx.cfg.get("required") and not item.refs(field):
            out.append(f"{item.id}: no {field} reference")
        out += [f"{item.id}: {field} {r} does not exist" for r in item.refs(field) if r not in known]
    return out


def rule_time_budget(ctx: Ctx) -> list[str]:
    """Detection + reaction must fit inside the fault tolerant time interval."""
    out = []
    for item in ctx.scoped():
        fdt, frt, ftti = (duration_ms(item.fields.get(k, "")) for k in ("fdt", "frt", "ftti"))
        if ftti is None or (fdt is None and frt is None):
            continue                       # nothing claimed here; a fields rule covers absence
        budget = (fdt or 0) + (frt or 0)
        if budget > ftti:
            out.append(f"{item.id}: fdt+frt {budget:g} ms exceeds ftti {ftti:g} ms")
    return out


def rule_asil_inherit(ctx: Ctx) -> list[str]:
    """ASIL is the parent's unless a decomposition is cited (26262-9:5)."""
    parents = {i.id: i for wp in ctx.generated.all_work_products() for i in ctx.generated.items(wp)}
    out = []
    for item in ctx.scoped():
        asil = (item.fields.get("asil") or "").strip().upper()
        if asil not in ASIL_ORDER:
            continue
        for pid in item.refs("parent"):
            parent = parents.get(pid)
            p_asil = (parent.fields.get("asil") or "").strip().upper() if parent else ""
            if p_asil not in ASIL_ORDER:
                continue
            if ASIL_ORDER.index(asil) != ASIL_ORDER.index(p_asil) and not item.fields.get("decomposition"):
                out.append(f"{item.id}: asil {asil} differs from parent {pid} ({p_asil}) "
                           "with no decomposition cited")
    return out


def rule_aux(ctx: Ctx) -> list[str]:
    """A companion artefact produced by tooling is attached (e.g. metrics.md)."""
    name = ctx.cfg["file"]
    path = ctx.generated.path / ctx.target.work_product / name
    return [] if path.exists() else [f"{name} is not attached to {ctx.target.work_product}"]


def rule_matches(ctx: Ctx) -> list[str]:
    """A required construct appears in the document (a Mermaid diagram, a section)."""
    pattern = ctx.cfg["pattern"]
    return [] if re.search(pattern, ctx.content, re.I | re.M) else [ctx.cfg.get("says", f"no match for /{pattern}/")]


def rule_defined_once(ctx: Ctx) -> list[str]:
    """Ids of this prefix are defined here and referenced, never redefined elsewhere."""
    prefix = ctx.cfg.get("prefix") or ctx.target.prefixes[0]
    out = []
    for wp in ctx.generated.all_work_products():
        if wp == ctx.target.work_product:
            continue
        foreign = [i.id for i in ctx.generated.items(wp) if i.prefix == prefix]
        if foreign:
            out.append(f"{prefix} items also defined in {wp}: {', '.join(sorted(foreign))}")
    return out


OPEN_POINTS_RE = re.compile(r"^#{1,6}\s*open points\b.*$", re.I | re.M)


def rule_pending_listed(ctx: Ctx) -> list[str]:
    """Every PENDING marker is also named in the open-points section.

    A marker buried beside the item it belongs to is easy to miss when reading the document as
    a reviewer or an assessor would; the section is the one place that has to be complete.
    """
    pending = ids.find_pending(ctx.content)
    if not pending:
        return []                                  # nothing open: no section needed
    m = OPEN_POINTS_RE.search(ctx.content)
    if not m:
        return [f"{len(pending)} open point(s) but no `## Open points` section"]
    section = ctx.content[m.end():]
    nxt = re.search(r"^#{1,2}\s+\S", section, re.M)  # the section runs to the next top-level heading
    section = section[:nxt.start()] if nxt else section
    return [f"open point not listed in the section: {p[:80]}" for p in pending if p.strip() not in section]


def rule_cites_clauses(ctx: Ctx) -> list[str]:
    """The body cites every clause this work product is responsible for.

    Front matter is excluded: listing a clause in the header is bookkeeping, citing it in the
    text is the claim the checklist is after.
    """
    if ctx.target is None or not ctx.target.clauses:
        return []
    body = ids.FRONT_MATTER_RE.sub("", ctx.content)
    return [f"clause {c} is declared for this work product but never cited in the body"
            for c in ctx.target.clauses if c not in body]


RULES = {"fields": rule_fields, "field_in": rule_field_in, "refs": rule_refs,
         "time_budget": rule_time_budget, "asil_inherit": rule_asil_inherit,
         "aux": rule_aux, "matches": rule_matches, "defined_once": rule_defined_once,
         "pending_listed": rule_pending_listed, "cites_clauses": rule_cites_clauses}


class RuleReviewAgent:
    """Same interface as ReviewAgent, no model. Built on the checklist, never the method."""

    def __init__(self, spec: AgentSpec, target: AgentSpec,
                 checklists: ChecklistRegister, generated: GeneratedStore):
        assert not hasattr(checklists, "method"), "reviewer must not receive the authoring method"
        self.spec = spec
        self.target = target
        self.checklists = checklists
        self.generated = generated

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def work_product(self) -> str:
        return self.target.work_product

    def run(self, content: str) -> ReviewVerdict:
        findings: list[Finding] = []
        name = self.target.checklist or self.target.work_product
        for entry in self.checklists.items(name):
            if entry.get("check") == "structural":
                continue                    # the gate decided it already; never report it twice
            findings += self._apply(entry, content)
        blocking = [f for f in findings if f.severity in ("blocker", "major")]
        return ReviewVerdict(work_product=self.target.work_product, reviewer=self.spec.id,
                             verdict="rework" if blocking else "approved", findings=findings)

    def _apply(self, entry: dict, content: str) -> list[Finding]:
        cfg = entry.get("rule")
        clause = entry.get("clause")
        if not cfg:                          # nothing decidable here: a person owes this one
            return [Finding(id=entry["id"], severity="minor", checklist_item=entry.get("text"),
                            clause=clause, description=f"confirmation review required (no automatable "
                                                       f"rule): {entry.get('text', '')}")]
        fn = RULES.get(cfg.get("kind"))
        if fn is None:
            return [Finding(id=entry["id"], severity="minor", checklist_item=entry.get("text"), clause=clause,
                            description=f"unknown rule kind '{cfg.get('kind')}' "
                                        f"(have: {', '.join(sorted(RULES))}) — item not checked")]
        try:
            failures = fn(Ctx(self.target, content, self.generated, cfg))
        except Exception as e:               # a broken rule must not pass the work product
            return [Finding(id=entry["id"], severity="major", checklist_item=entry.get("text"), clause=clause,
                            description=f"rule '{cfg.get('kind')}' could not be evaluated: {type(e).__name__}: {e}")]
        severity = cfg.get("severity", "major")
        return [Finding(id=f"{entry['id']}.{n}", severity=severity, checklist_item=entry.get("text"),
                        clause=clause, description=f, returns_to=cfg.get("returns_to"))
                for n, f in enumerate(failures, 1)]
