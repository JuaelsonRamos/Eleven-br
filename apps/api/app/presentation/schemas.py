import re
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.domain.policies import Plan


class AccountInput(BaseModel):
    """Input contract for future registration; no public registration flow yet."""

    email: EmailStr | None = None
    phone: str | None = None
    password: Annotated[str, Field(min_length=12, max_length=128)]
    display_name: Annotated[str, Field(min_length=1, max_length=80)]

    @model_validator(mode="after")
    def validate_contact(self) -> Self:
        if self.email:
            self.email = self.email.strip().lower()
        if self.phone and not re.fullmatch(r"\+[1-9][0-9]{7,14}", self.phone):
            raise ValueError("Use a phone number in E.164 format")
        if not self.email and not self.phone:
            raise ValueError("Email or phone is required")
        self.display_name = self.display_name.strip()
        if not self.display_name:
            raise ValueError("Display name is required")
        return self


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    code: str
    city: str
    state: str
    modality: str
    status: str
    plan: Plan


class ProfileRead(BaseModel):
    user_id: UUID
    player_id: UUID | None
    display_name: str | None


class AdministrationRead(BaseModel):
    team_id: UUID
    president_membership_id: UUID
    plan: Plan
    active_player_limit: int
    administrator_limit: int
