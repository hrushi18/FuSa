### Method: FMEDA (ISO 26262-5 §8, §9, Annex C)
- Enumerate hardware parts, failure rates (FIT, source cited), failure-mode distributions and per-mode classification.
- Diagnostic coverage per failure mode is claimed against an SM id and justified (supplier manual or Annex D-style rationale).
- Do NOT compute SPFM, LFM or PMHF in prose. Emit the table `input/fmeda-failure-modes.csv` structure and write
  `[PENDING: metrics <- tools.metrics]` where the numbers go; the orchestrator runs the metrics tool and attaches `metrics.md`.
- A missed metric target is a finding that returns to sys-tsc and hw-design (feedback loop), never a rounding exercise.
