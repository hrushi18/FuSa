"""FuSa Agent Framework — ISO 26262 / SEooC.

Layers (mirror the architecture diagram):
  input/                 INPUTS           what the chain is fed with
  fusa/agents            AGENT WORKFLOW   one agent per work product
  fusa/gate.py           REVIEW & QA      deterministic structural checks
  fusa/agents/base.py    REVIEW & QA      ReviewAgent, independent of the authoring method
  fusa/registers         DATA & KNOWLEDGE one register per kind of knowledge
  fusa/orchestrator.py   EXECUTION        creation order, gating, status write-back
  _generated/            OUTPUTS          what leaves the chain
"""
__version__ = "0.1.0"
