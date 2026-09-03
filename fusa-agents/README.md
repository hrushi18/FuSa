# FuSa Agent Framework — ISO 26262 / SEooC (+ ISO 21434, ASPICE, tool runners, ReqIF)

An agentic framework that produces functional-safety work products with **one agent per work product**,
**one home per kind of knowledge**, a **deterministic gate**, and an **independent reviewer**.
Built for ISO 26262 SEooC; the norm, methods and checklists are data, so other standards plug in.

```
INPUTS            input/                       item definition, architecture, supplier FMEDAs, FIT data
AGENT WORKFLOW    config/agents.yaml           22+ declared agents, 7 phases, one work product each
                  fusa/agents/                 AuthoringAgent (generic, prompt assembled from registers)
REVIEW & QA       fusa/gate.py                 structural checks on every commit (deterministic)
                  fusa/agents/base.py          ReviewAgent — built WITHOUT the authoring method
                  _checklist-register/         norm-derived definition of done
DATA & KNOWLEDGE  _clause-register/            ISO 26262 clause by clause (ids + your licensed text)
                  _reference-register/         conventions/ (how docs look) + methods/ (how analyses are done)
                  _generated/                  project data written by the chain
EXECUTION         fusa/orchestrator.py         creation order · gating · status write-back · feedback loop
                  fusa/tools/                  ID grammar, PENDING markers, SPFM/LFM/PMHF
                  fusa/runners/                tool-runner agents: cppcheck/MISRA, SARIF (semgrep, CodeQL, ...) → findings
                  fusa/adapters/               ReqIF import/export; codebeamer REST stub
OUTPUTS           _generated/<WP>/<WP>.md      + <WP>.review.json, metrics.md, process-status.json
```

## Quick start

```bash
pip install -e ".[dev]"
python -m fusa plan                        # creation order from the dependency graph
FUSA_DRY_RUN=1 python -m fusa run-all      # whole chain offline, deterministic stubs, no API key
export ANTHROPIC_API_KEY=...               # then for real:
python -m fusa run sys-sads                # one agent: author → gate → independent review
python -m fusa --reviewer rules run-all    # review by executing the checklist — deterministic, no key
python -m fusa --author deterministic --reviewer rules run-all   # the whole chain from input tables: no model, no API key
python -m fusa run-all
python -m fusa status                      # live board
python -m fusa gate TSC                    # re-run the structural gate on a work product
python -m fusa metrics input/fmeda-failure-modes.csv --asil D
python -m fusa import-reqif input/customer-requirements.reqif --work-product SYS-REQ --prefix CR --id-attribute req_id
python -m fusa export-reqif TSR                       # -> _generated/TSR/TSR.reqif
python -m fusa aspice                                 # base-practice coverage over the status board
python -m fusa report --asil B                        # release validation -> _generated/VALIDATION-REPORT.md (exit 1 if not releasable)
python -m fusa template                               # write the 23-column safety-requirements Excel template (+ Description sheet)
python -m fusa template --kind fmeda                  # write the FMEDA failure-mode CSV template (also ⬇ Templates in the dashboard)
                                                      #   Requirement IDs fill themselves in (SR-nnn); `sr-1`, blanks and repeats are
                                                      #   made canonical on import — an id never rejects an upload
python -m fusa ui                                     # dashboard. The left panel offers two named runs —
                                                      #   ▶ Run without a model (your tables + checklist rules, no key)
                                                      #   ▶ Run with a model   (a model writes and reviews)
                                                      #   and exports the results: /results.csv carries the mode that
                                                      #   produced each row, so the two runs diff line for line
python -m fusa ui                                     # dashboard: live RELEASABLE/NOT RELEASABLE badge + printable report at /report
                                                      #   ⬆ Inputs: drop the filled requirements .xlsx (-> SYS-REQ) or FMEDA .csv — validated, saved, chain re-runs
                                                      #   ⬇ Excel report: /report.xlsx — Summary (verdict + lifecycle: Item→HARA→Safety Goals→FSR→TSR→Design→Verification→Safety Validation),
                                                      #      per-requirement validation status, work-product evidence, column descriptions
pytest
```

Env switches: `FUSA_PROVIDER` (`anthropic` | `grok` | `groq` | `openai` | `gemini`),
`FUSA_MODEL` (defaults: `claude-sonnet-5` / `grok-4.6` / `openai/gpt-oss-120b` / `gpt-5.6` /
`gemini-3.1-pro`), the provider's key (`XAI_API_KEY`/`GROK_API_KEY`, `GROQ_API_KEY`,
`OPENAI_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`), `FUSA_DRY_RUN=1`, `FUSA_STRICT_PENDING=1`
(downstream may not start while upstream has PENDING markers), `FUSA_ROOT`.

Runs against a **local LLM** (Ollama, LM Studio, vLLM) via `ANTHROPIC_BASE_URL`, or against
**Grok (xAI)**, **Groq (GroqCloud)**, **OpenAI** or **Gemini** — provider, model and API key
are also settable live in the dashboard (**⚙ LLM**), or once in a gitignored `.env`
(copy `.env.example`). See [docs/SOP-local-llm.md](docs/SOP-local-llm.md).

## How the principles are enforced (not just stated)

| Principle | Where it is enforced |
|---|---|
| One home per knowledge type | five `Registers` classes over five directories; agents never read across them |
| Clause-precise citation | agents receive only the clause ids declared in `agents.yaml`; text lives in `_clause-register` |
| Defined once, referenced everywhere | `gate.py` rejects any `SM-nnn` not defined in `SM-CATALOG` |
| Pending is a valid state | `[PENDING: … <- agent]` grammar; counted by the gate; never a review finding by itself |
| Deterministic where it counts | ids, parents, coverage: `tools/ids.py` + `gate.py`; SPFM/LFM/PMHF: `tools/metrics.py` (`tools: [metrics]` in the spec) |
| One id convention, no id ever throws | `ids.canonical` is the single spelling rule (`sr-1` → `SR-001`) used at both boundaries — `reqtable.normalise_ids` for the spreadsheet, `ids.normalise_items` for authored work products. Blanks are assigned, repeats renumbered, junk replaced; every change is reported, none is an error. `fusa gate` also works on an imported work product (`SYS-REQ`), which has no agent |
| Ids belong to the framework, not the model | `ids.normalise_items` runs on every authored draft before the gate: `### HZ-nnn` placeholders are numbered, `HZ-1` padded, duplicates renumbered, `## HZ-002 — title` recovered into an item + `- title:`, and an id owned by another work product (`AOU` in a HARA) is demoted to commentary naming its owner instead of failing the run |
| Independent review | `ReviewAgent` is constructed on `ConventionsView`, which has no `.method()`; asserted in code and in tests |
| Authoring without a model | `--author deterministic` (or `FUSA_AUTHOR=deterministic`) renders a work product from engineer-authored tables where a `generator:` is declared. Every enabled authoring agent has one: `hazards.csv` → HARA (ASIL by S×E×C lookup), + `safety-goals.csv`/`assumptions.csv` → SADS, + `technical-requirements.csv` → TSR, `safety-mechanisms.csv` → SM-CATALOG, + `allocation.csv` → TSC (Mermaid view drawn from the same rows), + `hardware-requirements.csv` → HSR, + `hardware-design.csv` → HW-DESIGN, `fmeda-failure-modes.csv` → HW-FMEDA (over the same parse the metrics tool uses), `failure-modes.csv` → SYS-FMEA, `assets.csv`/`threat-scenarios.csv` → TARA (risk from the house matrix). Judgement stays with the engineer, in a file that is diffable and reviewable; anything not decided is `[PENDING: … <- project]`, never a plausible default. Agents with no generator still use the model |
| Derived, not restated | a generated TSR inherits `asil` and `safe_state` from its parent goal and assembles its sentence from the method's own pattern; a TSC item reads `ftti` through the requirement to that goal, so the time-budget check compares the allocation against the goal that set it. A goal with no requirement, or a requirement with no allocation, is reported rather than left silent |
| Review without a model | `--reviewer rules` (or `FUSA_REVIEWER=rules`) executes the checklist instead of reading it to an LLM: 22 of the 34 judgement items carry a `rule:` and are decided deterministically; the rest become `minor` findings naming the clause, so the confirmation review a person owes (26262-8 §9) is visible rather than implied |
| Two named runs, not four combinations | the panel offers **Run without a model** (tables + rules, no API key) and **Run with a model**, each with its own button; the with-a-model button says why it is unavailable rather than failing when pressed. `/results.csv` and `/checks.csv` export what happened, tagged with the mode, so the two runs compare directly |
| Provenance is the interface | the dashboard's left panel answers one question per section: what is ready, how each work product is written (`TABLE` / `TOOL` / `MODEL`), what decides each of its checks (`GATE` / `RULE` / `MODEL` / `YOU`), and what needs you. Colour encodes the basis — teal reproduces, violet is a model's word, amber is yours — and clicking a mark filters the board. Authoring and review can be switched from the panel, and the header refuses to name a model the current mode never calls |
| Checklists compose | a checklist may declare `extends: generic` to inherit the house-wide items (open points, clause citation) instead of restating them; a locally redefined id wins, and inheritance is opt-in |
| Feedback loop | a reviewer finding with `returns_to: <agent>` puts that upstream work product into `REWORK` — and a generated FMEA fires the same loop from a fact, not an opinion: a failure mode with a violated safety goal and no `sm` is flagged `finding: uncovered` and returns to `sys-tsc` |

## V-cycle coverage — four kinds of building block

| Kind | `kind:` in agents.yaml | Produces its content by | Examples shipped |
|---|---|---|---|
| Authoring agent | `authoring` | model + method + clauses + upstream WPs | SADS, TSR, TSC, SM-CATALOG, FMEA, FMEDA, **TARA** (ISO 21434) |
| Tool-runner agent | `runner` | executing an external tool and parsing its report | **sw-static-analysis** (cppcheck/MISRA XML), **sec-scan** (SARIF) |
| Generator | `generator:` block | rendering engineer-authored tables, no model (`--author deterministic`) | HARA, SADS, TSR, SM-CATALOG, TSC, HSR, HW-DESIGN, HW-FMEDA, SYS-FMEA, TARA |
| Derivation | `generator:` block, no input table | reading what upstream work products already imply | **CSG** (goals for treated threats), **TSC-CLOSURE** (analysis findings back to the concept), **TEST-SPEC** (a case per requirement's own verification method), **TRACEABILITY** (the matrix, walked over `parent:` links) |
| Adapter (boundary) | — (CLI) | importing/exporting a tool format | **ReqIF** in/out (`SYS-REQ`), codebeamer stub |

All four go through the same gate, the same independent reviewer and the same status board. A second
standard is a new clause register + methods + checklists (see `iso21434.yaml`, `tara.md`, `TARA.yaml`), not new code.
Tool findings carry `- returns_to: <agent>` (by severity or by tag, e.g. `CWE` → `cs-tara`), which puts the
owning upstream work product into `rework` — the same feedback loop reviewers use.

`config/aspice-map.yaml` maps work products to ASPICE base practices; `fusa aspice` reports coverage.

`fusa --author deterministic --reviewer rules run-all` produces all sixteen enabled work products with
no API key. In the shipped sample data one is legitimately unfinished: the supply monitor's slow droop
(`SFM-007`) has no safety mechanism, so the FMEA flags it `uncovered`, the feedback loop returns TSC to
`rework`, and the three phase-7 products that depend on the concept wait rather than certify one under
rework. Cover that failure mode in `input/safety-mechanisms.csv` and the chain completes.

Still out of scope (by design, for now): executing tests on target / platform performance measurement, HLD/LLD agents
beyond the declared rows, and a real codebeamer transport. The seams for each exist (`kind: runner`, `agents.yaml`,
`fusa/adapters/codebeamer.py`).

## Status lifecycle

`not_started → (blocked) → drafted → gate_passed | gate_failed → reviewed | rework`

A downstream agent starts only when every enabled upstream is `gate_passed` or `reviewed`.
Disabled upstreams are allowed: the author marks the gap `[PENDING: …]` and the owner is named.

## Adding an agent

1. Add a row to `config/agents.yaml` (`id`, `work_product`, `phase`, `requires`, `covers`, `clauses`,
   `method`, `checklist`, `item_prefixes`, optional `tools`).
2. Write `_reference-register/methods/<method>.md` and `_checklist-register/<WP>.yaml`.
3. If it needs a deterministic tool, add a branch in `Orchestrator._run_tool`.

No Python is needed for a new authoring agent — the prompt is assembled from the registers.

## Work-product grammar

```markdown
---
id: TSR
agent: sys-tsr
clauses: 26262-4:6, 26262-8:6
---
### TSR-001
- parent: SG-001
- asil: B
- sm: SM-003
- text: The BPSM shall signal an invalid pressure status within 10 ms of detecting a sense-IC fault.
[PENDING: FTTI for SG-002 <- sys-sads]
```

## What is scaffolded vs. what you add

Enabled in this scaffold: `sys-hara`, `sys-sads`, `sys-tsr`, `sm-catalog`, `sys-tsc`, `sys-fmea`, `hw-hsr`,
`hw-design`, `hw-fmeda`, `cs-tara`, `sw-static-analysis`, `sec-scan`, `verification-review`; `SYS-REQ` via
ReqIF or Excel-template import. The chain demonstrates the full lifecycle: Item (input) → HARA (`HZ-nnn`,
S/E/C, ASIL) → Safety Goals (SADS `SG-nnn`, parents in HARA) → FSR (SYS-REQ) → TSR → Design (TSC,
SM-CATALOG, HSR, HW-DESIGN) → Verification (scans + independent review) → Safety Validation (report).
The remaining agents are declared with `enabled: false` so the plan, the PENDING owners and the coverage
graph are already complete. `_clause-register/*.yaml` ships clause ids and topic labels only — fill `text`
from your licensed copy of the standard.

Sample inputs describe a fictional SEooC (a brake-pressure sensor module) so the chain runs out of the box.
