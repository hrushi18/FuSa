### Method: safety mechanism catalogue
- One `### SM-nnn` per mechanism: `- detects:` (failure modes / faults), `- reaction:`, `- fttI_budget:`, `- dc_claim:` (0..1, with source),
  `- source:` (own design | supplier safety manual §x), `- allocated_to:` (element).
- Mechanisms from supplier safety manuals are imported by reference with their diagnostic-coverage claim and the
  supplier's assumptions of use — do not re-derive their coverage.
- Every mechanism must be referenced by at least one TSR; otherwise flag `- status: unallocated`.
