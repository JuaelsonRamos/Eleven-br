from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.team_codes import normalize_code

JoinStatus = Literal["PENDING", "APPROVED", "REJECTED", "CANCELLED"]


class CodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=512)

    @field_validator("code")
    @classmethod
    def normalize(cls, value: str) -> str:
        return normalize_code(value)


class ConfirmInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: bool = Field(default=False, strict=True)


class ApproveInput(ConfirmInput):
    membership_id: UUID | None = None


class JoinTeam(BaseModel):
    id: UUID
    name: str
    code: str
    city: str
    state: str
    modalities: list[str]
    crest_url: str | None


class LookupRead(BaseModel):
    team: JoinTeam
    membership_status: str | None
    pending: bool
    request_status: JoinStatus | None = None


class SearchRead(BaseModel):
    items: list[LookupRead]
    has_more: bool


class RequestRead(BaseModel):
    id: UUID
    team: JoinTeam
    status: JoinStatus
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class AdminRequestRead(BaseModel):
    id: UUID
    name: str
    masked_contact: str
    created_at: datetime
    status: JoinStatus


class LinkCandidate(BaseModel):
    membership_id: UUID
    name: str
    status: str
    photo_url: str | None
    unavailable_reason: str | None


class RequestDetail(BaseModel):
    request: AdminRequestRead
    candidates: list[LinkCandidate]
    identity_conflict: str | None
