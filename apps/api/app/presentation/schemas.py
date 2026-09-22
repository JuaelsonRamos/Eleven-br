from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.policies import Plan


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
    photo_url: str | None = None
    email: str | None = None
    phone: str | None = None


class AdministrationRead(BaseModel):
    team_id: UUID
    president_membership_id: UUID
    plan: Plan
    active_player_limit: int
    administrator_limit: int
