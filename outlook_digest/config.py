from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class General:
    lookback_hours: int = 24
    max_per_run: int = 200
    max_scan: int = 2000
    archive_dir: str = "archive"
    db_path: str = "data/mail.db"
    log_dir: str = "data/logs"


@dataclass(frozen=True)
class Folders:
    include: tuple[str, ...] = ("Inbox",)
    skip_folders: tuple[str, ...] = ()


@dataclass(frozen=True)
class Filters:
    skip_senders: tuple[str, ...] = ()
    skip_subject_keywords: tuple[str, ...] = ()
    include_keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class Translate:
    engine: str = "glossary"


@dataclass(frozen=True)
class AI:
    provider: str = "mock"
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    api_key_env: str = "OUTLOOK_DIGEST_API_KEY"
    timeout_seconds: int = 60
    max_chars: int = 12000
    temperature: float = 0.2


@dataclass(frozen=True)
class Config:
    root: Path
    general: General = field(default_factory=General)
    folders: Folders = field(default_factory=Folders)
    filters: Filters = field(default_factory=Filters)
    ai: AI = field(default_factory=AI)
    translate: Translate = field(default_factory=Translate)
    categories: dict[str, tuple[str, ...]] = field(default_factory=dict)
    glossary: dict[str, str] = field(default_factory=dict)
    urgent_keywords: tuple[str, ...] = ()

    @property
    def archive_root(self) -> Path:
        return self.root / self.general.archive_dir

    @property
    def db_path(self) -> Path:
        return self.root / self.general.db_path

    @property
    def log_dir(self) -> Path:
        return self.root / self.general.log_dir


def load_config(path: Path | None = None, root: Path | None = None) -> Config:
    root = Path(root) if root else PROJECT_ROOT
    path = Path(path) if path else root / "config.toml"
    data: dict = {}
    if path.exists():
        with path.open("rb") as fh:
            data = tomllib.load(fh)

    def section(name: str) -> dict:
        value = data.get(name, {})
        return value if isinstance(value, dict) else {}

    general = General(
        **{
            k: v
            for k, v in section("general").items()
            if k in General.__dataclass_fields__
        }
    )
    folders = Folders(
        include=tuple(section("folders").get("include", ["Inbox"])),
        skip_folders=tuple(section("folders").get("skip_folders", [])),
    )
    filters = Filters(
        skip_senders=tuple(s.lower() for s in section("filters").get("skip_senders", [])),
        skip_subject_keywords=tuple(
            s.lower() for s in section("filters").get("skip_subject_keywords", [])
        ),
        include_keywords=tuple(
            s.lower() for s in section("filters").get("include_keywords", [])
        ),
    )
    ai_raw = section("ai")
    ai = AI(
        **{k: v for k, v in ai_raw.items() if k in AI.__dataclass_fields__}
    )
    translate = Translate(
        engine=str(section("translate").get("engine", "glossary")).lower()
    )
    categories = {
        name: tuple(keywords)
        for name, keywords in section("categories").items()
        if isinstance(keywords, list)
    }
    glossary = {
        str(term): str(zh)
        for term, zh in section("glossary").items()
        if isinstance(zh, str) and zh.strip()
    }
    urgent = tuple(section("priority").get("urgent_keywords", []))

    return Config(
        root=root,
        general=general,
        folders=folders,
        filters=filters,
        ai=ai,
        translate=translate,
        categories=categories,
        glossary=glossary,
        urgent_keywords=urgent,
    )
