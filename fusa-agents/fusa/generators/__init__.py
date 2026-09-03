"""Deterministic authoring: work products rendered from engineer-authored tables, no model.

A generator is the authoring counterpart of a tool runner. Where the runner turns an analyser's
report into items, a generator turns a table of engineering decisions into them — the S/E/C a
person assigned, the safe state they chose — and derives everything that follows mechanically.

This does not remove judgement; it moves it out of a model's reply and into an input file that
is reviewable, diffable and version-controlled, where a safety file wants it. The same table
always yields the same work product.
"""
from .base import GeneratorAgent
from .kinds import GENERATORS

__all__ = ["GeneratorAgent", "GENERATORS"]
