"""Course content, read from two places.

The user's own content lives outside the repository — it may derive from licensed or
employer-internal training material, and this repository is public — so it is read from
`FUSA_CONTENT_DIR` and never committed. The repo ships a generic sample so a fresh clone has a
working course. A local module of the same id wins; local `groups.json` replaces the sample's
outright, because group order is one editorial decision rather than a set to merge.
"""
from __future__ import annotations

import json
from pathlib import Path


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:      # name the file: "invalid JSON" alone is unfixable
        raise ValueError(f"{path.name}: not valid JSON ({e})") from e
    except UnicodeDecodeError as e:
        raise ValueError(f"{path.name}: not UTF-8 ({e})") from e


class ContentRegistry:
    def __init__(self, sample_dir: Path, local_dir: Path | None = None):
        self.sample_dir = Path(sample_dir)
        self.local_dir = Path(local_dir) if local_dir else None

    def _dirs(self) -> list[Path]:
        """Sample first, local second — later wins."""
        return [d for d in (self.sample_dir, self.local_dir) if d and d.is_dir()]

    def _file(self, name: str, default):
        found = default
        for d in self._dirs():
            if (d / name).is_file():
                found = _read_json(d / name)
        return found

    def groups(self) -> list[dict]:
        return sorted(self._file("groups.json", []), key=lambda g: g.get("order", 0))

    def paths(self) -> list[dict]:
        return self._file("paths.json", [])

    def glossary(self) -> dict[str, str]:
        return self._file("glossary.json", {})

    def scenarios(self, tool: str) -> list[dict]:
        """The cases an interactive tool walks a learner through. Content, not code: the tool
        is the method, and a team's own worked examples replace these without touching JS."""
        return self._file(f"scenarios/{tool}.json", [])

    def modules(self) -> list[dict]:
        by_id: dict[str, dict] = {}
        for d in self._dirs():
            for p in sorted((d / "modules").glob("*.json")) if (d / "modules").is_dir() else []:
                m = _read_json(p)
                if not isinstance(m, dict):
                    raise ValueError(f"{p.name}: a module file must be a JSON object")
                if not str(m.get("id") or "").strip():
                    raise ValueError(f'{p.name}: missing required field "id"')
                by_id[m["id"]] = m
        order = {g["id"]: g.get("order", 0) for g in self.groups()}
        return sorted(by_id.values(),
                      key=lambda m: (order.get(m.get("group"), 99), m.get("order", 0), m["id"]))

    def module(self, mid: str) -> dict | None:
        return next((m for m in self.modules() if m["id"] == mid), None)

    def bundle(self) -> dict:
        return {"groups": self.groups(), "modules": self.modules(),
                "paths": self.paths(), "glossary": self.glossary()}
