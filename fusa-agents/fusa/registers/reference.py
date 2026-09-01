"""ReferenceRegister — house conventions and authoring methods.

  _reference-register/conventions/*.md   how documents look (ids, structure, diagram rules)
  _reference-register/methods/*.md       how an analysis is done (FMEA method, requirements authoring)

ConventionsView exposes conventions only. The reviewer is built on it so the
reviewer can check *form and norm* without inheriting the author's *method*
(ISO 26262-8 confirmation-measure independence).
"""
from __future__ import annotations

from pathlib import Path


class ConventionsView:
    def __init__(self, conv_dir: Path):
        self._dir = Path(conv_dir)

    def convention(self, name: str) -> str:
        p = self._dir / f"{name}.md"
        return p.read_text(encoding="utf-8") if p.exists() else f"(convention '{name}' not found)"

    def render_conventions(self, names: list[str]) -> str:
        return "\n\n".join(self.convention(n) for n in names) if names else ""

    def list_conventions(self) -> list[str]:
        return sorted(p.stem for p in self._dir.glob("*.md"))


class ReferenceRegister(ConventionsView):
    def __init__(self, path: Path):
        self.path = Path(path)
        super().__init__(self.path / "conventions")
        self._methods = self.path / "methods"

    def method(self, name: str) -> str:
        p = self._methods / f"{name}.md"
        return p.read_text(encoding="utf-8") if p.exists() else f"(method '{name}' not found)"

    def list_methods(self) -> list[str]:
        return sorted(p.stem for p in self._methods.glob("*.md"))

    def conventions_only(self) -> ConventionsView:
        """What the reviewer gets."""
        return ConventionsView(self.path / "conventions")
