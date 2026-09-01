### Method: safety requirements authoring (ISO 26262-8 §6)
- One requirement, one testable statement, one parent. Attributes: asil, parent, verification (method), rationale.
- Use the pattern: `<element> shall <behaviour> [under <condition>] [within <time>]`.
- ASIL is inherited from the parent unless decomposition is documented (26262-9:5) — cite it if you do.
- If the parent is missing or ambiguous, write PENDING; do not derive from what the parent "probably" says.
