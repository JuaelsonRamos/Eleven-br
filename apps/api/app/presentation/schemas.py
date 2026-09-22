from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.policies import Plan
from app.domain.team_identity import STATES, Modality


class TeamInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    city: str = Field(min_length=1, max_length=100)
    state: str
    modalities: list[Modality] = Field(min_length=1)

    @field_validator("modalities")
    @classmethod
    def unique_modalities(cls, values: list[Modality]) -> list[Modality]:
        # A set of choices with a stable domain order, independent of click order.
        return [modality for modality in Modality if modality in values]

    @field_validator("name", "city", mode="before")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("state")
    @classmethod
    def valid_state(cls, value: str) -> str:
        value = value.upper()
        if value not in STATES:
            raise ValueError("Informe uma UF válida")
        return value


class TeamPublicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    code: str
    city: str
    state: str
    modalities: list[str]


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    code: str
    city: str
    state: str
    modalities: list[str]
    status: str
    plan: Plan
    crest_url: str | None = None
    my_role: str = "member"
    can_edit: bool = False
    active_player_count: int = 0


class ProfileRead(BaseModel):
    user_id: UUID
    player_id: UUID | None
    display_name: str | None
    photo_url: str | None = None
    email: str | None = None
    phone: str | None = None


class AdministrationRead(BaseModel):
    team_id: UUID
    president_membership_id: UUID
    plan: Plan
    active_player_limit: int
    administrator_limit: int
