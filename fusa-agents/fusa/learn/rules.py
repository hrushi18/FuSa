"""What content has to satisfy before it is worth showing anyone.

Two of these are load-bearing rather than cosmetic. A module naming a work product the chain
does not produce teaches a lifecycle this project cannot validate, and the platform's whole
claim is that the two are the same list. And this repository is public while the content that
drives it may be an employer's: an internal hostname in the shipped sample publishes it.
"""
from __future__ import annotations

WORD_CAP = 80          # a card should read in under twenty seconds, not be a specification

# C4 — nothing that names an internal system may reach the shipped sample.
INTERNAL_PATTERNS = ("sharepoint.com", "srv.volvo.com", "setoolgtt", "swap://",
                     "Navigator", "FS-QDPR", "WBS", "Volvo")

CARD_TYPES = {"concept", "example", "why", "diagram"}
QUESTION_TYPES = {"single", "multi", "numeric", "match"}


def check_module(m: dict) -> list[str]:
    mid = m.get("id", "<no id>")
    errs: list[str] = []
    cards = m.get("cards") or []
    for n, c in enumerate(cards):
        where = f"{mid} card {n}"
        if c.get("type") not in CARD_TYPES:
            errs.append(f"{where}: unknown card type {c.get('type')!r}")
        if c.get("type") == "diagram" and not (c.get("alt") or "").strip():
            errs.append(f"{where}: a diagram needs alt text — it is the only version some readers get")
        words = len((c.get("body") or "").split())
        if words > WORD_CAP:
            errs.append(f"{where}: {words} words, over the {WORD_CAP}-word cap")

    for q in m.get("quiz") or []:
        where = f"{mid} {q.get('id', '<no id>')}"
        if q.get("type") not in QUESTION_TYPES:
            errs.append(f"{where}: unknown question type {q.get('type')!r}")
        if not (q.get("explanation") or "").strip():
            errs.append(f"{where}: needs an explanation — a wrong answer with no reason teaches nothing")
        options = q.get("options") or []
        answer = q.get("answer")
        wanted = answer if isinstance(answer, list) else [answer]
        if q.get("type") in ("single", "multi"):
            if isinstance(answer, list) != (q["type"] == "multi"):
                errs.append(f"{where}: a {q['type']} answer has the wrong shape")
            elif any(not isinstance(a, int) or not 0 <= a < len(options) for a in wanted):
                errs.append(f"{where}: answer {answer!r} is not an index into {len(options)} options")
        ref = q.get("card_ref")
        if ref is not None and not 0 <= ref < len(cards):
            errs.append(f"{where}: card_ref {ref} is past the end of {len(cards)} cards")

    check = m.get("inline_check")
    if check:
        opts = check.get("options") or []
        if not isinstance(check.get("answer"), int) or not 0 <= check["answer"] < len(opts):
            errs.append(f"{mid} inline check: answer is not an index into its options")
    return errs


def check_bundle(reg, work_products: set[str], checklists: set[str]) -> list[str]:
    """Every module's rules, plus the two links to the chain that must not rot."""
    errs: list[str] = []
    for m in reg.modules():
        errs += check_module(m)
        for wp in m.get("work_products") or []:
            if wp not in work_products:
                errs.append(f"{m['id']}: work product {wp!r} is not produced by any agent")
        ref = m.get("checklist_ref")
        if ref and ref not in checklists:
            errs.append(f"{m['id']}: checklist_ref {ref!r} has no register file")
    return errs
