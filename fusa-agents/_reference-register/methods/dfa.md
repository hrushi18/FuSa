### Method: DFA (ISO 26262-9 §7; software interference per 26262-6 §7.4.11)

Two kinds of claim are analysed here, and every item says which it is in `- claim_kind:`.

**`independence`** — two elements are claimed not to fail together (redundancy, a monitor and the
channel it watches, the halves of an ASIL decomposition).

- The unit of analysis is the **claim, not the element**: `### <PREFIX>-nnn` with `- claim:` stating
  what is asserted to be independent of what, and `- elements:` naming both sides. An architecture
  that claims no independence anywhere needs no DFA; one that claims it without saying so has a gap
  in the concept, not in this analysis.
- Every claim says where it comes from in `- parent:` — the ASIL decomposition it enables
  (26262-9:5), the safety mechanism whose diagnostic independence is assumed, or the redundancy it
  protects. A claim with no origin is `[PENDING: source of the independence claim <- <design agent>]`.

**`freedom_from_interference`** — an element must not disturb another, typically of higher ASIL
(26262-9:7, 26262-6 §7.4.11). This claim is **asymmetric**, so it names the two sides by role:
`- protected:` (the element that must keep working) and `- interferer:` (the one that must not
disturb it), each with its ASIL. `- interference_type:` is one of `timing_execution` (blocking,
overrun, deadlock, starvation), `memory` (corruption of another element's data or code), or
`exchange_of_information` (loss, delay, repetition, masquerade, corruption of a message). One item
per interference type per pair — an element that could interfere three ways is three items.

**Both kinds are then worked the same way.**

- Walk the house coupling-factor list and record every factor **considered**, including those ruled
  out: shared supply · shared clock or timebase · shared memory or register file · shared ground,
  shielding or connector · common temperature, vibration or EMI environment · common design, tool or
  library · common production lot or calibration · shared calibration or parameter set · shared
  diagnostic path · shared software resource or task · shared communication channel · common human
  action (service, configuration, diagnosis). The list is house policy: extend it here rather than
  in an analysis, so every DFA walks the same list. A factor considered and dismissed is evidence;
  a factor never mentioned is a hole.
- Each factor considered becomes its own item under the claim: `- coupling_factor:` (from the list),
  `- category:` (`common_cause` where one root defeats both sides, `cascading` where one side's
  failure causes the other's), `- initiator:` (what physically happens), `- effect:` (what both
  sides do at the same time), and a `- verdict:`.
- **Three verdicts, and each is closed differently.**
  `mitigated` — a `- measure:` names the `SM-nnn`, physical separation, partition or diverse
  implementation that breaks the factor. Argument alone does not mitigate.
  `not_applicable` — the factor cannot arise in this architecture (there is no shared clock; the
  parts are on separate dies). It carries a `- rationale:` saying why, and no measure: inventing
  one to silence a factor that was correctly analysed away is worse than leaving it open.
  `open` — neither holds: `- finding: dependent_failure` and `- returns_to:` the design agent. An
  open dependent failure is a concept change, not a caveat.
- Independence or partitioning the **integrator** must provide (separate supplies, separate ECUs,
  routing, an MPU configuration) is an assumption of use, not a finding:
  `[PENDING: AOU for <claim> <- safety-manual-aou]`.
