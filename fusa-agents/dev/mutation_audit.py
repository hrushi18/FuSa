"""Mutation audit — does the suite actually check what it appears to check?

Break one token of production code, re-run the tests that cover it, and see what happens. A
suite that stays green has no test for that behaviour: the coverage is false assurance. This
exists because a Critical bug shipped behind a passing test — `progress.py` tolerated
unparseable JSON but not valid JSON of the wrong shape, and the test only ever wrote
`"{ not json"`, so the branch that mattered was never entered.

Run it from the package root:  .venv/bin/python dev/mutation_audit.py
Survivors land in /tmp/survivors.txt, each one a behaviour no test is watching.

Token-accurate: only real code tokens are mutated, never text inside strings or comments, so
a survivor is always a real gap rather than a mangled message.

Equivalent mutants — survivors that no test can kill, because they cannot change what the
program does. Each one is justified here rather than papered over with a test:

  fusa/learn/progress.py:41  `attempts < 0` -> `attempts <= 0`
      The value can only be an int here, and `rec.get("attempts") or 0` has already turned a
      falsy one into 0. At exactly 0 the body assigns 0 to something that is already 0, so
      both branches produce the same record.

  fusa/pdf.py:123  `cols = max(len(r) for r in rows)` -> `min`
      `cols` feeds `[width / cols] * cols` and `r + [""] * (cols - len(r))`. With the smaller
      count the padding expression is a no-op (`[""] * -1` is `[]`) and the colWidths list is
      short — and reportlab's LongTable takes its column count from the widest row and refits
      the widths to the frame either way. Rendering ragged tables both ways gives byte-
      identical content streams (see the short-row test in tests/test_report.py), so the
      padding is defensive against a future reportlab, not something this one can observe.
"""
import io, os, subprocess, tokenize
from pathlib import Path

ROOT = Path("/Users/hrushi/Desktop/AI/FUSA/fusa-agents")
PY_BIN = ROOT / ".venv/bin/python"

TARGETS = [
    ("fusa/learn/progress.py", "tests/test_learn_progress.py tests/test_learn_api.py"),
    ("fusa/learn/rules.py",    "tests/test_learn_rules.py tests/test_learn_api.py"),
    ("fusa/learn/content.py",  "tests/test_learn_content.py tests/test_learn_api.py"),
    ("fusa/learn/tools.py",    "tests/test_learn_tools.py"),
    ("fusa/pdf.py",            "tests/test_report.py"),
    ("fusa/agents/llm.py",     "tests/test_llm_retry.py tests/test_settings.py tests/test_dotenv.py"),
]
SWAP = {">=": ">", "<=": "<", "==": "!=", "!=": "==", ">": ">=", "<": "<=",
        "and": "or", "or": "and", "True": "False", "False": "True",
        "max": "min", "min": "max", "+": "-", "in": "not in"}

def mutants(src_text):
    """Yield (line, col_offset, old, new, new_source) for every mutable CODE token."""
    out = []
    toks = list(tokenize.generate_tokens(io.StringIO(src_text).readline))
    lines = src_text.splitlines(keepends=True)
    for t in toks:
        if t.type not in (tokenize.OP, tokenize.NAME):
            continue                                  # never STRING or COMMENT
        if t.string not in SWAP:
            continue
        r, c = t.start
        line = lines[r - 1]
        new_line = line[:c] + SWAP[t.string] + line[c + len(t.string):]
        new = lines[:]; new[r - 1] = new_line
        out.append((r, t.string, SWAP[t.string], "".join(new)))
    return out

def green(tests):
    # Stale .pyc reuse makes a killed mutant look like a survivor — a false-assurance
    # detector that itself gives false assurance. Never let bytecode outlive a mutation.
    env = os.environ | {"PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run(f"{PY_BIN} -B -m pytest {tests} -q -x -p no:cacheprovider --timeout=90",
                       shell=True, cwd=ROOT, capture_output=True, text=True, env=env)
    return r.returncode == 0

report = []
for src, tests in TARGETS:
    path = ROOT / src
    original = path.read_text()
    ms = mutants(original)
    print(f"{src}: {len(ms)} mutable tokens", flush=True)
    for row, old, new, mutated in ms:
        path.write_text(mutated)
        try:
            if green(tests):
                code = original.splitlines()[row - 1].strip()[:100]
                report.append(f"{src}:{row}  {old!r} -> {new!r}\n    {code}")
                print(f"  SURVIVED {src}:{row} {old!r}->{new!r}", flush=True)
        finally:
            path.write_text(original)

Path("/tmp/survivors.txt").write_text("\n".join(report))
print(f"\n=== {len(report)} survivors written to /tmp/survivors.txt ===")
