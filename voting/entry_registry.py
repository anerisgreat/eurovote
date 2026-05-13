"""
Static entry registry — loads all data/<year>/entries.yaml files at startup.
Entry and Event data never lives in the database; only user Votes do.
"""
import re
import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'


def _slug(country: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', country.lower()).strip('_')


def make_entry_id(year: int, country: str) -> str:
    """Stable ID: e.g. '2026_united_kingdom'. Survives artist/song edits."""
    return f"{year}_{_slug(country)}"


@dataclass
class EntryData:
    entry_id: str
    year: int
    country: str
    artist: str
    song_title: str
    performance_order: int
    image: str

    @property
    def image_url(self) -> Optional[str]:
        if self.image:
            return f"/media/{self.year}/images/{self.image}"
        return None


@dataclass
class EventData:
    year: int
    name: str
    entries: list  # list[EntryData], sorted by performance_order


# Module-level cache populated once at import time
_events: dict[int, EventData] = {}
_entries: dict[str, EntryData] = {}


def _load_all() -> None:
    if not DATA_DIR.exists():
        return
    for year_dir in sorted(DATA_DIR.iterdir()):
        if not year_dir.is_dir():
            continue
        try:
            year = int(year_dir.name)
        except ValueError:
            continue
        yaml_file = year_dir / 'entries.yaml'
        if not yaml_file.exists():
            continue
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        event_meta = data.get('event', {})
        entries = []
        for e in data.get('entries', []):
            entry_id = make_entry_id(year, e['country'])
            entry = EntryData(
                entry_id=entry_id,
                year=year,
                country=e.get('country', ''),
                artist=e.get('artist', ''),
                song_title=e.get('song_title', ''),
                performance_order=e.get('performance_order', 0),
                image=e.get('image', ''),
            )
            entries.append(entry)
            _entries[entry_id] = entry
        entries.sort(key=lambda e: e.performance_order)
        _events[year] = EventData(
            year=year,
            name=event_meta.get('name', f'Eurovision {year}'),
            entries=entries,
        )


_load_all()


def get_entry(entry_id: str) -> Optional[EntryData]:
    return _entries.get(entry_id)


def get_event(year: int) -> Optional[EventData]:
    return _events.get(year)


def get_all_events() -> list:  # list[EventData]
    return sorted(_events.values(), key=lambda e: e.year, reverse=True)
