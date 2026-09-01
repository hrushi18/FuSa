### Method: FMEA (ISO 26262-9 §8)
- Rows are `### FM-nnn` items: `- element:`, `- function:`, `- failure_mode:`, `- local_effect:`, `- item_effect:`,
  `- violated_sg:` (SG id), `- sm:` (SM ids), `- classification:` (SPF | RF | MPF_L | MPF_D | SAFE), `- rationale:`.
- Failure modes come from a fixed taxonomy per element type (loss, erroneous, unintended, stuck, delayed, oscillating).
- A failure mode with no SM and a violated SG is *uncovered*: keep it visible and set `- finding: uncovered`.
  Uncovered failure modes trigger the feedback loop to sys-tsc.
