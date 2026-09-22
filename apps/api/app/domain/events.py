from dataclasses import dataclass
from datetime import date, time


@dataclass(frozen=True)
class EventDraft:
    modality: str
    kind: str
    title: str
    date: date
    time: time
    location: str
    notes: str | None = None
    opponent: str | None = None
