from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.statistics import Period


class TotalsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    matches: int
    goals: int
    assists: int
    yellow_cards: int
    red_cards: int


class StatisticsPerson(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: Literal["member", "guest"]
    name: str
    player_id: UUID | None
    photo_url: str | None
    inactive: bool
    event_date: date | None
    totals: TotalsRead
    goals_position: int | None
    assists_position: int | None


class StatisticsPage(BaseModel):
    summary: TotalsRead
    players: list[StatisticsPerson]
    scorers: list[StatisticsPerson]
    assistants: list[StatisticsPerson]
    discipline: list[StatisticsPerson]
    modalities: list[str]
    period: Period
    modality: str | None


class StatisticsHistory(BaseModel):
    match_id: UUID
    event_id: UUID
    date: date
    title: str
    modality: str
    home_number: int
    away_number: int
    home_score: int
    away_score: int
    goals: int
    assists: int
    yellow_cards: int
    red_cards: int


class StatisticsProfile(BaseModel):
    person: StatisticsPerson
    goals_per_match: float
    assists_per_match: float
    history: list[StatisticsHistory]
    has_more: bool
