from __future__ import annotations

from pathlib import Path


class BriefExtensionError(RuntimeError):
    pass


class BriefExtension:
    """Fixed contract for the official APS briefing extension package."""

    DIRECTORY = "briefing"
    MANIFEST = "manifest.json"
    ENTRYPOINT = "entrypoint.py"
    RESPONSE_SCHEMA = Path("schemas") / "briefing_response.schema.json"

    def __init__(self, extensions_root: Path) -> None:
        self.extensions_root = extensions_root.resolve()
        self.root = self.extensions_root / self.DIRECTORY

    @property
    def entrypoint(self) -> Path:
        return self.root / self.ENTRYPOINT

    @property
    def required_files(self) -> tuple[Path, ...]:
        return (
            self.root / self.MANIFEST,
            self.entrypoint,
            self.root / self.RESPONSE_SCHEMA,
        )

    def missing_files(self) -> list[str]:
        return [path.relative_to(self.extensions_root).as_posix() for path in self.required_files if not path.is_file()]

    def require(self) -> None:
        missing = self.missing_files()
        if missing:
            raise BriefExtensionError("official briefing extension is incomplete: " + ", ".join(missing))
