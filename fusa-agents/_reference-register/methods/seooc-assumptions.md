### Method: SEooC assumptions (ISO 26262-10 §9)
1. State the *assumed* item: what system the element is expected to be part of, its function, its environment.
2. Derive *assumed* safety goals with ASIL, safe state, FTTI. Mark every one `- assumed: true`.
3. For every assumption that a downstream integrator must confirm, create an `### AOU-nnn` item (assumption of use).
4. Never present an assumption as a fact about the target item; the integrator validates them (26262-10:9).
