### Method: technical safety concept (ISO 26262-4 §6)
- For each TSR: allocate to an architectural element, name the safety mechanism(s) by SM id, state the safe state
  and the fault-tolerant time budget split (detection + reaction ≤ FTTI).
- Include the architecture as a Mermaid diagram per the diagram convention.
- Close-the-loop: when an analysis (FMEA/FTA/DFA/FMEDA) surfaces an uncovered failure mode, a single-point cut set
  or a missed metric target, the finding returns here and to the design — add or strengthen a mechanism, never
  argue the failure mode away.
