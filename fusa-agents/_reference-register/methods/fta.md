### Method: FTA (ISO 26262-9 §8 — deductive safety analysis, system / hardware / software)

- One tree per safety goal. The top event is a **safety goal violation stated as a failure of the
  item**, never a component fault: `### <PREFIX>-nnn` with `- top_event:` and `- parent:` naming the
  `SG-nnn` it violates. Two top events are two trees, not one tree with two roots.
- Every other node belongs to that tree by its link: `- parent:` names the node above it, and
  `- gate:` (`AND` | `OR`) says how *its own children* combine. A node with children and no gate is
  an unfinished tree, not an implicit OR.
- A leaf carries `- basic_event:` instead of a gate, and says what it stands for: `- element:`,
  `- failure_mode:` referencing the `FM`/`SFM` id where the analysis already names one, and `- sm:`
  for any mechanism that detects or controls it. A leaf with no analysed failure mode behind it is
  `[PENDING: basic event for <node> <- <the fmea agent>]` — never an invented component.
- **Cut sets are read off the tree, not asserted.** A leaf reachable from the top event through OR
  gates only is a single-point cut set: `- cut_set_order: 1`. One with no `- sm:` violates the safety
  goal on its own, so set `- finding: single_point_cut_set` and `- returns_to:` the design agent.
  Higher-order cut sets carry their order and the leaves that form them in `- cut_set:`.
- Quantification is optional and separate. If a probability is quoted, `- probability:` carries
  `- probability_source:` and the mission profile; the FMEDA remains the authority for PMHF and the
  hardware architectural metrics. An FTA number that disagrees with the FMEDA is a finding, not a
  correction.
- Where the tree contradicts an independence claim — two branches meeting at a shared element, or an
  ASIL decomposition (26262-9:5) whose halves are not disjoint — that is a DFA input, not an FTA
  verdict: raise `[PENDING: independence of <elements> <- <the dfa agent>]`.
