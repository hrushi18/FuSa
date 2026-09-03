### Method: FTA (ISO 26262-9 §8 — deductive safety analysis, system / hardware / software)

- One tree per safety goal. The top event is a **safety goal violation stated as a failure of the
  item**, never a component fault: `### <PREFIX>-nnn` with `- top_event:` and `- parent:` naming the
  `SG-nnn` it violates. Two top events are two trees, not one tree with two roots.
- Every other node belongs to that tree by its link: `- parent:` names the node above it, and
  `- gate:` says how *its own children* combine. A node that is not a basic event and states no
  gate is an unfinished tree, not an implicit OR.
- **House gate set: `AND` and `OR` only.** Trees stay coherent, so an inhibit gate is written as an
  AND with the enabling condition as its own basic event, and a priority-AND that the argument
  actually depends on is out of scope for this method — raise it with the safety manager rather
  than inventing a symbol.
- A **repeated basic event** — one cause feeding several branches, which is the normal case for
  shared supplies, clocks and connectors — is written **once** as an item, with `- also_under:`
  listing the other gates it feeds. It is never duplicated under a second id: two ids are two
  independent events to anything that counts cut sets or multiplies probabilities, and that is an
  arithmetic error, not a formatting one.
- A leaf carries `- basic_event:` instead of a gate, and says what it stands for: `- element:`,
  `- failure_mode:` referencing the `FM`/`SFM` id where the analysis already names one, and `- sm:`
  for any mechanism that detects or controls it. A leaf with no analysed failure mode behind it is
  `[PENDING: basic event for <node> <- <the fmea agent>]` — never an invented component.
- **Cut sets are read off the tree, not asserted.** A leaf reachable from the top event through OR
  gates only — by its `parent:` chain or any of its `also_under:` links — is a single-point cut set:
  `- cut_set_order: 1`. One with no `- sm:` violates the safety goal on its own, so set
  `- finding: single_point_cut_set` and `- returns_to:` the design agent. Higher-order cut sets
  carry their order and the leaves that form them in `- cut_set:`.
- **A mechanism does not make a leaf safe; it makes it partly covered.** Any leaf claiming an `sm:`
  states the coverage it claims in `- dc:` with the FMEDA item or safety manual behind it. The
  residual and latent parts of that fault are quantified in the FMEDA, which stays the authority
  for SPFM, LFM and PMHF — an FTA that implies coverage is binary is wrong even when its structure
  is right, and an FTA number that disagrees with the FMEDA is a finding, not a correction.
- Quantification is otherwise optional: if a probability is quoted, `- probability:` carries
  `- probability_source:` and the mission profile.
- Where the tree contradicts an independence claim — two branches meeting at a shared element, or an
  ASIL decomposition (26262-9:5) whose halves are not disjoint — that is a DFA input, not an FTA
  verdict: raise `[PENDING: independence of <elements> <- <the dfa agent>]`.
