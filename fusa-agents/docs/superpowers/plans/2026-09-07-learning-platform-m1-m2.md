# FuSa Learning Platform M1+M2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `/learn` — a working course shell with the V-model navigation, persisted progress, a card renderer and a scoring quiz engine — driven entirely by content JSON, so M4's authoring has somewhere to land.

**Architecture:** A second page served by the existing FastAPI app. Python owns content loading, validation and progress; the browser owns rendering. Content is read from a gitignored local directory with a committed generic sample as fallback, so employer-internal material never enters the public repo. No build step: vanilla ES modules.

**Tech Stack:** Python 3.11+, FastAPI, pydantic, PyYAML, pytest + `fastapi.testclient`. Browser: vanilla ES modules, no framework, no bundler, no npm.

**Spec:** `docs/superpowers/specs/2026-09-07-fusa-learning-platform-design.md`

## Global Constraints

- **No build step.** No `package.json`, no bundler, no npm dependency. Browser code is ES modules loaded with `<script type="module">`.
- **C1 — authored content is never committed.** `content/` is already in `.gitignore`. Never `git add` anything under it.
- **C4 — the shipped sample carries no internal references.** No `volvogroup.sharepoint.com`, `ahsp.sp.srv.volvo.com`, `setoolgtt`, `Navigator`, `FS-QDPR`, `WBS`, or `Volvo`. Enforced by a test.
- **R1 — original wording only.** Sample card text is written for this project. Never reproduce ISO 26262 wording, tables or figures. Cite clause ids only.
- **R2 — no ASIL rule in code.** Nothing in M1/M2 computes an ASIL. (The calculator is M3.)
- **Card body cap: 80 words.** Enforced by a test.
- **Pass mark:** `FUSA_LEARN_PASS_MARK`, default `0.8`.
- **Content dir:** `FUSA_CONTENT_DIR`, default `<ROOT>/content`.
- Follow repo idiom: module docstrings explain *why*, comments are sparse and earn their place, tests are named as sentences describing the behaviour.
- Run tests with `.venv/bin/python -m pytest` from `fusa-agents/`.

---

## File Structure

**Create:**
- `fusa/learn/__init__.py` — exports `ContentRegistry`, `ProgressStore`
- `fusa/learn/content.py` — load and merge sample + local content; the bundle the browser gets
- `fusa/learn/rules.py` — content validation; the guards that keep content honest and license-clean
- `fusa/learn/progress.py` — the progress record: load, record an attempt, derive status
- `fusa/ui/content-sample/groups.json` — the 12 nav groups
- `fusa/ui/content-sample/modules/orientation.what-is-fusa.json` — sample module 1
- `fusa/ui/content-sample/modules/concept.hara.json` — sample module 2
- `fusa/ui/content-sample/paths.json`, `glossary.json`
- `fusa/ui/static/tokens.css` — shared design tokens
- `fusa/ui/static/learn/index.html`, `app.js`, `nav.js`, `vmodel.js`, `module.js`, `quiz.js`
- `tests/test_learn_content.py`, `tests/test_learn_rules.py`, `tests/test_learn_progress.py`, `tests/test_learn_api.py`

**Modify:**
- `fusa/config.py` — two settings
- `fusa/ui/server.py` — five routes
- `fusa/ui/static/index.html` — import `tokens.css`
- `pyproject.toml` — package data

---

### Task 1: Content registry

**Files:**
- Create: `fusa/learn/__init__.py`, `fusa/learn/content.py`
- Create: `fusa/ui/content-sample/groups.json`, `paths.json`, `glossary.json`, `modules/orientation.what-is-fusa.json`, `modules/concept.hara.json`
- Modify: `fusa/config.py`, `pyproject.toml`
- Test: `tests/test_learn_content.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ContentRegistry(sample_dir: Path, local_dir: Path | None)` with `.groups() -> list[dict]`, `.modules() -> list[dict]`, `.module(mid: str) -> dict | None`, `.paths() -> list[dict]`, `.glossary() -> dict[str, str]`, `.bundle() -> dict` returning `{"groups": [...], "modules": [...], "paths": [...], "glossary": {...}}`. Modules are ordered by `(group order, module order)`. A local module id overrides a sample one.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_learn_content.py
"""Content is read from the user's local directory first and the shipped sample second, so
employer-internal material can drive the course without ever entering this repository."""
import json

import pytest

from fusa.learn import ContentRegistry


def write_module(d, mid, group="0", order=1, title="T"):
    (d / "modules").mkdir(parents=True, exist_ok=True)
    (d / "modules" / f"{mid}.json").write_text(json.dumps({
        "id": mid, "group": group, "order": order, "title": title,
        "vmodel_position": "concept", "clauses": [], "cards": [],
        "quiz": [], "work_products": [], "checklist_ref": None}), encoding="utf-8")


@pytest.fixture
def sample(tmp_path):
    d = tmp_path / "sample"
    d.mkdir()
    (d / "groups.json").write_text(json.dumps(
        [{"id": "0", "title": "Orientation", "order": 0},
         {"id": "2", "title": "Concept Phase", "order": 2}]), encoding="utf-8")
    (d / "paths.json").write_text("[]", encoding="utf-8")
    (d / "glossary.json").write_text(json.dumps({"ASIL": "a risk classification"}), encoding="utf-8")
    write_module(d, "orientation.intro", group="0", order=1, title="Sample intro")
    return d


def test_the_sample_is_served_when_there_is_no_local_content(sample, tmp_path):
    reg = ContentRegistry(sample, tmp_path / "nothing-here")
    assert [m["id"] for m in reg.modules()] == ["orientation.intro"]
    assert reg.module("orientation.intro")["title"] == "Sample intro"
    assert reg.glossary()["ASIL"] == "a risk classification"


def test_local_content_adds_to_the_sample(sample, tmp_path):
    local = tmp_path / "content"
    write_module(local, "concept.hara", group="2", order=1, title="HARA")
    reg = ContentRegistry(sample, local)
    assert [m["id"] for m in reg.modules()] == ["orientation.intro", "concept.hara"]


def test_a_local_module_overrides_the_sample_module_of_the_same_id(sample, tmp_path):
    local = tmp_path / "content"
    write_module(local, "orientation.intro", group="0", order=1, title="Mine")
    reg = ContentRegistry(sample, local)
    assert len(reg.modules()) == 1
    assert reg.module("orientation.intro")["title"] == "Mine"


def test_local_groups_replace_the_sample_groups_wholesale(sample, tmp_path):
    """Group order is a single editorial decision; merging two lists would interleave them."""
    local = tmp_path / "content"
    local.mkdir()
    (local / "groups.json").write_text(json.dumps(
        [{"id": "0", "title": "My orientation", "order": 0}]), encoding="utf-8")
    reg = ContentRegistry(sample, local)
    assert [g["title"] for g in reg.groups()] == ["My orientation"]


def test_modules_come_back_in_group_then_module_order(sample, tmp_path):
    local = tmp_path / "content"
    write_module(local, "concept.b", group="2", order=2)
    write_module(local, "concept.a", group="2", order=1)
    reg = ContentRegistry(sample, local)
    assert [m["id"] for m in reg.modules()] == ["orientation.intro", "concept.a", "concept.b"]


def test_an_unknown_module_id_is_none_not_an_error(sample, tmp_path):
    assert ContentRegistry(sample, tmp_path).module("no.such.module") is None


def test_the_bundle_is_everything_the_browser_needs_in_one_payload(sample, tmp_path):
    b = ContentRegistry(sample, tmp_path).bundle()
    assert set(b) == {"groups", "modules", "paths", "glossary"}
    assert b["modules"] and b["groups"]


def test_a_module_file_that_is_not_json_is_reported_not_swallowed(sample, tmp_path):
    local = tmp_path / "content"
    (local / "modules").mkdir(parents=True)
    (local / "modules" / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="broken.json"):
        ContentRegistry(sample, local).modules()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_learn_content.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fusa.learn'`

- [ ] **Step 3: Write the config settings**

Append to `fusa/config.py`, after `STRICT_PENDING`:

```python
# Learning platform. Content lives outside the repo by default: it may derive from licensed or
# employer-internal training material, and this repository is public. The shipped sample is
# generic and owned by this project — see docs/superpowers/specs for the constraint it carries.
CONTENT_DIR = Path(os.environ.get("FUSA_CONTENT_DIR", ROOT / "content"))
LEARN_PASS_MARK = float(os.environ.get("FUSA_LEARN_PASS_MARK", "0.8"))
```

- [ ] **Step 4: Write the sample groups, paths and glossary**

`fusa/ui/content-sample/groups.json` — all twelve, so the nav is complete from day one:

```json
[
  {"id": "0",  "order": 0,  "title": "Orientation"},
  {"id": "1",  "order": 1,  "title": "Functional Safety Management"},
  {"id": "2",  "order": 2,  "title": "Concept Phase"},
  {"id": "3",  "order": 3,  "title": "System — Technical Safety Concept"},
  {"id": "4",  "order": 4,  "title": "Hardware Safety"},
  {"id": "5",  "order": 5,  "title": "Software Safety"},
  {"id": "6",  "order": 6,  "title": "Integration, Testing & Validation"},
  {"id": "7",  "order": 7,  "title": "Assessment & Safety Case"},
  {"id": "8",  "order": 8,  "title": "Dependent Failure Analysis & Traceability"},
  {"id": "9",  "order": 9,  "title": "Cybersecurity Bridge"},
  {"id": "10", "order": 10, "title": "Role-Based Paths"},
  {"id": "11", "order": 11, "title": "Validate My FuSa System"}
]
```

`fusa/ui/content-sample/paths.json`:

```json
[]
```

`fusa/ui/content-sample/glossary.json`:

```json
{
  "ASIL": "Automotive Safety Integrity Level — the risk classification assigned to a hazardous event, from QM through A to D.",
  "Item": "The system or combination of systems the safety lifecycle is applied to.",
  "Safety Goal": "The top-level safety requirement for an item, derived from a hazardous event.",
  "FSR": "Functional safety requirement — derived from a safety goal, allocated to the preliminary architecture.",
  "TSR": "Technical safety requirement — the solution-oriented refinement of an FSR.",
  "HSI": "Hardware-software interface specification.",
  "DFA": "Dependent failure analysis — looks for common-cause and cascading failures between elements assumed independent.",
  "Work product": "A document or dataset the lifecycle requires as evidence."
}
```

- [ ] **Step 5: Write the two sample modules**

`fusa/ui/content-sample/modules/orientation.what-is-fusa.json`. Every word is written for this
project (R1); no clause text is quoted:

```json
{
  "id": "orientation.what-is-fusa",
  "group": "0",
  "order": 1,
  "title": "What is Functional Safety?",
  "vmodel_position": "concept",
  "clauses": ["26262-1:1"],
  "cards": [
    {"type": "concept", "title": "The scope is narrower than \"safety\"",
     "body": "Functional safety covers hazards caused by electrical and electronic systems behaving incorrectly. A brake controller that releases pressure when it should hold is in scope. A battery that catches fire on its own is not, unless a malfunction of an E/E system caused it."},
    {"type": "why", "title": "Why the boundary matters",
     "body": "Teams lose time arguing about hazards the standard never asked them to analyse. Knowing the boundary tells you which risks belong in this process and which belong to another discipline."},
    {"type": "diagram", "asset": "vmodel", "reveal": "concept",
     "alt": "The development V-model, with the concept phase highlighted. Work descends from item definition through hazard analysis and the safety concepts, then rises through integration, validation and assessment."}
  ],
  "inline_check": {
    "prompt": "A wiring harness overheats because a control unit commands a valve to stay open indefinitely. In scope?",
    "options": ["No — overheating is a thermal hazard", "Yes — a malfunction of an E/E system caused it"],
    "answer": 1,
    "explanation": "The heat is the harm, but the cause is E/E malfunctioning behaviour, which is exactly what this process addresses."
  },
  "quiz": [
    {"id": "q1", "type": "single",
     "prompt": "Which of these is outside the scope of functional safety?",
     "options": ["A sensor reporting a value it never measured",
                 "A corroding bracket failing under load with no E/E involvement",
                 "An actuator moving without being commanded"],
     "answer": 1, "card_ref": 0,
     "explanation": "No electrical or electronic malfunction is involved, so it belongs to another safety discipline."},
    {"id": "q2", "type": "multi",
     "prompt": "Which two statements are true of functional safety?",
     "options": ["It concerns malfunctioning behaviour of E/E systems",
                 "It replaces the need for general product safety work",
                 "It covers interactions between E/E systems"],
     "answer": [0, 2], "card_ref": 0,
     "explanation": "It sits alongside other safety work rather than replacing it, and interactions between systems are explicitly included."}
  ],
  "work_products": [],
  "checklist_ref": null
}
```

`fusa/ui/content-sample/modules/concept.hara.json`:

```json
{
  "id": "concept.hara",
  "group": "2",
  "order": 1,
  "title": "Hazard Analysis & Risk Assessment",
  "vmodel_position": "concept",
  "clauses": ["26262-3:6"],
  "cards": [
    {"type": "concept", "title": "What a HARA produces",
     "body": "A HARA takes the item definition and produces safety goals. In between it names what the item does, asks how each activity could go wrong, places those failures in driving situations, rates the resulting risk, and states the goal that would prevent each one."},
    {"type": "concept", "title": "Hazard, situation, hazardous event",
     "body": "A hazard is the item misbehaving. A situation is where the vehicle is when it happens. A hazardous event is the pair. Braking failing to engage is a hazard; failing to engage while children cross the road is a hazardous event, and only the pair can be rated."},
    {"type": "example", "example_ref": "generic-brakes", "title": "Worked: service brakes",
     "body": "Activity: deceleration. Guideword: omission. Hazard: service brakes do not engage. Situation: approaching a crossing. Hazardous event: brakes fail to engage as pedestrians cross. Safety goal: omission of service braking shall not occur."},
    {"type": "diagram", "asset": "vmodel", "reveal": "concept",
     "alt": "The V-model with hazard analysis highlighted, immediately after item definition and before the functional safety concept."}
  ],
  "inline_check": {
    "prompt": "\"Steering assist applies torque that was not requested.\" What is this?",
    "options": ["A hazardous event", "A hazard", "A safety goal"],
    "answer": 1,
    "explanation": "It describes the item misbehaving but names no situation, so it is a hazard and not yet a hazardous event."
  },
  "quiz": [
    {"id": "q1", "type": "single",
     "prompt": "What is the input to a HARA?",
     "options": ["The technical safety concept", "The item definition", "The hardware metrics report"],
     "answer": 1, "card_ref": 0,
     "explanation": "The HARA reads the item definition; everything downstream depends on its safety goals."},
    {"id": "q2", "type": "single",
     "prompt": "Which is a well-formed safety goal for the hazard \"unintended deployment\"?",
     "options": ["The sensor shall be redundant",
                 "Unintended deployment shall not occur",
                 "Deployment shall complete within 30 ms"],
     "answer": 1, "card_ref": 2,
     "explanation": "A safety goal states the hazard must not happen. Naming a sensor is a solution, and a timing figure belongs to a lower-level requirement."},
    {"id": "q3", "type": "single",
     "prompt": "Why can a hazard not be rated on its own?",
     "options": ["Because severity depends on the situation it occurs in",
                 "Because hazards are always ASIL D",
                 "Because rating happens in the technical safety concept"],
     "answer": 0, "card_ref": 1,
     "explanation": "Exposure and severity both depend on where and when the failure happens, which is what the situation supplies."}
  ],
  "work_products": ["HARA"],
  "checklist_ref": "HARA"
}
```

- [ ] **Step 6: Write the content registry**

`fusa/learn/content.py`:

```python
"""Course content, read from two places.

The user's own content lives outside the repository — it may derive from licensed or
employer-internal training material, and this repository is public — so it is read from
`FUSA_CONTENT_DIR` and never committed. The repo ships a generic sample so a fresh clone has a
working course. A local module of the same id wins; local `groups.json` replaces the sample's
outright, because group order is one editorial decision rather than a set to merge.
"""
from __future__ import annotations

import json
from pathlib import Path


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:      # name the file: "invalid JSON" alone is unfixable
        raise ValueError(f"{path.name}: not valid JSON ({e})") from e


class ContentRegistry:
    def __init__(self, sample_dir: Path, local_dir: Path | None = None):
        self.sample_dir = Path(sample_dir)
        self.local_dir = Path(local_dir) if local_dir else None

    def _dirs(self) -> list[Path]:
        """Sample first, local second — later wins."""
        return [d for d in (self.sample_dir, self.local_dir) if d and d.is_dir()]

    def _file(self, name: str, default):
        found = default
        for d in self._dirs():
            if (d / name).is_file():
                found = _read_json(d / name)
        return found

    def groups(self) -> list[dict]:
        return sorted(self._file("groups.json", []), key=lambda g: g.get("order", 0))

    def paths(self) -> list[dict]:
        return self._file("paths.json", [])

    def glossary(self) -> dict[str, str]:
        return self._file("glossary.json", {})

    def modules(self) -> list[dict]:
        by_id: dict[str, dict] = {}
        for d in self._dirs():
            for p in sorted((d / "modules").glob("*.json")) if (d / "modules").is_dir() else []:
                m = _read_json(p)
                by_id[m["id"]] = m
        order = {g["id"]: g.get("order", 0) for g in self.groups()}
        return sorted(by_id.values(),
                      key=lambda m: (order.get(m.get("group"), 99), m.get("order", 0), m["id"]))

    def module(self, mid: str) -> dict | None:
        return next((m for m in self.modules() if m["id"] == mid), None)

    def bundle(self) -> dict:
        return {"groups": self.groups(), "modules": self.modules(),
                "paths": self.paths(), "glossary": self.glossary()}
```

`fusa/learn/__init__.py`:

```python
"""The learning platform: course content and a learner's progress through it."""
from .content import ContentRegistry

__all__ = ["ContentRegistry"]
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_learn_content.py -q`
Expected: 8 passed

- [ ] **Step 8: Widen package data**

In `pyproject.toml`, replace the `[tool.setuptools.package-data]` block with:

```toml
[tool.setuptools.package-data]
"fusa.ui" = ["static/*", "static/learn/*", "content-sample/*.json", "content-sample/modules/*.json"]
```

- [ ] **Step 9: Run the whole suite and commit**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass

```bash
git add fusa/learn fusa/ui/content-sample fusa/config.py pyproject.toml tests/test_learn_content.py
git commit -m "feat(learn): course content, read locally first and shipped generic"
```

---

### Task 2: Content rules

**Files:**
- Create: `fusa/learn/rules.py`
- Test: `tests/test_learn_rules.py`

**Interfaces:**
- Consumes: `ContentRegistry` from Task 1.
- Produces: `check_module(m: dict) -> list[str]` (errors for one module), `check_bundle(reg, work_products: set[str], checklists: set[str]) -> list[str]`, `INTERNAL_PATTERNS: tuple[str, ...]`, `WORD_CAP = 80`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_learn_rules.py
"""Content cannot be reviewed by running it, so the rules that keep it honest live here.

Two of them are not style: a card that drifts from the chain teaches a work product that does
not exist, and an internal URL in the shipped sample publishes an employer's material from a
public repository.
"""
import json
import pathlib

import pytest
import yaml

from fusa.learn import ContentRegistry
from fusa.learn.rules import INTERNAL_PATTERNS, WORD_CAP, check_bundle, check_module

ROOT = pathlib.Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "fusa" / "ui" / "content-sample"


def module(**over):
    m = {"id": "g.m", "group": "0", "order": 1, "title": "T", "vmodel_position": "concept",
         "clauses": [], "cards": [{"type": "concept", "title": "C", "body": "short body"}],
         "inline_check": None, "quiz": [], "work_products": [], "checklist_ref": None}
    m.update(over)
    return m


def test_a_card_body_over_the_word_cap_is_an_error():
    long_body = " ".join(["word"] * (WORD_CAP + 1))
    errs = check_module(module(cards=[{"type": "concept", "title": "C", "body": long_body}]))
    assert any(str(WORD_CAP) in e for e in errs)


def test_a_diagram_card_without_alt_text_is_an_error():
    errs = check_module(module(cards=[{"type": "diagram", "asset": "vmodel"}]))
    assert any("alt" in e for e in errs)


def test_a_question_without_an_explanation_is_an_error():
    errs = check_module(module(quiz=[
        {"id": "q1", "type": "single", "prompt": "p", "options": ["a", "b"], "answer": 0}]))
    assert any("explanation" in e for e in errs)


def test_an_answer_index_outside_the_options_is_an_error():
    errs = check_module(module(quiz=[
        {"id": "q1", "type": "single", "prompt": "p", "options": ["a", "b"],
         "answer": 5, "explanation": "x"}]))
    assert any("answer" in e for e in errs)


def test_a_multi_answer_must_be_a_list_of_valid_indices():
    errs = check_module(module(quiz=[
        {"id": "q1", "type": "multi", "prompt": "p", "options": ["a", "b"],
         "answer": [0, 9], "explanation": "x"}]))
    assert any("answer" in e for e in errs)


def test_a_card_ref_past_the_end_of_the_cards_is_an_error():
    errs = check_module(module(quiz=[
        {"id": "q1", "type": "single", "prompt": "p", "options": ["a", "b"],
         "answer": 0, "explanation": "x", "card_ref": 7}]))
    assert any("card_ref" in e for e in errs)


def test_a_well_formed_module_has_no_errors():
    assert check_module(module()) == []


# ---- the two that are not style ----

def test_a_work_product_the_chain_does_not_produce_is_an_error(tmp_path):
    reg = ContentRegistry(SAMPLE, tmp_path)
    errs = check_bundle(reg, work_products={"HARA"}, checklists={"HARA"})
    assert errs == []
    errs = check_bundle(reg, work_products=set(), checklists={"HARA"})
    assert any("HARA" in e for e in errs)


def test_a_checklist_ref_with_no_register_file_is_an_error(tmp_path):
    reg = ContentRegistry(SAMPLE, tmp_path)
    errs = check_bundle(reg, work_products={"HARA"}, checklists=set())
    assert any("checklist" in e.lower() for e in errs)


def test_the_shipped_sample_names_no_internal_system(tmp_path):
    """C4. This repository is public; the sample must be publishable."""
    text = "\n".join(p.read_text(encoding="utf-8")
                     for p in SAMPLE.rglob("*.json"))
    for pattern in INTERNAL_PATTERNS:
        assert pattern.lower() not in text.lower(), f"sample content names {pattern!r}"


def test_the_shipped_sample_passes_every_rule():
    reg = ContentRegistry(SAMPLE, None)
    specs = yaml.safe_load((ROOT / "config" / "agents.yaml").read_text(encoding="utf-8"))
    wps = {a["work_product"] for a in specs["agents"]}
    checklists = {p.stem for p in (ROOT / "_checklist-register").glob("*.yaml")}
    assert check_bundle(reg, work_products=wps, checklists=checklists) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_learn_rules.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fusa.learn.rules'`

- [ ] **Step 3: Write the rules**

`fusa/learn/rules.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_learn_rules.py -q`
Expected: 11 passed

If `test_the_shipped_sample_passes_every_rule` fails, the sample content from Task 1 is at
fault — fix the content, not the rule.

- [ ] **Step 5: Commit**

```bash
git add fusa/learn/rules.py tests/test_learn_rules.py
git commit -m "feat(learn): the rules that keep content honest and publishable"
```

---

### Task 3: Progress store

**Files:**
- Create: `fusa/learn/progress.py`
- Modify: `fusa/learn/__init__.py`
- Test: `tests/test_learn_progress.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ProgressStore(path: Path, pass_mark: float = 0.8)` with `.load() -> dict`, `.record(module_id: str, *, score: float | None = None, cards_seen: int | None = None) -> dict` returning the module's record, `.status(module_id: str) -> str` in `{"not_started","in_progress","passed","needs_review"}`, `.summary() -> dict` mapping module id → record. The file shape is `{"version": 1, "modules": {...}, "tools": {}}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_learn_progress.py
"""Progress is the only state this platform keeps, and it is a plain file a person may edit or
lose. Every read has to survive that: a missing or damaged file means "nothing started yet",
never a stack trace in the middle of a lesson."""
import json

from fusa.learn.progress import ProgressStore


def store(tmp_path, **kw):
    return ProgressStore(tmp_path / "learning-progress.json", **kw)


def test_nothing_started_before_anything_is_recorded(tmp_path):
    s = store(tmp_path)
    assert s.status("concept.hara") == "not_started"
    assert s.summary() == {}


def test_seeing_cards_puts_a_module_in_progress(tmp_path):
    s = store(tmp_path)
    s.record("concept.hara", cards_seen=2)
    assert s.status("concept.hara") == "in_progress"


def test_a_score_at_the_pass_mark_passes(tmp_path):
    s = store(tmp_path, pass_mark=0.8)
    s.record("concept.hara", score=0.8)
    assert s.status("concept.hara") == "passed"


def test_a_score_below_the_pass_mark_needs_review(tmp_path):
    s = store(tmp_path, pass_mark=0.8)
    s.record("concept.hara", score=0.5)
    assert s.status("concept.hara") == "needs_review"


def test_the_best_score_is_kept_not_the_latest(tmp_path):
    """Retakes are encouraged, so a bad retake must not erase a pass."""
    s = store(tmp_path)
    s.record("concept.hara", score=0.9)
    s.record("concept.hara", score=0.2)
    rec = s.load()["modules"]["concept.hara"]
    assert rec["best"] == 0.9 and rec["attempts"] == 2
    assert s.status("concept.hara") == "passed"


def test_attempts_count_only_scored_submissions(tmp_path):
    s = store(tmp_path)
    s.record("concept.hara", cards_seen=3)
    s.record("concept.hara", score=0.5)
    assert s.load()["modules"]["concept.hara"]["attempts"] == 1


def test_progress_survives_a_reload(tmp_path):
    store(tmp_path).record("concept.hara", score=0.9)
    assert store(tmp_path).status("concept.hara") == "passed"


def test_a_corrupt_file_reads_as_nothing_started(tmp_path):
    (tmp_path / "learning-progress.json").write_text("{ not json", encoding="utf-8")
    assert store(tmp_path).status("concept.hara") == "not_started"


def test_a_corrupt_file_is_replaced_on_the_next_write_not_appended(tmp_path):
    p = tmp_path / "learning-progress.json"
    p.write_text("{ not json", encoding="utf-8")
    store(tmp_path).record("concept.hara", score=1.0)
    assert json.loads(p.read_text(encoding="utf-8"))["modules"]["concept.hara"]["best"] == 1.0


def test_a_record_carries_when_it_was_last_seen(tmp_path):
    rec = store(tmp_path).record("concept.hara", cards_seen=1)
    assert rec["last_seen"].endswith("+00:00")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_learn_progress.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fusa.learn.progress'`

- [ ] **Step 3: Write the progress store**

`fusa/learn/progress.py`:

```python
"""One learner's progress, in one file.

The file is plain JSON next to the rest of a project's generated state, which means a person
can read it, edit it, back it up — and corrupt it. Every read tolerates that: a damaged or
missing file reads as nothing started, because losing a quiz score is a nuisance while a
traceback in the middle of a lesson is a broken product.

Best score is kept rather than latest. Retakes are encouraged, and a bad retake erasing a pass
would punish the practice the platform is trying to produce.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

NOT_STARTED, IN_PROGRESS, PASSED, NEEDS_REVIEW = (
    "not_started", "in_progress", "passed", "needs_review")

EMPTY: dict = {"version": 1, "modules": {}, "tools": {}}


class ProgressStore:
    def __init__(self, path: Path, pass_mark: float = 0.8):
        self.path = Path(path)
        self.pass_mark = pass_mark

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return dict(EMPTY, modules={}, tools={})
        if not isinstance(data, dict) or not isinstance(data.get("modules"), dict):
            return dict(EMPTY, modules={}, tools={})
        data.setdefault("tools", {})
        return data

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def record(self, module_id: str, *, score: float | None = None,
               cards_seen: int | None = None) -> dict:
        data = self.load()
        rec = data["modules"].setdefault(
            module_id, {"best": None, "attempts": 0, "cards_seen": 0, "last_seen": None})
        if score is not None:
            rec["attempts"] += 1
            rec["best"] = score if rec["best"] is None else max(rec["best"], score)
        if cards_seen is not None:
            rec["cards_seen"] = max(rec.get("cards_seen") or 0, cards_seen)
        rec["last_seen"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rec["status"] = self._status_of(rec)
        self._save(data)
        return rec

    def _status_of(self, rec: dict) -> str:
        if rec.get("best") is not None:
            return PASSED if rec["best"] >= self.pass_mark else NEEDS_REVIEW
        return IN_PROGRESS if rec.get("cards_seen") else NOT_STARTED

    def status(self, module_id: str) -> str:
        rec = self.load()["modules"].get(module_id)
        return self._status_of(rec) if rec else NOT_STARTED

    def summary(self) -> dict:
        data = self.load()
        return {mid: rec | {"status": self._status_of(rec)}
                for mid, rec in data["modules"].items()}
```

Update `fusa/learn/__init__.py`:

```python
"""The learning platform: course content and a learner's progress through it."""
from .content import ContentRegistry
from .progress import ProgressStore

__all__ = ["ContentRegistry", "ProgressStore"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_learn_progress.py -q`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add fusa/learn/progress.py fusa/learn/__init__.py tests/test_learn_progress.py
git commit -m "feat(learn): a progress record that survives being hand-edited"
```

---

### Task 4: Endpoints

**Files:**
- Modify: `fusa/ui/server.py` (module docstring, imports, new routes near the other GETs)
- Test: `tests/test_learn_api.py`

**Interfaces:**
- Consumes: `ContentRegistry`, `ProgressStore`, `config.CONTENT_DIR`, `config.LEARN_PASS_MARK`.
- Produces: `GET /learn` (HTML), `GET /api/learn/content` (the bundle plus `content_errors`), `GET /api/learn/progress`, `POST /api/learn/progress` (body `{"module_id": str, "score": float|null, "cards_seen": int|null}`), and `app.state.content` / `app.state.progress` for tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_learn_api.py
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(workspace):
    from fusa.ui.server import create_app
    with TestClient(create_app(root=workspace, dry_run=True)) as c:
        yield c


def test_content_serves_the_bundle_the_browser_needs(client):
    b = client.get("/api/learn/content").json()
    assert set(b) >= {"groups", "modules", "paths", "glossary"}
    assert len(b["groups"]) == 12
    assert any(m["id"] == "concept.hara" for m in b["modules"])


def test_content_reports_its_own_rule_violations_rather_than_hiding_them(client):
    """A malformed course should say so in the UI, not render half of itself in silence."""
    assert client.get("/api/learn/content").json()["content_errors"] == []


def test_progress_starts_empty(client):
    assert client.get("/api/learn/progress").json()["modules"] == {}


def test_recording_a_score_is_readable_back(client):
    r = client.post("/api/learn/progress", json={"module_id": "concept.hara", "score": 0.9})
    assert r.status_code == 200 and r.json()["status"] == "passed"
    assert client.get("/api/learn/progress").json()["modules"]["concept.hara"]["best"] == 0.9


def test_recording_against_an_unknown_module_is_rejected(client):
    """Otherwise a typo silently accumulates progress against a module nobody can open."""
    r = client.post("/api/learn/progress", json={"module_id": "no.such.module", "score": 1.0})
    assert r.status_code == 404


def test_a_score_outside_zero_to_one_is_rejected(client):
    r = client.post("/api/learn/progress", json={"module_id": "concept.hara", "score": 4})
    assert r.status_code == 400


def test_progress_is_written_under_generated(client, workspace):
    client.post("/api/learn/progress", json={"module_id": "concept.hara", "score": 0.5})
    assert (workspace / "_generated" / "learning-progress.json").exists()


def test_the_learn_page_is_served(client):
    r = client.get("/learn")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert 'id="learn-nav"' in r.text


def test_the_workbench_is_untouched_by_all_this(client):
    assert client.get("/").status_code == 200
    assert client.get("/api/agents").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_learn_api.py -q`
Expected: FAIL — 404 on `/api/learn/content`

- [ ] **Step 3: Add the routes**

In `fusa/ui/server.py`, add to the module docstring after the `/report.pdf` line:

```
    GET  /learn               the learning platform shell
    GET  /api/learn/content   course bundle (groups, modules, paths, glossary) + rule violations
    GET  /api/learn/progress  this learner's progress record
    POST /api/learn/progress  record cards seen or a quiz score for one module
```

Add imports beside the existing ones:

```python
from .. import config
from ..learn import ContentRegistry, ProgressStore
from ..learn.rules import check_bundle
```

Add near `STATIC`:

```python
CONTENT_SAMPLE = Path(__file__).parent / "content-sample"
```

Inside `create_app`, after `app.state.runner = runner`:

```python
    content = ContentRegistry(CONTENT_SAMPLE, config.CONTENT_DIR)
    progress = ProgressStore(orch.root / "_generated" / "learning-progress.json",
                             pass_mark=config.LEARN_PASS_MARK)
    app.state.content = content
    app.state.progress = progress
```

Add the routes just before `@app.get("/")`:

```python
    @app.get("/api/learn/content")
    def learn_content():
        """The whole course in one payload, with its own rule violations attached — a course
        that breaks its rules should say so in the UI rather than render half of itself."""
        wps = {s.work_product for s in orch.specs}
        checklists = {p.stem for p in orch.reg.checklists.path.glob("*.yaml")}
        try:
            bundle = content.bundle()
        except ValueError as e:                    # a malformed content file, named
            raise HTTPException(status_code=500, detail=str(e))
        return bundle | {"content_errors": check_bundle(content, wps, checklists),
                         "pass_mark": config.LEARN_PASS_MARK}

    @app.get("/api/learn/progress")
    def learn_progress():
        return {"modules": progress.summary(), "pass_mark": config.LEARN_PASS_MARK}

    @app.post("/api/learn/progress")
    async def learn_progress_post(request: Request):
        data = await request.json()
        mid = (data.get("module_id") or "").strip()
        if not content.module(mid):
            raise HTTPException(status_code=404, detail=f"no such module: {mid!r}")
        score = data.get("score")
        if score is not None and not 0.0 <= float(score) <= 1.0:
            raise HTTPException(status_code=400, detail="score must be between 0 and 1")
        return progress.record(mid, score=None if score is None else float(score),
                               cards_seen=data.get("cards_seen"))

    @app.get("/learn")
    def learn_page():
        return FileResponse(STATIC / "learn" / "index.html")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_learn_api.py -q`
Expected: FAIL on `test_the_learn_page_is_served` only — the HTML does not exist yet. The other
eight pass. This is expected; Task 6 creates the page.

- [ ] **Step 5: Commit**

```bash
git add fusa/ui/server.py tests/test_learn_api.py
git commit -m "feat(learn): content and progress endpoints"
```

---

### Task 5: Shared design tokens

**Files:**
- Create: `fusa/ui/static/tokens.css`
- Modify: `fusa/ui/static/index.html` (the `<style>` opening, around line 7)
- Test: `tests/test_learn_api.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: `/static/tokens.css` defining `--bg --panel --panel2 --line --text --dim --accent`, the `--c-*` status colours, the `--p-*` provenance families, and **new** `--asil-qm --asil-a --asil-b --asil-c --asil-d`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_learn_api.py`:

```python
def test_both_pages_share_one_token_file(client):
    """One design system means one place the colours are defined, not two that drift."""
    css = client.get("/static/tokens.css")
    assert css.status_code == 200
    for token in ("--bg:", "--p-model:", "--asil-d:"):
        assert token in css.text
    assert "tokens.css" in client.get("/").text
    assert "tokens.css" in client.get("/learn").text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_learn_api.py::test_both_pages_share_one_token_file -q`
Expected: FAIL — 404 on `/static/tokens.css`

- [ ] **Step 3: Mount static files and write the tokens**

In `fusa/ui/server.py`, add the import:

```python
from fastapi.staticfiles import StaticFiles
```

and inside `create_app`, immediately before `return app`:

```python
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
```

Create `fusa/ui/static/tokens.css`. The values are lifted verbatim from the workbench's
existing `:root` block so nothing changes visually:

```css
/* One design system, one file. The workbench and the learning platform both import this;
   a colour defined twice is a colour that drifts. */
:root {
  --bg: #0e1116; --panel: #161b23; --panel2: #1c232e; --line: #2a3441;
  --text: #d7dee8; --dim: #7d8a9b; --accent: #5ba8f5;

  --c-not_started: #48566a; --c-blocked: #d9a441; --c-drafted: #5ba8f5;
  --c-gate_passed: #3fbcb2; --c-gate_failed: #e05555; --c-rework: #e08a3c;
  --c-reviewed: #52c47c; --c-disabled: #333c48;

  /* provenance — who decided a thing matters more than what it says */
  --p-machine: #3fbcb2;   /* a table, a tool, a rule — reproducible */
  --p-model:   #9d7bf0;   /* a language model — plausible, not reproducible */
  --p-human:   #d9a441;   /* a person must sign it */

  /* ASIL. One association, used everywhere a level appears, so the colour teaches too. */
  --asil-qm: #7d8a9b; --asil-a: #52c47c; --asil-b: #d9a441;
  --asil-c: #e08a3c;  --asil-d: #e05555;

  /* learner progress — the same four states in nav, dashboard and path views */
  --s-not_started: #48566a; --s-in_progress: #5ba8f5;
  --s-passed: #52c47c;      --s-needs_review: #d9a441;
}
```

In `fusa/ui/static/index.html`, replace the line `<style>` (line 7) with:

```html
<link rel="stylesheet" href="/static/tokens.css">
<style>
```

Then delete the `:root { ... }` block from that file's `<style>` (lines 8–19 in the original,
ending with the `--p-human` line and its closing `}`) — it now lives in `tokens.css`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass except `test_the_learn_page_is_served`

- [ ] **Step 5: Verify the workbench looks unchanged**

```bash
FUSA_DRY_RUN=1 .venv/bin/python -m uvicorn --factory fusa.ui.server:create_app --port 8801 &
sleep 3
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --virtual-time-budget=5000 --window-size=1500,1000 \
  --screenshot=/tmp/workbench-after.png http://127.0.0.1:8801/
```

Open `/tmp/workbench-after.png`. Expected: identical to before — dark theme, coloured status
bars, provenance chips. If anything is unstyled, a token was dropped in the move.

- [ ] **Step 6: Commit**

```bash
git add fusa/ui/static/tokens.css fusa/ui/static/index.html fusa/ui/server.py tests/test_learn_api.py
git commit -m "feat(ui): one token file for both pages"
```

---

### Task 6: The shell and the navigation tree

**Files:**
- Create: `fusa/ui/static/learn/index.html`, `fusa/ui/static/learn/app.js`, `fusa/ui/static/learn/nav.js`
- Test: `tests/test_learn_api.py` (append)

**Interfaces:**
- Consumes: `GET /api/learn/content`, `GET /api/learn/progress`.
- Produces: `app.js` exports `state` (`{groups, modules, paths, glossary, progress, passMark}`), `load()`, `route()`, `setProgress(moduleId, rec)`. `nav.js` exports `drawNav(onSelect)` and `STATUS_ICON`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_learn_api.py`:

```python
def test_the_shell_offers_the_nav_the_top_bar_and_the_content_region(client):
    html = client.get("/learn").text
    for marker in ('id="learn-nav"', 'id="learn-main"', 'id="learn-crumb"',
                   'id="learn-progress"', "app.js"):
        assert marker in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_learn_api.py -q -k shell`
Expected: FAIL — the file does not exist

- [ ] **Step 3: Write the shell**

`fusa/ui/static/learn/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FuSa learning</title>
<link rel="stylesheet" href="/static/tokens.css">
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font: 14px/1.5 "SF Mono", ui-monospace, Menlo, Consolas, monospace; }
  #shell { display: grid; grid-template-columns: 300px 1fr; min-height: 100vh; }
  @media (max-width: 900px) { #shell { grid-template-columns: 1fr; }
                              #side { position: static; height: auto; } }
  #side { background: var(--panel); border-right: 1px solid var(--line);
          position: sticky; top: 0; height: 100vh; overflow-y: auto; }
  #brand { padding: 16px 18px 12px; border-bottom: 1px solid var(--line); }
  #brand h1 { font-size: 15px; margin: 0 0 4px; letter-spacing: .6px; }
  #brand h1 span { color: var(--accent); }
  #brand p { margin: 0; font-size: 11px; color: var(--dim); }
  #search { margin: 10px 14px; width: calc(100% - 28px); background: var(--panel2);
            color: var(--text); border: 1px solid var(--line); border-radius: 6px;
            padding: 6px 10px; font: inherit; }
  #search:focus { outline: none; border-color: var(--accent); }

  .grp { border-bottom: 1px solid var(--line); }
  .grp > .g-top { display: flex; align-items: center; gap: 8px; padding: 9px 14px;
                  cursor: pointer; font-size: 12px; }
  .grp > .g-top:hover { background: var(--panel2); }
  .g-caret { color: var(--dim); width: 10px; flex: none; transition: transform .12s; }
  .grp.open .g-caret { transform: rotate(90deg); }
  .g-title { flex: 1; }
  .ring { font-size: 10px; color: var(--dim); flex: none; }
  .grp > .g-mods { display: none; padding: 0 0 6px; }
  .grp.open > .g-mods { display: block; }
  .mod { display: flex; align-items: center; gap: 8px; padding: 5px 14px 5px 32px;
         font-size: 12px; cursor: pointer; border-left: 2px solid transparent; }
  .mod:hover { background: var(--panel2); }
  .mod.on { background: var(--panel2); border-left-color: var(--accent); }
  .mod .ico { width: 12px; flex: none; text-align: center; }
  .st-not_started { color: var(--s-not_started); }
  .st-in_progress { color: var(--s-in_progress); }
  .st-passed      { color: var(--s-passed); }
  .st-needs_review{ color: var(--s-needs_review); }

  header { display: flex; align-items: center; gap: 12px; padding: 12px 20px;
           border-bottom: 1px solid var(--line); background: var(--panel);
           position: sticky; top: 0; z-index: 5; }
  #learn-crumb { font-size: 12px; color: var(--dim); }
  .spacer { flex: 1; }
  #learn-progress { font-size: 11px; color: var(--dim); }
  #learn-main { padding: 22px 26px 80px; max-width: 760px; }
  #banner { margin: 12px 20px 0; padding: 10px 12px; border-radius: 6px; font-size: 12px;
            border: 1px solid var(--c-gate_failed); color: var(--c-gate_failed); display: none; }
  #banner.on { display: block; }
</style>
</head>
<body>
<div id="shell">
  <aside id="side">
    <div id="brand">
      <h1>Fu<span>Sa</span> learning</h1>
      <p>ISO 26262, in the order the lifecycle actually runs.</p>
    </div>
    <input id="search" type="text" placeholder="search modules and terms…" autocomplete="off">
    <div id="learn-nav"></div>
  </aside>
  <main>
    <header>
      <span id="learn-crumb">…</span>
      <span class="spacer"></span>
      <span id="learn-progress">…</span>
    </header>
    <div id="banner"></div>
    <div id="learn-main"></div>
  </main>
</div>
<script type="module" src="./app.js"></script>
</body>
</html>
```

- [ ] **Step 4: Write the nav**

`fusa/ui/static/learn/nav.js`:

```js
// The nav IS the V-model: groups in lifecycle order, so a practitioner needs no legend.
import { state } from "./app.js";

export const STATUS_ICON = {
  not_started: "○", in_progress: "◐", passed: "✓", needs_review: "⚑",
};

const esc = s => { const d = document.createElement("div"); d.textContent = s ?? ""; return d.innerHTML; };

const statusOf = id => state.progress[id]?.status || "not_started";
const modulesOf = gid => state.modules.filter(m => m.group === gid);

export function drawNav(onSelect, filter = "") {
  const q = filter.trim().toLowerCase();
  const nav = document.getElementById("learn-nav");
  nav.innerHTML = state.groups.map(g => {
    const mods = modulesOf(g.id).filter(m => !q || m.title.toLowerCase().includes(q));
    if (q && !mods.length) return "";
    const done = modulesOf(g.id).filter(m => statusOf(m.id) === "passed").length;
    const total = modulesOf(g.id).length;
    const open = q || state.openGroups.has(g.id);
    return `<div class="grp ${open ? "open" : ""}" data-g="${esc(g.id)}">
      <div class="g-top" tabindex="0" role="button" aria-expanded="${open}">
        <span class="g-caret">▸</span>
        <span class="g-title">${esc(g.order)} · ${esc(g.title)}</span>
        <span class="ring">${total ? `${done}/${total}` : "—"}</span>
      </div>
      <div class="g-mods">${mods.map(m => {
        const st = statusOf(m.id);
        return `<div class="mod ${state.current === m.id ? "on" : ""}" data-m="${esc(m.id)}"
                     tabindex="0" role="button" title="${esc(st.replace("_", " "))}">
          <span class="ico st-${st}">${STATUS_ICON[st]}</span>
          <span>${esc(m.title)}</span></div>`;
      }).join("") || `<div class="mod" style="color:var(--dim);cursor:default">no modules yet</div>`}
      </div></div>`;
  }).join("");

  nav.querySelectorAll(".g-top").forEach(el => {
    const gid = el.parentElement.dataset.g;
    const toggle = () => {
      state.openGroups.has(gid) ? state.openGroups.delete(gid) : state.openGroups.add(gid);
      drawNav(onSelect, filter);
    };
    el.onclick = toggle;
    el.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } };
  });
  nav.querySelectorAll(".mod[data-m]").forEach(el => {
    const go = () => onSelect(el.dataset.m);
    el.onclick = go;
    el.onkeydown = e => { if (e.key === "Enter") go(); };
  });
}
```

- [ ] **Step 5: Write the app shell logic**

`fusa/ui/static/learn/app.js`:

```js
// Boot, routing and the one piece of shared state. Routing is the URL hash so a module is
// linkable and the back button works, with no router library to install.
import { drawNav } from "./nav.js";

export const state = {
  groups: [], modules: [], paths: [], glossary: {}, passMark: 0.8,
  progress: {}, openGroups: new Set(), current: null,
};

const $ = s => document.querySelector(s);
const api = (p, opt) => fetch(p, opt).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e)));

export async function load() {
  const [content, progress] = await Promise.all([
    api("/api/learn/content"), api("/api/learn/progress")]);
  Object.assign(state, content);
  state.progress = progress.modules;
  state.passMark = content.pass_mark;
  if (content.content_errors?.length) {
    const b = $("#banner");
    b.className = "on";
    b.textContent = `${content.content_errors.length} content problem(s): `
                  + content.content_errors.slice(0, 3).join(" · ");
  }
  if (state.groups.length) state.openGroups.add(state.groups[0].id);
}

export function setProgress(moduleId, rec) {
  state.progress[moduleId] = rec;
  drawNav(select);
  drawOverall();
}

function drawOverall() {
  const total = state.modules.length;
  const passed = state.modules.filter(m => state.progress[m.id]?.status === "passed").length;
  $("#learn-progress").textContent = total ? `${passed} of ${total} passed` : "no content yet";
}

export function select(moduleId) {
  location.hash = moduleId ? `#/${moduleId}` : "";
}

export async function route() {
  const id = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
  const mod = state.modules.find(m => m.id === id);
  state.current = mod ? mod.id : null;
  const group = state.groups.find(g => g.id === mod?.group);
  if (mod) state.openGroups.add(mod.group);
  $("#learn-crumb").textContent = mod ? `${group ? group.title : mod.group} → ${mod.title}`
                                      : "Pick a module to begin";
  drawNav(select);
  const main = $("#learn-main");
  if (!mod) {
    main.innerHTML = `<p style="color:var(--dim)">This course follows the lifecycle in the
      order it actually runs. Start at the top of the panel, or search for a term.</p>`;
    return;
  }
  const { renderModule } = await import("./module.js");
  renderModule(mod, main);
}

$("#search").oninput = e => drawNav(select, e.target.value);
window.addEventListener("hashchange", route);
load().then(() => { drawOverall(); route(); });
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass — including `test_the_learn_page_is_served` from Task 4

`route()` dynamically imports `module.js`, which does not exist until Task 8. That import only
runs when a module is selected, so the shell loads and the nav works. Selecting a module logs a
console error until Task 8 lands. That is expected at this checkpoint.

- [ ] **Step 7: See it**

```bash
FUSA_DRY_RUN=1 .venv/bin/python -m uvicorn --factory fusa.ui.server:create_app --port 8802 &
sleep 3
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --virtual-time-budget=6000 --window-size=1400,1000 \
  --screenshot=/tmp/learn-shell.png http://127.0.0.1:8802/learn
```

Open `/tmp/learn-shell.png`. Expected: 12 collapsible groups in lifecycle order, group 0 open,
`0/1` and `0/1` rings on groups 0 and 2, `—` on the empty ones, `○` before each module title,
and "0 of 2 passed" top right.

- [ ] **Step 8: Commit**

```bash
git add fusa/ui/static/learn tests/test_learn_api.py
git commit -m "feat(learn): the shell and a nav that is the V-model"
```

---

### Task 7: The V-model diagram

**Files:**
- Create: `fusa/ui/static/learn/vmodel.js`

**Interfaces:**
- Consumes: nothing.
- Produces: `vmodelSvg(reveal: string, alt: string) -> string` returning inline SVG. `reveal` is one of `item`, `hara`, `fsc`, `tsc`, `sw`, `hw`, `integration`, `validation`, `assessment`, `all` — phases at or before it are lit, the rest dimmed. Also exports `PHASES` (ordered ids) so `module.js` can validate a card's `reveal`.

Replaces 36 build-up slides from the deck and the brief's §5.1 mini-diagram.

- [ ] **Step 1: Write the component**

`fusa/ui/static/learn/vmodel.js`:

```js
// The deck spent 36 slides revealing this diagram one box at a time. It is one component:
// pass the phase a module sits in, and everything up to there is lit.
export const PHASES = ["item", "hara", "fsc", "tsc", "sw", "hw",
                       "integration", "validation", "assessment"];

const BOXES = [
  {id: "item",        label: "Item definition",      x: 20,  y: 20},
  {id: "hara",        label: "Hazard analysis",      x: 20,  y: 62},
  {id: "fsc",         label: "Functional safety concept", x: 20, y: 104},
  {id: "tsc",         label: "Technical safety concept",  x: 20, y: 146},
  {id: "sw",          label: "Software safety",      x: 150, y: 188},
  {id: "hw",          label: "Hardware safety",      x: 20,  y: 188},
  {id: "integration", label: "Integration & testing", x: 280, y: 146},
  {id: "validation",  label: "Validation",           x: 280, y: 104},
  {id: "assessment",  label: "Assessment",           x: 280, y: 62},
];

const esc = s => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export function vmodelSvg(reveal = "all", alt = "") {
  const upto = reveal === "all" ? PHASES.length : PHASES.indexOf(reveal) + 1;
  const lit = new Set(PHASES.slice(0, upto || PHASES.length));
  const boxes = BOXES.map(b => {
    const on = lit.has(b.id);
    return `<g opacity="${on ? 1 : 0.28}">
      <rect x="${b.x}" y="${b.y}" width="124" height="30" rx="5"
            fill="${on ? "var(--panel2)" : "transparent"}"
            stroke="${on ? "var(--accent)" : "var(--line)"}" stroke-width="1"/>
      <text x="${b.x + 62}" y="${b.y + 19}" text-anchor="middle" font-size="9"
            fill="${on ? "var(--text)" : "var(--dim)"}">${esc(b.label)}</text></g>`;
  }).join("");
  return `<figure style="margin:0">
    <svg viewBox="0 0 424 236" width="100%" role="img" aria-label="${esc(alt)}"
         style="max-width:520px">${boxes}</svg>
    <figcaption style="color:var(--dim);font-size:11px;margin-top:6px">${esc(alt)}</figcaption>
  </figure>`;
}
```

- [ ] **Step 2: Verify it renders both states**

Create `/tmp/vmodel-check.html`:

```html
<link rel="stylesheet" href="/static/tokens.css">
<body style="background:#0e1116">
<div id="a"></div><div id="b"></div>
<script type="module">
import { vmodelSvg } from "/static/learn/vmodel.js";
a.innerHTML = vmodelSvg("hara", "concept phase lit");
b.innerHTML = vmodelSvg("all", "whole lifecycle lit");
</script>
```

```bash
cp /tmp/vmodel-check.html fusa/ui/static/vmodel-check.html
FUSA_DRY_RUN=1 .venv/bin/python -m uvicorn --factory fusa.ui.server:create_app --port 8803 &
sleep 3
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --virtual-time-budget=5000 --window-size=700,700 \
  --screenshot=/tmp/vmodel.png http://127.0.0.1:8803/static/vmodel-check.html
rm fusa/ui/static/vmodel-check.html
```

Expected: two diagrams — the first with item definition and hazard analysis lit and the rest
dimmed, the second with all nine lit.

- [ ] **Step 3: Commit**

```bash
git add fusa/ui/static/learn/vmodel.js
git commit -m "feat(learn): one V-model component instead of 36 slides"
```

---

### Task 8: The module renderer

**Files:**
- Create: `fusa/ui/static/learn/module.js`
- Modify: `fusa/ui/static/learn/index.html` (append card styles inside `<style>`)

**Interfaces:**
- Consumes: `state`, `setProgress` from `app.js`; `vmodelSvg`, `PHASES` from `vmodel.js`; `startQuiz` from `quiz.js` (Task 9).
- Produces: `renderModule(mod: object, host: HTMLElement) -> void`.

- [ ] **Step 1: Add the card styles**

Append inside the `<style>` block of `fusa/ui/static/learn/index.html`, before `</style>`:

```css
  .card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
          padding: 18px 20px; margin-bottom: 14px; }
  .card h3 { margin: 0 0 8px; font-size: 13px; letter-spacing: .4px; }
  .card p { margin: 0; font-size: 13px; line-height: 1.65; }
  .card .kind { font-size: 9px; letter-spacing: 1.2px; text-transform: uppercase;
                color: var(--dim); display: block; margin-bottom: 6px; }
  .card.example { border-left: 3px solid var(--p-machine); }
  .card.why     { border-left: 3px solid var(--s-needs_review); }
  .pager { display: flex; align-items: center; gap: 10px; margin: 4px 0 18px; }
  .pager button, .qz button { background: var(--panel2); color: var(--text);
      border: 1px solid var(--line); border-radius: 6px; padding: 6px 14px;
      font: inherit; cursor: pointer; }
  .pager button:hover:not(:disabled), .qz button:hover:not(:disabled) { border-color: var(--accent); }
  .pager button:disabled, .qz button:disabled { opacity: .4; cursor: default; }
  .pager .dots { color: var(--dim); font-size: 11px; }
  .opt { display: block; width: 100%; text-align: left; margin: 6px 0; padding: 9px 12px;
         background: var(--panel2); border: 1px solid var(--line); border-radius: 6px;
         color: var(--text); font: inherit; cursor: pointer; }
  .opt:hover { border-color: var(--accent); }
  .opt.picked { border-color: var(--accent); }
  .opt.right  { border-color: var(--s-passed); color: var(--s-passed); }
  .opt.wrong  { border-color: var(--c-gate_failed); color: var(--c-gate_failed); }
  .why-line { font-size: 12px; color: var(--dim); margin-top: 8px; line-height: 1.6; }
  .wp { font-size: 11px; color: var(--dim); margin-top: 18px;
        border-top: 1px solid var(--line); padding-top: 12px; }
  .wp code { color: var(--p-machine); }
```

- [ ] **Step 2: Write the renderer**

`fusa/ui/static/learn/module.js`:

```js
// One card at a time. The brief asks for flashcards, not a specification: the pager exists to
// stop a lesson becoming a wall of text.
import { setProgress, state } from "./app.js";
import { PHASES, vmodelSvg } from "./vmodel.js";

const esc = s => { const d = document.createElement("div"); d.textContent = s ?? ""; return d.innerHTML; };
const KIND = { concept: "Concept", example: "Worked example", why: "Why it matters", diagram: "Where this sits" };

function cardHtml(card) {
  if (card.type === "diagram") {
    const reveal = PHASES.includes(card.reveal) ? card.reveal : "all";
    return `<div class="card diagram"><span class="kind">${KIND.diagram}</span>
      ${vmodelSvg(reveal, card.alt || "")}</div>`;
  }
  return `<div class="card ${esc(card.type)}">
    <span class="kind">${KIND[card.type] || ""}</span>
    ${card.title ? `<h3>${esc(card.title)}</h3>` : ""}
    <p>${esc(card.body)}</p></div>`;
}

function inlineCheckHtml(check) {
  return `<div class="card"><span class="kind">Quick check — not scored</span>
    <h3>${esc(check.prompt)}</h3>
    ${check.options.map((o, i) =>
      `<button class="opt" data-i="${i}">${esc(o)}</button>`).join("")}
    <div class="why-line" id="ic-why" hidden></div></div>`;
}

export function renderModule(mod, host) {
  let at = 0;
  const cards = mod.cards || [];
  const total = cards.length + (mod.inline_check ? 1 : 0);

  const draw = () => {
    const isCheck = mod.inline_check && at === cards.length;
    host.innerHTML = `<h2 style="font-size:16px;margin:0 0 4px">${esc(mod.title)}</h2>
      <p style="color:var(--dim);font-size:11px;margin:0 0 16px">
        ${esc((mod.clauses || []).join(" · ") || "no clause reference")}</p>
      ${isCheck ? inlineCheckHtml(mod.inline_check) : cardHtml(cards[at])}
      <div class="pager">
        <button id="prev" ${at === 0 ? "disabled" : ""}>← back</button>
        <span class="dots">${at + 1} / ${total}</span>
        <button id="next">${at + 1 === total ? (mod.quiz || []).length ? "Take the quiz →" : "Done" : "next →"}</button>
      </div>
      ${mod.work_products?.length ? `<div class="wp">In a real safety file this becomes
        ${mod.work_products.map(w => `<code>${esc(w)}</code>`).join(", ")}
        — the workbench checks it against
        <code>${esc(mod.checklist_ref || "generic")}</code>.</div>` : ""}`;

    host.querySelector("#prev").onclick = () => { at--; draw(); };
    host.querySelector("#next").onclick = async () => {
      if (at + 1 < total) { at++; draw(); return; }
      if ((mod.quiz || []).length) {
        const { startQuiz } = await import("./quiz.js");
        startQuiz(mod, host);
      }
    };
    if (isCheck) {
      host.querySelectorAll(".opt").forEach(el => {
        el.onclick = () => {
          const right = Number(el.dataset.i) === mod.inline_check.answer;
          el.classList.add(right ? "right" : "wrong");
          const why = host.querySelector("#ic-why");
          why.hidden = false;
          why.textContent = mod.inline_check.explanation;
        };
      });
    }
    record();
  };

  let best = 0;
  const record = () => {
    if (at + 1 <= best) return;                 // only ever report forward progress
    best = at + 1;
    fetch("/api/learn/progress", {
      method: "POST", headers: {"content-type": "application/json"},
      body: JSON.stringify({module_id: mod.id, cards_seen: best}),
    }).then(r => r.ok && r.json()).then(rec => rec && setProgress(mod.id, rec));
  };

  draw();
}
```

- [ ] **Step 3: Verify a module renders and marks itself in progress**

```bash
FUSA_DRY_RUN=1 .venv/bin/python -m uvicorn --factory fusa.ui.server:create_app --port 8804 &
sleep 3
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --virtual-time-budget=6000 --window-size=1400,1000 \
  --screenshot=/tmp/learn-module.png \
  "http://127.0.0.1:8804/learn#/concept.hara"
curl -s http://127.0.0.1:8804/api/learn/progress | python3 -m json.tool
```

Expected: the screenshot shows the HARA module's first card with a `1 / 5` pager and the
"In a real safety file this becomes `HARA`" footer; the progress JSON shows
`concept.hara` with `"status": "in_progress"`.

- [ ] **Step 4: Run the suite and commit**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass

```bash
git add fusa/ui/static/learn/module.js fusa/ui/static/learn/index.html
git commit -m "feat(learn): card renderer with an unscored inline check"
```

---

### Task 9: The quiz engine

**Files:**
- Create: `fusa/ui/static/learn/quiz.js`
- Test: `tests/test_learn_api.py` (append)

**Interfaces:**
- Consumes: `state`, `setProgress` from `app.js`.
- Produces: `startQuiz(mod: object, host: HTMLElement) -> void`. Scores `single` and `multi`, posts `score` in `0..1`, renders per-question explanations and a retake button.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_learn_api.py`:

```python
def test_a_passing_score_flips_the_module_to_passed(client):
    """The engine posts a fraction; the server owns what counts as a pass."""
    r = client.post("/api/learn/progress", json={"module_id": "concept.hara", "score": 1.0})
    assert r.json()["status"] == "passed"


def test_a_failing_score_flips_the_module_to_needs_review(client):
    r = client.post("/api/learn/progress", json={"module_id": "concept.hara", "score": 0.33})
    assert r.json()["status"] == "needs_review"


def test_a_retake_cannot_lose_an_earned_pass(client):
    client.post("/api/learn/progress", json={"module_id": "concept.hara", "score": 1.0})
    r = client.post("/api/learn/progress", json={"module_id": "concept.hara", "score": 0.0})
    assert r.json()["status"] == "passed" and r.json()["attempts"] == 2
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `.venv/bin/python -m pytest tests/test_learn_api.py -q -k "passing or failing or retake"`
Expected: PASS — the server side already does this (Task 3/4). These three pin the contract the
JS depends on, so a later change to the pass rule breaks a test rather than the UI silently.

- [ ] **Step 3: Write the quiz engine**

`fusa/ui/static/learn/quiz.js`:

```js
// Scoring lives here; what counts as a pass lives on the server. The engine posts a fraction
// and lets the server decide, so the threshold is one configurable value rather than a number
// duplicated in the browser.
import { setProgress, state } from "./app.js";

const esc = s => { const d = document.createElement("div"); d.textContent = s ?? ""; return d.innerHTML; };
const same = (a, b) => a.length === b.length && a.every(x => b.includes(x));

export function startQuiz(mod, host) {
  const questions = mod.quiz || [];
  const picked = questions.map(q => (q.type === "multi" ? [] : null));
  let submitted = false;

  const scoreOf = () => questions.reduce((n, q, i) => {
    const want = q.type === "multi" ? q.answer : [q.answer];
    const got = q.type === "multi" ? picked[i] : (picked[i] === null ? [] : [picked[i]]);
    return n + (same(want, got) ? 1 : 0);
  }, 0);

  const draw = () => {
    const score = scoreOf();
    host.innerHTML = `<h2 style="font-size:16px;margin:0 0 4px">${esc(mod.title)} — quiz</h2>
      <p style="color:var(--dim);font-size:11px;margin:0 0 16px">
        ${questions.length} question${questions.length === 1 ? "" : "s"} ·
        ${Math.round(state.passMark * 100)}% to pass · retakes keep your best score</p>
      <div class="qz">${questions.map((q, i) => {
        const want = q.type === "multi" ? q.answer : [q.answer];
        return `<div class="card">
          <span class="kind">${esc(q.type === "multi" ? "Choose all that apply" : "Question")} ${i + 1}</span>
          <h3>${esc(q.prompt)}</h3>
          ${q.options.map((o, oi) => {
            const chosen = q.type === "multi" ? picked[i].includes(oi) : picked[i] === oi;
            let cls = chosen ? "picked" : "";
            if (submitted) cls = want.includes(oi) ? "right" : chosen ? "wrong" : "";
            return `<button class="opt ${cls}" data-q="${i}" data-o="${oi}"
                      ${submitted ? "disabled" : ""}>${esc(o)}</button>`;
          }).join("")}
          ${submitted ? `<div class="why-line">${esc(q.explanation)}</div>` : ""}
        </div>`;
      }).join("")}</div>
      <div class="pager">
        ${submitted
          ? `<button id="retake">Retake</button><button id="back">Back to the cards</button>
             <span class="dots">${score} / ${questions.length}
             — ${score / questions.length >= state.passMark ? "passed" : "needs review"}</span>`
          : `<button id="submit">Submit</button>
             <span class="dots">${picked.filter(p => p !== null && p.length !== 0).length}
             of ${questions.length} answered</span>`}
      </div>`;

    host.querySelectorAll(".opt:not([disabled])").forEach(el => {
      el.onclick = () => {
        const qi = Number(el.dataset.q), oi = Number(el.dataset.o);
        if (questions[qi].type === "multi") {
          const at = picked[qi].indexOf(oi);
          at === -1 ? picked[qi].push(oi) : picked[qi].splice(at, 1);
        } else picked[qi] = oi;
        draw();
      };
    });
    if (submitted) {
      host.querySelector("#retake").onclick = () => {
        submitted = false;
        questions.forEach((q, i) => picked[i] = q.type === "multi" ? [] : null);
        draw();
      };
      host.querySelector("#back").onclick = async () => {
        const { renderModule } = await import("./module.js");
        renderModule(mod, host);
      };
    } else {
      host.querySelector("#submit").onclick = () => {
        submitted = true;
        draw();
        fetch("/api/learn/progress", {
          method: "POST", headers: {"content-type": "application/json"},
          body: JSON.stringify({module_id: mod.id, score: scoreOf() / questions.length}),
        }).then(r => r.ok && r.json()).then(rec => rec && setProgress(mod.id, rec));
      };
    }
  };

  draw();
}
```

- [ ] **Step 4: Verify the whole loop end to end**

```bash
FUSA_DRY_RUN=1 .venv/bin/python -m uvicorn --factory fusa.ui.server:create_app --port 8805 &
sleep 3
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --virtual-time-budget=6000 --window-size=1400,1100 \
  --screenshot=/tmp/learn-quiz.png "http://127.0.0.1:8805/learn#/concept.hara"
```

Then in a real browser at `http://127.0.0.1:8805/learn#/concept.hara`: page through the cards,
answer the inline check, take the quiz, submit. Confirm:
- every question shows its explanation after submit, right answers green, wrong picks red
- the score line reads `n / 3` with "passed" or "needs review"
- the nav icon for the module changes to `✓` or `⚑` without a reload
- "Retake" clears the picks; a worse retake leaves the icon at `✓`

```bash
curl -s http://127.0.0.1:8805/api/learn/progress | python3 -m json.tool
```

Expected: `best` is the highest score, `attempts` counts every submit.

- [ ] **Step 5: Run the suite and commit**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass

```bash
git add fusa/ui/static/learn/quiz.js tests/test_learn_api.py
git commit -m "feat(learn): quiz engine scoring against a server-owned pass mark"
```

---

## Done when

- `/learn` lists 12 groups in lifecycle order with completion rings and status icons
- Both sample modules render card by card, with an unscored inline check
- Quizzes score, explain, retake, and keep the best score
- The nav updates without a reload as progress changes
- Progress survives a restart and a hand-mangled file
- Content is read from `FUSA_CONTENT_DIR` first, the shipped sample second
- `content/` is gitignored and nothing under it is committed
- The workbench at `/` is visually and functionally unchanged
- The full suite passes

## Not in this plan

M3 (ASIL Calculator, HARA Builder, Traceability Lab), M4 (real content), M5 (dashboard,
role paths, validate-my-FuSa, certificate PDF). Each gets its own plan.

Two items from spec §5.1's top bar are deliberately deferred rather than forgotten: the
**role/path switcher** needs paths, which arrive with M5, and the **light/dark toggle** is not
scheduled anywhere — the workbench has always been dark-only, and adding a light palette means
a second set of token values and every colour re-checked for contrast. It belongs in its own
change, applied to both pages at once, not smuggled into the learning platform.

Overall progress reads as `n of m passed` rather than the spec's percentage: with a handful of
modules a percentage moves in jumps of 50% and reads as noise.
