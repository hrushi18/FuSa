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
python -m fusa run-all
python -m fusa status                      # live board
python -m fusa gate TSC                    # re-run the structural gate on a work product
python -m fusa metrics input/fmeda-failure-modes.csv --asil D
python -m fusa import-reqif input/customer-requirements.reqif --work-product SYS-REQ --prefix CR --id-attribute req_id
python -m fusa export-reqif TSR                       # -> _generated/TSR/TSR.reqif
python -m fusa aspice                                 # base-practice coverage over the status board
pytest
```

Env switches: `FUSA_MODEL` (default `claude-sonnet-5`), `FUSA_DRY_RUN=1`, `FUSA_STRICT_PENDING=1`
(downstream may not start while upstream has PENDING markers), `FUSA_ROOT`.

## How the principles are enforced (not just stated)

| Principle | Where it is enforced |
|---|---|
| One home per knowledge type | five `Registers` classes over five directories; agents never read across them |
| Clause-precise citation | agents receive only the clause ids declared in `agents.yaml`; text lives in `_clause-register` |
| Defined once, referenced everywhere | `gate.py` rejects any `SM-nnn` not defined in `SM-CATALOG` |
| Pending is a valid state | `[PENDING: … <- agent]` grammar; counted by the gate; never a review finding by itself |
| Deterministic where it counts | ids, parents, coverage: `tools/ids.py` + `gate.py`; SPFM/LFM/PMHF: `tools/metrics.py` (`tools: [metrics]` in the spec) |
| Independent review | `ReviewAgent` is constructed on `ConventionsView`, which has no `.method()`; asserted in code and in tests |
| Feedback loop | a reviewer finding with `returns_to: <agent>` puts that upstream work product into `REWORK` |

## V-cycle coverage — three kinds of building block

| Kind | `kind:` in agents.yaml | Produces its content by | Examples shipped |
|---|---|---|---|
| Authoring agent | `authoring` | model + method + clauses + upstream WPs | SADS, TSR, TSC, SM-CATALOG, FMEA, FMEDA, **TARA** (ISO 21434) |
| Tool-runner agent | `runner` | executing an external tool and parsing its report | **sw-static-analysis** (cppcheck/MISRA XML), **sec-scan** (SARIF) |
| Adapter (boundary) | — (CLI) | importing/exporting a tool format | **ReqIF** in/out (`SYS-REQ`), codebeamer stub |

All three go through the same gate, the same independent reviewer and the same status board. A second
standard is a new clause register + methods + checklists (see `iso21434.yaml`, `tara.md`, `TARA.yaml`), not new code.
Tool findings carry `- returns_to: <agent>` (by severity or by tag, e.g. `CWE` → `cs-tara`), which puts the
owning upstream work product into `rework` — the same feedback loop reviewers use.

`config/aspice-map.yaml` maps work products to ASPICE base practices; `fusa aspice` reports coverage.

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

Enabled in this scaffold: `sys-sads`, `sys-tsr`, `sm-catalog`, `sys-tsc`, `sys-fmea`, `hw-fmeda`, `cs-tara`,
`sw-static-analysis`, `sec-scan`, `verification-review`; `SYS-REQ` via ReqIF import.
The remaining agents are declared with `enabled: false` so the plan, the PENDING owners and the coverage
graph are already complete. `_clause-register/*.yaml` ships clause ids and topic labels only — fill `text`
from your licensed copy of the standard. FTA and DFA method files are placeholders.

Sample inputs describe a fictional SEooC (a brake-pressure sensor module) so the chain runs out of the box.
