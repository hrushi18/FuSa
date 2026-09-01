from fusa.tools.metrics import FailureMode, compute


def test_dc_split_and_metrics():
    rows = [
        FailureMode("A", "m1", 100.0, "SR", 0.9, "SM-001"),   # RF 10, MPF_D 90
        FailureMode("B", "m2", 10.0, "SR", 0.0),              # SPF 10
        FailureMode("C", "m3", 20.0, "MPF", 0.5, "SM-002"),   # MPF_L 10, MPF_D 10
        FailureMode("D", "m4", 70.0, "SAFE"),
    ]
    m = compute(rows)
    assert m.lam_sr == 200.0 and m.lam_spf == 10.0 and abs(m.lam_rf - 10.0) < 1e-9
    assert abs(m.spfm - (1 - 20 / 130)) < 1e-9
    assert abs(m.lfm - (1 - 10 / 110)) < 1e-9
    assert m.pmhf_fit == 30.0 and not any("PMHF" in v for v in m.check("B"))
    assert any("SPFM" in v for v in m.check("D"))
