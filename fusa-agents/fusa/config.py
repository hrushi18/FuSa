"""Paths and runtime switches. Nothing else lives here."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("FUSA_ROOT", Path(__file__).resolve().parents[1]))

# One home per knowledge type — these directories never mix.
CLAUSE_DIR = ROOT / "_clause-register"        # norm: ISO 26262 clause by clause
REFERENCE_DIR = ROOT / "_reference-register"  # house conventions + authoring methods
CHECKLIST_DIR = ROOT / "_checklist-register"  # definition of done
GENERATED_DIR = ROOT / "_generated"           # project data produced by the chain
INPUT_DIR = ROOT / "input"                    # item definition, supplier FMEDAs, safety manuals
AGENTS_FILE = ROOT / "config" / "agents.yaml"
STATUS_FILE = GENERATED_DIR / "process-status.json"

# Model is configurable; see https://docs.claude.com/en/docs/about-claude/models for current IDs.
MODEL = os.environ.get("FUSA_MODEL", "claude-sonnet-5")
MAX_TOKENS = int(os.environ.get("FUSA_MAX_TOKENS", "6000"))

# FUSA_DRY_RUN=1 runs the full chain with deterministic stub content and no API calls.
DRY_RUN = os.environ.get("FUSA_DRY_RUN", "0") == "1"

# Strict gating: a downstream agent may not start while an upstream has PENDING markers.
STRICT_PENDING = os.environ.get("FUSA_STRICT_PENDING", "0") == "1"
