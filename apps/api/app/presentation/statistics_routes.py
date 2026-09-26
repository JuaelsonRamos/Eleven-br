from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.application import statistics
from app.domain.statistics import Period
from app.domain.team_identity import Modality
from app.presentation.dependencies import CurrentUser, SessionDep
from app.presentation.statistics_schemas import StatisticsPage, StatisticsProfile

router = APIRouter(prefix="/v1/teams/{team_id}/statistics", tags=["statistics"])


@router.get("", response_model=StatisticsPage)
def overview(
    team_id: UUID,
    session: SessionDep,
    user: CurrentUser,
    period: Period = "all",
    modality: Modality | None = None,
) -> StatisticsPage:
    return StatisticsPage.model_validate(
        statistics.overview(
            session, user_id=user.id, team_id=team_id, period=period, modality=modality
        )
    )


@router.get("/players/{membership_id}", response_model=StatisticsProfile)
def player(
    team_id: UUID,
    membership_id: UUID,
    session: SessionDep,
    user: CurrentUser,
    period: Period = "all",
    modality: Modality | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> StatisticsProfile:
    return StatisticsProfile.model_validate(
        statistics.profile(
            session,
            user_id=user.id,
            team_id=team_id,
            person_id=membership_id,
            kind="member",
            period=period,
            modality=modality,
            offset=offset,
            limit=limit,
        )
    )


@router.get("/guests/{guest_id}", response_model=StatisticsProfile)
def guest(
    team_id: UUID,
    guest_id: UUID,
    session: SessionDep,
    user: CurrentUser,
    period: Period = "all",
    modality: Modality | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> StatisticsProfile:
    return StatisticsProfile.model_validate(
        statistics.profile(
            session,
            user_id=user.id,
            team_id=team_id,
            person_id=guest_id,
            kind="guest",
            period=period,
            modality=modality,
            offset=offset,
            limit=limit,
        )
    )
