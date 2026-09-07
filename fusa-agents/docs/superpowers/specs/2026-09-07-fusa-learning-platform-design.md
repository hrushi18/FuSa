# FuSa Learning & Validation Platform — design

Status: approved for planning · 2026-09-07

A second page in the existing workbench that teaches ISO 26262 from fresher level upward,
tests understanding, and validates a real safety file against the same checklist it taught.

The point of the design is that the training and the validation read **the same registers the
agent chain reads**. A learner who finishes the course can read a real gap report without
translation because it is literally the same checklist, not because two copies were kept in
sync by discipline.

---

## 1. Corrections to the original brief

Four things in the build prompt do not match the repository. They are settled here so the
plan does not inherit them.

| Brief says | Actually | Consequence |
|---|---|---|
| "22-agent FUSA system" | **30 declared agents, 16 enabled, 13 disabled**, over 7 phases | `agent_mapping` targets work products, not an agent count. No number is hardcoded in copy. |
| ASIL via "S+E+C formula", "sum < 6 → QM" | The chain uses a **36-key S×E×C lookup** in `_reference-register/asil-table.yaml`, shipped empty | The calculator reads that file. No formula is implemented. See §3. |
| Assessors check learner competence records | Single-user local, no accounts | Assessors receive the exported PDF. No assessor view is built. |
| "the two worked examples already in your source deck" | No deck exists in the repo | Content milestone blocks on the deck being supplied. Engineering milestones do not. |

## 2. Decisions

1. **Single engineer, local.** Runs as the workbench runs: `fusa ui`, no accounts, no database.
   Progress is a JSON file beside `_generated/`. Certification is a PDF the learner hands over.
2. **Separate page, shared server.** The same FastAPI app serves `/learn`. The existing
   dashboard at `/` is not rebuilt; it gains only an import of the shared token file.
3. **Vanilla ES modules, no build step.** The repo has no `package.json`, no bundler and no
   node dependency; `pip install` is the whole install story. A JS toolchain would cost
   reproducible builds and a second CI story in a project whose report states that re-running
   the same inputs produces the same file. Content is JSON, so a framework remains possible
   later without touching the content model.
4. **Content comes from the user's deck**, structured by us, preserving its wording and its
   Airbag / Service Brakes worked examples.

## 3. Licensing constraints (binding on all content and code)

The repository already refuses to reproduce normative content in two places, and this
platform must not become the hole in that policy:

- `_clause-register/*.yaml` ships **clause ids without their text**.
- `_reference-register/asil-table.yaml` ships **36 empty keys** with the instruction to fill
  them from the reader's own licensed copy, and `POST /api/asil-table` deliberately has no
  "fill with AI" path because a hallucinated ASIL is wrong all the way down the chain with
  nothing downstream able to notice.

Therefore:

- **R1.** Card and quiz text is original explanation in our own words. It cites clause ids.
  It never reproduces the standard's wording, its tables, or its figures.
- **R2.** The ASIL Calculator implements **no determination rule of its own**. It reads
  `asil-table.yaml`. An unfilled cell renders as "not yet filled — transcribe it from your
  licensed copy", with a link to fill it, and never as a guess.
- **R3.** The only values the platform states without the table are the ones the repo already
  treats as definitional and handles in code: S0, E0 and C0 are QM.
- **R4.** Worked examples use the user's own teaching cases, not extracts from the standard.

R2 has a second benefit: a learner is taught exactly the mapping their own chain applies, so
training and tool can never disagree. An additive mnemonic would disagree in specific cells.

## 4. Architecture

```
fusa/ui/
  static/
    tokens.css          NEW  shared design tokens; imported by both pages
    index.html               workbench — unchanged but for the tokens import
    learn/              NEW
      index.html             shell: left nav, top bar, main region
      app.js                 routing (hash-based), boot, progress load/save
      nav.js                 collapsible V-model tree, completion rings, status icons
      module.js              card carousel + inline check
      quiz.js                question types, scoring, feedback
      progress.js            storage interface (see §6)
      tools/
        asil.js              ASIL Calculator            (reads /api/asil-table)
        hara.js              HARA Builder
        trace.js             Traceability Lab           (reads /api/checks)
        validate.js          Validate My FUSA System    (reads /api/report, /api/checks)
  content/              NEW  authored content, shipped as package data
    groups.json              the 12 nav groups: id, display title, order
    modules/*.json
    paths.json
    glossary.json
```

`pyproject.toml` package-data widens from `"fusa.ui": ["static/*"]` to include
`static/learn/*`, `static/learn/tools/*`, `content/*.json` and `content/modules/*.json`,
or an installed copy serves a shell with no content.

New endpoints, all thin:

| Route | Purpose |
|---|---|
| `GET /learn` | the shell |
| `GET /api/learn/content` | every module + path + glossary, one payload |
| `GET /api/learn/progress` | the progress record |
| `POST /api/learn/progress` | upsert one module's attempt |
| `GET /learn/certificate.pdf` | completion record, via `fusa/pdf.py` |

Reused as-is: `/api/asil-table` (GET/POST), `/api/checks`, `/api/report`, `/api/agents`.

## 5. Content data model

One module = one lesson + one quiz. Stored one file per module so a module is reviewable as
a unit and a bad edit cannot corrupt the whole course.

```json
{
  "id": "concept.hara",
  "group": "2",
  "title": "Hazard Analysis & Risk Assessment",
  "vmodel_position": "concept",
  "clauses": ["26262-3:6"],
  "cards": [
    {"type": "concept", "title": "...", "body": "...", "alt": null},
    {"type": "example", "example_ref": "airbag", "body": "..."},
    {"type": "why",     "body": "..."},
    {"type": "diagram", "asset": "hara-anatomy.svg", "alt": "required, not optional"}
  ],
  "inline_check": {"prompt": "...", "options": ["..."], "answer": 1, "explanation": "..."},
  "quiz": [
    {"id": "q1", "type": "single", "prompt": "...", "options": ["..."], "answer": 2,
     "explanation": "...", "card_ref": 1}
  ],
  "work_products": ["HARA"],
  "checklist_ref": "HARA"
}
```

`group` is an id (`"0"`–`"11"`); its display title and order live in `content/groups.json`,
so renaming a group is one edit rather than one per module.

Two fields carry the whole validation tie-in:

- **`work_products`** — the ids the chain actually produces (`HARA`, `TSC`, `HW-FMEDA`, …),
  replacing the brief's `agent_mapping`. Work products are stable; agent ids and counts are not.
- **`checklist_ref`** — the `_checklist-register/<name>.yaml` this module teaches. It is what
  lets §8 say "you learned these 6 checks; your file fails 2 of them."

A CI test asserts every `work_products` entry exists in `config/agents.yaml` and every
`checklist_ref` resolves to a register file — so content cannot drift from the chain silently.

**Card types:** `concept`, `example`, `why`, `diagram`. **Question types:** `single`,
`multi`, `numeric`, `match` (drag term → ASIL). `explanation` is mandatory on every question;
`card_ref` points back at the card that teaches it.

**Pacing (§5.4 of the brief):** a card body is capped at 80 words, enforced by the same CI
test. `alt` is mandatory on every `diagram` card.

## 6. Progress model

```json
{"version": 1,
 "modules": {"concept.hara": {"status": "passed", "best": 0.83, "attempts": 3,
                              "last_seen": "2026-09-07T…", "cards_seen": 6}},
 "tools":   {"hara_builder": {"scenarios_done": ["airbag", "brakes"]}}}
```

Written to `_generated/learning-progress.json` — already gitignored, already where per-project
state lives. Statuses are the brief's four: `not_started`, `in_progress`, `passed`,
`needs_review`, and drive one icon set used identically in the nav tree, the dashboard cards
and the path view.

`progress.js` is a **storage interface** with one file-backed implementation. Multi-user is
out of scope, but nothing in the UI reaches past this interface, so it stays addable.

Pass threshold is **configurable, defaulting to 0.8** (`FUSA_LEARN_PASS_MARK`). An arbitrary
fixed number gating a competence record is something an assessor will ask you to justify.

## 7. The three tools

**ASIL Calculator.** Three selects (S0–S3, E0–E4, C0–C3) → the value from `asil-table.yaml`.
Any zero class → QM, stated as definitional (R3). A blank cell renders as unfilled with an
inline "fill it now" that `POST`s to the existing `/api/asil-table`. Shows *which* of the 36
keys was consulted, so the learner sees it is a lookup, not arithmetic. Doubles as a better
filling UI than the bare grid the dashboard has today.

**HARA Builder.** Guided form: Item → guideword → Hazard → Situation → Hazardous event →
S/E/C → ASIL (via the calculator) → Safety Goal. Three scenarios: Airbag worked through with
answers shown, Service Brakes with answers revealed only on submission, and a third novel
scenario. Output is shaped like a row of `input/hazards.csv`, so a learner can export their
exercise and feed it to the real chain.

**Traceability Lab.** Builds a deliberately broken trace from real registers: Safety Goal →
FSR → TSR → HW/SW req → test case → result. The learner identifies (a) the broken link,
(b) the phase that owns the fix, (c) the evidence that would close it — the brief's rubric.
Cases are generated from `/api/checks` plus seeded defects, so they reflect this project's
actual work products rather than invented ones.

## 8. Validate My FUSA System

Not a new engine. A learner-facing rendering of what `report.validate()` already computes.

| Brief | Source |
|---|---|
| ✅ present | assessment `ok`, gate passed, reviewed |
| ⚠️ present but not traced | gate warnings, `[PENDING]` markers, open minor findings |
| ❌ missing | `not_started`, gate failed, open blocker/major |
| grouped by V-model phase | `spec.phase`, the 7 phases already on the board |

Each row links back to the module whose `checklist_ref` covers it — the loop that makes
Success Criterion #4 structural rather than aspirational. File upload is **not** built:
the chain already ingests `input/` via the existing upload endpoints, and a second ingest
path would be a second source of truth.

## 9. Design system

`tokens.css` holds what both pages share, extracted from the workbench's existing palette so
nothing is re-invented: surface/line/text colours, the provenance families (`--p-machine`
teal, `--p-model` violet, `--p-human` amber), status colours, spacing and type scale.

**ASIL colours are new and must be used identically everywhere** they appear — nav badges,
calculator output, quiz feedback, gap report: `QM` neutral, `A`→`D` ascending severity.
Defined once as `--asil-qm … --asil-d`.

Responsive per the brief: left panel collapses to a drawer under 900px (the breakpoint the
workbench already uses); cards stay single-column and swipeable.

**Cut from the brief:** the §5.1 right-rail glossary. A click-to-define on the term itself
does the same job without a third column competing with the nav for width. `glossary.json`
still ships and powers the inline definitions and search.

## 10. Testing

Python side, in the existing pytest suite:
- content schema validation for every module file (required fields, card word cap, `alt` on
  diagrams, `explanation` on every question, answer index in range)
- every `work_products` id exists in `config/agents.yaml`; every `checklist_ref` resolves
- progress round-trips; a corrupt progress file degrades to `not_started`, never a crash
- `/api/learn/*` contract tests, as `tests/test_ui.py` does today
- the calculator endpoint never invents a value for an unfilled cell — the R2 guard, tested

JS has no test runner and this design does not add one. Logic that deserves testing (ASIL
lookup, scoring, progress transitions) lives behind the Python endpoints or is thin enough to
verify through the served-HTML marker tests the repo already uses.

## 11. Milestones

Each ships independently. Only M4 blocks on the deck.

| # | Ships | Blocked by deck |
|---|---|---|
| M1 | `/learn` shell: nav tree, rings, status icons, progress persistence, placeholders | no |
| M2 | Module renderer + quiz engine, wired to progress | no |
| M3 | ASIL Calculator, HARA Builder, Traceability Lab | no |
| M4 | Content: groups 0–2 first as the reference implementation, then 3–9 | **yes** |
| M5 | Landing dashboard, Validate-my-FUSA view, role paths, PDF certificate | no |

M5 carries the brief's §5.2 dashboard — path cards, continue-where-you-left-off, quick-launch
tiles for the three tools, recent scores — because it needs paths and enough modules to be
worth landing on.

**Plan boundaries.** This spec covers all five milestones so the shape is settled, but it is
not one implementation plan. **M1+M2 form the first plan** (shell, renderer, quiz, progress —
one coherent vertical slice that ends with a usable course of placeholder modules). M3, M4 and
M5 each get their own plan afterwards, written against whatever M1–M2 actually produced.

## 12. Out of scope

Accounts, multi-user, assessor views over others' records, file upload for §4.6, a JS build
step or framework, revamping the existing workbench UI, and any authoring of ISO 26262
content not derived from the user's deck.

## 13. Open

- The deck. M4 cannot start without it.
- Group 10's four role paths need the user's call on which modules belong to each; the brief's
  sketch is a starting point, not a decision.
- Whether the third HARA Builder scenario (steering assist) is authored by us or supplied.
