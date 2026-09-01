from fusa.gate import run_gate
from fusa.models import AgentSpec
from fusa.registers import GeneratedStore


def _spec(**kw):
    base = dict(id="sys-tsr", work_product="TSR", title="t", phase=1, requires=["SADS"], covers=["SADS"])
    base.update(kw)
    return AgentSpec(**base)


SADS = "---\nid: SADS\n---\n### SG-001\n- text: a\n### SG-002\n- text: b\n"


def test_orphan_parent_is_error(tmp_path):
    store = GeneratedStore(tmp_path)
    store.write("SADS", SADS)
    tsr = "---\nid: TSR\n---\n### TSR-001\n- parent: SG-099\n"
    res = run_gate(_spec(), tsr, store)
    assert not res.passed and any("SG-099 does not exist" in e for e in res.errors)


def test_duplicate_and_cross_store_ids(tmp_path):
    store = GeneratedStore(tmp_path)
    store.write("SADS", SADS)
    tsr = "---\nid: TSR\n---\n### TSR-001\n- parent: SG-001\n### TSR-001\n- parent: SG-002\n"
    res = run_gate(_spec(), tsr, store)
    assert any("duplicate id" in e for e in res.errors)
    tsc = "---\nid: TSC\n---\n### TSR-001\n- parent: SG-001\n"       # wrong prefix + clash
    store.write("TSR", "---\nid: TSR\n---\n### TSR-001\n- parent: SG-001\n")
    res = run_gate(_spec(id="sys-tsc", work_product="TSC", requires=["TSR"], covers=["TSR"]), tsc, store)
    assert any("prefix not allowed" in e for e in res.errors)
    assert any("already used in TSR" in e for e in res.errors)


def test_gate_without_children_is_warning_and_pending_counted(tmp_path):
    store = GeneratedStore(tmp_path)
    store.write("SADS", SADS)
    tsr = "---\nid: TSR\n---\n### TSR-001\n- parent: SG-001\n\n[PENDING: FTTI for SG-002 <- sys-sads]\n"
    res = run_gate(_spec(), tsr, store)
    assert res.passed
    assert any("SG-002" in w for w in res.warnings)
    assert res.pending == ["FTTI for SG-002 <- sys-sads"]


def test_unknown_sm_reference(tmp_path):
    store = GeneratedStore(tmp_path)
    store.write("SM-CATALOG", "---\nid: SM-CATALOG\n---\n### SM-001\n- detects: x\n")
    tsc = "---\nid: TSC\n---\n### TSC-001\n- sm: SM-001, SM-007\n"
    res = run_gate(_spec(id="sys-tsc", work_product="TSC", requires=["SM-CATALOG"], covers=[]), tsc, store)
    assert not res.passed and any("SM-007" in e for e in res.errors)
