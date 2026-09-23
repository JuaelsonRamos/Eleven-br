from uuid import UUID

from fastapi import APIRouter

from app.application import formations
from app.domain.formations import Choice
from app.presentation.dependencies import CurrentUser, SessionDep
from app.presentation.formation_schemas import DrawInput, FormationPage, MoveInput

router = APIRouter(prefix="/v1/teams/{team_id}/events/{event_id}/formation", tags=["formations"])


@router.get("", response_model=FormationPage)
def detail(team_id: UUID, event_id: UUID, session: SessionDep, user: CurrentUser) -> FormationPage:
    return FormationPage.model_validate(
        formations.detail(session, user_id=user.id, team_id=team_id, event_id=event_id)
    )


@router.post("/draw", response_model=FormationPage)
def draw(
    team_id: UUID, event_id: UUID, data: DrawInput, session: SessionDep, user: CurrentUser
) -> FormationPage:
    formations.draw(
        session,
        user_id=user.id,
        team_id=team_id,
        event_id=event_id,
        choices=[Choice(**p.model_dump()) for p in data.participants],
        team_count=data.team_count,
        expected_fingerprint=data.expected_fingerprint,
        expected_version=data.expected_version,
        confirm_replace=data.confirm_replace,
    )
    return detail(team_id, event_id, session, user)


@router.put("/participants/{participant_id}", response_model=FormationPage)
def move(
    team_id: UUID,
    event_id: UUID,
    participant_id: UUID,
    data: MoveInput,
    session: SessionDep,
    user: CurrentUser,
) -> FormationPage:
    formations.move(
        session,
        user_id=user.id,
        team_id=team_id,
        event_id=event_id,
        participant_id=participant_id,
        **data.model_dump(),
    )
    return detail(team_id, event_id, session, user)
