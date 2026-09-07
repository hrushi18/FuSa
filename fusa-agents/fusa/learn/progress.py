"""One learner's progress, in one file.

The file is plain JSON next to the rest of a project's generated state, which means a person
can read it, edit it, back it up — and corrupt it. Every read tolerates that: a damaged or
missing file reads as nothing started, because losing a quiz score is a nuisance while a
traceback in the middle of a lesson is a broken product.

Best score is kept rather than latest. Retakes are encouraged, and a bad retake erasing a pass
would punish the practice the platform is trying to produce.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

NOT_STARTED, IN_PROGRESS, PASSED, NEEDS_REVIEW = (
    "not_started", "in_progress", "passed", "needs_review")


def _empty() -> dict:
    return {"version": 1, "modules": {}, "tools": {}}


def _clean(rec):
    """One record, or None if a hand edit left it a shape nothing downstream can read.

    Valid JSON with the wrong shape inside is the likelier hand edit than a missing brace, and
    it used to reach `_status_of` as `"0.9" >= 0.8`. Dropping the record costs one module's
    history; letting it through costs the whole page.
    """
    if not isinstance(rec, dict):
        return None
    best = rec.get("best")
    if best is not None and (isinstance(best, bool) or not isinstance(best, (int, float))):
        return None
    seen = rec.get("cards_seen") or 0
    if isinstance(seen, bool) or not isinstance(seen, int) or seen < 0:
        return None
    attempts = rec.get("attempts") or 0
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        attempts = 0                       # a count nobody reads is not worth losing a pass over
    return rec | {"best": best, "cards_seen": seen, "attempts": attempts}


class ProgressStore:
    def __init__(self, path: Path, pass_mark: float = 0.8):
        self.path = Path(path)
        self.pass_mark = pass_mark

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return _empty()
        if not isinstance(data, dict) or not isinstance(data.get("modules"), dict):
            return _empty()
        data["modules"] = {mid: clean for mid, rec in data["modules"].items()
                           if (clean := _clean(rec)) is not None}
        if not isinstance(data.get("tools"), dict):
            data["tools"] = {}
        return data

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def record(self, module_id: str, *, score: float | None = None,
               cards_seen: int | None = None) -> dict:
        data = self.load()
        rec = data["modules"].setdefault(
            module_id, {"best": None, "attempts": 0, "cards_seen": 0, "last_seen": None})
        if score is not None:
            rec["attempts"] += 1
            rec["best"] = score if rec["best"] is None else max(rec["best"], score)
        if cards_seen is not None:
            rec["cards_seen"] = max(rec.get("cards_seen") or 0, cards_seen)
        rec["last_seen"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rec["status"] = self._status_of(rec)
        self._save(data)
        return rec

    def _status_of(self, rec: dict) -> str:
        if rec.get("best") is not None:
            return PASSED if rec["best"] >= self.pass_mark else NEEDS_REVIEW
        return IN_PROGRESS if rec.get("cards_seen") else NOT_STARTED

    def status(self, module_id: str) -> str:
        rec = self.load()["modules"].get(module_id)
        return self._status_of(rec) if rec else NOT_STARTED

    def summary(self) -> dict:
        return {mid: rec | {"status": self._status_of(rec)}
                for mid, rec in self.load()["modules"].items()}
