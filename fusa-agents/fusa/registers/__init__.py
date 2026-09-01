"""One home per kind of knowledge.

  ClauseRegister      the norm      (_clause-register)
  ReferenceRegister   conventions + authoring methods (_reference-register)
  ChecklistRegister   definition of done (_checklist-register)
  GeneratedStore      project data  (_generated)
  ProcessRegister     live status board (_generated/process-status.json)

They are handed to agents as a bundle, but a ReviewAgent only receives
ConventionsView — never the authoring methods — to keep the reviewer independent.
"""
from .clause import ClauseRegister
from .reference import ReferenceRegister, ConventionsView
from .checklist import ChecklistRegister
from .generated import GeneratedStore
from .process import ProcessRegister
from dataclasses import dataclass


@dataclass
class Registers:
    clauses: ClauseRegister
    reference: ReferenceRegister
    checklists: ChecklistRegister
    generated: GeneratedStore
    process: ProcessRegister

    @classmethod
    def load(cls, root=None) -> "Registers":
        from .. import config
        root = root or config.ROOT
        return cls(
            clauses=ClauseRegister(root / "_clause-register"),
            reference=ReferenceRegister(root / "_reference-register"),
            checklists=ChecklistRegister(root / "_checklist-register"),
            generated=GeneratedStore(root / "_generated"),
            process=ProcessRegister(root / "_generated" / "process-status.json"),
        )


__all__ = ["Registers", "ClauseRegister", "ReferenceRegister", "ConventionsView",
           "ChecklistRegister", "GeneratedStore", "ProcessRegister"]
