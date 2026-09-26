from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.formations import MAX_PARTICIPANTS, MAX_TEAMS


class ParticipantChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["member", "guest"]
    source_id: UUID
    goalkeeper: bool = False


class DrawInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    team_count: int = Field(ge=2, le=MAX_TEAMS, strict=True)
    participants: list[ParticipantChoice] = Field(min_length=2, max_length=MAX_PARTICIPANTS)
    expected_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_version: int | None = Field(default=None, ge=1, strict=True)
    confirm_replace: bool = False


class MoveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    formation_id: UUID
    squad_id: UUID
    expected_version: int = Field(ge=1, strict=True)


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    kind: Literal["member", "guest"]
    source_id: UUID
    name: str


class ParticipantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    membership_id: UUID | None
    guest_id: UUID | None
    name: str
    goalkeeper: bool


class SquadRead(BaseModel):
    id: UUID
    number: int
    name: str
    participants: list[ParticipantRead]


class FormationRead(BaseModel):
    id: UUID
    version: int
    method: str
    team_count: int
    updated_at: datetime
    squads: list[SquadRead]
    excluded: list[ParticipantRead]


class FormationPage(BaseModel):
    locked_by_matches: bool
    can_manage: bool
    participants: list[CandidateRead]
    fingerprint: str
    participants_changed: bool
    formation: FormationRead | None
