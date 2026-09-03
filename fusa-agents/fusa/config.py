"""Paths and runtime switches. Nothing else lives here."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("FUSA_ROOT", Path(__file__).resolve().parents[1]))


def load_dotenv(path: Path | None = None) -> list[str]:
    """`KEY=value` lines from <root>/.env into the environment; returns the names set.

    A real environment variable always wins, so this is a convenience for keys you would
    otherwise re-export every session — not a config layer. The file is gitignored; keeping
    an API key in the working tree is the point, and also the risk.
    """
    path = path or ROOT / ".env"
    names = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return names
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip().removeprefix("export ").strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            names.append(key)
    return names


DOTENV_LOADED = load_dotenv()      # before anything below reads os.environ

# One home per knowledge type — these directories never mix.
CLAUSE_DIR = ROOT / "_clause-register"        # norm: ISO 26262 clause by clause
REFERENCE_DIR = ROOT / "_reference-register"  # house conventions + authoring methods
CHECKLIST_DIR = ROOT / "_checklist-register"  # definition of done
GENERATED_DIR = ROOT / "_generated"           # project data produced by the chain
INPUT_DIR = ROOT / "input"                    # item definition, supplier FMEDAs, safety manuals
AGENTS_FILE = ROOT / "config" / "agents.yaml"
STATUS_FILE = GENERATED_DIR / "process-status.json"

# Provider: "anthropic" (default), "grok" (xAI), "groq" (GroqCloud), "openai" or "gemini" — see agents/llm.py.
PROVIDER = os.environ.get("FUSA_PROVIDER", "anthropic")
GROK_BASE_URL = os.environ.get("FUSA_GROK_BASE_URL", "https://api.x.ai")
GROQ_BASE_URL = os.environ.get("FUSA_GROQ_BASE_URL", "https://api.groq.com/openai/v1")
OPENAI_BASE_URL = os.environ.get("FUSA_OPENAI_BASE_URL", "https://api.openai.com/v1")
GEMINI_BASE_URL = os.environ.get("FUSA_GEMINI_BASE_URL",
                                 "https://generativelanguage.googleapis.com/v1beta/openai")

# Model is configurable; docs.claude.com / docs.x.ai / console.groq.com/docs/models /
# developers.openai.com / ai.google.dev for current IDs.
MODEL = os.environ.get("FUSA_MODEL",
                       {"grok": "grok-4.6", "groq": "openai/gpt-oss-120b",
                        "openai": "gpt-5.6", "gemini": "gemini-3.1-pro"}.get(PROVIDER, "claude-sonnet-5"))
MAX_TOKENS = int(os.environ.get("FUSA_MAX_TOKENS", "6000"))

# FUSA_DRY_RUN=1 runs the full chain with deterministic stub content and no API calls.
DRY_RUN = os.environ.get("FUSA_DRY_RUN", "0") == "1"

# Independent review: "model" (an LLM reads the checklist) or "rules" (the checklist's own
# rules are executed — deterministic, no API key, judgement items raised for human sign-off).
REVIEWER = os.environ.get("FUSA_REVIEWER", "model")

# Strict gating: a downstream agent may not start while an upstream has PENDING markers.
STRICT_PENDING = os.environ.get("FUSA_STRICT_PENDING", "0") == "1"
