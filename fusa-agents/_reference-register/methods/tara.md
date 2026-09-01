### Method: TARA (ISO/SAE 21434 clause 15)
- Assets are `### AS-nnn` items: `- property:` (confidentiality | integrity | availability | authenticity), `- damage_scenario:`.
- Threat scenarios are `### TS-nnn`: `- parent:` (AS id), `- stride:` (S|T|R|I|D|E), `- attack_path:`, `- feasibility:`
  (very low | low | medium | high, with the attack-potential factors in `- rationale:`), `- impact:` (negligible | moderate | major | severe
  across safety / financial / operational / privacy), `- risk:` (1–5), `- treatment:` (avoid | reduce | share | retain).
- Risk value is looked up from the impact × feasibility matrix in the house convention; never re-derive the matrix.
- Safety-relevant impacts cite the affected safety goal id (SG-nnn) so the FuSa and cybersecurity chains cross-reference.
- Treated risks become cybersecurity goals (`CSG-nnn`, owned by cs-goals) — write [PENDING: CSG derivation <- cs-goals].
