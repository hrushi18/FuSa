"""Automated gate — structural checks run on every commit of a work product.

Checks (all deterministic, no model involved):
  - front matter present and `id` matches the work product
  - item ids carry the work product's prefix
  - duplicate ids (within the work product and across the whole store)
  - orphan parents: `parent:` references an id that exists nowhere
  - gates without children: a parent id in an upstream WP that no item here derives from
    (warning by default; error when the checklist marks full-coverage as structural)
  - unknown SM references: SM-nnn used but not defined in SM-CATALOG
  - pending markers are counted, reported, and never invented away

Item ids were already made deterministic before this runs (ids.normalise_items, called by the
authoring agent), so a prefix error here means a genuine scope problem, not model sloppiness.

A failed gate blocks the analysis from reaching review.
"""
from __future__ import annotations

from collections import Counter

from .models import AgentSpec, GateResult
from .registers import GeneratedStore
from .tools import ids

SM_CATALOG = "SM-CATALOG"


def run_gate(spec: AgentSpec, content: str, store: GeneratedStore, *, require_full_coverage: bool = False,
             extra_warnings: list[str] | tuple = ()) -> GateResult:
    wp = spec.work_product
    errors: list[str] = []
    warnings: list[str] = [f"id normalised: {n}" for n in extra_warnings]

    fm = ids.parse_front_matter(content)
    if not fm:
        errors.append("front matter missing")
    elif fm.get("id") != wp:
        errors.append(f"front matter id '{fm.get('id')}' != work product '{wp}'")

    items = ids.parse_items(content)
    if not items:
        warnings.append("no `### ID` items found — nothing to trace")

    # id prefix + duplicates
    for i in items:
        if i.prefix not in spec.prefixes:
            errors.append(f"{i.id}: prefix not allowed in {wp} (allowed: {', '.join(spec.prefixes)})")
    dup = [k for k, n in Counter(i.id for i in items).items() if n > 1]
    errors += [f"duplicate id within {wp}: {d}" for d in dup]

    store_ids = store.all_ids()
    clashes = [i.id for i in items if i.id in store_ids and store_ids[i.id] != wp]
    errors += [f"id {c} already used in {store_ids[c]}" for c in clashes]

    # orphan parents
    known = set(store_ids) | {i.id for i in items}
    for i in items:
        for p in i.refs("parent"):
            if p not in known:
                errors.append(f"{i.id}: parent {p} does not exist")

    # gates without children: every item of a covered upstream must have a child here
    covered = {p for i in items for p in i.refs("parent")}
    for up in spec.covers:
        for u in store.items(up):
            if u.prefix == "AOU":          # assumptions of use flow to the safety manual, not to requirements
                continue
            if u.id not in covered:
                msg = f"{u.id} ({up}) has no child in {wp}"
                (errors if require_full_coverage else warnings).append(msg)

    # unknown safety-mechanism references
    if wp != SM_CATALOG:
        used = ids.find_refs(content, "SM")
        defined = {i.id for i in store.items(SM_CATALOG)}
        for u in sorted(used - defined):
            (errors if store.exists(SM_CATALOG) else warnings).append(
                f"{u} referenced but not defined in {SM_CATALOG}" + ("" if store.exists(SM_CATALOG) else " (catalog not yet produced)"))

    pending = ids.find_pending(content)
    return GateResult(work_product=wp, passed=not errors, errors=errors, warnings=warnings, pending=pending)
