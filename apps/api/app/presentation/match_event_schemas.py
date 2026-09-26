from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.match_events import MatchEventType
from app.presentation.match_schemas import MatchActionInput, MatchRead


class MatchEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, strict=True)
    type: MatchEventType
    participant_id: UUID
    assist_participant_id: UUID | None = None


class RemoveMatchEventInput(MatchActionInput):
    pass


class MatchParticipantRead(BaseModel):
    id: UUID
    name: str
    is_guest: bool
    squad_id: UUID
    squad_name: str


class MatchEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    type: MatchEventType
    participant_id: UUID
    assist_participant_id: UUID | None
    squad_id: UUID
    created_at: datetime
    updated_at: datetime


class IdentifiedGoals(BaseModel):
    squad_id: UUID
    name: str
    score: int
    identified: int
    missing: int
    excess: int


class MatchEventsPage(BaseModel):
    match: MatchRead
    can_manage: bool
    participants: list[MatchParticipantRead]
    items: list[MatchEventRead]
    goals: list[IdentifiedGoals]
