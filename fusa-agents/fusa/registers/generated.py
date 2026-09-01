"""GeneratedStore — project data produced by the chain. Layout: _generated/<WP>/<WP>.md"""
from __future__ import annotations

from pathlib import Path

from ..tools import ids


class GeneratedStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

    def file(self, wp: str) -> Path:
        return self.path / wp / f"{wp}.md"

    def exists(self, wp: str) -> bool:
        return self.file(wp).exists()

    def read(self, wp: str) -> str:
        return self.file(wp).read_text(encoding="utf-8")

    def write(self, wp: str, content: str) -> Path:
        p = self.file(wp)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def write_aux(self, wp: str, name: str, content: str) -> Path:
        p = self.path / wp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def all_work_products(self) -> list[str]:
        return sorted(p.name for p in self.path.iterdir() if p.is_dir() and self.file(p.name).exists())

    def all_ids(self) -> dict[str, str]:
        """Every item id across the store -> owning work product."""
        out: dict[str, str] = {}
        for wp in self.all_work_products():
            for i in ids.parse_items(self.read(wp)):
                out.setdefault(i.id, wp)
        return out

    def items(self, wp: str) -> list[ids.Item]:
        return ids.parse_items(self.read(wp)) if self.exists(wp) else []
