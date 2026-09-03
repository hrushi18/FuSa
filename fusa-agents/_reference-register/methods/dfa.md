### Method: DFA (ISO 26262-9 §7 — analysis of dependent failures)

- The unit of analysis is an **independence claim, not an element**: `### <PREFIX>-nnn` with
  `- claim:` stating what is asserted to be independent of what, and `- elements:` naming both
  sides. An architecture that claims no independence anywhere needs no DFA; one that claims it
  without saying so has a gap in the concept, not in this analysis.
- Every claim comes from somewhere and says so in `- parent:` — the ASIL decomposition it enables
  (26262-9:5), the safety mechanism whose diagnostic independence is assumed, or the redundancy it
  protects. A claim with no origin is `[PENDING: source of the independence claim <- <design agent>]`.
- For each claim, walk the house coupling-factor list and record every factor **considered**,
  including those ruled out with a reason: shared supply · shared clock or timebase · shared memory
  or register file · shared ground, shielding or connector · common temperature, vibration or EMI
  environment · common design, tool or library · common production lot or calibration · shared
  software resource or task · shared communication channel · common human action (service,
  configuration, diagnosis). A factor considered and dismissed is evidence; a factor never mentioned
  is a hole.
- Each factor that applies becomes its own item: `- coupling_factor:` (from the list),
  `- category:` (`common_cause` where one root defeats both sides, `cascading` where one side's
  failure causes the other's), `- initiator:` (what physically happens), `- effect:` (what both
  sides do at the same time).
- **A coupling factor is closed by a measure, never by argument alone.** `- measure:` names the
  `SM-nnn`, the physical separation, or the diverse implementation that breaks it, with
  `- verdict: mitigated`. With no measure: `- verdict: open`, `- finding: dependent_failure`, and
  `- returns_to:` the design agent — an open dependent failure is a concept change, not a caveat.
- Independence the **integrator** must provide (separate supplies, separate ECUs, routing) is an
  assumption of use, not a finding: `[PENDING: AOU for <claim> <- safety-manual-aou]`.
