# Validate My FuSa System — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the release validation the chain already computes into a gap report a learner can read — ✅ / ⚠️ / ❌ by V-model phase, each row linked to the module that taught that checklist.

**Architecture:** No new analysis. `report.validate()` already assesses every work product; `/api/checks` already knows what decides each checklist item; the specs carry `phase`. This joins the three and renders them. The point is that the learner's course and the project's gap report are the same list, so Success Criterion #4 holds by construction rather than by discipline.

**Tech Stack:** Python 3.11+, FastAPI, pytest. Browser: vanilla ES modules, no build step. Node (optional) for harness tests.

**Spec:** `fusa-agents/docs/superpowers/specs/2026-09-07-fusa-learning-platform-design.md` §8, §11

## Global Constraints

- **No new engine.** Everything comes from `report.validate()`, `/api/checks` and `orch.specs`. If a number here disagrees with `/report.pdf`, this view is wrong.
- **No file upload.** The brief's §4.6 asked for one; `input/` already has upload endpoints and a second ingest path would be a second source of truth. Out of scope, deliberately.
- **No build step**; ES modules only. Import `esc` from `./esc.js`, never a local copy.
- **R2** stays absolute: nothing derives an ASIL from S/E/C. The behavioural oracle in `tests/test_learn_js.py` and `tests/test_learn_tools.py` must keep passing.
- **C1/C4/R1** on any shipped content.
- Run tests: `cd fusa-agents && .venv/bin/python -m pytest tests/ -q` (**578 passing**; only goes up).
- Every task ends with `.venv/bin/python dev/mutation_audit.py` in the FOREGROUND. Two survivors are known (`progress.py:41`, `pdf.py:123`); kill or justify anything new.
- **A test that passes while covering nothing is the defect this repo keeps shipping.** For each new test, break the behaviour it names and confirm it fails. Report which tests failed for which break.

---

## File Structure

**Create:** `tests/js/validate-paths.mjs`
**Modify:** `fusa/learn/tools.py` (add `gap_report`), `fusa/ui/server.py` (one route), `fusa/ui/static/learn/tools/validate.js` (new), `nav.js` (`TOOLS` gains a fourth entry), `learn/index.html` (styles), `tests/test_learn_tools.py`, `tests/test_learn_js.py`

---

### Task 1: The gap report

**Interfaces:** `fusa.learn.tools.gap_report(orch, asil="B") -> dict`:

```python
{"verdict": "NOT_RELEASABLE", "asil": "B", "generated": "...", "basis": "...",
 "totals": {"ok": 12, "warn": 2, "missing": 2},
 "phases": [{"phase": 1, "title": "Concept & Requirements",
             "rows": [{"work_product": "HARA", "agent": "sys-hara", "state": "warn",
                       "why": ["1 unresolved [PENDING] marker(s)"],
                       "checklist_ref": "HARA", "module_id": "concept.hara" | None}]}]}
```

**The mapping — this is the whole task, and it must not invent a judgement:**

| State | Condition, from the `Assessment` |
|---|---|
| `ok` | `a.ok` is true |
| `missing` | `status == "not_started"`, or `gate_errors`, or an open `blocker`/`major` finding |
| `warn` | anything else that is not ok: `gate_warnings`, `pending_count`, open minor findings |

`why` is the assessment's own `reasons` where it has them, so this view never phrases a
verdict the report did not reach.

`phase` comes from `orch.specs` joined on `work_product` (it is not on the `Assessment`).
`module_id` is the id of the module whose `checklist_ref` equals this work product's checklist,
or `None` — a work product with no lesson yet is normal and must not error.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_learn_tools.py
def test_the_gap_report_agrees_with_the_release_report(client, workspace):
    """No new engine. If these ever disagree, one of them is lying to an assessor."""
    from fusa.orchestrator import Orchestrator
    from fusa.report import validate
    from fusa.learn.tools import gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    rep = validate(orch)
    gaps = gap_report(orch)
    assert gaps["verdict"] == rep.verdict
    flat = {r["work_product"]: r for p in gaps["phases"] for r in p["rows"]}
    assert set(flat) == {a.work_product for a in rep.work_products}
    for a in rep.work_products:
        assert (flat[a.work_product]["state"] == "ok") == a.ok


def test_a_blocked_work_product_is_missing_not_merely_warned(client, workspace):
    from fusa.models import GateResult, Status
    from fusa.orchestrator import Orchestrator
    from fusa.learn.tools import gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    orch.reg.process.update("HARA", "sys-hara", status=Status.GATE_FAILED,
                            gate=GateResult(work_product="HARA", passed=False,
                                            errors=["HZ-001 has no parent"]))
    flat = {r["work_product"]: r for p in gap_report(orch)["phases"] for r in p["rows"]}
    assert flat["HARA"]["state"] == "missing"
    assert any("parent" in w for w in flat["HARA"]["why"])


def test_every_row_carries_the_phase_its_agent_belongs_to(client, workspace):
    from fusa.orchestrator import Orchestrator
    from fusa.learn.tools import gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    by_wp = {s.work_product: s.phase for s in orch.specs}
    for p in gap_report(orch)["phases"]:
        for r in p["rows"]:
            assert by_wp[r["work_product"]] == p["phase"]


def test_a_row_links_to_the_module_that_taught_its_checklist(client, workspace):
    """The loop that makes the course and the gap report one list rather than two."""
    from fusa.orchestrator import Orchestrator
    from fusa.learn.tools import gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    flat = {r["work_product"]: r for p in gap_report(orch)["phases"] for r in p["rows"]}
    assert flat["HARA"]["module_id"] == "concept.hara"       # the sample module teaches HARA


def test_a_work_product_with_no_lesson_yet_is_not_an_error(client, workspace):
    from fusa.orchestrator import Orchestrator
    from fusa.learn.tools import gap_report
    orch = Orchestrator(root=workspace, dry_run=True)
    flat = {r["work_product"]: r for p in gap_report(orch)["phases"] for r in p["rows"]}
    assert flat["TSC"]["module_id"] is None
```

- [ ] **Step 2** Run them; watch each fail (`gap_report` does not exist).
- [ ] **Step 3** Implement `gap_report` in `fusa/learn/tools.py`, reusing `validate()` and the
      `ContentRegistry` for the module join. Do not re-derive any verdict.
- [ ] **Step 4** Add `GET /api/learn/gaps?asil=B` to `fusa/ui/server.py`, beside the other
      learn routes, following their shape.
- [ ] **Step 5** Break each mapped condition in turn (make `ok` unconditional; drop the phase
      join; hardcode `module_id`) and confirm the matching test fails. Report which.
- [ ] **Step 6** Mutation audit; commit.

---

### Task 2: The view

**Interfaces:** `fusa/ui/static/learn/tools/validate.js` exporting `renderValidate(host)`, routed
at `#/tool/validate`; `nav.js`'s `TOOLS` gains `{id: "validate", title: "Validate My FuSa System"}`.

- Phases as sections in lifecycle order, each row `✅ / ⚠️ / ❌` with the work product, its agent
  and its `why` lines.
- A row with a `module_id` links to `#/<module_id>` — "learn what this checks".
- Colours reuse `--s-passed`, `--s-needs_review`, `--c-gate_failed`. No new palette.
- The header states the same `basis` sentence the PDF states, so the two cannot disagree about
  how much of the file a model wrote.
- **Nothing generated yet** is the first-run state: say so and link to the board, exactly as the
  Traceability Lab does.

- [ ] **Step 1** Failing node-harness test in `tests/js/validate-paths.mjs`: a scripted report
      renders one section per phase, the right icon per state, and a module link only where
      `module_id` is present.
- [ ] **Step 2** Watch it fail.
- [ ] **Step 3** Implement.
- [ ] **Step 4** A guard test proving the harness fails when the icon mapping is inverted.
- [ ] **Step 5** Screenshot in a temp `FUSA_ROOT`, once with nothing generated and once after a
      deterministic run. LOOK at both.
- [ ] **Step 6** Mutation audit; commit.

---

### Task 3: The loop back from the lesson

**Interfaces:** the module view gains a line naming how this project's own file fares against
the checklist the lesson just taught.

- [ ] **Step 1** Failing test: a module with a `checklist_ref` shows its work product's current
      state; a module without one shows nothing and does not error; nothing generated shows
      nothing rather than a false ✅.
- [ ] **Step 2** Watch it fail.
- [ ] **Step 3** Implement in `module.js`, reading the row from `/api/learn/gaps`.
- [ ] **Step 4** Screenshot the HARA lesson showing its own project state.
- [ ] **Step 5** Mutation audit; commit.

---

## Done when

- `/learn#/tool/validate` shows every work product by phase with ✅/⚠️/❌ and the report's own reasons
- Its verdict and per-work-product states equal `report.validate()`'s, asserted by a test
- Rows link to the lessons that taught them, and lessons link back to the project's state
- With nothing generated, both say so and link to the board
- Suite above 578; no unjustified mutation survivors
- Every new test has been shown to fail when the behaviour it names is broken

## Not in this plan

File upload (deliberately — see Global Constraints), the landing dashboard, role paths and the
certificate PDF (rest of M5), and M4's content.
