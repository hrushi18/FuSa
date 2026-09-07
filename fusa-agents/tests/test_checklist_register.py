"""The checklist registers are the definition of done, and they are hand-edited YAML.

An unquoted comma inside a flow mapping (`{id: X, text: a, b, clause: ...}`) ends the value:
YAML reads `text: a` and turns `b` into a key of its own. Nothing downstream can notice — the
item still has an id, a clause and a check, so the gate passes, the review passes, and half a
safety checklist item is simply gone from every report. These tests are the only place that
catches it.
"""
from __future__ import annotations

import pathlib

import pytest
import yaml

REGISTER = pathlib.Path(__file__).resolve().parents[1] / "_checklist-register"
ITEM_KEYS = {"id", "text", "clause", "check", "rule", "severity"}

FILES = sorted(REGISTER.glob("*.yaml"))


def items_of(path: pathlib.Path) -> list[dict]:
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("items", [])


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_checklist_item_has_a_key_yaml_invented_from_a_comma(path):
    stray = {i.get("id"): sorted(set(i) - ITEM_KEYS) for i in items_of(path) if set(i) - ITEM_KEYS}
    assert not stray, (
        f"{path.name}: unquoted comma split these items into extra keys — quote the value: {stray}")


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_every_checklist_item_keeps_a_usable_id_text_and_clause(path):
    for i in items_of(path):
        assert i.get("id") and i.get("text") and i.get("clause"), f"{path.name}: incomplete {i}"


@pytest.mark.parametrize("wp,item_id,text", [
    ("SADS", "SADS-01", "assumed item and its boundary are described (function, environment, interfaces)"),
    ("SADS", "SADS-02", "each assumed safety goal has ASIL, safe state, FTTI and `assumed: true`"),
    ("HARA", "HARA-01", "every hazard names function, malfunction, hazardous event and operational situation"),
    ("HARA", "HARA-02", "each hazard carries S, E, C with a stated rationale for each value"),
    ("SM-CATALOG", "SM-01", "each SM has detects, reaction, dc_claim with source, allocated_to"),
    ("TSC", "TSC-04", "architecture diagram present, Mermaid, SMs labelled by id"),
])
def test_the_full_sentence_survives_its_commas(wp, item_id, text):
    """Spot checks that record what these items are actually meant to say."""
    found = next(i for i in items_of(REGISTER / f"{wp}.yaml") if i.get("id") == item_id)
    assert found["text"] == text
