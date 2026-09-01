### Method: HARA (ISO 26262-3 clause 6, assumed for SEooC)

- Hazards are `### HZ-nnn` items derived from the item definition's functions and malfunctions:
  `- function:` (item function that fails), `- malfunction:` (loss / unintended / degraded / stuck),
  `- hazardous_event:` (vehicle-level consequence in an operational situation), `- situation:` (driving scenario).
- Each hazard is classified with `- severity:` (S0–S3), `- exposure:` (E0–E4), `- controllability:` (C0–C3)
  and `- asil:` (QM | A | B | C | D) looked up from the S×E×C table in the standard; never re-derive the table.
- The rationale for each S/E/C value goes in `- rationale:`; an assumed operational situation must be stated,
  not implied — for an SEooC every situation is an assumption the integrator confirms.
- Each ASIL-rated hazard names the safety goal that mitigates it as a downstream expectation:
  write [PENDING: safety goal derivation for HZ-nnn <- sys-sads] when SADS does not exist yet;
  once SADS exists, safety goals (`SG-nnn`) carry `- parent: HZ-nnn` back to the hazard.
- QM-rated hazards stay in the table with their rationale — showing what was ruled out is part of the argument.
- The highest ASIL over all hazards of a function bounds the ASIL of every safety goal derived from it.
