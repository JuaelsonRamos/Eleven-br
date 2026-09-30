from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.domain.policies import Plan
from app.domain.team_identity import STATES, Modality

# Validation error type whose message the API returns as `detail` (see main.py).
OUTDATED_CLIENT = "outdated_client"


def official_state(value: str) -> str:
    value = value.upper()
    if value not in STATES:
        raise ValueError("Informe uma UF válida")
    return value


class LocationInput(BaseModel):
    """UF plus IBGE municipality code; the name always comes from the official table."""

    model_config = ConfigDict(extra="forbid")
    state: str
    municipality_code: int = Field(ge=1100000, le=5399999, strict=True)

    @model_validator(mode="before")
    @classmethod
    def no_typed_city(cls, data: object) -> object:
        # Clients from before the official list send a typed city: still refused (422),
        # but with a message they display, instead of a generic field error.
        if isinstance(data, dict) and "city" in data and "municipality_code" not in data:
            raise PydanticCustomError(
                OUTDATED_CLIENT, "Atualize o app para escolher a cidade na lista oficial."
            )
        return data

    @field_validator("state")
    @classmethod
    def valid_state(cls, value: str) -> str:
        return official_state(value)


class TeamProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    modalities: list[Modality] = Field(min_length=1)
    category: Literal["male", "female", "mixed"] | None = None

    @field_validator("modalities")
    @classmethod
    def unique_modalities(cls, values: list[Modality]) -> list[Modality]:
        # A set of choices with a stable domain order, independent of click order.
        return [modality for modality in Modality if modality in values]

    @field_validator("name", mode="before")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return " ".join(value.split()) if isinstance(value, str) else value


class TeamInput(TeamProfileInput, LocationInput):
    """Similar-team check: same fields as registration, category optional."""


class TeamCreate(TeamInput):
    category: Literal["male", "female", "mixed"]


class TeamEdit(TeamProfileInput):
    """Location is not edited here; older clients may resend the current one unchanged."""

    city: str | None = Field(default=None, max_length=100)
    state: str | None = None
    municipality_code: int | None = None

    @field_validator("city", mode="before")
    @classmethod
    def clean_city(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("state")
    @classmethod
    def valid_state(cls, value: str | None) -> str | None:
        return None if value is None else official_state(value)


class TeamPublicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    code: str
    city: str
    state: str
    modalities: list[str]
    category: str | None = None


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    code: str
    city: str
    state: str
    modalities: list[str]
    category: str | None = None
    status: str
    plan: Plan
    crest_url: str | None = None
    my_role: str = "member"
    can_edit: bool = False
    active_player_count: int = 0
    # Internal IBGE code (never shown) and whether the President confirmed the location.
    municipality_code: int | None = None
    location_confirmed: bool = False


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


class PresidencyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    membership_id: UUID
    confirm: bool = Field(strict=True)
