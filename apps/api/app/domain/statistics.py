from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal
from uuid import UUID

Period = Literal["all", "month", "last30", "year"]


def period_start(period: Period, today: date) -> date | None:
    if period == "month":
        return today.replace(day=1)
    if period == "last30":
        return today - timedelta(days=29)
    if period == "year":
        return today.replace(month=1, day=1)
    return None


@dataclass
class Totals:
    matches: int = 0
    goals: int = 0
    assists: int = 0
    yellow_cards: int = 0
    red_cards: int = 0


@dataclass
class PersonStatistics:
    id: UUID
    kind: Literal["member", "guest"]
    name: str
    totals: Totals
    player_id: UUID | None = None
    photo_url: str | None = None
    inactive: bool = False
    event_date: date | None = None
    goals_position: int | None = None
    assists_position: int | None = None


def ranking(people: list[PersonStatistics], *, assists: bool = False) -> list[PersonStatistics]:
    primary, secondary = ("assists", "goals") if assists else ("goals", "assists")
    ordered = sorted(
        [p for p in people if getattr(p.totals, primary) > 0],
        key=lambda p: (
            -getattr(p.totals, primary),
            -getattr(p.totals, secondary),
            p.name.casefold(),
            p.kind,
            str(p.id),
        ),
    )
    previous: tuple[int, int] | None = None
    position = 0
    for index, person in enumerate(ordered, 1):
        score = (getattr(person.totals, primary), getattr(person.totals, secondary))
        if score != previous:
            position = index
        if assists:
            person.assists_position = position
        else:
            person.goals_position = position
        previous = score
    return ordered
