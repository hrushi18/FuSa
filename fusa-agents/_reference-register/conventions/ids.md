### Convention: identifiers
- Every traceable item is a Markdown heading `### <PREFIX>-<nnn>` where PREFIX is the work-product id
  (`SG`, `TSR`, `TSC`, `SM`, `FM` for failure modes, `HSR`, `SSR`, …) and nnn is zero-padded, ≥3 digits.
- Directly under the heading, one bullet per attribute: `- key: value`. Mandatory keys per work product are
  listed in its checklist. Common keys: `parent`, `asil`, `sm`, `text`, `rationale`, `verification`.
- `parent:` names exactly one upstream id. Multiple parents → split the item, except where a method
  gives a second link its own field (a fault tree writes a repeated basic event once and lists the
  other gates it feeds in `also_under:`). The gate warns on a second `parent:` rather than accepting
  it silently: two links recorded as one is an untraceable trace.
- `sm:` lists safety mechanisms by id only (`SM-001, SM-004`). Never describe a mechanism outside SM-CATALOG.
- Ids are never reused, renumbered or reassigned. Deleted items keep their id with `- status: withdrawn`.
- Missing inputs: `[PENDING: <what is missing> <- <agent-id>]` — never a guess.
- **Numbers are assigned by the framework, not by the author.** Write `### <PREFIX>-nnn`; the id pass
  fills the number in, pads it to three digits and resolves duplicates before the gate runs.
- A prefix belongs to exactly one work product. An item whose prefix is owned elsewhere is demoted to a
  `####` commentary block naming its owner — the text stays, the false trace does not. Such a block is
  correct output, not a review finding; the missing item is raised in the owning work product instead.

### Convention: checklist rules
- A checklist item that a machine can decide carries a `rule:` block and is executed, not read:
  `rule: {kind: fields, require: [severity, exposure, controllability, rationale]}`.
  Kinds: `fields`, `field_in`, `refs`, `time_budget`, `asil_inherit`, `aux`, `matches`, `defined_once`.
- An item with no `rule:` is a matter of judgement and is reported as a `minor` finding naming its
  clause — the confirmation review a person owes (26262-8 §9), recorded rather than assumed.
- Items marked `check: structural` belong to the gate and are never reported twice.
- Every work product ends with a `## Open points` section naming each `[PENDING: …]` it contains
  (rule `pending_listed`), and cites in its body each clause it is responsible for
  (rule `cites_clauses`). The markers stay beside the item they concern; the section is the index.
