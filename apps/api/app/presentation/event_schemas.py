from datetime import date as Date
from datetime import datetime
from datetime import time as Time
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.team_identity import Modality


class EventInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    modality: Modality
    kind: Literal["PELADA", "JOGO"]
    title: str = Field(min_length=1, max_length=100)
    date: Date
    time: Time
    location: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    opponent: str | None = Field(default=None, max_length=100)

    @field_validator("time")
    @classmethod
    def local_time(cls, value: Time) -> Time:
        if value.tzinfo is not None or value.second or value.microsecond:
            raise ValueError("Informe o horário local em HH:MM, sem fuso ou segundos")
        return value

    @model_validator(mode="after")
    def opponent_only_for_game(self) -> Self:
        if self.kind == "PELADA" and self.opponent:
            raise ValueError("Adversário é opcional apenas para jogo avulso")
        return self


class EventCreate(EventInput):
    recurring_weekly: bool = False
    recurring_until: Date | None = None

    @model_validator(mode="after")
    def weekly_range(self) -> Self:
        if self.recurring_weekly or self.recurring_until is not None:
            if self.kind != "PELADA":
                raise ValueError("Somente peladas permitem recorrência semanal")
            if self.recurring_until is not None and (self.recurring_until - self.date).days < 7:
                raise ValueError("O término deve ser pelo menos 7 dias após a primeira pelada")
        return self


class AttendanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response: Literal["VOU", "NAO_VOU"]


class GuestInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)


class Participant(BaseModel):
    membership_id: UUID
    player_id: UUID
    name: str
    response: Literal["VOU", "NAO_VOU", "PENDENTE"]


class GuestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str


class EventRead(EventInput):
    id: UUID
    team_id: UUID
    series_id: UUID | None
    recurring_until: Date | None
    recurrence_status: Literal["active", "cancelled"] | None
    status: Literal["open", "cancelled"]
    created_at: datetime
    updated_at: datetime
    can_manage: bool
    my_response: Literal["VOU", "NAO_VOU", "PENDENTE"]
    going: int
    not_going: int
    pending: int
    participants: list[Participant]
    guests: list[GuestRead]


class EventPage(BaseModel):
    items: list[EventRead]
    can_manage: bool
