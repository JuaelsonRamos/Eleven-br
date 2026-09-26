from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateMatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    formation_id: UUID
    expected_formation_version: int = Field(ge=1, strict=True)
    home_formation_team_id: UUID
    away_formation_team_id: UUID


class MatchActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, strict=True)
    confirm: bool = Field(default=False, strict=True)


class MatchScoreInput(MatchActionInput):
    home_score: int = Field(ge=0, le=999, strict=True)
    away_score: int = Field(ge=0, le=999, strict=True)


class MatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    team_id: UUID
    event_id: UUID
    formation_id: UUID
    home_formation_team_id: UUID
    away_formation_team_id: UUID
    home_score: int
    away_score: int
    status: Literal["SCHEDULED", "IN_PROGRESS", "FINISHED", "CANCELLED"]
    version: int
    started_at: datetime | None
    finished_at: datetime | None
    corrected_at: datetime | None
    created_at: datetime
    updated_at: datetime
