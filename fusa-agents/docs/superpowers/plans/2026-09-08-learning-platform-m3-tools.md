# FuSa Learning Platform M3 — the three interactive tools

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the ASIL Calculator, the HARA Builder and the Traceability Lab — the three things a learner *does* rather than reads, and the reason spec §11's connector will read to them without translation.

**Architecture:** Three vanilla ES modules under `static/learn/tools/`, reachable from the nav and from a card. Each is backed by an endpoint that reuses what the agent chain already computes — the calculator calls `generators.kinds.determine_asil`, the lab reads `/api/checks` — so the tool and the chain cannot disagree.

**Tech Stack:** Python 3.11+, FastAPI, PyYAML, pytest. Browser: vanilla ES modules, no framework, no bundler, no npm. Node (optional) for the JS harness tests.

**Spec:** `fusa-agents/docs/superpowers/specs/2026-09-07-fusa-learning-platform-design.md` (§3 R2, §7, §9)

## Global Constraints

- **R2 is the reason this milestone exists and the easiest thing to break.** No code may implement an ASIL determination rule. The one lookup is `fusa/generators/kinds.py::determine_asil(sev, exp, ctr, table)`; the calculator calls it. Reimplementing it in Python or JavaScript — including the widely-published `S+E+C = 7/8/9/10` mnemonic — is a licensing violation and a correctness hazard, because it would disagree with whatever the user actually transcribed.
- **R3.** S0, E0 and C0 are QM by class definition; that is already inside `determine_asil` and is the only ASIL fact stated without the table.
- **An unfilled cell is never a guess.** `determine_asil` returns `(None, key)` for a missing combination. The UI renders that as "not transcribed yet" with a link to fill it, never as QM and never as blank.
- **No build step.** No `package.json`, no bundler, no npm.
- **C1/C4.** Nothing under `content/` is committed; nothing employer-internal enters the shipped sample.
- **Card body cap 80 words**; `alt` mandatory on diagram cards.
- New browser modules import the shared `esc()` from `./esc.js` — never define a local one.
- Every JS behaviour that can fail gets a node-harness test under `tests/js/`, following `tests/test_learn_js.py`. A harness that cannot fail is a defect.
- Run tests: `cd fusa-agents && .venv/bin/python -m pytest tests/ -q` (currently **492 passing**; the number only goes up).
- After each task, run `.venv/bin/python dev/mutation_audit.py` over the files you touched. A surviving mutation is a missing test unless you justify it as an equivalent mutant.

---

## File Structure

**Create:**
- `fusa/learn/tools.py` — the Python behind the tools: ASIL lookup, trace-case construction
- `fusa/ui/static/learn/tools/asil.js` — ASIL Calculator
- `fusa/ui/static/learn/tools/hara.js` — HARA Builder
- `fusa/ui/static/learn/tools/trace.js` — Traceability Lab
- `tests/test_learn_tools.py`, `tests/js/tools-paths.mjs`

**Modify:**
- `fusa/ui/server.py` — three endpoints
- `fusa/ui/static/learn/app.js` — route `#/tool/<id>`
- `fusa/ui/static/learn/nav.js` — a Tools group above the lifecycle groups
- `fusa/ui/static/learn/index.html` — tool styles
- `pyproject.toml` — package-data for `static/learn/tools/*`

---

### Task 1: The ASIL lookup endpoint

**Files:** Create `fusa/learn/tools.py`, `tests/test_learn_tools.py`. Modify `fusa/ui/server.py`.

**Interfaces:**
- Produces `fusa.learn.tools.asil_lookup(reg, sev, exp, ctr) -> dict` returning
  `{"asil": str|None, "why": str, "key": str, "filled": int, "total": int, "file": str}`.
- Produces `GET /api/learn/asil?s=S3&e=E4&c=C3` returning that dict.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_learn_tools.py
"""The calculator teaches the lookup the chain performs, by performing the same one.

Reimplementing the determination rule here — even as the well-known S+E+C mnemonic, which
does reproduce the table exactly — would put normative content this project deliberately does
not ship into the source, and would disagree with whatever the engineer actually transcribed.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(workspace):
    from fusa.ui.server import create_app
    with TestClient(create_app(root=workspace, dry_run=True)) as c:
        yield c


def fill(client, **cells):
    r = client.post("/api/asil-table", json={"values": cells})
    assert r.status_code == 200, r.text
    return r


def test_a_zero_class_is_qm_without_consulting_the_table(client):
    """S0/E0/C0 is QM by the definition of the class, which is why it needs no licensed value."""
    r = client.get("/api/learn/asil", params={"s": "S0", "e": "E4", "c": "C3"}).json()
    assert r["asil"] == "QM" and "class definition" in r["why"]


def test_a_filled_cell_comes_back_from_the_table(client):
    fill(client, **{"S3-E4-C3": "D"})
    r = client.get("/api/learn/asil", params={"s": "S3", "e": "E4", "c": "C3"}).json()
    assert r["asil"] == "D" and r["key"] == "S3-E4-C3"
    assert "table" in r["why"]


def test_an_unfilled_cell_is_reported_as_unfilled_never_guessed(client):
    """The whole reason the calculator reads a file instead of applying a formula."""
    r = client.get("/api/learn/asil", params={"s": "S2", "e": "E3", "c": "C2"}).json()
    assert r["asil"] is None
    assert r["key"] == "S2-E3-C2"


def test_the_answer_matches_what_the_chain_would_derive_for_the_same_hazard(client, workspace):
    """One lookup, two callers. If these ever disagree the platform is teaching a fiction."""
    from fusa.generators.kinds import determine_asil, load_asil_table
    from fusa.orchestrator import Orchestrator
    fill(client, **{"S3-E4-C3": "D", "S1-E1-C1": "QM"})
    orch = Orchestrator(root=workspace, dry_run=True)
    table = load_asil_table(orch.reg)
    for s, e, c in [("S3", "E4", "C3"), ("S1", "E1", "C1"), ("S2", "E2", "C2"), ("S0", "E1", "C1")]:
        chain, _ = determine_asil(s, e, c, table)
        api = client.get("/api/learn/asil", params={"s": s, "e": e, "c": c}).json()["asil"]
        assert api == chain, f"{s}-{e}-{c}: calculator said {api}, chain said {chain}"


def test_the_endpoint_reports_how_much_of_the_table_is_transcribed(client):
    before = client.get("/api/learn/asil", params={"s": "S1", "e": "E1", "c": "C1"}).json()
    assert before["filled"] == 0 and before["total"] == 36
    fill(client, **{"S1-E1-C1": "QM"})
    after = client.get("/api/learn/asil", params={"s": "S1", "e": "E1", "c": "C1"}).json()
    assert after["filled"] == 1 and after["total"] == 36


@pytest.mark.parametrize("s,e,c", [("S9", "E1", "C1"), ("", "E1", "C1"), ("S1", "E9", "C1")])
def test_a_class_outside_the_scales_is_rejected_not_looked_up(client, s, e, c):
    assert client.get("/api/learn/asil", params={"s": s, "e": e, "c": c}).status_code == 400


def test_no_source_file_implements_a_determination_rule():
    """R2, asserted rather than trusted: the mnemonic must not appear in this codebase."""
    import pathlib, re
    root = pathlib.Path(__file__).resolve().parents[1] / "fusa"
    pattern = re.compile(r"(sev\s*\+\s*exp|s\s*\+\s*e\s*\+\s*c)", re.I)
    for p in list(root.rglob("*.py")) + list(root.rglob("*.js")):
        assert not pattern.search(p.read_text(encoding="utf-8")), f"{p} looks like an ASIL formula"
```

- [ ] **Step 2: Run it and watch it fail**

`cd fusa-agents && .venv/bin/python -m pytest tests/test_learn_tools.py -q`
Expected: FAIL — 404 on `/api/learn/asil`.

- [ ] **Step 3: Write `fusa/learn/tools.py`**

```python
"""What the interactive tools need from the project, and nothing they could compute themselves.

The ASIL calculator is the reason this module exists. It performs no determination of its own:
it calls the same `determine_asil` the HARA generator calls, over the same table the engineer
transcribed from their licensed standard. A learner is therefore taught the mapping their own
chain applies, and an unfilled cell says so instead of guessing.
"""
from __future__ import annotations

from ..generators.kinds import ASIL_TABLE_FILE, determine_asil, load_asil_table

SEVERITY = ("S0", "S1", "S2", "S3")
EXPOSURE = ("E0", "E1", "E2", "E3", "E4")
CONTROLLABILITY = ("C0", "C1", "C2", "C3")


class UnknownClass(ValueError):
    """A class outside the scales. Looking it up would silently return 'not transcribed yet'
    for a combination that does not exist, which reads as a gap in the user's table."""


def asil_lookup(reg, sev: str, exp: str, ctr: str) -> dict:
    s, e, c = (v.strip().upper() for v in (sev, exp, ctr))
    for value, scale, name in ((s, SEVERITY, "severity"), (e, EXPOSURE, "exposure"),
                               (c, CONTROLLABILITY, "controllability")):
        if value not in scale:
            raise UnknownClass(f"{name} {value!r} is not one of {', '.join(scale)}")
    table = load_asil_table(reg)
    asil, why = determine_asil(s, e, c, table)
    return {"asil": asil, "why": why, "key": f"{s}-{e}-{c}", "file": ASIL_TABLE_FILE,
            "filled": sum(1 for v in table.values() if str(v).strip()),
            "total": len(SEVERITY[1:]) * len(EXPOSURE[1:]) * len(CONTROLLABILITY[1:])}
```

- [ ] **Step 4: Add the endpoint**

In `fusa/ui/server.py`, add to the docstring after the `/api/learn/progress` lines:

```
    GET  /api/learn/asil      S×E×C -> ASIL, by the same lookup the chain performs
```

Import beside the others:

```python
from ..learn.tools import UnknownClass, asil_lookup
```

Add beside the other learn routes:

```python
    @app.get("/api/learn/asil")
    def learn_asil(s: str, e: str, c: str):
        """The calculator's answer is the chain's answer: same function, same table."""
        try:
            return asil_lookup(orch.reg, s, e, c)
        except UnknownClass as exc:
            raise HTTPException(status_code=400, detail=str(exc))
```

- [ ] **Step 5: Run the tests**

Expected: all of `tests/test_learn_tools.py` passes; full suite > 492.

- [ ] **Step 6: Mutation-audit the new file**

Add `("fusa/learn/tools.py", "tests/test_learn_tools.py")` to `TARGETS` in `dev/mutation_audit.py`, run it, and kill every survivor or justify it.

- [ ] **Step 7: Commit**

```bash
git add fusa/learn/tools.py fusa/ui/server.py tests/test_learn_tools.py dev/mutation_audit.py
git commit -m "feat(learn): the calculator answers with the chain's own lookup"
```

---

### Task 2: The ASIL Calculator UI

**Files:** Create `fusa/ui/static/learn/tools/asil.js`. Modify `app.js` (route), `nav.js` (Tools group), `index.html` (styles), `pyproject.toml`.

**Interfaces:** Produces `renderAsil(host)`. Routes at `#/tool/asil`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_learn_tools.py`:

```python
def test_the_calculator_asks_the_server_rather_than_deriving_an_answer(client):
    """If the browser ever computes an ASIL itself, the licensed table stops being the source."""
    js = client.get("/static/learn/tools/asil.js")
    assert js.status_code == 200
    assert "/api/learn/asil" in js.text, "the calculator must ask the server"
    for formula in ("S+E+C", "s + e + c", "sum 7", "= 7", "severity + exposure"):
        assert formula not in js.text, f"asil.js appears to derive an ASIL: {formula!r}"


def test_the_shell_routes_to_a_tool(client):
    assert "#/tool/" in client.get("/static/learn/app.js").text
```

- [ ] **Step 2: Watch them fail** — 404 on the tool file.

- [ ] **Step 3: Write the calculator**

```js
// fusa/ui/static/learn/tools/asil.js
// Three selects and one lookup. The answer is not computed here and must never be: the
// determination table is normative content this project does not ship, so the server reads the
// engineer's own transcription. An unfilled cell says so — a guess would be wrong all the way
// down the chain with nothing downstream able to notice.
import { banner } from "../app.js";
import { esc } from "../esc.js";

const SCALES = {
  s: {label: "Severity", classes: ["S0", "S1", "S2", "S3"],
      hint: "how badly the harm hurts, if it happens"},
  e: {label: "Exposure", classes: ["E0", "E1", "E2", "E3", "E4"],
      hint: "how much of the time the vehicle is in that situation"},
  c: {label: "Controllability", classes: ["C0", "C1", "C2", "C3"],
      hint: "whether a driver can act in time to avoid it"},
};
const ASIL_VAR = a => `var(--asil-${String(a).toLowerCase()})`;

export function renderAsil(host) {
  const pick = {s: "S3", e: "E4", c: "C3"};

  const draw = (result) => {
    host.innerHTML = `
      <h2 style="font-size:16px;margin:0 0 4px">ASIL Calculator</h2>
      <p style="color:var(--dim);font-size:11px;margin:0 0 16px">
        Reads the S×E×C table in your project. It is not a formula.</p>
      <div class="tool">
        ${Object.entries(SCALES).map(([k, sc]) => `
          <div class="scale">
            <label for="sc-${k}">${esc(sc.label)}</label>
            <select id="sc-${k}" data-k="${k}">${sc.classes.map(cl =>
              `<option ${pick[k] === cl ? "selected" : ""}>${cl}</option>`).join("")}</select>
            <span class="hint">${esc(sc.hint)}</span>
          </div>`).join("")}
      </div>
      <div class="verdict" id="asil-out">${result ? verdictHtml(result) : "…"}</div>`;
    host.querySelectorAll("select[data-k]").forEach(el => {
      el.onchange = () => { pick[el.dataset.k] = el.value; go(); };
    });
  };

  const verdictHtml = r => {
    if (r.asil === null) {
      return `<div class="unfilled">
        <b>${esc(r.key)} is not transcribed yet.</b>
        <p>This project ships the determination table empty — its values are normative content
        from the standard, so they come from your own licensed copy. ${r.filled} of ${r.total}
        combinations are filled in <code>${esc(r.file)}</code>.</p>
        <p>Until this cell is filled the chain leaves the hazard
        <code>[PENDING]</code> rather than guessing, and so does this calculator.</p></div>`;
    }
    return `<div class="asil-answer">
      <span class="asil-badge" style="color:${ASIL_VAR(r.asil)};border-color:${ASIL_VAR(r.asil)}">
        ${esc(r.asil)}</span>
      <span class="asil-why">${esc(r.why)}</span></div>
      <p class="hint">Same lookup <code>sys-hara</code> performs for a hazard rated
      ${esc(r.key.replace(/-/g, " / "))}.</p>`;
  };

  const go = () => {
    const q = new URLSearchParams(pick).toString();
    fetch(`/api/learn/asil?${q}`)
      .then(r => r.ok ? r.json() : r.json().then(b => Promise.reject(new Error(b.detail))))
      .then(r => { host.querySelector("#asil-out").innerHTML = verdictHtml(r); })
      .catch(err => banner(`the calculator could not answer — ${err.message}`));
  };

  draw(null);
  go();
}
```

- [ ] **Step 4: Route it**

In `app.js`, inside `route()`, before the module lookup:

```js
  if (location.hash.startsWith("#/tool/")) {
    const id = location.hash.slice("#/tool/".length);
    const mod = {asil: "./tools/asil.js", hara: "./tools/hara.js", trace: "./tools/trace.js"}[id];
    state.current = `tool:${id}`;
    $("#learn-crumb").textContent = `Tools → ${id}`;
    drawNav(select);
    if (!mod) { $("#learn-main").innerHTML = `<p style="color:var(--dim)">No such tool.</p>`; return; }
    const m = await import(mod);
    (m.renderAsil || m.renderHara || m.renderTrace)($("#learn-main"));
    return;
  }
```

- [ ] **Step 5: Add a Tools group to the nav**

In `nav.js`, render a fixed group above the content groups:

```js
const TOOLS = [
  {id: "asil",  title: "ASIL Calculator"},
  {id: "hara",  title: "HARA Builder"},
  {id: "trace", title: "Traceability Lab"},
];
```
Render it with the same `.grp`/`.mod` markup, `data-t="<id>"` instead of `data-m`, clicking sets `location.hash = "#/tool/" + id`. Tools carry no completion ring — show `—`.

- [ ] **Step 6: Styles**

Append inside `<style>` in `learn/index.html`:

```css
  .tool { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 18px; }
  @media (max-width: 720px) { .tool { grid-template-columns: 1fr; } }
  .scale { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
  .scale label { display: block; font-size: 11px; color: var(--dim); margin-bottom: 6px; }
  .scale select { width: 100%; background: var(--panel2); color: var(--text);
                  border: 1px solid var(--line); border-radius: 6px; padding: 6px 8px; font: inherit; }
  .scale .hint { display: block; font-size: 10px; color: var(--dim); margin-top: 6px; line-height: 1.5; }
  .hint { color: var(--dim); font-size: 11px; }
  .verdict { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 18px 20px; }
  .asil-badge { display: inline-block; border: 2px solid; border-radius: 8px;
                padding: 6px 18px; font-size: 20px; font-weight: 700; margin-right: 14px; }
  .asil-why { color: var(--dim); font-size: 12px; }
  .unfilled { border-left: 3px solid var(--s-needs_review); padding-left: 12px; }
  .unfilled p { font-size: 12px; color: var(--dim); line-height: 1.6; }
```

- [ ] **Step 7: Widen package data**

`pyproject.toml`: add `"static/learn/tools/*"` to the `fusa.ui` list.

- [ ] **Step 8: Verify in the real app**

```bash
FUSA_DRY_RUN=1 .venv/bin/python -m uvicorn --factory fusa.ui.server:create_app --port 8810 &
sleep 3
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --virtual-time-budget=6000 --window-size=1400,900 \
  --screenshot=/tmp/asil.png "http://127.0.0.1:8810/learn#/tool/asil"
```
Expected: three selects, and — because the shipped table is empty — the "S3-E4-C3 is not
transcribed yet, 0 of 36 filled" state, NOT an ASIL. That empty-by-default result is the
feature. Then fill a cell via `POST /api/asil-table` and confirm the badge appears in the
right colour.

- [ ] **Step 9: Commit**

---

### Task 3: The HARA Builder

**Files:** Create `fusa/ui/static/learn/tools/hara.js`. Append tests to `tests/test_learn_tools.py` and `tests/js/tools-paths.mjs`.

**Interfaces:** Produces `renderHara(host)`. Routes at `#/tool/hara`.

Guided sequence, one step at a time, per spec §7: Item → guideword → Hazard → Situation →
Hazardous event → S/E/C → ASIL (via `/api/learn/asil`) → Safety goal.

- Guidewords are a fixed list: too late, too early, omission, commission, too high, too low,
  reverse, other.
- Three scenarios: one worked with answers shown, one revealing answers only on submission, one
  with no answer key. **Scenario content lives in `content-sample/` under C4/R1**, not in the JS —
  the tool is the mechanism, the cases are content.
- The output row uses the columns of `input/hazards.csv` exactly:
  `id,function,malfunction,hazardous_event,situation,severity,exposure,controllability,rationale,asil`
  and offers a "copy this row" action, so an exercise can be pasted into the real chain.

- [ ] **Step 1** Write the failing tests: the built row has exactly the hazards.csv columns in
  order; a completed exercise's ASIL comes from `/api/learn/asil` and not from the browser.
- [ ] **Step 2** Watch them fail.
- [ ] **Step 3** Add the scenarios to `content-sample/` and load them through `ContentRegistry`.
- [ ] **Step 4** Write `hara.js`.
- [ ] **Step 5** Node-harness test in `tests/js/tools-paths.mjs`: a scenario advances step by
  step, and the finished row serialises to the hazards.csv column order.
- [ ] **Step 6** Screenshot-verify all three scenarios.
- [ ] **Step 7** Mutation-audit, then commit.

---

### Task 4: The Traceability Lab

**Files:** Create `fusa/ui/static/learn/tools/trace.js`. Extend `fusa/learn/tools.py` with
`trace_case(orch, seed)`. Append tests.

**Interfaces:** Produces `trace_case(orch, seed: int) -> dict` and `GET /api/learn/trace?seed=N`.

Per spec §7 the chain is Safety Goal → FSR → TSR → HW/SW req → test case → result, built from
**real work products** via `/api/checks` plus one seeded defect, so the cases reflect this
project rather than invented ones. The learner identifies (a) the broken link, (b) the phase
that owns the fix, (c) the evidence that would close it.

- [ ] **Step 1** Failing tests: a case always contains exactly one broken link; the same seed
  gives the same case (reproducible, so an instructor can set one); the phase named as owner is
  a real `spec.phase`; every work product cited exists in `config/agents.yaml`.
- [ ] **Step 2** Watch them fail.
- [ ] **Step 3** Implement `trace_case`, seeded with `random.Random(seed)` so it is deterministic.
- [ ] **Step 4** Endpoint + `trace.js`, scoring all three parts of the rubric independently and
  explaining each.
- [ ] **Step 5** Node-harness test for the scoring.
- [ ] **Step 6** Mutation-audit, screenshot, commit.

---

### Task 5: Surface the tools where a learner meets them

**Files:** `fusa/ui/static/learn/module.js`, `content-sample/modules/concept.hara.json`.

- [ ] **Step 1** Failing test: a card of type `tool` renders a launch button linking to
  `#/tool/<id>`, and `rules.py` rejects a `tool` card naming a tool that does not exist.
- [ ] **Step 2** Watch it fail.
- [ ] **Step 3** Add the `tool` card type to `rules.py` (`CARD_TYPES`) and `module.js`.
- [ ] **Step 4** Add a `tool` card to the HARA sample module pointing at the calculator, so the
  lesson and the tool are one path rather than two.
- [ ] **Step 5** Full suite, mutation audit, commit.

---

## Done when

- `/learn#/tool/asil` answers from the project's own table, and says "not transcribed yet" —
  with a count — for every cell the engineer has not filled
- The calculator and `sys-hara` return the same ASIL for the same S/E/C, asserted by a test
- No file in the repo contains an ASIL determination formula, asserted by a test
- The HARA Builder emits a row with `input/hazards.csv`'s exact columns
- The Traceability Lab builds reproducible cases from real work products
- A lesson card can launch a tool
- Full suite green and above 492; mutation audit shows no unjustified survivors

## Not in this plan

M4 (the deck's real content; still needs the assessor-path decision slide 134 does not make) and
M5 (dashboard, role paths, validate-my-FuSa view, certificate PDF).
