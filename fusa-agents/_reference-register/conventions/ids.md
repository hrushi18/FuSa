### Convention: identifiers
- Every traceable item is a Markdown heading `### <PREFIX>-<nnn>` where PREFIX is the work-product id
  (`SG`, `TSR`, `TSC`, `SM`, `FM` for failure modes, `HSR`, `SSR`, …) and nnn is zero-padded, ≥3 digits.
- Directly under the heading, one bullet per attribute: `- key: value`. Mandatory keys per work product are
  listed in its checklist. Common keys: `parent`, `asil`, `sm`, `text`, `rationale`, `verification`.
- `parent:` names exactly one upstream id. Multiple parents → split the item.
- `sm:` lists safety mechanisms by id only (`SM-001, SM-004`). Never describe a mechanism outside SM-CATALOG.
- Ids are never reused, renumbered or reassigned. Deleted items keep their id with `- status: withdrawn`.
- Missing inputs: `[PENDING: <what is missing> <- <agent-id>]` — never a guess.
