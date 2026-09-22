from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.domain.contacts import normalize_contact


class RosterFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nickname: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=254)

    @field_validator("nickname", "phone", "email", mode="before")
    @classmethod
    def empty_to_none(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("phone", "email")
    @classmethod
    def contact(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        channel, result = normalize_contact(value)
        if channel != info.field_name:
            raise ValueError("Informe o contato no campo correspondente.")
        return result


class RosterCreate(RosterFields):
    name: str = Field(min_length=1, max_length=80)
    confirm_duplicate: bool = False

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value


class RosterUpdate(RosterFields):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    confirm_duplicate: bool = False

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: object) -> object:
        if value is None:
            raise ValueError("Informe o nome do jogador.")
        return RosterCreate.clean_name(value)


class RosterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    membership_id: UUID
    player_id: UUID
    name: str
    nickname: str | None
    phone: str | None
    email: str | None
    photo_url: str | None
    status: Literal["active", "inactive"]
    account_linked: bool
    is_president: bool


class RosterPage(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    items: list[RosterRead]
    active_count: int
    inactive_count: int
    active_limit: int
    can_manage: bool
    plan: str


class SimilarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    membership_id: UUID
    name: str
    status: str
    account_linked: bool
    reasons: list[str]
