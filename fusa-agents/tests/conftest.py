import os, shutil, pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Copy knowledge registers into a temp root so tests never touch the real _generated."""
    for d in ["_clause-register", "_reference-register", "_checklist-register", "config", "input"]:
        shutil.copytree(ROOT / d, tmp_path / d)
    (tmp_path / "_generated").mkdir()
    monkeypatch.setenv("FUSA_ROOT", str(tmp_path))
    monkeypatch.setenv("FUSA_DRY_RUN", "1")
    import importlib, fusa.config
    importlib.reload(fusa.config)
    return tmp_path
